import {
  ChunkEventSchema,
  JobAcceptedSchema,
  JobStatusSchema,
  type BassitoStreamMessage,
  type JobAccepted,
  type JobStatus,
  type ShotSpec,
} from "./types";

const DEFAULT_ENGINE_URL =
  process.env.BASSITO_ENGINE_URL ?? "http://localhost:8000";

export interface GenerateRequest {
  prompt: string;
  shots?: ShotSpec[];
}

export interface ExtendRequest {
  source_clip_path: string;
  prompt: string;
  duration_seconds?: number;
}

export interface RestyleRequest {
  source_clip_path: string;
  style_prompt: string;
  duration_seconds?: number;
}

/**
 * Typed HTTP client for the bassito LongLive-2.0 FastAPI service.
 *
 * The service lives on the Blackwell engine node and is the single source
 * of NVFP4 inference; this client is what romeo_phd uses to drive it.
 */
export class BassitoLongLiveClient {
  constructor(public readonly baseUrl: string = DEFAULT_ENGINE_URL) {}

  async generate(req: GenerateRequest): Promise<JobAccepted> {
    return this.acceptedPost("/v1/longlive/generate", req);
  }

  async extend(req: ExtendRequest): Promise<JobAccepted> {
    return this.acceptedPost("/v1/longlive/extend", req);
  }

  async restyle(req: RestyleRequest): Promise<JobAccepted> {
    return this.acceptedPost("/v1/longlive/restyle", req);
  }

  async jobStatus(jobId: string): Promise<JobStatus> {
    const res = await fetch(`${this.baseUrl}/v1/jobs/${encodeURIComponent(jobId)}`);
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(
        `bassito jobStatus(${jobId}) failed: HTTP ${res.status} ${text}`,
      );
    }
    return JobStatusSchema.parse(await res.json());
  }

  /**
   * Yields each SSE message from the bassito chunk stream until the
   * terminal `done` event. Wraps the platform fetch ReadableStream so
   * callers can `for await` directly without an SSE library.
   */
  async *streamJob(jobId: string): AsyncIterable<BassitoStreamMessage> {
    const res = await fetch(
      `${this.baseUrl}/v1/jobs/${encodeURIComponent(jobId)}/stream`,
      { headers: { Accept: "text/event-stream" } },
    );
    if (!res.ok || !res.body) {
      throw new Error(
        `bassito streamJob(${jobId}) failed: HTTP ${res.status}`,
      );
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let currentEvent = "message";

    while (true) {
      const { done, value } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const raw of lines) {
        const line = raw.replace(/\r$/, "");
        if (line === "") {
          currentEvent = "message";
          continue;
        }
        if (line.startsWith("event:")) {
          currentEvent = line.slice(6).trim();
          continue;
        }
        if (line.startsWith("data:")) {
          const payload = line.slice(5).trim();
          if (!payload) continue;
          const parsed = JSON.parse(payload);
          if (currentEvent === "chunk") {
            yield { type: "chunk", data: ChunkEventSchema.parse(parsed) };
          } else if (currentEvent === "done") {
            yield { type: "done", data: JobStatusSchema.parse(parsed) };
            return;
          }
        }
      }
    }
  }

  private async acceptedPost(
    path: string,
    body: unknown,
  ): Promise<JobAccepted> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(
        `bassito ${path} failed: HTTP ${res.status} ${text}`,
      );
    }
    return JobAcceptedSchema.parse(await res.json());
  }
}

/** Process-wide default client; reads BASSITO_ENGINE_URL at import time. */
export const bassitoClient = new BassitoLongLiveClient();
