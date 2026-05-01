import {
  FusionDrawRequest,
  FusionDrawRequestSchema,
  FusionDrawResponse,
  FusionDrawResponseSchema,
  FusionRetryRequest,
  FusionRetryRequestSchema,
} from "../types.js";

export interface BuxterFusionClientOptions {
  /** Base URL of the Buxter HTTP wrapper, e.g. http://localhost:8081 */
  baseUrl: string;
  /** Optional bearer token forwarded as Authorization: Bearer ... */
  token?: string;
  /** Override fetch (useful for tests). Defaults to globalThis.fetch. */
  fetcher?: typeof fetch;
}

export class BuxterFusionClient {
  private readonly baseUrl: string;
  private readonly token?: string;
  private readonly fetcher: typeof fetch;

  constructor(options: BuxterFusionClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.token = options.token;
    this.fetcher = options.fetcher ?? globalThis.fetch.bind(globalThis);
  }

  async draw(input: FusionDrawRequest): Promise<FusionDrawResponse> {
    const body = FusionDrawRequestSchema.parse(input);
    return this.post("/api/fusion/draw", body);
  }

  async retry(input: FusionRetryRequest): Promise<FusionDrawResponse> {
    const body = FusionRetryRequestSchema.parse(input);
    return this.post("/api/fusion/retry", body);
  }

  private async post(
    path: string,
    body: unknown,
  ): Promise<FusionDrawResponse> {
    const headers: Record<string, string> = {
      "content-type": "application/json",
    };
    if (this.token) {
      headers.authorization = `Bearer ${this.token}`;
    }

    const response = await this.fetcher(`${this.baseUrl}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const text = await response.text().catch(() => "");
      throw new BuxterFusionError(
        `Buxter ${path} returned ${response.status}: ${text || response.statusText}`,
        response.status,
      );
    }

    const json = await response.json();
    return FusionDrawResponseSchema.parse(json);
  }
}

export class BuxterFusionError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "BuxterFusionError";
    this.status = status;
  }
}
