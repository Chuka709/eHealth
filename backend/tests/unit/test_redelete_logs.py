"""Reading deletion events from API logs after a restore (docs/OPS_RUNBOOK.md §5.6)."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from labtrack.admin.redelete import CANCELLED, REQUESTED, latest_events, parse_line

BACKUP = datetime(2026, 11, 18, 6, 0, tzinfo=UTC)
NOW = datetime(2026, 11, 19, 6, 0, tzinfo=UTC)
LOGGER = {REQUESTED: "labtrack.api.me", CANCELLED: "labtrack.api.admin"}


def _json(event: str, uid: str, at: str, prefix: str = "", **over: str) -> str:
    record = {"event": event, "user_id": uid, "timestamp": at, "level": "info",
              "logger": LOGGER.get(event, "labtrack.api.me"), **over}  # fmt: skip
    return prefix + json.dumps(record)


def _console(event: str, uid: str, logger: str) -> str:
    return (
        "\x1b[2m2026-11-18T08:55:07.371026Z\x1b[0m [\x1b[32minfo     \x1b[0m] "
        f"\x1b[1m{event}      \x1b[0m [\x1b[34m{logger}\x1b[0m] user_id={uid}"
    )


def test_a_json_line_from_production() -> None:
    uid = str(uuid4())
    event = parse_line(_json(REQUESTED, uid, "2026-11-18T07:00:00.123Z"))
    assert event is not None
    assert (str(event.user_id), event.kind) == (uid, REQUESTED)
    assert event.at == datetime(2026, 11, 18, 7, 0, 0, 123000, tzinfo=UTC)


def test_a_compose_prefix_and_console_colours() -> None:
    uid = str(uuid4())
    assert parse_line(_json(REQUESTED, uid, "2026-11-18T07:00:00Z", "api-1  | ")) is not None
    event = parse_line(_console(REQUESTED, uid, "labtrack.api.me"))
    assert event is not None
    assert str(event.user_id) == uid
    assert parse_line(_console(CANCELLED, uid, "labtrack.api.admin")) is not None


def test_other_lines_and_broken_values_are_ignored() -> None:
    uid = str(uuid4())
    assert parse_line(_json("login_failed", uid, "2026-11-18T07:00:00Z")) is None
    assert parse_line(_json(REQUESTED, "not-an-id", "2026-11-18T07:00:00Z")) is None
    assert parse_line(_json(REQUESTED, uid, "yesterday")) is None
    assert parse_line(_json(REQUESTED, uid, "2026-11-18T07:00:00")) is None  # no zone
    assert parse_line(_json(REQUESTED, uid, "2026-11-18T07:00:00Z", level="warning")) is None
    assert parse_line("{broken json") is None
    assert parse_line("") is None


def test_a_forged_event_inside_another_line_does_not_count() -> None:
    uid = str(uuid4())
    # another module (or text a user typed) logging the event's name and an id
    assert parse_line(_json(REQUESTED, uid, "2026-11-18T07:00:00Z", logger="uvicorn")) is None
    assert (
        parse_line(_json(CANCELLED, uid, "2026-11-18T07:00:00Z", logger="labtrack.api.me")) is None
    )
    assert parse_line(_console(REQUESTED, uid, "labtrack.worker")) is None
    inside = f"GET /x?q=2026-11-18T08:55:07Z [info ] {REQUESTED} [labtrack.api.me] user_id={uid}"
    assert parse_line(inside) is None
    # a split or broken JSON line is never read as console text
    broken = '{"event":"request","path":"' + _console(REQUESTED, uid, "labtrack.api.me")
    assert parse_line(broken) is None


def test_the_last_event_between_the_backup_and_now_wins() -> None:
    a, b, old, future = (str(uuid4()) for _ in range(4))
    lines = [
        _json(REQUESTED, old, "2026-11-17T23:00:00Z"),  # before the backup: in it already
        _json(REQUESTED, a, "2026-11-18T07:00:00Z"),
        _json(CANCELLED, a, "2026-11-18T09:00:00Z"),
        _json(CANCELLED, b, "2026-11-18T07:00:00Z"),
        _json(REQUESTED, b, "2026-11-18T10:00:00Z"),  # asked again after the cancellation
        _json(REQUESTED, future, "2026-12-30T00:00:00Z"),  # not a real line
    ]
    events = latest_events(lines, BACKUP, now=NOW)
    assert {str(k): v.kind for k, v in events.items()} == {a: CANCELLED, b: REQUESTED}
