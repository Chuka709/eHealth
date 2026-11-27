"""/admin endpoints (docs/04 §1 "Супер админ", §6). Role labtrack_admin only; every change goes
through the database's admin_* functions, which check the acting admin and their session."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from labtrack.admin import auth as admin_auth
from labtrack.admin import csv_import, users
from labtrack.api.admin_deps import Admin, AdminLoginDb, SuperAdmin, require_admin_network
from labtrack.api.deps import client_ip
from labtrack.api.errors import AppError, ErrorBody
from labtrack.api.ratelimit import per_ip
from labtrack.config import get_settings
from labtrack.core.text import valid_display_name
from labtrack.sms import SmsSender, get_sms_sender

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin_network)])

Username = Annotated[str, StringConstraints(pattern=r"^[a-z0-9._]{3,32}$", to_lower=True)]
Password = Annotated[str, StringConstraints(min_length=1, max_length=128)]
TotpCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]

ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorBody},
    401: {"model": ErrorBody},
    403: {"model": ErrorBody},
    404: {"model": ErrorBody},
    409: {"model": ErrorBody},
    422: {"model": ErrorBody},
    429: {"model": ErrorBody},
}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdminLoginRequest(Strict):
    username: Username
    password: Password
    totp_code: TotpCode


class AdminSessionOut(BaseModel):
    session_token: str
    expires_at: datetime


class AdminMeOut(BaseModel):
    admin_id: UUID
    role: str


@router.post(
    "/auth/login",
    response_model=AdminSessionOut,
    responses=ERRORS,
    dependencies=[
        Depends(per_ip("admin_login", lambda: get_settings().rate_admin_login_per_minute))
    ],
)
async def login(body: AdminLoginRequest, request: Request, db: AdminLoginDb) -> AdminSessionOut:
    result = await admin_auth.login(
        db,
        username=body.username,
        password=body.password,
        totp_code=body.totp_code,
        ip=client_ip(request),
    )
    return AdminSessionOut(session_token=result.session_token, expires_at=result.expires_at)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT, responses=ERRORS)
async def logout(ctx: Admin) -> Response:
    await admin_auth.logout(ctx.db, session_token=ctx.session_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/auth/me", response_model=AdminMeOut, responses=ERRORS)
async def me(ctx: Admin) -> AdminMeOut:
    return AdminMeOut(admin_id=ctx.admin_id, role=ctx.role)


# --- users (docs/04 §1) -----------------------------------------------------------------------


def _display_name(value: str) -> str:
    if not valid_display_name(value):
        raise ValueError("display_name")
    return value


DisplayName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    AfterValidator(_display_name),
]
# Mongolian national id (РД): two Cyrillic letters + 8 digits; compared case-insensitively.
NationalId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[А-ЯӨҮЁа-яөүё]{2}[0-9]{8}$"),
]
StatusReason = Literal[
    "user_request", "identity_verified", "suspected_compromise", "left_program", "other"
]
ResetReason = Literal["forgot_password", "lost_device", "suspected_compromise", "other"]


def _phone(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return users.normalise_phone(value)
    except ValueError as exc:
        raise AppError(422, "admin.invalid_phone") from exc


class CreateUserRequest(Strict):
    username: Username
    display_name: DisplayName
    role: Literal["user", "doctor"] = "user"
    phone: Annotated[str, StringConstraints(max_length=20)] | None = None
    national_id: NationalId | None = None


class CreatedOut(BaseModel):
    id: UUID


class UserOut(BaseModel):
    id: UUID
    username: str
    display_name: str
    role: str
    account_status: str
    phone_last4: str | None
    created_at: datetime
    deletion_scheduled_for: datetime | None


class UserListOut(BaseModel):
    items: list[UserOut]
    next_after: str | None


class LiveTokenOut(BaseModel):
    purpose: str
    channel: str
    expires_at: datetime


class UserDetailOut(UserOut):
    live_token: LiveTokenOut | None
    active_sessions: int
    identity_checks_today: int


class StatusRequest(Strict):
    status: Literal["active", "locked", "disabled"]
    reason: StatusReason


class NationalIdRequest(Strict):
    national_id: NationalId


class IdentityCheckOut(BaseModel):
    check_id: int
    match: bool


class TokenRequest(Strict):
    purpose: Literal["activation", "admin_reset"]
    channel: Literal["in_person_qr", "sms"]
    identity_check_id: int | None = None
    reason: ResetReason | None = None


class CancelDeletionRequest(Strict):
    reason: Literal["user_request", "suspected_compromise", "other"]


class TokenOut(BaseModel):
    expires_at: datetime
    # in-person QR only: shown once on the admin's screen as a QR code
    link: str | None
    # False: the user got no SMS (link or reset notice) - tell them another way
    notice_sent: bool


class PhoneOut(BaseModel):
    phone: str | None


class SecurityEventOut(BaseModel):
    id: int
    at: datetime
    action: str
    actor_id: UUID | None
    target_user_id: UUID | None
    details: dict[str, object]


def _user_out(row: users.UserRow) -> UserOut:
    return UserOut(
        id=row.id,
        username=row.username,
        display_name=row.display_name,
        role=row.role,
        account_status=row.account_status,
        phone_last4=row.phone_last4,
        created_at=row.created_at,
        deletion_scheduled_for=row.deletion_scheduled_for,
    )


@router.post("/users", status_code=201, response_model=CreatedOut, responses=ERRORS)
async def create_user(body: CreateUserRequest, ctx: SuperAdmin) -> CreatedOut:
    uid = await users.create_user(
        ctx.db,
        username=body.username,
        display_name=body.display_name,
        role=body.role,
        phone=_phone(body.phone),
        national_id=body.national_id,
    )
    return CreatedOut(id=uid)


@router.get("/users", response_model=UserListOut, responses=ERRORS)
async def search_users(
    ctx: Admin,
    *,
    q: Annotated[str | None, Query(max_length=64)] = None,
    status: Literal["pending_activation", "active", "locked", "disabled"] | None = None,
    after: Annotated[str | None, Query(max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    deletion_pending: bool = False,
) -> UserListOut:
    rows = await users.search_users(
        ctx.db,
        query=q,
        status=status,
        after=after,
        limit=limit,
        deletion_pending=deletion_pending,
    )
    return UserListOut(
        items=[_user_out(r) for r in rows],
        next_after=rows[-1].username if len(rows) == limit else None,
    )


@router.get("/users/{user_id}", response_model=UserDetailOut, responses=ERRORS)
async def get_user(user_id: UUID, ctx: Admin) -> UserDetailOut:
    detail = await users.get_user(ctx.db, user_id)
    token = detail.live_token
    return UserDetailOut(
        **_user_out(detail.user).model_dump(),
        live_token=LiveTokenOut(purpose=token[0], channel=token[1], expires_at=token[2])
        if token
        else None,
        active_sessions=detail.active_sessions,
        identity_checks_today=detail.identity_checks_today,
    )


@router.post("/users/{user_id}/status", status_code=204, responses=ERRORS)
async def set_status(user_id: UUID, body: StatusRequest, ctx: Admin) -> Response:
    """Support may only unlock (locked -> active); the database enforces it."""
    await users.set_status(ctx.db, user_id, body.status, body.reason)
    return Response(status_code=204)


@router.post("/users/{user_id}/unlock-login", status_code=204, responses=ERRORS)
async def clear_lockout(user_id: UUID, ctx: Admin) -> Response:
    """Clears the failed-login lockout counters (the account status is unchanged)."""
    await users.clear_lockout(ctx.db, user_id)
    return Response(status_code=204)


@router.post("/users/{user_id}/identity-check", response_model=IdentityCheckOut, responses=ERRORS)
async def identity_check(
    user_id: UUID, body: NationalIdRequest, ctx: SuperAdmin
) -> IdentityCheckOut:
    """Yes/no only, computed by the database; 5 per user and 50 per admin a day."""
    check_id, match = await users.identity_check(ctx.db, user_id, body.national_id)
    return IdentityCheckOut(check_id=check_id, match=match)


@router.put("/users/{user_id}/identity", status_code=204, responses=ERRORS)
async def set_identity(user_id: UUID, body: NationalIdRequest, ctx: SuperAdmin) -> Response:
    """In person, from the ID card; only when none is stored (CSV accounts, doctors)."""
    await users.set_identity(ctx.db, user_id, body.national_id)
    return Response(status_code=204)


@router.post("/users/{user_id}/tokens", response_model=TokenOut, responses=ERRORS)
async def issue_token(
    user_id: UUID,
    body: TokenRequest,
    request: Request,
    ctx: SuperAdmin,
    sms: Annotated[SmsSender, Depends(get_sms_sender)],
) -> TokenOut:
    issued = await users.issue_token(
        ctx.db,
        sms,
        user_id=user_id,
        purpose=body.purpose,
        channel=body.channel,
        identity_check_id=body.identity_check_id,
        reason=body.reason,
        admin_ip=client_ip(request),
    )
    return TokenOut(expires_at=issued.expires_at, link=issued.link, notice_sent=issued.notice_sent)


@router.post("/users/{user_id}/cancel-deletion", status_code=204, responses=ERRORS)
async def cancel_deletion(user_id: UUID, body: CancelDeletionRequest, ctx: SuperAdmin) -> Response:
    """Within 30 days of the user's request. The account comes back locked and needs a reset
    (identity check + new password): cancelling never hands it to whoever asked."""
    await users.cancel_deletion(ctx.db, user_id, body.reason)
    # beside the request's log line: a restore from an older backup reads both (OPS_RUNBOOK §5.6)
    log.info("account_deletion_cancelled", user_id=str(user_id))
    return Response(status_code=204)


@router.post("/users/{user_id}/phone", response_model=PhoneOut, responses=ERRORS)
async def reveal_phone(user_id: UUID, ctx: Admin) -> PhoneOut:
    """The full registered number, for the call-back step; every reveal is audited."""
    return PhoneOut(phone=await users.reveal_phone(ctx.db, user_id))


@router.get("/security-events", response_model=list[SecurityEventOut], responses=ERRORS)
async def security_events(
    ctx: SuperAdmin, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[SecurityEventOut]:
    return [
        SecurityEventOut(
            id=e.id,
            at=e.at,
            action=e.action,
            actor_id=e.actor_id,
            target_user_id=e.target_user_id,
            details=e.details,
        )
        for e in await users.security_events(ctx.db, limit)
    ]


# --- CSV import (docs/04 §1): in memory only; preview, then commit the same file --------------


class ImportProblemOut(BaseModel):
    row: int  # 0 = the whole file
    field: str


class ImportPreviewRowOut(BaseModel):
    row: int
    username: str
    display_name: str
    role: str
    phone_last4: str | None


class ImportPreviewOut(BaseModel):
    sha256: str
    rows: list[ImportPreviewRowOut]
    problems: list[ImportProblemOut]


class ImportResultOut(BaseModel):
    created: int


_CSV_BODY = {
    "requestBody": {"required": True, "content": {"text/csv": {"schema": {"type": "string"}}}}
}


async def _csv_body(request: Request) -> bytes:
    """Read before the admin transaction opens (declared first), so a slow upload holds no
    database connection or session lock."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > csv_import.MAX_BYTES:
        raise AppError(413, "admin.import_too_large")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > csv_import.MAX_BYTES:
            raise AppError(413, "admin.import_too_large")
    return bytes(data)


