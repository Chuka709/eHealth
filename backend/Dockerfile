# syntax=docker/dockerfile:1.7
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    VIRTUAL_ENV=/app/.venv PATH="/app/.venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
# libmagic: file type from content, never from the name (Phase 3.2, python-magic)
# Pango + HarfBuzz and Noto Sans (Mongolian Cyrillic Ө, Ү): WeasyPrint's "Эмчид үзүүлэх" PDF (7.5)
RUN apt-get update && apt-get install -y --no-install-recommends libmagic1 \
        libpango-1.0-0 libpangoft2-1.0-0 fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 app
WORKDIR /app

# Production-like image: runtime deps only
FROM base AS runtime
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev
USER app
EXPOSE 8000
CMD ["uvicorn", "labtrack.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]

# Dev/test image: + dev deps; src and tests are bind-mounted by compose
FROM base AS dev
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src
COPY tests ./tests
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen
USER app
EXPOSE 8000
CMD ["uvicorn", "labtrack.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/src", "--no-access-log"]
