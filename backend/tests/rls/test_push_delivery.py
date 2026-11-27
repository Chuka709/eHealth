"""Push delivery by the push role, labtrack_push (Phase 2.8b, 2.11b; H12, H16; security review L3).

Expo is a fake here: nothing leaves the test. The queue is shared with other tests, so every
assertion looks only at this test's own tokens.
"""

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text
from labtrack.worker.push import (
    MESSAGES_PER_REQUEST,
    PushRejectedError,
    Receipt,
    Ticket,
    check_receipts,
    send_pending,
    token_hash,
)

from .conftest import as_user, make_user, scalar
from .test_admin_functions import ARGON, NID, _check, _create, _issue
from .test_admin_functions import _token as _activation_token
from .test_caregivers import _caregiver, _family, _invite, _session
from .test_caregivers import _token as _push_token

pytestmark = pytest.mark.db


class FakeExpo:
    def __init__(self) -> None:
        self.requests: list[list[dict[str, Any]]] = []
        self.fail = False
        self.ticket_errors: dict[str, str] = {}  # token -> Expo error code
        self.receipts_by_id: dict[str, Receipt] = {}
        self.poison: set[str] = set()  # tokens Expo refuses a whole request for

    def send(self, messages: Sequence[Mapping[str, Any]]) -> list[Ticket]:
        if self.fail:
            raise ConnectionError("exp.host unreachable")
        assert len(messages) <= MESSAGES_PER_REQUEST
        if any(m["to"] in self.poison for m in messages):
            raise PushRejectedError("PUSH_TOO_MANY_EXPERIENCE_IDS")
        self.requests.append([dict(m) for m in messages])
        return [
            Ticket(False, None, self.ticket_errors[m["to"]])
            if m["to"] in self.ticket_errors
            else Ticket(True, f"tk-{uuid4().hex}", None)
            for m in messages
        ]

    def receipts(self, ticket_ids: Sequence[str]) -> dict[str, Receipt]:
        return {i: self.receipts_by_id[i] for i in ticket_ids if i in self.receipts_by_id}

    def to(self, token: str) -> list[dict[str, Any]]:
        return [m for request in self.requests for m in request if m["to"] == token]


async def _with_token(app_engine: AsyncEngine, owner_engine: AsyncEngine, user: UUID) -> Any:
    session, token = await _session(owner_engine, user), _push_token()
    async with as_user(app_engine, user) as conn:
        assert await scalar(
            conn, bound_text("select set_session_push_token(:s, :t)"), {"s": session, "t": token}
        )
    return session, token


async def _receipt_rows(maint_engine: AsyncEngine, session: Any) -> list[Any]:
    async with maint_engine.connect() as conn:
        return list(
            (
                await conn.execute(
                    bound_text(
                        "select id, notification_id, ticket_id, status, error, token_sha256"
                        " from push_receipts where session_id = :s order by id"
                    ),
                    {"s": session},
                )
            ).all()
        )


async def _session_token(owner_engine: AsyncEngine, session: Any) -> str | None:
    async with owner_engine.connect() as conn:
        token: str | None = await scalar(
            conn, bound_text("select push_token from sessions where id = :s"), {"s": session}
        )
    return token