CsvBody = Annotated[bytes, Depends(_csv_body)]


def _problems(problems: list[csv_import.Problem]) -> list[ImportProblemOut]:
    return [ImportProblemOut(row=p.line, field=p.field) for p in problems]


@router.post(
    "/users/import/preview",
    response_model=ImportPreviewOut,
    responses=ERRORS,
    openapi_extra=_CSV_BODY,
)
async def import_preview(body: CsvBody, ctx: SuperAdmin) -> ImportPreviewOut:
    """Validate a CSV without creating anything. Errors name the row and field, not the value."""
    del ctx  # authorisation only
    parsed = csv_import.parse(body)
    return ImportPreviewOut(
        sha256=parsed.sha256,
        rows=[
            ImportPreviewRowOut(
                row=r.line,
                username=r.username,
                display_name=r.display_name,
                role=r.role,
                phone_last4=r.phone[-4:] if r.phone else None,
            )
            for r in parsed.rows
        ],
        problems=_problems(parsed.problems),
    )


@router.post(
    "/users/import",
    response_model=ImportResultOut,
    responses={**ERRORS, 413: {"model": ErrorBody}},
    openapi_extra=_CSV_BODY,
)
async def import_commit(
    body: CsvBody,
    ctx: SuperAdmin,
    sha256: Annotated[str, Query(pattern=r"^[0-9a-f]{64}$")],
) -> ImportResultOut | JSONResponse:
    """Create every row as `pending_activation` (no password), all or none.

    `sha256` from the preview makes sure the admin commits exactly the file they reviewed.
    """
    parsed = csv_import.parse(body)
    if parsed.sha256 != sha256:
        raise AppError(409, "admin.import_changed")
    problems = await users.import_users(ctx.db, parsed)
    if problems:
        return JSONResponse(
            status_code=422,
            content={
                "code": "admin.import_invalid",
                "message_key": "error.admin.import_invalid",
                "problems": [p.model_dump() for p in _problems(problems)],
            },
        )
    return ImportResultOut(created=len(parsed.rows))
