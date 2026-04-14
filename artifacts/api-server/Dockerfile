# syntax=docker/dockerfile:1.7
#
# Dockerfile for @workspace/api-server (Express + pipeline executor).
#
# Build artifact: artifacts/api-server/dist/index.cjs (esbuild CJS bundle).
# Workspace packages (@workspace/db, @workspace/api-zod,
# @workspace/integrations-anthropic-ai) are bundled into the cjs by
# artifacts/api-server/build.ts. A small set of npm deps (cookie-parser,
# js-yaml, and transitive deps of externals in build.ts allowlist) is
# marked external and must be resolvable at runtime via node_modules.
#
# Strategy: multi-stage build with a full pnpm workspace install in the
# builder stage, then copy the entire resolved /repo tree into the runtime
# image. This is ~1.5 GB uncompressed — acceptable for Phase 0. Image
# size optimisation (pnpm deploy, prod-only prune, distroless base) is
# deferred to a later pass once the baseline is green.

ARG NODE_VERSION=22
ARG PNPM_VERSION=9

# ---- base: corepack-managed pnpm --------------------------------------------
FROM node:${NODE_VERSION}-slim AS base
RUN corepack enable && corepack prepare pnpm@${PNPM_VERSION} --activate
WORKDIR /repo

# ---- builder: install whole workspace, build api-server ---------------------
FROM base AS builder

# Copy the full monorepo. Cache efficiency is sacrificed for correctness in
# this first pass; a future optimisation will copy package.jsons first and
# bind-mount pnpm store. A .dockerignore (next landing) keeps .git and any
# local dist/ outputs out of the build context.
COPY . .

RUN pnpm install --frozen-lockfile

# esbuild bundle → artifacts/api-server/dist/index.cjs
RUN pnpm --filter @workspace/api-server run build

# ---- runtime: minimal image carrying the built repo -------------------------
FROM base AS runtime

# Copying the entire builder tree preserves pnpm's symlinked node_modules
# layout, which the runtime externals (cookie-parser, js-yaml, etc.) rely on.
COPY --from=builder /repo /repo

ENV NODE_ENV=production
ENV PORT=3001

# Express listens on 3001 per artifacts/api-server/src/index.ts + README.
EXPOSE 3001

# DATABASE_URL must be supplied at runtime (docker-compose wires it to the
# postgres service). ANTHROPIC_API_KEY is wired the same way.
CMD ["node", "artifacts/api-server/dist/index.cjs"]
