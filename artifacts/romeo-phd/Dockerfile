# syntax=docker/dockerfile:1.7
#
# Dockerfile for @workspace/romeo-phd (React 19 + Vite 7 + Tailwind 4).
#
# Strategy: build static assets in a Node builder stage via pnpm + vite,
# then serve them from an nginx:alpine runtime. The runtime image carries
# only the compiled /assets + index.html and our nginx config, so the
# final image stays ~50 MB instead of the ~1.5 GB builder image.
#
# nginx config (./nginx.conf) adds:
#   - SPA fallback (try_files … /index.html) for Wouter routes
#   - /api/ reverse proxy to the api-server container
#   - SSE-friendly settings (no buffering, long read timeout) so the
#     pipeline execute stream at /api/pipelines/:id/execute works through
#     the proxy

ARG NODE_VERSION=22
ARG PNPM_VERSION=9
ARG NGINX_VERSION=1.27-alpine

# ---- base: corepack-managed pnpm --------------------------------------------
FROM node:${NODE_VERSION}-slim AS base
RUN corepack enable && corepack prepare pnpm@${PNPM_VERSION} --activate
WORKDIR /repo

# ---- builder: install full workspace, build romeo-phd -----------------------
FROM base AS builder

# Full monorepo into the build context. Optimisation (package.json-first
# layer caching) is deferred to the same pass that optimises the api-server
# Dockerfile.
COPY . .

RUN pnpm install --frozen-lockfile

# vite.config.ts reads PORT and BASE_PATH at module load, even for
# `vite build`. PORT has no effect on the built assets; BASE_PATH is wired
# into Vite's `base` option and must match the URL prefix where the site
# will be served. Default to `/` here (root-served) and override via
# --build-arg BASE_PATH=… in compose if the deployment changes.
ARG BUILD_BASE_PATH=/
ENV PORT=5173
ENV BASE_PATH=${BUILD_BASE_PATH}

RUN pnpm --filter @workspace/romeo-phd run build

# ---- runtime: nginx serving the static bundle -------------------------------
FROM nginx:${NGINX_VERSION} AS runtime

# Replace the stock default.conf with our SPA + /api proxy + SSE config.
COPY artifacts/romeo-phd/nginx.conf /etc/nginx/conf.d/default.conf

# Vite output lands at artifacts/romeo-phd/dist/public per vite.config.ts.
COPY --from=builder /repo/artifacts/romeo-phd/dist/public /usr/share/nginx/html

EXPOSE 80

# Foreground nginx so the container stays attached to its logs.
CMD ["nginx", "-g", "daemon off;"]
