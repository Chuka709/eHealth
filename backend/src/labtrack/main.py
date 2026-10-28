from fastapi import FastAPI

from labtrack import __version__
from labtrack.api import health
from labtrack.config import get_settings
from labtrack.logging import configure_logging
from labtrack.observability import init_sentry


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(json=settings.environment != "dev")
    init_sentry(settings)
    app = FastAPI(
        title="LabTrack MN API",
        version=__version__,
        openapi_url=f"{settings.api_prefix}/openapi.json",
        docs_url=f"{settings.api_prefix}/docs" if settings.environment == "dev" else None,
        redoc_url=None,
    )
    app.include_router(health.router, prefix=settings.api_prefix)
    return app