async def test_a_notice_is_pushed_once_with_generic_text_and_two_ids(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    maint_engine: AsyncEngine,
    push_engine: AsyncEngine,
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    session, token = await _with_token(app_engine, owner_engine, carer)
    invitation = await _invite(app_engine, owner, patient, name)
    expo = FakeExpo()

    await send_pending(push_engine, expo)
    [message] = expo.to(token)
    assert set(message) == {"to", "title", "body", "data", "sound", "priority", "channelId"}
    # L3: the app reads everything else through the API once signed in
    assert set(message["data"]) == {"notification_id", "kind"}
    assert message["data"]["kind"] == "share_invite"
    shown = f"{message['title']} {message['body']} {message['data']}"
    for secret in (str(patient), str(invitation), str(owner), str(carer), name, "Test"):
        assert secret not in shown.replace("LabTrack", "")
    [receipt] = await _receipt_rows(maint_engine, session)
    assert (receipt.status, receipt.error) == ("sent", None)
    assert receipt.ticket_id.startswith("tk-")
    assert bytes(receipt.token_sha256) == token_hash(token)

    # a second run (or a retried task) pushes nothing again
    await send_pending(push_engine, expo)
    assert len(expo.to(token)) == 1


async def test_a_refused_request_marks_nothing_and_is_sent_on_the_next_run(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    maint_engine: AsyncEngine,
    push_engine: AsyncEngine,
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    session, token = await _with_token(app_engine, owner_engine, carer)
    await _invite(app_engine, owner, patient, name)
    expo = FakeExpo()
    expo.fail = True
    result = await send_pending(push_engine, expo)
    assert result.failed_requests >= 1
    assert await _receipt_rows(maint_engine, session) == []
    expo.fail = False
    await send_pending(push_engine, expo)
    assert len(expo.to(token)) == 1


async def test_device_not_registered_clears_the_token_at_once(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    maint_engine: AsyncEngine,
    push_engine: AsyncEngine,
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    session, token = await _with_token(app_engine, owner_engine, carer)
    await _invite(app_engine, owner, patient, name)
    expo = FakeExpo()
    expo.ticket_errors[token] = "DeviceNotRegistered"
    await send_pending(push_engine, expo)
    [receipt] = await _receipt_rows(maint_engine, session)
    assert (receipt.status, receipt.error, receipt.ticket_id) == (
        "error",
        "DeviceNotRegistered",
        None,
    )
    assert await _session_token(owner_engine, session) is None


async def _age(owner_engine: AsyncEngine, session: Any, minutes: int) -> None:
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update push_receipts set created_at = now() - make_interval(mins => :m)"
                " where session_id = :s"
            ),
            {"m": minutes, "s": session},
        )


async def test_receipts_are_read_later_and_a_new_token_survives_an_old_receipt(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    maint_engine: AsyncEngine,
    push_engine: AsyncEngine,
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    session, _ = await _with_token(app_engine, owner_engine, carer)
    await _invite(app_engine, owner, patient, name)
    expo = FakeExpo()
    await send_pending(push_engine, expo)
    [sent] = await _receipt_rows(maint_engine, session)

    # too early: Expo is not asked yet
    expo.receipts_by_id[sent.ticket_id] = Receipt(False, "DeviceNotRegistered")
    await check_receipts(push_engine, expo)
    assert (await _receipt_rows(maint_engine, session))[0].status == "sent"

    # the app registered a new token meanwhile (reinstall): the old ticket must not clear it
    fresh = _push_token()
    async with as_user(app_engine, carer) as conn:
        await conn.execute(
            bound_text("select set_session_push_token(:s, :t)"), {"s": session, "t": fresh}
        )
    await _age(owner_engine, session, 20)
    await check_receipts(push_engine, expo)
    [checked] = await _receipt_rows(maint_engine, session)
    assert (checked.status, checked.error) == ("error", "DeviceNotRegistered")
    assert await _session_token(owner_engine, session) == fresh


async def test_a_late_device_not_registered_clears_the_same_token(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    maint_engine: AsyncEngine,
    push_engine: AsyncEngine,
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    session, _ = await _with_token(app_engine, owner_engine, carer)
    await _invite(app_engine, owner, patient, name)
    expo = FakeExpo()
    await send_pending(push_engine, expo)
    [sent] = await _receipt_rows(maint_engine, session)
    expo.receipts_by_id[sent.ticket_id] = Receipt(False, "DeviceNotRegistered")
    await _age(owner_engine, session, 20)
    result = await check_receipts(push_engine, expo)
    assert result.forgotten_tokens >= 1
    assert await _session_token(owner_engine, session) is None


async def test_an_ok_receipt_and_one_expo_never_answered(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    maint_engine: AsyncEngine,
    push_engine: AsyncEngine,
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    session, token = await _with_token(app_engine, owner_engine, carer)
    other_session, _ = await _with_token(app_engine, owner_engine, carer)
    await _invite(app_engine, owner, patient, name)
    expo = FakeExpo()
    await send_pending(push_engine, expo)
    [sent] = await _receipt_rows(maint_engine, session)
    expo.receipts_by_id[sent.ticket_id] = Receipt(True, None)
    await _age(owner_engine, session, 20)
    await _age(owner_engine, other_session, 25 * 60)  # Expo has dropped it by now
    await check_receipts(push_engine, expo)
    assert [(r.status, r.error) for r in await _receipt_rows(maint_engine, session)] == [
        ("ok", None)
    ]
    assert [(r.status, r.error) for r in await _receipt_rows(maint_engine, other_session)] == [
        ("error", "Expired")
    ]
    assert await _session_token(owner_engine, session) == token


async def test_an_admin_reset_reaches_the_signed_out_phone_in_its_language(
    owner_engine: AsyncEngine,
    app_engine: AsyncEngine,
    admin_engine: AsyncEngine,
    maint_engine: AsyncEngine,
    push_engine: AsyncEngine,
) -> None:
    """H12: the real reset (admin_issue_token) signs every session out and still tells them."""
    admin = await make_user(owner_engine, "super_admin")
    user = await _create(admin_engine, admin)
    activation = _activation_token()[1]
    await _issue(admin_engine, admin, user, "activation", activation)
    async with app_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("select user_id from activation_consume(:h, :pw, null, false)"),
            {"h": activation, "pw": ARGON},
        )
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(bound_text("update users set locale = 'en' where id = :u"), {"u": user})
    session, token = await _with_token(app_engine, owner_engine, user)
    second = await make_user(owner_engine, "super_admin")  # not the enrolling admin (0006)
    check_id, ok = await _check(admin_engine, second, user, NID)
    assert ok
    await _issue(admin_engine, second, user, "admin_reset", _activation_token()[1], check_id, "sms")
    async with owner_engine.connect() as conn:
        assert (
            await scalar(
                conn,
                bound_text("select revoked_reason from sessions where id = :s"),
                {"s": session},
            )
            == "admin_reset"
        )

    expo = FakeExpo()
    await send_pending(push_engine, expo)
    [message] = expo.to(token)
    assert message["data"]["kind"] == "admin_reset"
    assert message["body"].startswith("An admin issued a password reset code")
    assert message["body"].endswith("Never share the code.")


async def test_the_receipt_token_function_is_the_workers_only(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    user = await make_user(owner_engine)
    async with as_user(app_engine, user) as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(bound_text("select maint_forget_receipt_token(1)"))


async def _sent_at(owner_engine: AsyncEngine, user: UUID) -> list[Any]:
    async with owner_engine.connect() as conn:
        return list(
            (
                await conn.execute(
                    bound_text("select sent_push_at from notifications where user_id = :u"),
                    {"u": user},
                )
            ).scalars()
        )


async def test_one_refused_token_holds_up_nobody_else(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    maint_engine: AsyncEngine,
    push_engine: AsyncEngine,
) -> None:
    """Security review H1: a token of another Expo project makes Expo refuse the request."""
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    bad_session, bad = await _with_token(app_engine, owner_engine, carer)
    good_session, good = await _with_token(app_engine, owner_engine, carer)
    owner2, carer2, patient2, name2 = await _family(app_engine, owner_engine)
    _, other = await _with_token(app_engine, owner_engine, carer2)
    await _invite(app_engine, owner, patient, name)
    await _invite(app_engine, owner2, patient2, name2)
    expo = FakeExpo()
    expo.poison.add(bad)
    await send_pending(push_engine, expo)
    assert len(expo.to(good)) == 1
    assert len(expo.to(other)) == 1
    [refused] = await _receipt_rows(maint_engine, bad_session)
    assert (refused.status, refused.error) == ("error", "PUSH_TOO_MANY_EXPERIENCE_IDS")
    assert [r.status for r in await _receipt_rows(maint_engine, good_session)] == ["sent"]
    assert all(at is not None for at in await _sent_at(owner_engine, carer))
    await send_pending(push_engine, expo)  # nothing is tried again
    assert (len(expo.to(good)), len(expo.to(other))) == (1, 1)


async def test_a_rate_limited_device_is_sent_again_and_the_others_are_not(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    maint_engine: AsyncEngine,
    push_engine: AsyncEngine,
) -> None:
    """Security review M1: MessageRateExceeded / InvalidCredentials are about the moment or the
    setup, so the notice is not marked; the device that got it is not sent it twice."""
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    slow_session, slow = await _with_token(app_engine, owner_engine, carer)
    _, fine = await _with_token(app_engine, owner_engine, carer)
    await _invite(app_engine, owner, patient, name)
    expo = FakeExpo()
    expo.ticket_errors[slow] = "MessageRateExceeded"
    await send_pending(push_engine, expo)
    assert await _receipt_rows(maint_engine, slow_session) == []
    assert await _sent_at(owner_engine, carer) == [None]
    del expo.ticket_errors[slow]
    await send_pending(push_engine, expo)
    assert (len(expo.to(slow)), len(expo.to(fine))) == (2, 1)
    assert all(at is not None for at in await _sent_at(owner_engine, carer))


async def test_a_dose_alert_waits_for_nobody_who_is_no_longer_the_caregiver(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    maint_engine: AsyncEngine,
    push_engine: AsyncEngine,
) -> None:
    """Security review L1: access ended before the alert went out - it is not pushed."""
    _, carer, patient = await _caregiver(app_engine, owner_engine)
    _, token = await _with_token(app_engine, owner_engine, carer)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into notifications (user_id, kind, patient_id, entity_id, title_key)"
                " values (:u, 'dose_overdue', :p, :e, 'notification.dose_overdue')"
            ),
            {"u": carer, "p": patient, "e": str(uuid4())},
        )
        await conn.execute(
            bound_text(
                "update patient_access set revoked_at = now()"
                " where patient_id = :p and user_id = :u"
            ),
            {"p": patient, "u": carer},
        )
    expo = FakeExpo()
    await send_pending(push_engine, expo)
    # the invitation's own notice still goes out; the dose alert does not
    assert [m["data"]["kind"] for m in expo.to(token)] == ["share_invite"]


async def test_a_profile_notice_is_pushed_only_while_access_lasts(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    maint_engine: AsyncEngine,
    push_engine: AsyncEngine,
) -> None:
    """Commit review of 0023: every kind about a profile, not only dose alerts."""
    _, carer, patient = await _caregiver(app_engine, owner_engine)
    _, token = await _with_token(app_engine, owner_engine, carer)
    async with owner_engine.connect() as conn, conn.begin():
        for kind in ("review_ready", "critical_pending"):
            await conn.execute(
                bound_text(
                    "insert into notifications (user_id, kind, patient_id, entity_id, title_key)"
                    " values (:u, :k, :p, :e, 'notification.x')"
                ),
                {"u": carer, "k": kind, "p": patient, "e": str(uuid4())},
            )
        await conn.execute(
            bound_text(
                "update patient_access set revoked_at = now()"
                " where patient_id = :p and user_id = :u"
            ),
            {"p": patient, "u": carer},
        )
    expo = FakeExpo()
    await send_pending(push_engine, expo)
    assert [m["data"]["kind"] for m in expo.to(token)] == ["share_invite"]


async def test_a_moved_token_still_reaches_the_phone_an_admin_reset_signed_out(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """Commit review of 0023 (H12): taking over a victim's token after a reset does not silence
    the reset notice; every move between accounts is audited."""
    victim, other, thief = (
        await make_user(owner_engine),
        await make_user(owner_engine),
        await make_user(owner_engine),
    )
    reset_session, token = await _with_token(app_engine, owner_engine, victim)
    other_session = await _session(owner_engine, other)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update sessions set revoked_at = now(), revoked_reason = 'admin_reset'"
                " where id = :s"
            ),
            {"s": reset_session},
        )
        # arranged: another account's live session holds the same token too
        await conn.execute(
            bound_text("update sessions set push_token = :t where id = :s"),
            {"t": token, "s": other_session},
        )
    thief_session, _ = await _with_token(app_engine, owner_engine, thief)
    async with as_user(app_engine, thief) as conn:
        await conn.execute(
            bound_text("select set_session_push_token(:s, :t)"), {"s": thief_session, "t": token}
        )
    assert await _session_token(owner_engine, reset_session) == token
    assert await _session_token(owner_engine, other_session) is None
    async with owner_engine.connect() as conn:
        moves = (
            await conn.execute(
                bound_text(
                    "select actor_id, entity_id, diff from audit_logs"
                    " where action = 'session.push_token_moved' and actor_id = :t"
                ),
                {"t": thief},
            )
        ).all()
    assert [(m.actor_id, m.entity_id, m.diff) for m in moves] == [
        (thief, str(thief_session), {"sessions": 1})
    ]


async def test_the_push_role_reaches_delivery_only(
    owner_engine: AsyncEngine, maint_engine: AsyncEngine, push_engine: AsyncEngine
) -> None:
    """2.11b: the one role with internet reads no PHI, runs no maintenance and never deletes a
    receipt; the maintenance role no longer delivers."""
    denied_push = (
        "select count(*) from users",
        "select count(*) from medications",
        "select count(*) from notifications",
        "select push_token from sessions limit 1",
        "select session_id from push_receipts limit 1",
        "delete from push_receipts where id = 0",
        "select * from maint_caregiver_alert_targets()",
    )
    for sql in denied_push:
        async with push_engine.connect() as conn:
            with pytest.raises(DBAPIError, match="permission denied"):
                await conn.execute(bound_text(sql))
    async with push_engine.connect() as conn:
        await conn.execute(bound_text("select count(*) from maint_push_queue(1)"))
    for sql in (
        "select count(*) from maint_push_queue(1)",
        "select maint_mark_pushed(array[]::bigint[])",
        "select maint_forget_push_token('x')",
        "select maint_forget_receipt_token(0)",
    ):
        async with maint_engine.connect() as conn:
            with pytest.raises(DBAPIError, match="permission denied"):
                await conn.execute(bound_text(sql))


async def test_the_push_role_holds_nothing_but_push_receipts(owner_engine: AsyncEngine) -> None:
    """2.11b: every table, view and sequence the push role can touch (a new grant shows here)."""
    async with owner_engine.connect() as conn:
        rows = (
            await conn.execute(
                bound_text(
                    "select c.relname from pg_class c"
                    " where c.relnamespace = 'public'::regnamespace"
                    " and c.relkind in ('r', 'p', 'v', 'm', 'S', 'f') and ("
                    " (c.relkind <> 'S' and (has_table_privilege('labtrack_push', c.oid,"
                    " 'select,insert,update,delete,truncate,references,trigger')"
                    " or has_any_column_privilege('labtrack_push', c.oid,"
                    " 'select,insert,update,references')))"
                    " or (c.relkind = 'S'"
                    " and has_sequence_privilege('labtrack_push', c.oid, 'usage,select,update')))"
                )
            )
        ).scalars()
        assert set(rows) == {"push_receipts", "push_receipts_id_seq"}
