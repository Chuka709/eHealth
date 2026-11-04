from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from labtrack import __version__, consents
from labtrack.api import admin, auth, health, me, patients
from labtrack.api.errors import install_error_handlers
from labtrack.config import get_settings
from labtrack.logging import configure_logging
from labtrack.observability import init_sentry


def create_app() -> FastAPI:
    settings = get_settings()
    consents.assert_releasable(settings.environment)
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

    @app.middleware("http")
    async def _no_store(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Tokens, phone numbers and account lists must not sit in browser or proxy caches.
        response = await call_next(request)
        if request.url.path.startswith(f"{settings.api_prefix}/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(me.router, prefix=settings.api_prefix)
    app.include_router(patients.router, prefix=settings.api_prefix)
    app.include_router(admin.router, prefix=settings.api_prefix)
    return app
