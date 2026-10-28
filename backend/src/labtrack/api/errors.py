"""Domain errors -> `{code, message_key}` responses (CLAUDE.md "Хэв маяг").

Responses never contain exception text, values or names; clients translate `message_key`.
"""

from datetime import timedelta

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


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

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Field names only - pydantic's default body echoes the submitted values (passwords).
        fields = sorted({".".join(str(p) for p in e["loc"][1:]) for e in exc.errors()})
        return JSONResponse(
            status_code=422,
            content={"code": "validation", "message_key": "error.validation", "fields": fields},
        )
