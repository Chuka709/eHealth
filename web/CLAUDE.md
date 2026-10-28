# web/ — Next.js 16 (admin panel, shared-link viewer)

@AGENTS.md

- Next 16 differs from older versions; consult `node_modules/next/dist/docs/` or https://nextjs.org/docs (llms.txt) before using an API.
- `cacheComponents` is on: data is dynamic by default; uncached data must render inside `<Suspense>`; cache explicitly with `"use cache"`.
- Auth (Phase 1): BFF — route handlers keep tokens in httpOnly cookies; browser JS never sees a token. `/api/*` is FastAPI (via Caddy); web-only server routes go under `/bff/*`.
- `lang="mn"`, Noto Sans (Cyrillic). Flags = colour + glyph + text. Never expose error details to the page.

## Commands
- `pnpm --filter web dev | build | typecheck | test` (vitest). Docker image: `web/Dockerfile` (context = repo root, standalone output).
