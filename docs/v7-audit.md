# Romeo_PHD v7.0 — Baseline Audit

**Branch:** `claude/romeo-phd-v7-kubernetes-ymnbl`
**Baseline commit:** `28b3d54` (main, merge of PR #2 "Introduce Buxter MAS")
**Audit date:** 2026-04-14
**Scope:** what actually exists in the repo vs. the v7 "Kubernetes for Agents" vision.

This document is deliberately honest. Several pieces that were informally
described as "already built" are **not present in the repo**. We call them
out so the v7 roadmap starts from reality, not from memory.

---

## 1. What is actually in the repo today

All paths below are verified against `main` at `28b3d54`.

### 1.1 Monorepo layout

- pnpm workspace (`pnpm-workspace.yaml`) — packages under `artifacts/*`,
  `lib/*`, `lib/integrations/*`, `scripts`.
- TypeScript across the board (`tsconfig.base.json`, `tsconfig.json`).
- Node toolchain only — **no Rust, no Go, no Python services**. Buxter's
  Python/FreeCAD runtime is a design document, not yet an artifact.

### 1.2 Backend — `artifacts/api-server`

Express 5 service (dev on port 3001) with:

- `src/app.ts`, `src/index.ts` — entrypoint / app wiring.
- `src/lib/pipeline-parser.ts` (~4.4 KB) — YAML → DAG parser.
  README describes this as "Kahn's Algorithm + YAML parser".
- `src/lib/pipeline-executor.ts` (~9 KB) — LLM workers + HITL
  (human-in-the-loop) pause/resume.
- `src/routes/health.ts`, `src/routes/pipeline/` — REST surface.
- `src/middlewares/` — request middlewares.
- `build.ts` — per-package build script.

Documented HTTP surface (from README, not re-verified line-by-line):

| Method | URL | Purpose |
|--------|-----|---------|
| GET    | `/api/healthz` | Health check |
| GET    | `/api/pipelines` | List pipelines |
| POST   | `/api/pipelines` | Create pipeline from YAML |
| GET    | `/api/pipelines/:id` | Pipeline + nodes |
| POST   | `/api/pipelines/:id/execute` | Run (SSE) |
| POST   | `/api/pipelines/:id/resume` | Resume after HITL pause |
| POST   | `/api/consultations/:id/respond` | Operator answer |
| GET    | `/api/telemetry` | Telemetry logs |

### 1.3 Frontend — `artifacts/romeo-phd`

React 19 + Vite 7 + Tailwind v4, Wouter routing, React Query hooks
from `@workspace/api-client-react`. Pages:

- `src/pages/ide.tsx` (~17 KB) — Monaco editor + React Flow canvas
  for authoring pipelines.
- `src/pages/dashboard.tsx` (~20 KB) — Mission Control dashboard,
  contains the Buxter MAS blueprint visualization.
- `src/pages/telemetry.tsx` (~4 KB) — live agent logs.
- `src/pages/consultations.tsx` (~6.3 KB) — HITL approval queue.
- `src/pages/not-found.tsx`.
- SSE streaming implemented manually with `fetch` + `ReadableStream`
  (per `requirements.yaml`).

### 1.4 Shared libs — `lib/`

- `lib/db/` — Drizzle ORM + PostgreSQL schema.
- `lib/api-spec/` — OpenAPI 3.1 spec.
- `lib/api-zod/` — Zod schemas (generated from spec).
- `lib/api-client-react/` — React Query hooks (generated from spec).
- `lib/integrations-anthropic-ai/` — Anthropic SDK wrapper.
- `lib/integrations/` — other integrations.

### 1.5 Third artifact — `artifacts/mockup-sandbox`

A **UI mockup preview playground** (Vite + React, has
`mockupPreviewPlugin.ts` and its own `index.html`). This is *not* an
agent sandbox, not a runtime isolation layer, and not written in Rust.
Its purpose is rendering generated UI mockups inside the IDE page.

### 1.6 Buxter MAS (first target vertical)

- `docs/buxter-mas-architecture.md` — roles: Orchestrator,
  FreeCAD Modeling Agent, Geometry/Topology Validator, Interoperability
  Agent, SolidWorks RPA/CV Agent.
- `docs/buxter-sprint-1-spec.md`, `buxter-sprint-2-spec.md`,
  `buxter-sprint-3-spec.md` — sprint ТЗ.
- Declared tech stack (per doc): **Python 3.11, FreeCAD Python API,
  OpenCV/YOLO + PyAutoGUI, optional C# SolidWorks microservice,
  orchestration TBD (LangGraph / CrewAI / AutoGen / Semantic Kernel /
  custom FastAPI+Redis)**.
- Current surface in repo: **dashboard blueprint + YAML pipeline
  templates only**. No Python agent code, no FreeCAD integration,
  no RPA runner. Buxter is a specified use-case, not a running one.
- **Out of scope for the v7 branch.** Buxter is being developed in a
  separate branch (see §6 decisions). The v7 branch only touches the
  platform layer; it must not modify Buxter docs, templates, or UI
  blueprints.

---

## 2. Claims that did NOT survive the audit

These were described as existing, but the repo search returns zero
results. Before any v7 work assumes they exist, we reset expectations.

| Claim | Reality |
|---|---|
| **Moltis — Rust sandbox** | No Rust files in repo. Zero matches for `moltis`. `artifacts/mockup-sandbox` is a Vite UI preview plugin, not a runtime sandbox. Moltis was *planned* for fast execution — it is a future Phase 4 component, not existing code. |
| **Semantic conflict resolution** | Zero matches in code search. Not implemented. |
| **Multi-tenant namespaces / RBAC for agents** | No implementation. No auth layer visible in `api-server/src/routes`. |
| **OpenTelemetry / Jaeger / Prometheus / Grafana** | Not wired. Telemetry is a custom `/api/telemetry` log stream, not OTel. |
| **A2A protocol / MCP gateway / Agent Registry** | Not present. |
| **Kubernetes CRDs (AgentCard, Pipeline, AgentDeployment)** | Not present. Pipelines are plain YAML parsed by `pipeline-parser.ts`, not K8s resources. |
| **Reconciliation loop / operator-style controller** | Not present. Executor is a one-shot runner, not a controller. |
| **SPIFFE identity / mTLS between agents** | Not present. |
| **Circuit breakers / backpressure / DLQ / cost scheduler** | Not present. |
| **CI workflows** | Originally missing; **added in this branch** as `.github/workflows/ci.yml` (commit `121c668`). |
| **Docker / Helm / kind-config** | No `Dockerfile`, no K8s manifests, no Helm chart, no kind config. Project currently runs only in Codespaces / Replit. |

**Nothing above is a criticism of past work — a lot of surface has been
built.** It only means v7 will be adding these layers, not reorganizing
existing ones.

---

## 3. Confirmed platform gaps for "Kubernetes for Agents" positioning

Summarizing the gaps in one place so the roadmap can be ordered:

1. **No packaging layer.** To deploy this anywhere beyond a Codespace we
   need a `Dockerfile` per artifact + a `docker-compose.yml` for the
   whole stack (api-server, UI, Postgres).
2. **~~No CI.~~** ✅ **Fixed in this branch** (`.github/workflows/ci.yml`).
   Typecheck + build on every PR / push to `main` and `claude/**`.
3. **No K8s surface.** No manifests, no CRDs, no controller, no Helm.
4. **No identity / isolation model.** Anthropic API key is pulled from
   env; there is no per-agent identity, no mTLS, no sandbox escape
   story for Buxter's RPA agent (which will drive SolidWorks GUIs —
   explicitly high-risk).
