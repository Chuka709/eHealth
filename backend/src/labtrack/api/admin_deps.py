"""Dependencies for /admin: network allowlist, the admin session and its transaction."""

import ipaddress
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Annotated, Final
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.admin.db import get_admin_login_sessionmaker, get_admin_sessionmaker
from labtrack.api.deps import client_ip
from labtrack.api.errors import AppError
from labtrack.config import get_settings
from labtrack.core.security import sha256_hex
from labtrack.db.sql import bound_text

_bearer = HTTPBearer(auto_error=False)

# Used only when ADMIN_ALLOWED_NETWORKS is unset in dev/test.
_DEV_NETWORKS: Final = tuple(
    ipaddress.ip_network(n)
    for n in ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "::1/128", "fc00::/7")
)


@dataclass(frozen=True)
class AdminContext:
    db: AsyncSession
    admin_id: UUID
    role: str
    session_token: str


async def require_admin_network(request: Request) -> None:
    """Caddy allowlists /admin too; this keeps the API closed if a proxy rule is missed."""
    settings = get_settings()
    allowed = settings.admin_allowed_networks
    networks = (
        tuple(allowed)
        if allowed is not None
        else _DEV_NETWORKS
        if settings.environment in {"dev", "test"}
        else ()
    )
    ip = client_ip(request)
    try:
        addr = ipaddress.ip_address(ip) if ip else None
    except ValueError:
        addr = None
    if addr is None or not any(addr in net for net in networks):
        raise AppError(404, "not_found")  # the admin surface does not exist from outside


async def admin_login_db() -> AsyncGenerator[AsyncSession]:
    """Sign-in only (role labtrack_admin_login)."""
    async with get_admin_login_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def admin_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AsyncGenerator[AdminContext]:
    """A transaction as the signed-in admin; the database validates the session itself."""
    if credentials is None:
        raise AppError(401, "admin.session_invalid")
    async with get_admin_sessionmaker()() as session:
        row = (
            await session.execute(
                bound_text("select * from admin_session_begin(:h)"),
                {"h": sha256_hex(credentials.credentials)},
            )
        ).one_or_none()
        if row is None:
            await session.commit()  # keep an idle/expired session's revocation
            raise AppError(401, "admin.session_invalid")
        try:
            yield AdminContext(session, row.admin_id, str(row.role), credentials.credentials)
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def super_admin(
    ctx: Annotated[AdminContext, Depends(admin_context, scope="function")],
) -> AdminContext:
    """Support staff may only unlock and reveal phones; everything else is super_admin.

    The database enforces the same split (admin_actor role lists); this gives a clean 403.
    """
    if ctx.role != "super_admin":
        raise AppError(403, "admin.forbidden")
    return ctx


AdminLoginDb = Annotated[AsyncSession, Depends(admin_login_db, scope="function")]
Admin = Annotated[AdminContext, Depends(admin_context, scope="function")]
SuperAdmin = Annotated[AdminContext, Depends(super_admin)]
