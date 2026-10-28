"""Request dependencies: database transactions and the authenticated user."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.api.errors import AppError
from labtrack.auth.tokens import AccessClaims, InvalidTokenError, decode_access_token
from labtrack.db.session import anonymous_transaction, get_sessionmaker, user_transaction
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
    return claims


async def user_db(
    claims: Annotated[AccessClaims, Depends(current_claims)],
) -> AsyncGenerator[AsyncSession]:
    """A transaction as the authenticated user (RLS applies)."""
    async with user_transaction(claims.user_id) as session:
        yield session


def client_ip(request: Request) -> str | None:
    # uvicorn rewrites request.client from X-Forwarded-For only for FORWARDED_ALLOW_IPS (Caddy).
    return request.client.host if request.client else None


Claims = Annotated[AccessClaims, Depends(current_claims)]
AnonymousDb = Annotated[AsyncSession, Depends(anonymous_db)]
UserDb = Annotated[AsyncSession, Depends(user_db)]
