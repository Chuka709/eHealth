from fastapi import FastAPI

from labtrack import __version__
from labtrack.api import auth, health
from labtrack.api.errors import install_error_handlers
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
        # Schema and docs only in dev/test; `just gen-client` builds the schema without HTTP.
        openapi_url=f"{settings.api_prefix}/openapi.json"
        if settings.environment in {"dev", "test"}
        else None,
        docs_url=f"{settings.api_prefix}/docs" if settings.environment == "dev" else None,
        redoc_url=None,
    )
    install_error_handlers(app)
    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    return app
