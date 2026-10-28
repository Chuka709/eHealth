# syntax=docker/dockerfile:1.7
# Build context: repository root (pnpm workspace).
FROM node:22-alpine AS base
ENV PNPM_HOME=/pnpm PATH="/pnpm:$PATH" NEXT_TELEMETRY_DISABLED=1
RUN npm install -g pnpm@12.15.0
WORKDIR /repo

FROM base AS build
COPY pnpm-workspace.yaml pnpm-lock.yaml package.json ./
COPY packages/shared/package.json packages/shared/
COPY web/package.json web/
COPY mobile/package.json mobile/
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile --filter web...
COPY packages/shared packages/shared
COPY web web
RUN pnpm --filter web build

FROM node:22-alpine AS runtime
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /app
RUN addgroup -S app && adduser -S app -G app
# Owned by root, read-only for the app user: a compromised process cannot rewrite its own code.
COPY --from=build /repo/web/.next/standalone ./
COPY --from=build /repo/web/.next/static ./web/.next/static
COPY --from=build /repo/web/public ./web/public
# The only writable path: Next.js runtime cache.
RUN mkdir -p web/.next/cache && chown app:app web/.next/cache
USER app
EXPOSE 3000
CMD ["node", "web/server.js"]
