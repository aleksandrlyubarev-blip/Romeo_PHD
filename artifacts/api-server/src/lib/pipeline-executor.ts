import { eq } from "drizzle-orm";
import { randomUUID } from "crypto";
import { db, pipelines, pipelineNodes, consultations, telemetryEvents } from "@workspace/db";
import { anthropic } from "@workspace/integrations-anthropic-ai";
import { resolvePersonaForNodeType } from "./agent-personas";
import {
  MODELS,
  MANDATORY_NEGATIVE_RESULT_RULE,
  WORKER_TIER_RULES,
  resolveRouteForNodeType,
  type ModelRoute,
} from "./model-routing";

async function logTelemetry(
  pipelineId: number,
  nodeId: string | null,
  eventType: string,
  payload: Record<string, unknown>
) {
  await db.insert(telemetryEvents).values({
    pipelineId,
    nodeId,
    eventType,
    payload: JSON.stringify(payload),
  });
}

interface NodeResult {
  output: string;
  confidenceScore: number;
  status: "RESOLVED" | "NEEDS_CLARIFICATION" | "AMBIGUOUS";
  consultationMessage?: string;
  /** Модель, фактически давшая ответ (с учётом refusal-fallback). */
  model: string;
  /** Ярус маршрутизации: architect | manager | worker. */
  tier: string;
  /** Время работы ИИ над узлом — главный сканер качества архитектуры. */
  durationMs: number;
}

/**
 * Один вызов модели по маршруту. Для architect-яруса (Fable 5) при
 * policy-отказе классификаторов (stop_reason: "refusal") запрос
 * повторяется на Opus 4.8 — иначе ложное срабатывание на безобидной
 * смежной теме валит весь пайплайн.
 */
async function callModelWithRoute(
  route: ModelRoute,
  systemPrompt: string,
  userMessage: string
): Promise<{ text: string | null; model: string }> {
  const request = (model: string) =>
    anthropic.messages.create({
      model,
      max_tokens: route.maxTokens,
      system: systemPrompt,
      messages: [{ role: "user", content: userMessage }],
      // Fable 5: thinking всегда включён, параметр не передаётся вовсе.
      // Haiku 4.5: adaptive thinking недоступен.
      ...(route.sendAdaptiveThinking ? { thinking: { type: "adaptive" as const } } : {}),
      // Haiku 4.5 не принимает effort — отправляем только там, где поддержано.
      ...(route.effort ? { output_config: { effort: route.effort } } : {}),
    });

  let message = await request(route.model);
  let servedBy = route.model;

  if (message.stop_reason === "refusal" && route.useRefusalFallback) {
    message = await request(MODELS.architectFallback);
    servedBy = MODELS.architectFallback;
  }

  if (message.stop_reason === "refusal") {
    return { text: null, model: servedBy };
  }

  // При включённом thinking первый блок может быть thinking-блоком —
  // ищем текстовый блок, а не берём content[0].
  const textBlock = message.content.find((b) => b.type === "text");
  return { text: textBlock?.type === "text" ? textBlock.text : null, model: servedBy };
}

/** Заглушки, которыми модель иногда подменяет реальный негативный ответ. */
const STUB_OUTPUTS = new Set(["n/a", "na", "none", "null", "-"]);

/**
 * Обязательное правило негативного ответа (MANDATORY_NEGATIVE_RESULT_RULE)
 * живёт только в промпте — модель может его проигнорировать. Проверяем
 * тот же инвариант на сервере: пустой или заглушечный output не принимается
 * как RESOLVED, что бы ни сказала модель про свою уверенность.
 */
function isBlankOrStubOutput(output: string): boolean {
  const trimmed = output.trim();
  return trimmed.length === 0 || STUB_OUTPUTS.has(trimmed.toLowerCase());
}