5. **No observability standard.** Telemetry is bespoke; we cannot
   correlate across agents, pipelines and LLM calls.
6. **DB is single-tenant.** Drizzle schema has one namespace. Multi-tenant
   `Pipeline` resources will need schema changes and migrations.
7. **Replit coupling, scheduled for removal.** `pnpm-workspace.yaml`
   pins `@replit/vite-plugin-*`; `.replitignore` is in the root; each
   artifact has a `.replit-artifact/` folder. Per §6 decision we no
   longer use Replit — this can be cleaned up in Phase 0.

---

## 4. Sequenced plan for v7

Ordering is chosen so each step is **shippable on its own** and
**unblocks the next step**. No "big bang" rewrites.

### Phase 0 — Baseline safety net
1. ✅ This audit doc (`docs/v7-audit.md`).
2. ✅ **`.github/workflows/ci.yml`** — lint (future) + typecheck + build
   on PR. Single highest-leverage change: without CI, every subsequent
   v7 step is unverified. **Landed in commit `121c668`.**
3. ⏳ **Root `Dockerfile` + `docker-compose.yml`** — api-server, UI,
   Postgres. No K8s yet. Goal: `docker compose up` gives a working
   stack on any machine.
4. ⏳ **Replit cleanup** (per §6 decision). Remove `@replit/vite-plugin-*`
   from the workspace catalog, delete `.replitignore` and
   `.replit-artifact/` folders, drop Replit plugins from any
   `vite.config.ts`. This must not regress CI.

