import sentry_sdk
from fastapi import FastAPI

from labtrack import __version__
from labtrack.api import health
from labtrack.config import get_settings
from labtrack.logging import configure_logging


def _init_sentry() -> None:
    settings = get_settings()
    if settings.sentry_dsn is None:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.environment,
        release=__version__,
        send_default_pii=False,  # PHI never leaves the server via Sentry
        include_local_variables=False,
        max_request_body_size="never",
    )


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(json=settings.environment != "dev")
    _init_sentry()
    app = FastAPI(
        title="LabTrack MN API",
        version=__version__,
        openapi_url=f"{settings.api_prefix}/openapi.json",
        docs_url=f"{settings.api_prefix}/docs" if settings.environment == "dev" else None,
        redoc_url=None,
    )
    app.include_router(health.router, prefix=settings.api_prefix)
    return app
