# Romeo PHD — Agent Orchestration Platform

## Stack
- TypeScript monorepo (pnpm workspaces)
- API: Express 5 (port 3001)
- UI: React 19 + Vite 7 (port 5173)
- DB: PostgreSQL + Drizzle ORM
- Styling: Tailwind CSS v4

## Commands
- Dev (full): `pnpm run dev` (API + UI concurrently)
- Dev API only: `pnpm run dev:api`
- Dev UI only: `pnpm run dev:ui`
- Build: `pnpm run build`
- Typecheck: `pnpm run typecheck`
- DB push: `pnpm run db:push`

## Architecture
- artifacts/api-server/ — Express 5 REST API with pipeline executor
- artifacts/romeo-phd/ — React + Vite frontend (IDE, dashboards)
- artifacts/mockup-sandbox/ — Mockup sandbox
- lib/db/ — Drizzle ORM schema + PostgreSQL
- lib/api-zod/ — Zod schemas (auto-generated)
- lib/api-client-react/ — React Query hooks (auto-generated)
- lib/api-spec/ — OpenAPI 3.1 specification
- lib/integrations-anthropic-ai/ — Anthropic Claude integration
- lib/integrations/ — External service integrations
- docs/ — Buxter MAS architecture and sprint specs
- scripts/ — Build and utility scripts

## Key Concepts
- Pipeline executor uses Kahn's algorithm for DAG topological sorting
- HITL (Human-in-the-Loop) consultation queues for operator approvals
- SSE-based streaming for real-time pipeline execution
- Buxter: autonomous multi-agent CAD system (FreeCAD + SolidWorks)

## Code Standards
- pnpm only (yarn/npm rejected by preinstall hook)
- TypeScript strict mode throughout
- Zod schemas and API client are auto-generated from OpenAPI spec
- ALWAYS run typecheck before claiming work is done
- NEVER edit auto-generated files in lib/api-zod/ or lib/api-client-react/
