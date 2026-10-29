# web/ — Next.js 16 (admin panel, shared-link viewer)

@AGENTS.md

- Next 16 differs from older versions; consult `node_modules/next/dist/docs/` or https://nextjs.org/docs (llms.txt) before using an API.
- `cacheComponents`/PPR is OFF (Phase 1.10): pages are rendered per request so the strict nonce CSP (`src/proxy.ts`) covers every script; a prerendered shell cannot carry the nonce.
- Auth (Phase 1): BFF — route handlers keep tokens in httpOnly cookies; browser JS never sees a token. `/api/*` is FastAPI (via Caddy); web-only server routes go under `/bff/*`.
- `lang="mn"`, Noto Sans (Cyrillic). Flags = colour + glyph + text. Never expose error details to the page.

## Commands
- `pnpm --filter web dev | build | typecheck | test` (vitest). Docker image: `web/Dockerfile` (context = repo root, standalone output).