async function executeNodeWithLLM(
  nodeName: string,
  nodeType: string,
  prompt: string | null,
  previousOutputs: Record<string, string>
): Promise<NodeResult> {
  const contextStr =
    Object.keys(previousOutputs).length > 0
      ? `\n\nContext from previous pipeline steps:\n${Object.entries(previousOutputs)
          .map(([k, v]) => `[${k}]: ${v}`)
          .join("\n")}`
      : "";

  const persona = resolvePersonaForNodeType(nodeType);
  const route = resolveRouteForNodeType(nodeType);

  const systemPrompt = `You are an AI worker in a pipeline execution system called Romeo PHD v6.0.
You process pipeline nodes deterministically. For each node, you:
1. Execute the task described in the prompt
2. Return a structured JSON response with your output and confidence score

Your response MUST be a valid JSON object with these fields:
{
  "output": "Your processed result as a string",
  "confidence_score": 0.85,
  "reasoning": "Brief explanation of your approach",
  "status": "RESOLVED" | "NEEDS_CLARIFICATION" | "AMBIGUOUS"
}

Status rules:
- RESOLVED (confidence >= 0.8): Task completed with high confidence
- AMBIGUOUS (0.6 <= confidence < 0.8): Multiple valid interpretations, needs human review
- NEEDS_CLARIFICATION (confidence < 0.6): Insufficient information, requires operator input

${MANDATORY_NEGATIVE_RESULT_RULE}${route.tier === "worker" ? `\n\n${WORKER_TIER_RULES}` : ""}${persona ? `\n\n${persona}` : ""}`;

  const userMessage = `Node: "${nodeName}" (type: ${nodeType})
Task: ${prompt ?? `Execute the ${nodeType} task for node: ${nodeName}`}${contextStr}

Process this pipeline node and return your result as JSON.`;

  const startedAt = Date.now();
  const { text, model } = await callModelWithRoute(route, systemPrompt, userMessage);
  const durationMs = Date.now() - startedAt;
  const routeMeta = { model, tier: route.tier, durationMs };

  if (text === null) {
    return {
      output: "Node execution was refused by safety classifiers (including fallback model)",
      confidenceScore: 0,
      status: "NEEDS_CLARIFICATION",
      consultationMessage: "LLM request refused; operator review required",
      ...routeMeta,
    };
  }

  const content = { type: "text" as const, text };

  try {
    // Extract JSON from response (may be wrapped in markdown)
    const jsonMatch = content.text.match(/\{[\s\S]*\}/);
    if (!jsonMatch) throw new Error("No JSON found in response");

    const parsed = JSON.parse(jsonMatch[0]);
    const confidence = typeof parsed.confidence_score === "number" ? parsed.confidence_score : 0.5;

    let status: "RESOLVED" | "NEEDS_CLARIFICATION" | "AMBIGUOUS" = "RESOLVED";
    if (parsed.status && ["RESOLVED", "NEEDS_CLARIFICATION", "AMBIGUOUS"].includes(parsed.status)) {
      status = parsed.status;
    } else if (confidence >= 0.8) {
      status = "RESOLVED";
    } else if (confidence >= 0.6) {
      status = "AMBIGUOUS";
    } else {
      status = "NEEDS_CLARIFICATION";
    }

    const output = String(parsed.output ?? content.text);

    // Серверный энфорсмент MANDATORY_NEGATIVE_RESULT_RULE: модель не должна
    // отделываться пустым/заглушечным output, даже если сама проставила
    // status: RESOLVED и высокую уверенность — иначе правило работает только
    // "на честном слове" модели.
    if (status === "RESOLVED" && isBlankOrStubOutput(output)) {
      return {
        output,
        confidenceScore: 0,
        status: "NEEDS_CLARIFICATION",
        consultationMessage:
          "Модель вернула пустой или заглушечный output ('N/A'/'none'/'-') вопреки " +
          "обязательному правилу негативного ответа; требуется явный результат от оператора.",
        ...routeMeta,
      };
    }

    return {
      output,
      confidenceScore: confidence,
      status,
      consultationMessage:
        status !== "RESOLVED"
          ? `Confidence score: ${confidence.toFixed(2)}. ${parsed.reasoning ?? ""}`
          : undefined,
      ...routeMeta,
    };
  } catch {
    // If JSON parsing fails, use the raw text with moderate confidence
    return {
      output: content.text,
      confidenceScore: 0.7,
      status: "AMBIGUOUS",
      consultationMessage: "Could not parse structured response; using raw output",
      ...routeMeta,
    };
  }
}

