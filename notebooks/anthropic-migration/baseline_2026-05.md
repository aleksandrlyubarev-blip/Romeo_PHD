# PinoCut / Romeo PhD — Anthropic baseline (May 2026)

> **ТЗ Phase 0.1.** Fill before 31.05.2026. Shared cross-repo template with
> Andrew-Analitic; PinoCut-specific rows here track the text sub-agents that
> Phase 2.3 will migrate (Script, Visual Prompt, Consistency).
>
> **Related.** The 15.06 auth flip procedure lives in the Andrew-Analitic
> repo as `notebooks/anthropic-migration/auth_flip_runbook.md` — the same
> document covers both repos. PinoCut-specific wiring decisions are
> recorded there under § 3.2.

## M1 — Monthly Anthropic API spend (May 2026)

Source: Anthropic Console → Usage → May 2026. Aggregate over both
projects/keys if PinoCut uses a separate key from Andrew Swarm.

- [ ] Total Anthropic spend, both repos: `$_____`
- [ ] PinoCut share (rough split by tag/key/model), $: `_____`

| Model                         | Spend, $ | Tokens in | Tokens out |
| ----------------------------- | -------- | --------- | ---------- |
| claude-sonnet-4-6             |          |           |            |
| claude-haiku-4-5              |          |           |            |
| (other)                       |          |           |            |

## M2 — PinoCut text-agent call volume (last 30 days)

Source: `telemetry_events` table in PinoCut DB (filter
`eventType='node_executed'`). Group by node type or by Anthropic
client invocation site if telemetry granularity allows.

| Agent                | Current LLM     | Calls, N | Tokens in | Tokens out | Spend, $ |
| -------------------- | --------------- | -------- | --------- | ---------- | -------- |
| Script               |                 |          |           |            |          |
| Visual Prompt        |                 |          |           |            |          |
| Consistency          |                 |          |           |            |          |
| pipeline-executor    | claude-sonnet-4-6 |        |           |            |          |
| (other text nodes)   |                 |          |           |            |          |

If a sub-agent is not yet wired through `@workspace/integrations-anthropic-ai`,
note its current provider (OpenAI, Grok, other) and migration cost.

## M3 — Build / typecheck health

Source: `pnpm run typecheck` on `main` as of cutoff.

- [ ] Status: pass / fail (paste output)
- [ ] Last green commit SHA: `__________`

## M4 — Latency p50 / p95 per text-agent

Source: `telemetryEvents.payload` durations (if recorded). If not recorded,
add timing to `pipeline-executor.ts` before the auth flip — without it Phase
2.3 cannot prove a no-regression A/B.

| Agent             | p50, ms | p95, ms |
| ----------------- | ------- | ------- |
| Script            |         |         |
| Visual Prompt     |         |         |
| Consistency       |         |         |
| pipeline-executor |         |         |

## M5 — Interactive Claude subscription utilization (Max 5x)

Same snapshot used for Andrew-Analitic — link or copy the figure here so the
two notebooks remain consistent.

- [ ] Average daily usage, %: `_____`

## M6 — $/task per text-agent

Derived: per-agent spend / per-agent call count from M2.

| Agent             | $/task |
| ----------------- | ------ |
| Script            |        |
| Visual Prompt     |        |
| Consistency       |        |
| pipeline-executor |        |

## Sign-off

- [ ] Baseline frozen by: `__________` on `__________`
- [ ] Linked commit on `claude/anthropic-sdk-migration-mPKYD`: `__________`