### Phase 1 — Kubernetes packaging (not yet a control plane)
5. **Helm chart `charts/romeo-phd/`** that deploys the existing
   api-server + UI + Postgres into any cluster. Still one-tenant, still
   one pipeline runner. This is "lift and shift", not "operator".
6. **`kind-config.yaml` + `make kind-up`** — one-command local cluster
   for developers.

Shipping Phase 1 means "Romeo_PHD runs on Kubernetes". That is already
a real v7 milestone — *before* we get into CRDs.

### Phase 2 — Control plane (the actual "Kubernetes for Agents" bit)
7. Define CRDs: `AgentCard`, `Pipeline`, `AgentRun`. These should mirror
   the current YAML schema in `pipeline-parser.ts`, so we have a clean
   1:1 migration path.
8. Write the **controller** (TypeScript, using `@kubernetes/client-node`)
   that watches `Pipeline` resources and invokes the existing
   `pipeline-executor.ts` in a reconciliation loop. Reuse the executor —
   do not rewrite it.
9. Multi-tenant namespaces + a minimal RBAC surface for agents.

### Phase 3 — Reliability & observability
10. OpenTelemetry SDK in `api-server` + exporter to an OTLP collector.
    Replace (or shadow) `/api/telemetry` with OTel traces.
11. Prometheus metrics endpoint; Grafana dashboards shipped with the
    Helm chart.
12. Retry / circuit-breaker / DLQ configurable in the YAML schema.

### Phase 4 — Identity & isolation (Moltis lands here)
13. SPIFFE identity per agent pod; mTLS via SPIRE sidecar.
14. **Moltis** — introduced here as a new Rust sandbox crate, per §6
    decision. Target use: fast execution / isolation for high-risk
    agents (Buxter's RPA runner being the canonical first consumer).
    Candidates to evaluate against Moltis: gVisor, Firecracker,
    WasmEdge. The choice is made in Phase 4, not earlier.

### Phase 5 — Standards & ecosystem
15. A2A protocol adapter + MCP gateway. Feasible only after the control
    plane exists.

---

## 5. Recommended first PR after this audit

~~CI + Dockerfiles + docker-compose.~~ Split into two landings:

- ✅ **Landing 1 (done):** `.github/workflows/ci.yml`. Commit `121c668`.
- ⏳ **Landing 2 (next):** `Dockerfile` per artifact + root
  `docker-compose.yml` + Replit cleanup. Can ride in a single PR because
  removing Replit plugins is only safe once CI is green.

All later phases (CRDs, controllers, SPIFFE, OTel) are gated on Phase 0
being green in CI first.

---

## 6. Decisions (resolved 2026-04-14)

Original open questions from the first revision of this doc, now
answered by Aleksandr:

1. **`andrew-analitic` scope** — **Out of scope.** v7 work only touches
   `romeo_phd`. The branch spec that referenced `andrew-analitic` will
   not be honored; no pushes will land there from this effort.
2. **Buxter runtime language** — **Out of scope for v7.** Buxter is
   developed in a separate branch. The v7 branch must not modify
   Buxter docs, YAML templates, or dashboard blueprints. v7 only
   delivers the platform (packaging, K8s, control plane, observability,
   isolation) that Buxter will later run on.
3. **"Moltis"** — **Keep as planned Phase 4 component.** Moltis was
   planned as a fast-execution sandbox and will be introduced as a new
   Rust crate when Phase 4 (identity & isolation) lands. It does not
   exist in the repo today and will not be referenced as if it did.
4. **Replit coupling** — **Remove.** Replit is no longer the dev
   environment. Phase 0 item 4 handles the cleanup
   (`@replit/vite-plugin-*`, `.replitignore`, `.replit-artifact/`).
   docker-compose becomes the default local stack.
