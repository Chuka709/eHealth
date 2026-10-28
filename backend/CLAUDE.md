# backend/ — FastAPI, Celery, clinical core

- Layout: `src/labtrack/{api,db,worker,core,...}`; `router → service → repository`; Pydantic (API) and SQLAlchemy (DB) models stay separate.
- Raw SQL: only `labtrack.db.sql.bound_text("... :param ...")` — `sqlalchemy.text` is banned by ruff (TID251). Never f-strings in SQL.
- PHI access only inside `user_transaction(user_id)` (sets `app.user_id` per transaction). Runtime role `labtrack_app`; migrations `labtrack_owner` (`MIGRATION_DATABASE_URL`).
- Migrations: hand-written SQL in `alembic/versions/NNNN_slug.py`, always with `downgrade()`. New PHI table → `phi-table` skill.
- Logs: `structlog` with `redact_phi` — log IDs, never values/names. Sentry: `observability.py` (all data collection off).
- Celery task args: IDs only.

## Commands (repo root)
- `just test-api` — pytest **in the Linux container** against `labtrack_test` (runs alembic up → down → up first). `just test-api -k name` to filter.
- `just lint-api` — ruff format/check + mypy --strict (local `uv`, Windows OK).
- Local `uv run pytest` runs unit tests only; DB tests skip without `TEST_DATABASE_URL`.
- Windows: `uv` is in `%LOCALAPPDATA%\Microsoft\WinGet\Links`; set `UV_PYTHON_DOWNLOADS=never` (system Python 3.13).
