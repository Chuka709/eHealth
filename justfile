set dotenv-load := true
set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

# PowerShell blocks the pnpm .ps1 shim under the default execution policy; the .cmd shim needs no policy change.
pnpm := if os() == "windows" { "pnpm.cmd" } else { "pnpm" }

compose := "docker compose -f infra/docker-compose.yml --env-file .env"
api := compose + " run --rm --no-deps api"

default:
    @just --list

# One-time: random dev secrets + JS deps + local Python env (LSP/ruff/mypy only)
init:
    python scripts/init_env.py
    {{pnpm}} install
    cd backend; uv sync

# --- Infra ---
up:
    {{compose}} up -d --build --wait

down:
    {{compose}} down

ps:
    {{compose}} ps

logs service="":
    {{compose}} logs -f --tail=100 {{service}}

# --- Backend (runs inside the Linux container: same as production) ---
migrate:
    {{compose}} run --rm migrate

seed:
    {{compose}} run --rm migrate python -m labtrack.cli seed

# Admins are created by the owner role in the migrate container (never through the API).
create-admin username role="super_admin":
    {{compose}} run --rm migrate python -m labtrack.cli create-admin {{username}} --role {{role}}

# One-off after migration 0008: phone numbers sealed under the KEK move to user keys.
rewrap-user-keys:
    {{compose}} run --rm migrate python -m labtrack.cli rewrap-user-keys

unlock-admin username:
    {{compose}} run --rm migrate python -m labtrack.cli unlock-admin {{username}}

test-api *args:
    {{compose}} run --rm test pytest -q --no-header {{args}}

test-rls:
    {{compose}} run --rm test pytest -q --no-header tests/rls

lint-api:
    cd backend; uv run ruff format --check .
    cd backend; uv run ruff check .
    cd backend; uv run mypy src

# --- JS ---
lint-js:
    {{pnpm}} exec biome check .
    {{pnpm}} -r --parallel typecheck

test-js:
    {{pnpm}} -r --parallel test

mobile:
    {{pnpm}} --filter mobile start

web:
    {{pnpm}} --filter web dev

# Regenerate the TypeScript API client from the backend's OpenAPI schema (no DB needed)
gen-client:
    cd backend; uv run python -m labtrack.cli openapi ../packages/shared/openapi.json
    cd backend; uv run python -m labtrack.cli error-codes ../packages/shared/error-codes.json
    {{pnpm}} --filter @labtrack/shared gen

# CI: fail if the committed client is stale
check-client: gen-client
    git diff --exit-code -- packages/shared/openapi.json packages/shared/src/api/schema.d.ts packages/shared/error-codes.json

# --- Aggregates ---
lint: lint-api lint-js

test: test-api test-js

check: lint test
