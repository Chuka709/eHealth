"""Deletions put back after a restore (OPS_RUNBOOK §5.6): the original time, sessions and
tokens ended, audited; nothing else touched; dry run writes nothing."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.admin.redelete import CANCELLED, REQUESTED, Event, Outcome, apply_events
from labtrack.db.sql import bound_text

from .conftest import make_user, scalar


async def _deleted_at(owner_engine: AsyncEngine, user: UUID) -> datetime | None:
    async with owner_engine.connect() as conn:
        value: datetime | None = await scalar(
            conn, bound_text("select deleted_at from users where id = :u"), {"u": user}
        )
        return value


async def _session(owner_engine: AsyncEngine, user: UUID) -> UUID:
    async with owner_engine.connect() as conn, conn.begin():
        sid: UUID = await scalar(
            conn,
            bound_text(
                "insert into sessions (user_id, family_id, token_hash, expires_at,"
                " family_expires_at) values (:u, gen_random_uuid(), :h, now() + interval '1 day',"
                " now() + interval '1 day') returning id"
            ),
            {"u": user, "h": uuid4().hex * 2},
        )
        return sid


async def test_dry_run_changes_nothing_then_apply_restores_the_request(
    owner_engine: AsyncEngine,
) -> None:
    user, other = await make_user(owner_engine), await make_user(owner_engine)
    sid = await _session(owner_engine, user)
    asked = datetime.now(UTC) - timedelta(days=3)
    events = {user: Event(user, REQUESTED, asked)}

    async with owner_engine.connect() as conn, conn.begin():
        assert await apply_events(conn, events, apply=False) == {user: Outcome.WOULD_REAPPLY}
    assert await _deleted_at(owner_engine, user) is None

    async with owner_engine.connect() as conn, conn.begin():
        assert await apply_events(conn, events, apply=True) == {user: Outcome.REAPPLIED}
    assert await _deleted_at(owner_engine, user) == asked  # the purge keeps its date
    assert await _deleted_at(owner_engine, other) is None
    async with owner_engine.connect() as conn:
        revoked = await scalar(
            conn, bound_text("select revoked_reason from sessions where id = :s"), {"s": sid}
        )
        audits = await scalar(
            conn,
            bound_text(
                "select count(*) from audit_logs where target_user_id = :u"
                " and action = 'account.deletion_reapplied' and actor_role = 'cli'"
            ),
            {"u": user},
        )
    assert revoked == "account_deletion"
    assert audits == 1

    async with owner_engine.connect() as conn, conn.begin():  # a second run: nothing new
        assert await apply_events(conn, events, apply=True) == {user: Outcome.ALREADY_PENDING}


async def test_cancelled_absent_and_admin_accounts_are_left_alone(
    owner_engine: AsyncEngine,
) -> None:
    user, admin = await make_user(owner_engine), await make_user(owner_engine, "super_admin")
    gone = uuid4()
    now = datetime.now(UTC)
    events = {
        user: Event(user, CANCELLED, now),
        admin: Event(admin, REQUESTED, now),
        gone: Event(gone, REQUESTED, now),
    }
    async with owner_engine.connect() as conn, conn.begin():
        outcomes = await apply_events(conn, events, apply=True)
    assert outcomes == {
        user: Outcome.CANCELLED,
        admin: Outcome.NOT_ELIGIBLE,
        gone: Outcome.ABSENT,
    }
    assert await _deleted_at(owner_engine, user) is None
    assert await _deleted_at(owner_engine, admin) is None


async def test_a_cancellation_whose_restored_row_still_waits_is_flagged(
    owner_engine: AsyncEngine,
) -> None:
    """Requested before the backup, cancelled after it: the restored row would be purged."""
    user = await make_user(owner_engine)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update users set deleted_at = now() - interval '40 days' where id = :u"),
            {"u": user},
        )
    events = {user: Event(user, CANCELLED, datetime.now(UTC))}
    async with owner_engine.connect() as conn, conn.begin():
        assert await apply_events(conn, events, apply=True) == {user: Outcome.CANCELLED_BUT_PENDING}
    assert await _deleted_at(owner_engine, user) is not None  # nothing decided for the operator
