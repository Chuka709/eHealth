"""Account deletions applied again after a restore from a backup (docs/OPS_RUNBOOK.md §5.6).

A restored database forgets every deletion requested after the backup was taken. The API logs
each request (`account_deletion_requested`, user id only) before it answers, and each admin
cancellation (`account_deletion_cancelled`); this reads those log lines, keeps each account's
last event since the backup, and puts the deletion back with its original time - so the 30-day
purge keeps its date (one older than 30 days is purged by the next daily run).

Runs as labtrack_owner (the migrate container), audited as actor 'cli'. Dry run unless asked to
apply. Prints ids and counts only (rule 3).
"""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from labtrack.db.sql import bound_text

REQUESTED = "account_deletion_requested"
CANCELLED = "account_deletion_cancelled"
# Each event comes from one logger only (a line another module wrote, or text a user typed
# that ended up inside a log line, never counts - security review 8.4 M2).
_LOGGER = {REQUESTED: "labtrack.api.me", CANCELLED: "labtrack.api.admin"}
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_PREFIX = r"(?:[\w.-]+\s+\|\s)?"  # `docker compose logs` without --no-log-prefix
# the console renderer (dev), the whole line: `2026-11-18T08:55:07.371026Z [info     ]
# account_deletion_requested     [labtrack.api.me] user_id=<uuid>`
_CONSOLE = re.compile(
    rf"^{_PREFIX}(?P<at>\d{{4}}-\d\d-\d\dT[0-9:.]+Z) \[info\s*\] "
    rf"(?P<event>{REQUESTED}|{CANCELLED})\s+\[(?P<logger>[\w.]+)\] user_id=(?P<uid>{_UUID})\s*$"
)
_JSON = re.compile(rf"^{_PREFIX}(?P<json>\{{.*\}})\s*$")
_FUTURE = timedelta(minutes=5)  # clock skew between hosts; later than that is not a real line


@dataclass(frozen=True)
class Event:
    user_id: UUID
    kind: str  # REQUESTED or CANCELLED
    at: datetime


class Outcome(StrEnum):
    REAPPLIED = "reapplied"
    WOULD_REAPPLY = "would_reapply"  # dry run
    ALREADY_PENDING = "already_pending"
    ABSENT = "absent"  # not in the restored database: made after the backup, or purged
    CANCELLED = "cancelled"  # an admin cancelled it after the request; nothing pending now
    # cancelled after the backup, but the restored row still waits for the purge: an operator
    # decides before the maintenance worker runs (security review 8.4 M1)
    CANCELLED_BUT_PENDING = "cancelled_but_pending"
    NOT_ELIGIBLE = "not_eligible"  # an admin account (deletion is for users and doctors)


def _parse_at(value: str) -> datetime | None:
    try:
        at = datetime.fromisoformat(value)
    except ValueError:
        return None
    return at if at.tzinfo else None  # the logs are UTC with a zone; a bare time is not ours


def _event(kind: object, logger: object, uid: object, at: object) -> Event | None:
    if not isinstance(kind, str) or _LOGGER.get(kind) != logger or not isinstance(uid, str):
        return None
    when = _parse_at(at) if isinstance(at, str) else None
    try:
        user_id = UUID(uid)
    except ValueError:
        return None
    return Event(user_id, kind, when) if when else None


def parse_line(line: str) -> Event | None:
    """One whole log line: JSON (production) or the console renderer (dev), with an optional
    `docker compose logs` prefix. None unless it is a deletion event from its own logger."""
    text = _ANSI.sub("", line).rstrip("\r\n")
    m = _JSON.match(text)
    if m:
        try:
            record = json.loads(m["json"])
        except ValueError:
            return None  # a broken or split JSON line is skipped, never read as console text
        if not isinstance(record, dict) or record.get("level") != "info":
            return None
        return _event(
            record.get("event"),
            record.get("logger"),
            record.get("user_id"),
            record.get("timestamp"),
        )
    m = _CONSOLE.match(text)
    return _event(m["event"], m["logger"], m["uid"], m["at"]) if m else None


def latest_events(
    lines: Iterable[str], since: datetime, now: datetime | None = None
) -> dict[UUID, Event]:
    """Each account's last deletion event between `since` (the backup's time) and now."""
    latest = (now or datetime.now(UTC)) + _FUTURE
    last: dict[UUID, Event] = {}
    for line in lines:
        event = parse_line(line)
        if event is None or not since <= event.at <= latest:
            continue
        seen = last.get(event.user_id)
        if seen is None or event.at >= seen.at:
            last[event.user_id] = event
    return last


async def _apply_one(conn: AsyncConnection, event: Event, *, apply: bool) -> Outcome:
    row = (
        await conn.execute(
            bound_text("select role::text, deleted_at from users where id = :u for update"),
            {"u": event.user_id},
        )
    ).one_or_none()
    if row is None:
        return Outcome.ABSENT
    role, deleted_at = row
    if event.kind == CANCELLED:
        return Outcome.CANCELLED if deleted_at is None else Outcome.CANCELLED_BUT_PENDING
    if role not in ("user", "doctor"):
        return Outcome.NOT_ELIGIBLE
    if deleted_at is not None:
        return Outcome.ALREADY_PENDING
    if not apply:
        return Outcome.WOULD_REAPPLY
    # as request_account_deletion() (0008, 0011), with the original time and any status
    await conn.execute(
        bound_text("update users set deleted_at = :at where id = :u"),
        {"at": event.at, "u": event.user_id},
    )
    await conn.execute(
        bound_text("select revoke_user_sessions(:u, 'account_deletion')"), {"u": event.user_id}
    )
    await conn.execute(
        bound_text(
            "update activation_tokens set revoked_at = now()"
            " where user_id = :u and used_at is null and revoked_at is null"
        ),
        {"u": event.user_id},
    )
    await conn.execute(
        bound_text(
            "insert into audit_logs (actor_role, action, target_user_id, entity, entity_id)"
            " values ('cli', 'account.deletion_reapplied', :u, 'user', :eid)"
        ),
        {"u": event.user_id, "eid": str(event.user_id)},
    )
    return Outcome.REAPPLIED


async def reapply_deletions(
    url: str, events: dict[UUID, Event], *, apply: bool
) -> dict[UUID, Outcome]:
    """One transaction for all: a failure leaves the restored database as it was."""
    engine = create_async_engine(url, hide_parameters=True)
    try:
        async with engine.connect() as conn, conn.begin():
            return await apply_events(conn, events, apply=apply)
    finally:
        await engine.dispose()


async def apply_events(
    conn: AsyncConnection, events: dict[UUID, Event], *, apply: bool
) -> dict[UUID, Outcome]:
    return {
        uid: await _apply_one(conn, events[uid], apply=apply) for uid in sorted(events, key=str)
    }
