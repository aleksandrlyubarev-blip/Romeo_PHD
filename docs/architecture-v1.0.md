# Architecture v1.0 — Hybrid Hierarchical Multi-Agent Graph (mirror)

**Status:** 🟡 DRAFT (Phase 1 in progress)
**Source of truth:** [`romeoflexvision/docs/architecture-v1.0.md`](https://github.com/aleksandrlyubarev-blip/RomeoFlexVision/blob/claude/roboqc-90day-launch-WgUEV/docs/architecture-v1.0.md)

## Romeo_PHD-specific notes

### Mapping layers → code

| Layer | Implemented in |
|---|---|
| Orchestration (LangGraph TS) | `artifacts/deepagents-runtime/` (NEW Phase 1) |
| DAG executor (Kahn's) | `artifacts/api-server/src/lib/pipeline-parser.ts` (REUSE) |
| LLM workers + HITL | `artifacts/api-server/src/lib/pipeline-executor.ts` (REUSE) |
| HITL UI | `artifacts/romeo-phd/src/pages/consultations.tsx` (REUSE) |
| Telemetry | `artifacts/romeo-phd/src/pages/telemetry.tsx` (REUSE) |
| Mission control | `artifacts/romeo-phd/src/pages/dashboard.tsx` (REUSE) |
| Anthropic SDK | `lib/integrations-anthropic-ai/` (REUSE) |
| Persistence | `lib/db/` (REUSE schema) |

### Edge inference

Не в этом репо — edge inference stack разворачивается отдельно (Docker package в Phase 3, Python-based). Этот TS-monorepo = cloud orchestration + UI + audit, не инференс.

### Open questions for Romeo_PHD

- [ ] LangGraph TS pin version — будет решено в spike в Phase 1 Week 1
- [ ] Persist LangGraph state через lib/db или builtin checkpointer? (предпочтительно Drizzle, но фиксировать в ADR-002)
- [ ] OpenAPI расширение на deepagents endpoints (codegen в api-zod + api-client-react)
