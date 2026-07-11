import { Router, type IRouter } from "express";
import { randomUUID } from "node:crypto";
import { eq } from "drizzle-orm";
import {
  db,
  inspections,
  consultations,
  insertInspectionSchema,
  type InsertInspection,
} from "@workspace/db";

const router: IRouter = Router();

// Payload mirrors rhaef_v2.tools.interfaces.InspectionResult so the
// RoboQC inference service can post directly to /api/inspections.
type DetectedDefect = {
  defect_class: string;
  bbox?: [number, number, number, number] | null;
  mask_uri?: string | null;
  confidence: number;
};

type InspectionResultBody = {
  inspection_id: string;
  image_uri: string;
  overall_pass: boolean;
  confidence: number;
  model_version: string;
  requires_hitl?: boolean;
  defects?: DetectedDefect[];
};

// HITL threshold for borderline confidence. Anything below this OR
// with requires_hitl=true creates a consultations row for the QC
// engineer console. The consultations table's pipelineId is now
// nullable so inspections-driven HITL works without a parent pipeline.
const HITL_CONFIDENCE_THRESHOLD = 0.85;

function parseBody(raw: unknown): InspectionResultBody | string {
  if (typeof raw !== "object" || raw === null) return "body must be a JSON object";
  const b = raw as Record<string, unknown>;
  if (typeof b.inspection_id !== "string") return "inspection_id must be a string";
  if (typeof b.image_uri !== "string") return "image_uri must be a string";
  if (typeof b.overall_pass !== "boolean") return "overall_pass must be a boolean";
  if (typeof b.confidence !== "number" || b.confidence < 0 || b.confidence > 1) {
    return "confidence must be a number in [0,1]";
  }
  if (typeof b.model_version !== "string") return "model_version must be a string";
  const requiresHitl = typeof b.requires_hitl === "boolean" ? b.requires_hitl : false;
  const defects = Array.isArray(b.defects) ? (b.defects as DetectedDefect[]) : [];
  return {
    inspection_id: b.inspection_id,
    image_uri: b.image_uri,
    overall_pass: b.overall_pass,
    confidence: b.confidence,
    model_version: b.model_version,
    requires_hitl: requiresHitl,
    defects,
  };
}

function formatConsultationMessage(body: InspectionResultBody): string {
  const summary = body.defects
    ?.map((d) => `${d.defect_class}@${d.confidence.toFixed(2)}`)
    .join(", ");
  return `RoboQC borderline inspection ${body.inspection_id} ` +
    `(model=${body.model_version}, confidence=${body.confidence.toFixed(2)})` +
    (summary ? `: ${summary}` : "");
}

router.post("/inspections", async (req, res): Promise<void> => {
  const parsed = parseBody(req.body);
  if (typeof parsed === "string") {
    res.status(400).json({ error: parsed });
    return;
  }
  const needsHitl = parsed.requires_hitl === true || parsed.confidence < HITL_CONFIDENCE_THRESHOLD;

  let consultationId: number | null = null;
  if (needsHitl) {
    const [consultation] = await db
      .insert(consultations)
      .values({
        pipelineId: null,
        nodeId: "inspection",
        approvalId: randomUUID(),
        functionName: `roboqc_inspect:${parsed.model_version}`,
        arguments: JSON.stringify({
          inspection_id: parsed.inspection_id,
          image_uri: parsed.image_uri,
          confidence: parsed.confidence,
          defects: parsed.defects ?? [],
        }),
        message: formatConsultationMessage(parsed),
        status: "PENDING",
      })
      .returning();
    consultationId = consultation?.id ?? null;
  }

  const payload: InsertInspection = insertInspectionSchema.parse({
    inspectionId: parsed.inspection_id,
    imageUri: parsed.image_uri,
    overallPass: parsed.overall_pass,
    confidence: parsed.confidence,
    modelVersion: parsed.model_version,
    requiresHitl: needsHitl,
    defects: parsed.defects ?? [],
    hitlConsultationId: consultationId,
  });
  const [row] = await db.insert(inspections).values(payload).returning();
  res.status(201).json({
    inspection: row,
    hitl_routed: needsHitl,
    consultation_id: consultationId,
  });
});

router.get("/inspections/:inspectionId", async (req, res): Promise<void> => {
  const inspectionId = req.params.inspectionId;
  if (!inspectionId) {
    res.status(400).json({ error: "inspectionId is required" });
    return;
  }
  const [row] = await db
    .select()
    .from(inspections)
    .where(eq(inspections.inspectionId, inspectionId))
    .limit(1);
  if (!row) {
    res.status(404).json({ error: "inspection not found" });
    return;
  }
  res.json(row);
});

export default router;
