"""Admin context for DB-level tests.

Since 0006 every admin_* function needs the acting admin's live session, begun in the same
transaction with admin_session_begin(token_hash). Tests that call the functions directly
arrange the session row as the schema owner and begin it on the labtrack_admin connection; the
real path (password + TOTP -> admin_session_create) is tested in tests/api/test_admin_auth.py.
"""

import hashlib
import secrets
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from labtrack.db.sql import bound_text


async def open_admin_session(
    owner_engine: AsyncEngine, admin_id: UUID, ip: str | None = None
) -> str:
    """A live admin session; returns its token hash."""
    token_hash = hashlib.sha256(secrets.token_bytes(16)).hexdigest()
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into admin_sessions (admin_id, token_hash, ip, expires_at)"
                " values (:a, :h, cast(:ip as inet), now() + interval '8 hours')"
            ),
            {"a": admin_id, "h": token_hash, "ip": ip},
        )
    return token_hash


async def set_admin_context(conn: AsyncConnection, token_hash: str) -> None:
    """Begin the session in this transaction (on a labtrack_admin connection)."""
    await conn.execute(bound_text("select * from admin_session_begin(:h)"), {"h": token_hash})
