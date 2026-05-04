# RoboQC 90-Day Launch Plan (OME-style) — mirror

Источник: [`romeoflexvision/docs/90day-launch-plan.md`](https://github.com/aleksandrlyubarev-blip/RomeoFlexVision/blob/claude/roboqc-90day-launch-WgUEV/docs/90day-launch-plan.md)

**Branch:** `claude/roboqc-90day-launch-WgUEV` (оба репо)
**Window:** 2026-04-21 → 2026-07-21
**Founder mode:** Architect, 2h/day review only
**Primary wedge (weeks 1-4):** Architecture v1.0

## Romeo_PHD-specific deliverables

### Phase 1 (Weeks 1-4)
- `artifacts/deepagents-runtime/` — LangGraph TS wrapper поверх `pipeline-executor.ts`
- `docs/architecture-v1.0.md` — mirror из romeoflexvision
- `docs/decisions/adr-001..004-*.md` — mirror
- End-to-end demo: 1 General + 2 Majors + 4 Sergeants через LangGraph + HITL pause

### Phase 2 (Weeks 5-8)
- `artifacts/research-agent/` — URL → summary → tradeoff → decision record
- Operator UI extensions: role-based views, offline mode, 1C-MES/OPC UA hooks
- New API endpoints: `/api/research-agent/ingest`, `/api/research-agent/decisions`

### Phase 3 (Weeks 9-12)
- Edge inference deployment package (Docker)
- `artifacts/operator-ui/` — вынесена из romeo-phd для shop-floor deployment
- Audit trail в Postgres (переиспользует lib/db schema)

## Reuse > rewrite

Каждый новый artifact ОБЯЗАН использовать существующие:
- pipeline-parser.ts (Kahn's Algorithm)
- pipeline-executor.ts (LLM workers + HITL)
- consultations.tsx UI pattern
- lib/db Drizzle schema
- lib/integrations-anthropic-ai

Код, который дублирует эти примитивы, будет отклонён на review.
