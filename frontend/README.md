# Mesh frontend

SvelteKit 2 + Svelte 5 single-page app (adapter-static, SSR off). Package manager: Bun.

```sh
bun install
bun run dev        # http://localhost:3010, proxies /v1 and /healthz to API_PROXY_TARGET (default http://localhost:3011)
bun run check      # svelte-kit sync + svelte-check
bun run lint       # prettier --check + eslint
bun run format
bun run test       # vitest
bun run e2e        # playwright (reuses whatever serves :3010)
bun run build      # static output in build/
bun run gen:api    # regenerate src/lib/api/schema.d.ts from ../backend/openapi.json
```

Design tokens live in `src/app.css` (copied verbatim from the PRD). Pages use token classes only.
