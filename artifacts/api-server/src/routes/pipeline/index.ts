import { Router, type IRouter } from "express";
import { eq } from "drizzle-orm";
import {
  db,
  pipelines,
  pipelineNodes,
  consultations,
  telemetryEvents,
} from "@workspace/db";
import {
  ListPipelinesResponse,
  CreatePipelineBody,
  GetPipelineParams,
  GetPipelineResponse,
  DeletePipelineParams,
  ResumePipelineParams,
  ResumePipelineBody,
  ResumePipelineResponse,
  ExecutePipelineParams,
  ListPipelineNodesParams,
  ListPipelineNodesResponse,
  ListConsultationsParams,
  ListConsultationsResponse,
  RespondToConsultationParams,
  RespondToConsultationBody,
  RespondToConsultationResponse,
  ListTelemetryEventsQueryParams,
  ListTelemetryEventsResponse,
} from "@workspace/api-zod";
import {
  parsePipelineYaml,
  kahnTopologicalSort,
  computeNodePositions,
  CyclicDependencyError,
} from "../../lib/pipeline-parser";
import { executePipeline } from "../../lib/pipeline-executor";

const router: IRouter = Router();

// ─── List Pipelines ──────────────────────────────────────────────────────────
router.get("/pipelines", async (_req, res): Promise<void> => {
  const all = await db.select().from(pipelines).orderBy(pipelines.createdAt);
  res.json(ListPipelinesResponse.parse(all));
});

// ─── Create + Parse Pipeline ─────────────────────────────────────────────────
router.post("/pipelines", async (req, res): Promise<void> => {
  const parsed = CreatePipelineBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }

  let parsedPipeline;
  try {
    parsedPipeline = parsePipelineYaml(parsed.data.yamlContent);
  } catch (err) {
    if (err instanceof CyclicDependencyError) {
      res.status(400).json({ error: err.message });
    } else {
      res.status(400).json({ error: `YAML parse error: ${err instanceof Error ? err.message : String(err)}` });
    }
    return;
  }

  // Validate topological order (Kahn's algorithm)
  let sortedNodes;
  try {
    sortedNodes = kahnTopologicalSort(parsedPipeline.nodes);
  } catch (err) {
    res.status(400).json({ error: err instanceof Error ? err.message : String(err) });
    return;
  }

  // Compute positions
  const positions = computeNodePositions(parsedPipeline.nodes);

  // Create pipeline in DB
  const [pipeline] = await db
    .insert(pipelines)
    .values({
      name: parsed.data.name || parsedPipeline.name,
      yamlContent: parsed.data.yamlContent,
      status: "pending",
      nodeCount: sortedNodes.length,
      resolvedCount: 0,
    })
    .returning();

  // Insert nodes in topological order
  for (const node of sortedNodes) {
    const pos = positions.get(node.id) ?? { x: 100, y: 100 };
    await db.insert(pipelineNodes).values({
      pipelineId: pipeline.id,
      nodeId: node.id,
      name: node.name,
      type: node.type,
      prompt: node.prompt ?? null,
      dependencies: JSON.stringify(node.dependencies),
      status: "PENDING",
      positionX: pos.x,
      positionY: pos.y,
    });
  }

  res.status(201).json(pipeline);
});

// ─── Get Pipeline with Nodes ─────────────────────────────────────────────────
router.get("/pipelines/:id", async (req, res): Promise<void> => {
  const params = GetPipelineParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const [pipeline] = await db
    .select()
    .from(pipelines)
    .where(eq(pipelines.id, params.data.id));

  if (!pipeline) {
    res.status(404).json({ error: "Pipeline not found" });
    return;
  }

  const nodes = await db
    .select()
    .from(pipelineNodes)
    .where(eq(pipelineNodes.pipelineId, params.data.id))
    .orderBy(pipelineNodes.id);

  const nodesFormatted = nodes.map((n) => ({
    ...n,
    dependencies: JSON.parse(n.dependencies) as string[],
  }));

  res.json(
    GetPipelineResponse.parse({
      ...pipeline,
      nodes: nodesFormatted,
    })
  );
});

// ─── Delete Pipeline ──────────────────────────────────────────────────────────
router.delete("/pipelines/:id", async (req, res): Promise<void> => {
  const params = DeletePipelineParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const [pipeline] = await db
    .delete(pipelines)
    .where(eq(pipelines.id, params.data.id))
    .returning();

  if (!pipeline) {
    res.status(404).json({ error: "Pipeline not found" });
    return;
  }

  res.sendStatus(204);
});

// ─── Execute Pipeline (SSE) ──────────────────────────────────────────────────
router.post("/pipelines/:id/execute", async (req, res): Promise<void> => {
  const params = ExecutePipelineParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const [pipeline] = await db
    .select()
    .from(pipelines)
    .where(eq(pipelines.id, params.data.id));

  if (!pipeline) {
    res.status(404).json({ error: "Pipeline not found" });
    return;
  }

  if (pipeline.status === "running") {
    res.status(400).json({ error: "Pipeline is already running" });
    return;
  }

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");

  try {
    await executePipeline(params.data.id, (event, data) => {
      res.write(`data: ${JSON.stringify({ event, ...data })}\n\n`);
    });
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : "Unknown error";
    res.write(`data: ${JSON.stringify({ event: "error", error: errMsg })}\n\n`);
  }

  res.write(`data: ${JSON.stringify({ event: "stream_end" })}\n\n`);
  res.end();
});

