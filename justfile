set dotenv-load := true
set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

# PowerShell blocks the pnpm .ps1 shim under the default execution policy; the .cmd shim needs no policy change.
pnpm := if os() == "windows" { "pnpm.cmd" } else { "pnpm" }

compose := "docker compose -f infra/docker-compose.yml --env-file .env"
# Playwright browsers inside the repo (the system drive may be small).
export PLAYWRIGHT_BROWSERS_PATH := justfile_directory() / ".playwright-browsers"
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
# Roles added after the data directory was created (labtrack_push, 2.11b): idempotent, run
# before `just migrate`. Recreates postgres when .env gained a password (`just init`).
db-roles:
    {{compose}} up -d --wait postgres
    {{compose}} exec -T postgres sh /docker-entrypoint-initdb.d/02-push-role.sh
    {{compose}} exec -T postgres sh /docker-entrypoint-initdb.d/03-backup-role.sh

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

# Admin web end to end against the running stack (`just up` first). Creates a throwaway admin.
e2e-web *args:
    {{pnpm}} --filter web exec playwright test {{args}}

# Reading quality against hand-checked answers (docs/05 "Eval"): synthetic eval/cases (in git)
# and real eval/local (git-ignored, PHI). `just eval --details`, `--check` (DoD), `--ai` (costs
# money; ANTHROPIC_API_KEY and EXTRACTION_MODEL from the environment).
eval *args:
    cd backend; $env:UV_PYTHON_DOWNLOADS = "never"; uv run python -m labtrack.extraction.evaluate ../eval/cases ../eval/local --seed ../seed/lab_tests.json --report ../eval/report.md {{args}}

test-api *args:
    {{compose}} run --rm test pytest -q --no-header {{args}}

# Fuzz the user API with schemathesis against the running dev stack (`just up` first).
# schemathesis runs from a uv tool env on F: (not in the API image); see backend/scripts/fuzz_api.py
fuzz-api:
    $env:UV_CACHE_DIR = "F:/.uv-cache"; $env:UV_TOOL_DIR = "F:/.uv-tools"; cd backend; uv run python scripts/fuzz_api.py

# Persistent demo accounts and records on the dev stack (backend/scripts/seed_demo.py);
# credentials in .env.demo (git-ignored). `just seed-demo --reset` retires and seeds them anew.
seed-demo *args:
    $env:UV_CACHE_DIR = "F:/.uv-cache"; $env:UV_TOOL_DIR = "F:/.uv-tools"; cd backend; uv run python scripts/seed_demo.py {{args}}

# The 2.10d device checks on the seeded demo accounts (no activation): `just e2e-mobile-fast`
# runs reminders, wizard, travel and offline; name stages to run only those.
e2e-mobile-fast *stages:
    $env:UV_CACHE_DIR = "F:/.uv-cache"; $env:UV_TOOL_DIR = "F:/.uv-tools"; cd backend; uv run python scripts/e2e_mobile.py --fast {{quote(stages)}}

# Maestro flows (mobile/.maestro, or the given files) against the dev build on the running
# Android emulator; a throwaway user is provisioned and disabled afterwards. Maestro needs Java:
# JAVA_HOME (Android Studio's jbr). See backend/scripts/e2e_mobile.py
e2e-mobile *flows:
    $env:UV_CACHE_DIR = "F:/.uv-cache"; $env:UV_TOOL_DIR = "F:/.uv-tools"; cd backend; uv run python scripts/e2e_mobile.py {{quote(flows)}}

# Encrypted backup of the database and documents into ./backups (8.2; docs/OPS_RUNBOOK.md)
backup:
    {{compose}} --profile ops run --rm --build backup backup.sh

# Restore the newest (or the given) backup into a scratch database and check it
restore-drill identity stamp="":
    {{compose}} --profile ops run --rm --build -v "{{absolute_path(identity)}}:/run/secrets/backup-identity:ro" restore-drill restore-drill.sh '{{stamp}}'

# Recreate the empty test database (as in infra/postgres/init/01-roles.sh). Downgrades do not
# remove objects an older revision of a migration created, so tests could run on a stale schema.
reset-test-db:
    {{compose}} exec -T postgres psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c "drop database if exists labtrack_test with (force)" -c "create database labtrack_test owner labtrack_owner" -c "revoke all on database labtrack_test from public" -c "grant connect on database labtrack_test to labtrack_app, labtrack_admin, labtrack_admin_login, labtrack_maint, labtrack_push"

test-rls:
    {{compose}} run --rm test pytest -q --no-header tests/rls

lint-api:
    cd backend; uv run ruff format --check .
    cd backend; uv run ruff check .
    cd backend; uv run mypy src tests alembic

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
    cd backend; uv run python -m labtrack.cli consent-versions ../packages/shared/consent-versions.json
    {{pnpm}} --filter @labtrack/shared gen

# CI: fail if the committed client is stale
check-client: gen-client
    git diff --exit-code -- packages/shared/openapi.json packages/shared/src/api/schema.d.ts packages/shared/error-codes.json packages/shared/consent-versions.json

# --- Aggregates ---
lint: lint-api lint-js

test: test-api test-js

check: lint test
