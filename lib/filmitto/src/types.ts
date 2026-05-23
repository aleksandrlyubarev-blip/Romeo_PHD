import { z } from "zod/v4";

/**
 * One shot in a Filmitto multi-shot storyboard. Mirrors the bassito
 * `longlive_engine.ShotSpec` dataclass field-for-field.
 */
export const ShotSpecSchema = z.object({
  prompt: z.string().min(1),
  duration_seconds: z.number().positive().default(4.0),
  reference_image_path: z.string().nullable().optional(),
  reference_clip_path: z.string().nullable().optional(),
  shot_id: z.string().optional(),
});
export type ShotSpec = z.infer<typeof ShotSpecSchema>;

/**
 * Streaming event emitted by bassito for each decoded chunk. Mirrors the
 * `longlive_engine.ChunkEvent` dataclass.
 */
export const ChunkEventSchema = z.object({
  shot_id: z.string(),
  chunk_index: z.number().int().nonnegative(),
  frames_done: z.number().int().nonnegative(),
  frames_total: z.number().int().nonnegative(),
  partial_video_path: z.string().nullable().optional(),
});
export type ChunkEvent = z.infer<typeof ChunkEventSchema>;

/** 202 Accepted response from bassito generate/extend/restyle. */
export const JobAcceptedSchema = z.object({
  job_id: z.string(),
  status: z.string(),
  stream_url: z.string(),
});
export type JobAccepted = z.infer<typeof JobAcceptedSchema>;

/** Terminal status emitted at the end of an SSE stream. */
export const JobStatusSchema = z.object({
  job_id: z.string(),
  status: z.string(),
  long_video_path: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
  shot_count: z.number().int().nonnegative().optional(),
});
export type JobStatus = z.infer<typeof JobStatusSchema>;

export type BassitoStreamMessage =
  | { type: "chunk"; data: ChunkEvent }
  | { type: "done"; data: JobStatus };
