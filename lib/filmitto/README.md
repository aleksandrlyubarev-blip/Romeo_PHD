# @workspace/filmitto

Filmitto is the romeo_phd control plane for long-video film production.
It drives the LongLive-2.0 inference engine that lives in the separate
[`bassito`](https://github.com/aleksandrlyubarev-blip/bassito) repo.

This package contains:

- `types.ts`     — zod-validated `ShotSpec`, `ChunkEvent`, `JobAccepted`,
  `JobStatus`. These mirror the bassito Python contract one-to-one.
- `bassito_client.ts` — `BassitoLongLiveClient` with `generate`,
  `extend`, `restyle`, `jobStatus`, and `streamJob` (async iterator over
  the SSE chunk stream).
- `storyboard_agent.ts` — `generateStoryboard(filmPrompt)` uses the
  Anthropic SDK (`@workspace/integrations-anthropic-ai`) with a cached
  system prompt and a tool-use schema to produce a typed `ShotSpec[]`.

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `BASSITO_ENGINE_URL` | `http://localhost:8000` | Where the bassito LongLive FastAPI service is listening. On the Blackwell engine node. |
| `FILMITTO_STORYBOARD_MODEL` | `claude-sonnet-4-6` | Anthropic model id for the storyboard agent. |
| `AI_INTEGRATIONS_ANTHROPIC_BASE_URL` / `_API_KEY` | — | Inherited from `@workspace/integrations-anthropic-ai`. |
| `DATABASE_URL` | — | Inherited from `@workspace/db` (for the filmitto_* tables). |

## Wiring

The API surface in `artifacts/api-server/src/routes/filmitto/` uses this
package. From an api-server route handler:

```ts
import { BassitoLongLiveClient, generateStoryboard } from "@workspace/filmitto";

const client = new BassitoLongLiveClient(); // reads BASSITO_ENGINE_URL
const shots = await generateStoryboard("a moonlit desert chase");
const job = await client.generate({ prompt: "", shots });
for await (const event of client.streamJob(job.job_id)) {
  // event.type === "chunk" | "done"
}
```

## Filmitto Architecture

```
browser  -->  romeo_phd UI  -->  api-server  -->  @workspace/filmitto  -->  bassito LongLive HTTP service (Blackwell)
                                                          |
                                                          +->  Anthropic SDK (storyboard agent)
```

The heavy NVFP4 inference lives entirely inside bassito on Blackwell
hardware; this package only consumes its HTTP contract.