export async function executePipeline(
  pipelineId: number,
  onEvent: (event: string, data: Record<string, unknown>) => void
) {
  const [pipeline] = await db
    .select()
    .from(pipelines)
    .where(eq(pipelines.id, pipelineId));

  if (!pipeline) throw new Error("Pipeline not found");

  // Update status to running
  await db
    .update(pipelines)
    .set({ status: "running", updatedAt: new Date() })
    .where(eq(pipelines.id, pipelineId));

  onEvent("pipeline_started", { pipelineId, name: pipeline.name });
  await logTelemetry(pipelineId, null, "pipeline_started", { name: pipeline.name });

  // Get nodes in topological order (already stored sorted)
  const nodes = await db
    .select()
    .from(pipelineNodes)
    .where(eq(pipelineNodes.pipelineId, pipelineId))
    .orderBy(pipelineNodes.id);

  const previousOutputs: Record<string, string> = {};
  let resolvedCount = 0;
  let hasPaused = false;

  for (const node of nodes) {
    // Check if dependencies are resolved
    const deps = JSON.parse(node.dependencies) as string[];
    const depsResolved = deps.every(
      (depId) =>
        nodes.find((n) => n.nodeId === depId)?.status === "RESOLVED" ||
        previousOutputs[depId] !== undefined
    );

    if (!depsResolved) {
      onEvent("node_skipped", { nodeId: node.nodeId, reason: "dependencies_not_met" });
      continue;
    }

    onEvent("node_started", { nodeId: node.nodeId, name: node.name });
    await logTelemetry(pipelineId, node.nodeId, "node_started", { name: node.name });

    // Update node to running (we'll use PENDING as in-progress indicator)
    await db
      .update(pipelineNodes)
      .set({ status: "PENDING" })
      .where(eq(pipelineNodes.id, node.id));

    onEvent("node_status_changed", { nodeId: node.nodeId, status: "PENDING" });

    try {
      const result = await executeNodeWithLLM(
        node.name,
        node.type,
        node.prompt,
        previousOutputs
      );

      // Save result
      await db
        .update(pipelineNodes)
        .set({
          status: result.status,
          output: result.output,
          confidenceScore: result.confidenceScore,
          executedAt: new Date(),
        })
        .where(eq(pipelineNodes.id, node.id));

      onEvent("node_status_changed", {
        nodeId: node.nodeId,
        status: result.status,
        output: result.output,
        confidenceScore: result.confidenceScore,
        model: result.model,
        tier: result.tier,
        durationMs: result.durationMs,
      });

      await logTelemetry(pipelineId, node.nodeId, "node_executed", {
        status: result.status,
        confidenceScore: result.confidenceScore,
        model: result.model,
        tier: result.tier,
        // Время работы ИИ — сканер качества архитектуры: минуты — норма,
        // десятки минут на простом узле — красный флаг запутанного кода.
        durationMs: result.durationMs,
      });

      if (result.status === "RESOLVED") {
        previousOutputs[node.nodeId] = result.output;
        resolvedCount++;

        // Update pipeline resolved count
        await db
          .update(pipelines)
          .set({ resolvedCount, updatedAt: new Date() })
          .where(eq(pipelines.id, pipelineId));
      } else {
        // Create consultation request for HITL
        const approvalId = randomUUID();
        await db.insert(consultations).values({
          pipelineId,
          nodeId: node.nodeId,
          approvalId,
          functionName: node.name,
          arguments: JSON.stringify({ nodeType: node.type, prompt: node.prompt }),
          message: result.consultationMessage ?? `Node requires human review (confidence: ${result.confidenceScore?.toFixed(2)})`,
          status: "PENDING",
        });

        onEvent("hitl_required", {
          nodeId: node.nodeId,
          status: result.status,
          approvalId,
          message: result.consultationMessage,
          confidenceScore: result.confidenceScore,
        });

        await logTelemetry(pipelineId, node.nodeId, "hitl_triggered", {
          approvalId,
          status: result.status,
          confidenceScore: result.confidenceScore,
        });

        // Pause pipeline
        await db
          .update(pipelines)
          .set({ status: "paused", updatedAt: new Date() })
          .where(eq(pipelines.id, pipelineId));

        onEvent("pipeline_paused", { pipelineId, nodeId: node.nodeId, approvalId });
        hasPaused = true;
        break;
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "Unknown error";

      await db
        .update(pipelineNodes)
        .set({ status: "NEEDS_CLARIFICATION", output: `Error: ${errMsg}` })
        .where(eq(pipelineNodes.id, node.id));

      onEvent("node_error", { nodeId: node.nodeId, error: errMsg });
      await logTelemetry(pipelineId, node.nodeId, "node_error", { error: errMsg });

      await db
        .update(pipelines)
        .set({ status: "failed", updatedAt: new Date() })
        .where(eq(pipelines.id, pipelineId));

      onEvent("pipeline_failed", { pipelineId, error: errMsg });
      return;
    }
  }

  if (!hasPaused) {
    await db
      .update(pipelines)
      .set({ status: "completed", resolvedCount, updatedAt: new Date() })
      .where(eq(pipelines.id, pipelineId));

    onEvent("pipeline_completed", { pipelineId, resolvedCount });
    await logTelemetry(pipelineId, null, "pipeline_completed", { resolvedCount });
  }
}
