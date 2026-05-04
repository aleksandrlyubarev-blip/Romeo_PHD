# ADR-001: Orchestrator choice (ROMA vs LangGraph vs Moltis) — mirror

**Status:** 🟡 PROPOSED
**Date:** 2026-04-21
**Source:** [romeoflexvision/docs/decisions/adr-001-orchestrator-choice.md](https://github.com/aleksandrlyubarev-blip/RomeoFlexVision/blob/claude/roboqc-90day-launch-WgUEV/docs/decisions/adr-001-orchestrator-choice.md)

## Romeo_PHD-specific implications (если ACCEPTED LangGraph)

### Spike plan (Phase 1 Week 1)

1. Создать `artifacts/deepagents-runtime/` как workspace package
2. Dependency: `@langchain/langgraph` (TS), pin minor version
3. Wrap `pipeline-executor.ts` как custom node:
   ```ts
   import { StateGraph } from "@langchain/langgraph";
   import { runPipeline } from "@workspace/api-server/lib/pipeline-executor";
   const node = async (state) => runPipeline(state.pipelineId, state.input);
   ```
4. Проверить HITL interrupt: LangGraph `interrupt()` → запись в `consultations` таблицу через lib/db → UI consultations.tsx показывает → resume возвращает control LangGraph
5. End-to-end demo: 1 General + 2 Majors + 4 Sergeants, mock LLM responses, полный флоу с одним HITL pause

### Risks specific to Romeo_PHD

- LangGraph state checkpointer может конфликтовать с существующим Drizzle persistence — spike должен это выявить
- React Flow в ide.tsx ожидает определённый graph format — нужен adapter LangGraph → React Flow nodes
- Existing YAML format из pipeline-parser.ts может потребовать extension (sub-graph nesting)

### Validation criteria

До ACCEPTED:
- [ ] Spike runs locally (`pnpm --filter @workspace/deepagents-runtime run demo`)
- [ ] HITL pause/resume работает end-to-end
- [ ] Founder review demo (≤1 час)
- [ ] No conflicts с существующими typecheck/lint
