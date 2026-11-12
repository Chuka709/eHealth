from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from labtrack import __version__, consents
from labtrack.api import (
    admin,
    auth,
    caregivers,
    documents,
    emergency_card,
    health,
    health_records,
    lab_reports,
    me,
    patients,
    records,
)
from labtrack.api.errors import install_error_handlers
from labtrack.config import get_settings
from labtrack.documents.files import MAX_BYTES
from labtrack.logging import configure_logging
from labtrack.observability import init_sentry

# the 20 MB file plus the multipart envelope and the client_id field
UPLOAD_BODY_MAX = MAX_BYTES + 64 * 1024


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

    @app.middleware("http")
    async def _upload_size(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # A document upload is the one large body (Caddy allows it only there). Refused from
        # its declared length before anything parses it; Caddy caps a body that lies.
        if request.method == "POST" and request.url.path.endswith("/documents"):
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > UPLOAD_BODY_MAX:
                return JSONResponse(
                    status_code=413,
                    content={
                        "code": "document.too_large",
                        "message_key": "error.document.too_large",
                    },
                )
        return await call_next(request)

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(me.router, prefix=settings.api_prefix)
    app.include_router(patients.router, prefix=settings.api_prefix)
    app.include_router(records.router, prefix=settings.api_prefix)
    app.include_router(records.catalog_router, prefix=settings.api_prefix)
    app.include_router(health_records.router, prefix=settings.api_prefix)
    app.include_router(documents.router, prefix=settings.api_prefix)
    app.include_router(lab_reports.router, prefix=settings.api_prefix)
    app.include_router(emergency_card.router, prefix=settings.api_prefix)
    app.include_router(caregivers.router, prefix=settings.api_prefix)
    app.include_router(caregivers.me_router, prefix=settings.api_prefix)
    app.include_router(admin.router, prefix=settings.api_prefix)
    return app
