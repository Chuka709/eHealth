"""/auth endpoints (docs/04 §1). There is no self-registration and no password recovery code:
accounts are created by an admin and activated with a one-time token."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from labtrack.api.deps import AnonymousDb, Claims, UserDb, client_ip, presented_credentials
from labtrack.api.errors import AppError, ErrorBody
from labtrack.api.ratelimit import per_ip
from labtrack.auth import service
from labtrack.config import get_settings
from labtrack.core.text import clean_device_label
from labtrack.db.sql import bound_text

router = APIRouter(prefix="/auth", tags=["auth"])

Username = Annotated[str, StringConstraints(pattern=r"^[a-z0-9._]{3,32}$", to_lower=True)]
Password = Annotated[str, StringConstraints(min_length=1, max_length=128)]
OpaqueToken = Annotated[str, StringConstraints(min_length=20, max_length=200)]

_ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorBody},
    401: {"model": ErrorBody},
    422: {"model": ErrorBody},
    429: {"model": ErrorBody},
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(_Strict):
    username: Username
    password: Password
    device_name: Annotated[
        str | None, StringConstraints(max_length=200), AfterValidator(clean_device_label)
    ] = None
    platform: Literal["ios", "android", "web"]
    device_token: OpaqueToken | None = None


class RefreshRequest(_Strict):
    refresh_token: OpaqueToken


class ActivateRequest(_Strict):
    token: OpaqueToken
    # From the user's sign-in card: the token alone does not activate (an SMS link may be
    # caught by another app claiming the labtrack:// scheme).
    username: Username
    new_password: Password


class ChangePasswordRequest(_Strict):
    current_password: Password
    new_password: Password
    sign_out_other_devices: bool = True
    # This phone's trusted-device token: it keeps its trust, every other device loses it.
    device_token: OpaqueToken | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth token type, not a secret
    expires_in: int
    refresh_token: str
    device_token: str | None = Field(
        default=None, description="Returned once when this device becomes trusted; store securely."
    )


class SessionOut(BaseModel):
    id: UUID
    device_name: str | None
    platform: str | None
    created_at: datetime
    last_used_at: datetime | None
    current: bool


def _tokens(pair: service.TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        expires_in=pair.expires_in,
        refresh_token=pair.refresh_token,
        device_token=pair.device_token,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    responses=_ERRORS,
    dependencies=[Depends(per_ip("login", lambda: get_settings().rate_login_per_minute))],
)
async def login(body: LoginRequest, request: Request, db: AnonymousDb) -> TokenResponse:
    pair = await service.login(
        db,
        username=body.username,
        password=body.password,
        device_name=body.device_name,
        platform=body.platform,
        device_token=body.device_token,
        ip=client_ip(request),
    )
    return _tokens(pair)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses=_ERRORS,
    dependencies=[Depends(per_ip("refresh", lambda: get_settings().rate_refresh_per_minute))],
)
async def refresh(body: RefreshRequest, db: AnonymousDb) -> TokenResponse:
    return _tokens(await service.refresh(db, refresh_token=body.refresh_token))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, db: AnonymousDb) -> Response:
    await service.logout(db, refresh_token=body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/activate",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ERRORS,
    dependencies=[Depends(per_ip("activate", lambda: get_settings().rate_activate_per_minute))],
)
async def activate(body: ActivateRequest, request: Request, db: AnonymousDb) -> Response:
    """Set the account's password with a one-time activation/reset token, then log in."""
    await service.activate(
        db,
        token=body.token,
        username=body.username,
        new_password=body.new_password,
        ip=client_ip(request),
        # The app sends no credentials here; a live admin session among them means the
        # issuing admin is using the token (docs/04 §6.1) and it is refused.
        presented=presented_credentials(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def change_password(body: ChangePasswordRequest, claims: Claims, db: UserDb) -> Response:
    me_row = (
        await db.execute(
            bound_text("select username, display_name from users where id = app_user_id()")
        )
    ).one()
    await service.change_password(
        db,
        username=me_row.username,
        display_name=me_row.display_name,
        current_password=body.current_password,
        new_password=body.new_password,
        current_session=claims.session_id,
        sign_out_other_devices=body.sign_out_other_devices,
        device_token=body.device_token,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions", response_model=list[SessionOut], responses=_ERRORS)
async def sessions(claims: Claims, db: UserDb) -> list[SessionOut]:
    rows = await db.execute(
        bound_text(
            "select id, device_name, platform, created_at, last_used_at from sessions"
            " where revoked_at is null and expires_at > now() order by created_at desc"
        )
    )
    return [SessionOut(**r._mapping, current=r.id == claims.session_id) for r in rows]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def revoke_session(session_id: UUID, claims: Claims, db: UserDb) -> Response:
    revoked = (
        await db.execute(
            bound_text("select revoke_my_session(:s, 'user_revoke')"), {"s": session_id}
        )
    ).scalar_one_or_none()
    if not revoked:
        raise AppError(404, "auth.session_not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