// ─── Resume Pipeline ──────────────────────────────────────────────────────────
router.post("/pipelines/:id/resume", async (req, res): Promise<void> => {
  const params = ResumePipelineParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const body = ResumePipelineBody.safeParse(req.body);
  if (!body.success) {
    res.status(400).json({ error: body.error.message });
    return;
  }

  const [pipeline] = await db
    .select()
    .from(pipelines)
    .where(eq(pipelines.id, params.data.id));

  if (!pipeline) {
    res.status(404).json({ error: "Pipeline not found" });
    return;
  }

  // Find the node and update it based on decision
  const [node] = await db
    .select()
    .from(pipelineNodes)
    .where(
      eq(pipelineNodes.pipelineId, params.data.id),
    );

  if (body.data.decision === "approve") {
    // Mark the node as RESOLVED and update the consultation
    await db
      .update(pipelineNodes)
      .set({ status: "RESOLVED", output: body.data.feedback ?? "Approved by operator" })
      .where(
        eq(pipelineNodes.pipelineId, params.data.id)
      );

    await db
      .update(pipelines)
      .set({ status: "pending", updatedAt: new Date() })
      .where(eq(pipelines.id, params.data.id));
  } else {
    await db
      .update(pipelineNodes)
      .set({ status: "NEEDS_CLARIFICATION" })
      .where(eq(pipelineNodes.pipelineId, params.data.id));

    await db
      .update(pipelines)
      .set({ status: "failed", updatedAt: new Date() })
      .where(eq(pipelines.id, params.data.id));
  }

  const [updated] = await db
    .select()
    .from(pipelines)
    .where(eq(pipelines.id, params.data.id));

  res.json(ResumePipelineResponse.parse(updated));
});

// ─── List Pipeline Nodes ─────────────────────────────────────────────────────
router.get("/pipelines/:id/nodes", async (req, res): Promise<void> => {
  const params = ListPipelineNodesParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const nodes = await db
    .select()
    .from(pipelineNodes)
    .where(eq(pipelineNodes.pipelineId, params.data.id))
    .orderBy(pipelineNodes.id);

  const formatted = nodes.map((n) => ({
    ...n,
    dependencies: JSON.parse(n.dependencies) as string[],
  }));

  res.json(ListPipelineNodesResponse.parse(formatted));
});

// ─── List Consultations ───────────────────────────────────────────────────────
router.get("/pipelines/:id/consultations", async (req, res): Promise<void> => {
  const params = ListConsultationsParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const items = await db
    .select()
    .from(consultations)
    .where(eq(consultations.pipelineId, params.data.id))
    .orderBy(consultations.createdAt);

  const formatted = items.map((c) => ({
    ...c,
    arguments: JSON.parse(c.arguments) as Record<string, unknown>,
  }));

  res.json(ListConsultationsResponse.parse(formatted));
});

// ─── Respond to Consultation ──────────────────────────────────────────────────
router.post("/consultations/:approvalId/respond", async (req, res): Promise<void> => {
  const params = RespondToConsultationParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }

  const body = RespondToConsultationBody.safeParse(req.body);
  if (!body.success) {
    res.status(400).json({ error: body.error.message });
    return;
  }

  const [consultation] = await db
    .select()
    .from(consultations)
    .where(eq(consultations.approvalId, params.data.approvalId));

  if (!consultation) {
    res.status(404).json({ error: "Consultation not found" });
    return;
  }

  const [updated] = await db
    .update(consultations)
    .set({
      status: body.data.decision === "approve" ? "APPROVED" : "REJECTED",
      feedback: body.data.feedback ?? null,
    })
    .where(eq(consultations.approvalId, params.data.approvalId))
    .returning();

  // Update the node status accordingly
  const nodeStatus = body.data.decision === "approve" ? "RESOLVED" : "NEEDS_CLARIFICATION";
  await db
    .update(pipelineNodes)
    .set({
      status: nodeStatus,
      output: body.data.feedback ?? (body.data.decision === "approve" ? "Approved by operator" : "Rejected by operator"),
      executedAt: new Date(),
    })
    .where(
      eq(pipelineNodes.pipelineId, consultation.pipelineId),
    );

  // If approved, update pipeline resolved count
  if (body.data.decision === "approve") {
    const [pipeline] = await db.select().from(pipelines).where(eq(pipelines.id, consultation.pipelineId));
    if (pipeline) {
      await db.update(pipelines).set({
        resolvedCount: pipeline.resolvedCount + 1,
        status: "pending",
        updatedAt: new Date(),
      }).where(eq(pipelines.id, consultation.pipelineId));
    }
  }

  res.json(
    RespondToConsultationResponse.parse({
      ...updated,
      arguments: JSON.parse(updated.arguments) as Record<string, unknown>,
    })
  );
});

// ─── Telemetry ────────────────────────────────────────────────────────────────
router.get("/telemetry", async (req, res): Promise<void> => {
  const queryParams = ListTelemetryEventsQueryParams.safeParse(req.query);

  let query = db.select().from(telemetryEvents).$dynamic();

  if (queryParams.success && queryParams.data.pipelineId) {
    query = query.where(eq(telemetryEvents.pipelineId, queryParams.data.pipelineId));
  }

  const limit = queryParams.success && queryParams.data.limit ? queryParams.data.limit : 50;
  const events = await query.orderBy(telemetryEvents.createdAt).limit(limit);

  const formatted = events.map((e) => ({
    ...e,
    payload: JSON.parse(e.payload) as Record<string, unknown>,
  }));

  res.json(ListTelemetryEventsResponse.parse(formatted));
});

export default router;
