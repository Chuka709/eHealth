"""The RLS user context must never leak between transactions on a pooled connection."""

import os
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from labtrack.db.sql import bound_text

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif("TEST_DATABASE_URL" not in os.environ, reason="needs compose test DB"),
]

_SET = bound_text("select set_config('app.user_id', :uid, true)")
_GET = bound_text("select nullif(current_setting('app.user_id', true), '')")


async def test_user_id_is_transaction_scoped_on_a_single_pooled_connection() -> None:
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"], pool_size=1, max_overflow=0)
    uid = str(uuid4())
    try:
        async with engine.connect() as conn:
            async with conn.begin():
                await conn.execute(_SET, {"uid": uid})
                assert (await conn.execute(_GET)).scalar_one() == uid
            async with conn.begin():
                assert (await conn.execute(_GET)).scalar_one() is None
        async with engine.connect() as conn, conn.begin():
            assert (await conn.execute(_GET)).scalar_one() is None
    finally:
        await engine.dispose()


async def test_runtime_role_cannot_create_temp_tables() -> None:
    """Blocks pg_temp shadowing of tables used by security definer functions."""
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    try:
        async with engine.connect() as conn:
            with pytest.raises(Exception, match="permission denied"):
                await conn.execute(bound_text("create temp table t_shadow (x int)"))
    finally:
        await engine.dispose()
