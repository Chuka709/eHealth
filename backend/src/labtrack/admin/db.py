"""Database access for the admin API: a separate engine as `labtrack_admin`.

That role can read account metadata and execute the admin_* functions - nothing else: no table
writes, no patient tables, no secret columns, no sign-in (a separate `labtrack_admin_login`
engine serves only POST /admin/auth/login). Each admin request opens its transaction with
admin_session_begin(), which validates the admin's session and sets `app.user_id` and
`app.admin_sid`; every admin_* function checks both (migration 0006).
"""

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from labtrack.config import get_settings


def _engine(url: object, name: str) -> AsyncEngine:
    if url is None:
        raise RuntimeError(f"{name} is not set")
    return create_async_engine(
        str(url),
        pool_pre_ping=True,
        pool_reset_on_return="rollback",
        hide_parameters=True,  # national ids, phone ciphertexts, token hashes
        pool_size=2,
        max_overflow=3,
    )


@lru_cache
def get_admin_sessionmaker() -> async_sessionmaker[AsyncSession]:
    engine = _engine(get_settings().admin_database_url, "ADMIN_DATABASE_URL")
    return async_sessionmaker(engine, expire_on_commit=False)


@lru_cache
def get_admin_login_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Sign-in only (labtrack_admin_login): admin password hashes and session creation."""
    engine = _engine(get_settings().admin_login_database_url, "ADMIN_LOGIN_DATABASE_URL")
    return async_sessionmaker(engine, expire_on_commit=False)
