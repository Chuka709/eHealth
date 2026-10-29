"""Request dependencies: database transactions and the authenticated user."""

import ipaddress
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.api.errors import AppError
from labtrack.auth.tokens import AccessClaims, InvalidTokenError, decode_access_token
from labtrack.db.session import anonymous_transaction, get_sessionmaker
from labtrack.db.sql import bound_text

_bearer = HTTPBearer(auto_error=False)


async def anonymous_db() -> AsyncGenerator[AsyncSession]:
    """No user context: only the auth definer functions are usable.

    Commits on success and rolls back on error; a service may commit earlier on purpose
    (e.g. to keep a failed login attempt before raising).
    """
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def current_claims(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AccessClaims:
    if credentials is None:
        raise AppError(401, "auth.required")
    try:
        claims = decode_access_token(credentials.credentials)
    except InvalidTokenError as exc:
        raise AppError(401, "auth.session_invalid") from exc
    # The JWT is not enough: the session must still exist and the account be active with the
    # same token_version (logout, admin reset and disabling apply immediately).
    async with anonymous_transaction() as session:
        alive = (
            await session.execute(
                bound_text("select session_check(:s, :u, :tv)"),
                {"s": claims.session_id, "u": claims.user_id, "tv": claims.token_version},
            )
        ).scalar_one()
    if not alive:
        raise AppError(401, "auth.session_invalid")
    # Admins never get a user session (0006); should one appear, it must not reach user or
    # patient routes (CLAUDE.md 2a).
    if claims.role not in {"user", "doctor"}:
        raise AppError(403, "auth.forbidden")
    return claims


async def user_db(
    claims: Annotated[AccessClaims, Depends(current_claims)],
) -> AsyncGenerator[AsyncSession]:
    """A transaction as the authenticated user (RLS applies).

    Same commit/rollback contract as anonymous_db; a service that commits early (to keep a
    failed attempt) ends the user context with that transaction, so it must raise right after.
    """
    async with get_sessionmaker()() as session:
        try:
            await session.execute(
                bound_text("select set_config('app.user_id', :uid, true)"),
                {"uid": str(claims.user_id)},
            )
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


def client_ip(request: Request) -> str | None:
    """The client address, or None if it is not an IP (it is cast to inet in SQL)."""
    # uvicorn rewrites request.client from X-Forwarded-For only for FORWARDED_ALLOW_IPS (Caddy).
    host = request.client.host if request.client else None
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


# The admin web (BFF) keeps the admin session in this httpOnly cookie and sends it to the
# admin API as a bearer token.
ADMIN_SESSION_COOKIE = "__Host-labtrack_admin"


def presented_credentials(request: Request) -> list[str]:
    """Bearer token and admin cookie values on a request (checked against admin sessions)."""
    values = []
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        values.append(auth[7:].strip())
    if cookie := request.cookies.get(ADMIN_SESSION_COOKIE):
        values.append(cookie)
    return [v for v in values if 0 < len(v) <= 512]  # noqa: PLR2004


Claims = Annotated[AccessClaims, Depends(current_claims)]
# scope="function": the transaction commits when the endpoint returns, before the response is
# sent. With the default ("request") the client could receive a new session or refresh token
# and use it before the row that backs it is committed.
AnonymousDb = Annotated[AsyncSession, Depends(anonymous_db, scope="function")]
UserDb = Annotated[AsyncSession, Depends(user_db, scope="function")]
