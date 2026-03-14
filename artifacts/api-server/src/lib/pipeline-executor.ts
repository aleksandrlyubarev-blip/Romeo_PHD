import { eq } from "drizzle-orm";
import { randomUUID } from "crypto";
import { db, pipelines, pipelineNodes, consultations, telemetryEvents } from "@workspace/db";
import { anthropic } from "@workspace/integrations-anthropic-ai";

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
- NEEDS_CLARIFICATION (confidence < 0.6): Insufficient information, requires operator input`;

  const userMessage = `Node: "${nodeName}" (type: ${nodeType})
Task: ${prompt ?? `Execute the ${nodeType} task for node: ${nodeName}`}${contextStr}

Process this pipeline node and return your result as JSON.`;

  const message = await anthropic.messages.create({
    model: "claude-sonnet-4-6",
    max_tokens: 8192,
    system: systemPrompt,
    messages: [{ role: "user", content: userMessage }],
  });

  const content = message.content[0];
  if (content.type !== "text") {
    return {
      output: "Node execution produced no text output",
      confidenceScore: 0.5,
      status: "AMBIGUOUS",
      consultationMessage: "LLM returned non-text content",
    };
  }

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

    return {
      output: String(parsed.output ?? content.text),
      confidenceScore: confidence,
      status,
      consultationMessage:
        status !== "RESOLVED"
          ? `Confidence score: ${confidence.toFixed(2)}. ${parsed.reasoning ?? ""}`
          : undefined,
    };
  } catch {
    // If JSON parsing fails, use the raw text with moderate confidence
    return {
      output: content.text,
      confidenceScore: 0.7,
      status: "AMBIGUOUS",
      consultationMessage: "Could not parse structured response; using raw output",
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
      });

      await logTelemetry(pipelineId, node.nodeId, "node_executed", {
        status: result.status,
        confidenceScore: result.confidenceScore,
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
