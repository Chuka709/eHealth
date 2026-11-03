"""Domain errors -> `{code, message_key}` responses (CLAUDE.md "Хэв маяг").

Responses never contain exception text, values or names; clients translate `message_key`.
"""

from datetime import timedelta

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger(__name__)

# Errors raised by the framework itself (unparsable JSON body, unknown route, wrong method):
# they get the same `{code, message_key}` shape as ours instead of `{"detail": ...}`.
_FRAMEWORK_CODES = {
    400: "validation",
    401: "auth.required",
    403: "auth.forbidden",
    404: "not_found",
    405: "not_found",
}


class ErrorBody(BaseModel):
    code: str
    message_key: str


class AppError(Exception):
    def __init__(self, status: int, code: str, *, retry_after: timedelta | None = None) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.retry_after = retry_after


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = {}
        if exc.retry_after is not None:
            headers["Retry-After"] = str(max(1, int(exc.retry_after.total_seconds())))
        return JSONResponse(
            status_code=exc.status,
            content=ErrorBody(code=exc.code, message_key=f"error.{exc.code}").model_dump(),
            headers=headers,
        )

    @app.exception_handler(DBAPIError)
    async def _database(_: Request, exc: DBAPIError) -> JSONResponse:
        # Driver text can hold row values ("Failing row contains (...)"): only the SQLSTATE
        # is logged and nothing is returned.
        pg = getattr(exc.orig, "__cause__", None) or exc.orig
        log.error("db_error", sqlstate=getattr(pg, "sqlstate", None))
        return JSONResponse(
            status_code=500, content={"code": "internal", "message_key": "error.internal"}
        )

    @app.exception_handler(StarletteHTTPException)
    async def _framework(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _FRAMEWORK_CODES.get(exc.status_code, "internal")
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorBody(code=code, message_key=f"error.{code}").model_dump(),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Field names only - pydantic's default body echoes the submitted values (passwords).
        fields = sorted({".".join(str(p) for p in e["loc"][1:]) for e in exc.errors()})
        return JSONResponse(
            status_code=422,
            content={"code": "validation", "message_key": "error.validation", "fields": fields},
        )
