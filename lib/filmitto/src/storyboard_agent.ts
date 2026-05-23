import { anthropic } from "@workspace/integrations-anthropic-ai";
import { z } from "zod/v4";
import { ShotSpecSchema, type ShotSpec } from "./types";

const DEFAULT_MODEL =
  process.env.FILMITTO_STORYBOARD_MODEL ?? "claude-sonnet-4-6";

const SYSTEM_PROMPT = `You are the Filmitto storyboard architect.

The user gives you a high-level film prompt. You expand it into a
multi-shot storyboard suitable for autoregressive long-video generation
(LongLive-2.0).

Rules:
- Produce between 3 and 8 shots that tell a coherent story arc.
- Each shot prompt is 1-3 sentences of vivid visual description:
  camera, subject, action, lighting, mood. No dialogue.
- Keep durations between 2 and 8 seconds per shot.
- Use distinct compositions across shots so the model renders visible cuts.
- Reuse subjects and setting between consecutive shots so multi-shot
  conditioning stays coherent.
- Return shots in narrative order.

Emit the storyboard exclusively via the emit_storyboard tool.`;

const StoryboardOutputSchema = z.object({
  shots: z.array(ShotSpecSchema.omit({ shot_id: true })).min(1).max(12),
});

const EMIT_STORYBOARD_TOOL = {
  name: "emit_storyboard",
  description:
    "Emit the final ordered list of shots that make up the storyboard.",
  input_schema: {
    type: "object" as const,
    additionalProperties: false,
    required: ["shots"],
    properties: {
      shots: {
        type: "array",
        minItems: 1,
        maxItems: 12,
        items: {
          type: "object",
          additionalProperties: false,
          required: ["prompt", "duration_seconds"],
          properties: {
            prompt: { type: "string", minLength: 1 },
            duration_seconds: { type: "number", minimum: 1, maximum: 10 },
            reference_image_path: { type: ["string", "null"] },
            reference_clip_path: { type: ["string", "null"] },
          },
        },
      },
    },
  },
};

export interface StoryboardOptions {
  model?: string;
  maxTokens?: number;
}

/**
 * Expand a high-level film prompt into a typed list of `ShotSpec`s.
 *
 * Uses prompt caching (`cache_control: "ephemeral"`) on the system
 * prompt so repeated invocations with the same architect persona are
 * cheap, and tool_choice forces the model through the structured
 * `emit_storyboard` output so the result is always parseable.
 */
export async function generateStoryboard(
  filmPrompt: string,
  opts: StoryboardOptions = {},
): Promise<ShotSpec[]> {
  const response = await anthropic.messages.create({
    model: opts.model ?? DEFAULT_MODEL,
    max_tokens: opts.maxTokens ?? 2048,
    system: [
      {
        type: "text",
        text: SYSTEM_PROMPT,
        cache_control: { type: "ephemeral" },
      },
    ],
    tools: [EMIT_STORYBOARD_TOOL],
    tool_choice: { type: "tool", name: "emit_storyboard" },
    messages: [
      {
        role: "user",
        content: `Film prompt:\n\n${filmPrompt}\n\nProduce the storyboard now.`,
      },
    ],
  });

  for (const block of response.content) {
    if (block.type === "tool_use" && block.name === "emit_storyboard") {
      const parsed = StoryboardOutputSchema.parse(block.input);
      return parsed.shots.map((shot, index) => ({
        ...shot,
        shot_id: `shot_${String(index + 1).padStart(2, "0")}`,
      }));
    }
  }

  throw new Error(
    "Filmitto storyboard agent did not emit a tool_use block. Raw response stop_reason: " +
      response.stop_reason,
  );
}
