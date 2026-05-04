# CLAUDE.md — Romeo_PHD

Project memory for Claude Code agents working in this repo.

## What this repo is

**Romeo_PHD** — инженерный backend / pipeline orchestration platform для RoboQC. Публичный surface (landing, telegram-bot, voice) живёт в [`romeoflexvision`](https://github.com/aleksandrlyubarev-blip/RomeoFlexVision).

## Tech stack

- **pnpm workspace** monorepo (TypeScript)
- **API server:** Express 5 + Drizzle ORM + PostgreSQL (port 3001)
- **UI:** React 18 + Vite + Monaco Editor + React Flow (port 5173)
- **API spec:** OpenAPI 3.1 → Zod → React Query хуки (auto-generated)
- **LLM integration:** Anthropic SDK в `lib/integrations-anthropic-ai/`
- **Orchestration:** Kahn's Algorithm DAG в `pipeline-parser.ts` + LLM workers / HITL в `pipeline-executor.ts`
- **Wrapper (Phase 1):** LangGraph TS поверх этого (см. ADR-001)

## Layout

```
artifacts/
  api-server/                # Express 5 :3001
    src/lib/pipeline-parser.ts      ← Kahn's Algorithm + YAML (REUSE)
    src/lib/pipeline-executor.ts    ← LLM workers + HITL pause/resume (REUSE)
    src/routes/pipeline/            ← REST endpoints
  romeo-phd/                 # React + Vite :5173
    src/pages/ide.tsx              ← Monaco + React Flow
    src/pages/consultations.tsx    ← HITL approval queue (REUSE for ADR review)
    src/pages/telemetry.tsx        ← live agent logs
    src/pages/dashboard.tsx        ← mission control
  mockup-sandbox/            # эксперименты
  deepagents-runtime/        # ← NEW в Phase 1 (PoC)
  research-agent/            # ← NEW в Phase 2
lib/
  db/                        # Drizzle schema
  api-zod/                   # auto-generated Zod schemas
  api-client-react/          # auto-generated React Query hooks
  api-spec/                  # OpenAPI 3.1
  integrations/
  integrations-anthropic-ai/ # Anthropic SDK обёртка
docs/
  90day-launch-plan.md       # текущий launch plan
  architecture-v1.0.md       # source of truth (Phase 1)
  decisions/                 # ADRs
  buxter-*.md                # отдельный trail (CAD MAS)
```

## Common commands

```bash
pnpm install
pnpm run dev              # API :3001 + UI :5173 параллельно
pnpm run typecheck        # TS check по всем workspace packages
pnpm --filter @workspace/db run push --accept-data-loss   # сброс + пересоздание БД
pnpm --filter @workspace/api-server run dev               # только API
sudo service postgresql start                             # если PG не запущен
```

## Decision framework (4 criteria — междурепо identical с romeoflexvision)

1. **Edge latency** — sub-200ms на RTX 3060/4060?
2. **Few-shot** — работает на 10-30 samples?
3. **Integration** — вписывается в LangGraph TS + pipeline-executor (см. ADR-001)?
4. **Defect impact** — измеримо улучшает escape rate?

## Extension points (куда добавлять новый код)

- **Новый agent runtime** → `artifacts/<name>/` как workspace package
- **Новый LLM integration** → `lib/integrations-<provider>/`
- **Новый API endpoint** → `lib/api-spec/` сначала (спек), потом codegen в `lib/api-zod` + `lib/api-client-react`, потом handler в `artifacts/api-server/src/routes/`
- **Новая UI page** → `artifacts/romeo-phd/src/pages/<name>.tsx`

## Reuse policy

НИКОГДА не писать заново:
- DAG executor (есть в pipeline-executor.ts)
- HITL pause/resume (есть там же + consultations.tsx)
- Telemetry pipeline (есть в telemetry.tsx + /api/telemetry)
- Anthropic client init (есть в integrations-anthropic-ai)
- DB schema (есть в lib/db, Drizzle migrations)

## API endpoints (текущие)

| Method | URL | Пояснение |
|---|---|---|
| GET | `/api/healthz` | health |
| GET | `/api/pipelines` | список |
| POST | `/api/pipelines` | создать из YAML |
| GET | `/api/pipelines/:id` | ноды |
| POST | `/api/pipelines/:id/execute` | запуск (SSE) |
| POST | `/api/pipelines/:id/resume` | resume после HITL pause |
| POST | `/api/consultations/:id/respond` | ответ оператора |
| GET | `/api/telemetry` | логи |

## Founder mode (current)

2 часа/день review-only. Архитектурные решения — только через ADR в `docs/decisions/`. Новые research items — в backlog Research Agent’а (Phase 2), не в core code.

## Buxter trail

Отдельный параллельный трек (autonomous CAD MAS). Спеки в `docs/buxter-mas-architecture.md` + `docs/buxter-sprint-{1,2,3}-spec.md`. RoboQC это не блокирует — желательно переиспользовать тот же LangGraph runtime.
