# syntax=docker/dockerfile:1
# Build context is the repo root (compose: context: ., dockerfile: frontend/Dockerfile),
# so this file can copy both frontend/ and infra/nginx.conf.

FROM oven/bun:1.3.10 AS build
WORKDIR /app/frontend

# Dependencies first, for layer caching. `prepare` (svelte-kit sync) may no-op here; build syncs.
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile

COPY frontend/ ./
RUN bun run build

FROM nginx:1.27-alpine AS runtime
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/build /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=3 CMD wget -qO- http://127.0.0.1/index.html >/dev/null || exit 1
