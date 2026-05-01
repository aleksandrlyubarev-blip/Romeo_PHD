import { z } from "zod";

export const FusionExecModeSchema = z.enum(["dryrun", "subprocess", "mcp"]);
export type FusionExecMode = z.infer<typeof FusionExecModeSchema>;

export const FusionExportFormatSchema = z.enum(["stl", "step", "f3d"]);
export type FusionExportFormat = z.infer<typeof FusionExportFormatSchema>;

export const FusionDrawRequestSchema = z.object({
  description: z.string().min(1),
  photoBase64: z.string().optional(),
  photoMediaType: z
    .enum(["image/jpeg", "image/png", "image/webp", "image/gif"])
    .optional(),
  outputDir: z.string().optional(),
  execMode: FusionExecModeSchema.default("dryrun"),
  exportFormats: z.array(FusionExportFormatSchema).default(["stl", "step"]),
  model: z.string().optional(),
  timeoutSec: z.number().int().positive().max(1800).default(300),
});
export type FusionDrawRequest = z.infer<typeof FusionDrawRequestSchema>;

export const FusionDrawArtifactsSchema = z.object({
  scriptPath: z.string(),
  stlPath: z.string().nullable(),
  stepPath: z.string().nullable(),
  f3dPath: z.string().nullable(),
});
export type FusionDrawArtifacts = z.infer<typeof FusionDrawArtifactsSchema>;

export const FusionDrawResponseSchema = z.object({
  ok: z.boolean(),
  execMode: FusionExecModeSchema,
  artifacts: FusionDrawArtifactsSchema,
  returncode: z.number().int(),
  stdout: z.string(),
  stderr: z.string(),
  note: z.string().nullable().optional(),
});
export type FusionDrawResponse = z.infer<typeof FusionDrawResponseSchema>;

export const FusionRetryRequestSchema = FusionDrawRequestSchema.extend({
  outputDir: z.string(),
  priorScriptPath: z.string().optional(),
});
export type FusionRetryRequest = z.infer<typeof FusionRetryRequestSchema>;

export const FUSION_PIPELINE_NODE_TYPE = "buxter.fusion-360" as const;

export const FusionPipelineNodeConfigSchema = z.object({
  type: z.literal(FUSION_PIPELINE_NODE_TYPE),
  description: z.string().min(1),
  execMode: FusionExecModeSchema.default("dryrun"),
  exportFormats: z
    .array(FusionExportFormatSchema)
    .default(["stl", "step"]),
  outputDir: z.string().optional(),
  approvalRequired: z.boolean().default(false),
});
export type FusionPipelineNodeConfig = z.infer<
  typeof FusionPipelineNodeConfigSchema
>;
