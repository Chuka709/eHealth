"""Caregivers and push delivery (0020; phi-table; H12, H16): invitations, alert settings, dose
alerts, push tokens and the maintenance worker's queue."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import as_user, grant, make_patient, make_user, scalar

pytestmark = pytest.mark.db


async def _username(owner_engine: AsyncEngine, user: UUID) -> str:
    async with owner_engine.connect() as conn:
        name: str = await scalar(
            conn, bound_text("select username::text from users where id = :u"), {"u": user}
        )
    return name


async def _consent(app_engine: AsyncEngine, user: UUID, granted: bool = True) -> None:
    async with as_user(app_engine, user) as conn:
        await conn.execute(
            bound_text(
                "insert into consents (user_id, kind, version, granted)"
                " values (app_user_id(), 'caregiver_sharing', '1', :g)"
            ),
            {"g": granted},
        )


async def _invite(app_engine: AsyncEngine, owner: UUID, patient: UUID, username: str) -> Any:
    async with as_user(app_engine, owner) as conn:
        return await scalar(
            conn, bound_text("select invite_caregiver(:p, :u)"), {"p": patient, "u": username}
        )


async def _respond(app_engine: AsyncEngine, user: UUID, invitation: Any, accept: bool) -> Any:
    async with as_user(app_engine, user) as conn:
        return await scalar(
            conn,
            bound_text("select respond_caregiver_invitation(:i, :a)"),
            {"i": invitation, "a": accept},
        )


async def _reads(app_engine: AsyncEngine, user: UUID, patient: UUID) -> bool:
    async with as_user(app_engine, user) as conn:
        ok: bool = await scalar(conn, bound_text("select can_read_patient(:p)"), {"p": patient})
    return ok


async def _family(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> tuple[UUID, UUID, UUID, str]:
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await _consent(app_engine, owner)
    return owner, carer, patient, await _username(owner_engine, carer)


# --- invitations ------------------------------------------------------------------------------


async def test_an_invitation_needs_the_owners_consent(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    name = await _username(owner_engine, carer)
    with pytest.raises(DBAPIError, match="consent required"):
        await _invite(app_engine, owner, patient, name)
    await _consent(app_engine, owner, granted=True)
    await _consent(app_engine, owner, granted=False)  # withdrawn: the last answer counts
    with pytest.raises(DBAPIError, match="consent required"):
        await _invite(app_engine, owner, patient, name)


async def test_invite_accept_gives_access_only_after_the_answer(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    invitation = await _invite(app_engine, owner, patient, name)
    assert invitation is not None
    assert await _invite(app_engine, owner, patient, name) == invitation  # asked again: same
    assert not await _reads(app_engine, carer, patient)  # nothing before the answer
    async with as_user(app_engine, carer) as conn:
        seen = (await conn.execute(bound_text("select * from my_caregiver_invitations()"))).all()
        kinds = (await conn.execute(bound_text("select kind, entity_id from notifications"))).all()
    assert [r.id for r in seen] == [invitation]
    assert seen[0].inviter_name == "Test"
    assert "patient_name" not in seen[0]._mapping  # only after accepting (0025, Q45)
    assert [(k.kind, k.entity_id) for k in kinds] == [("share_invite", str(invitation))]

    assert await _respond(app_engine, carer, invitation, True) is True
    assert await _reads(app_engine, carer, patient)
    async with as_user(app_engine, carer) as conn:
        level = await scalar(
            conn,
            bound_text(
                "select level::text from patient_access where patient_id = :p"
                " and user_id = app_user_id()"
            ),
            {"p": patient},
        )
    assert level == "caregiver"
    assert await _respond(app_engine, carer, invitation, True) is False  # answered once
    async with owner_engine.connect() as conn:
        actions = (
            await conn.execute(
                bound_text(
                    "select action, diff from audit_logs where patient_id = :p"
                    " and action like 'caregiver.%' order by id"
                ),
                {"p": patient},
            )
        ).all()
    assert [a.action for a in actions] == ["caregiver.invite", "caregiver.accept"]
    assert all(a.diff is None for a in actions)  # ids only


async def test_nobody_oneself_or_a_sharer_gets_no_invitation_and_the_caller_cannot_tell(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    assert await _invite(app_engine, owner, patient, "no_such_user_" + uuid4().hex[:6]) is None
    assert await _invite(app_engine, owner, patient, await _username(owner_engine, owner)) is None
    await grant(app_engine, owner, patient, carer, "viewer")
    assert await _invite(app_engine, owner, patient, name) is None
    async with as_user(app_engine, owner) as conn:
        n = await scalar(
            conn,
            bound_text("select count(*) from caregiver_invitations where patient_id = :p"),
            {"p": patient},
        )
    assert n == 0


async def test_declined_revoked_and_expired_invitations_give_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    first = await _invite(app_engine, owner, patient, name)
    assert await _respond(app_engine, carer, first, False) is True
    assert not await _reads(app_engine, carer, patient)
    async with owner_engine.connect() as conn, conn.begin():  # the decline is 31 days old
        await conn.execute(
            bound_text(
                "update caregiver_invitations set responded_at = now() - interval '31 days'"
                " where id = :i"
            ),
            {"i": first},
        )

    second = await _invite(app_engine, owner, patient, name)
    async with as_user(app_engine, owner) as conn:
        assert await scalar(
            conn, bound_text("select revoke_caregiver_invitation(:i)"), {"i": second}
        )
    assert await _respond(app_engine, carer, second, True) is False

    third = await _invite(app_engine, owner, patient, name)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update caregiver_invitations set expires_at = now() - interval '1 second'"
                " where id = :i"
            ),
            {"i": third},
        )
    assert await _respond(app_engine, carer, third, True) is False
    assert not await _reads(app_engine, carer, patient)


async def test_only_the_invited_person_answers_and_only_the_owner_revokes(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    stranger = await make_user(owner_engine)
    invitation = await _invite(app_engine, owner, patient, name)
    assert await _respond(app_engine, stranger, invitation, True) is False
    assert not await _reads(app_engine, stranger, patient)
    async with as_user(app_engine, carer) as conn:
        assert not await scalar(
            conn, bound_text("select revoke_caregiver_invitation(:i)"), {"i": invitation}
        )
    async with as_user(app_engine, stranger) as conn:
        assert await scalar(conn, bound_text("select count(*) from caregiver_invitations")) == 0
        with pytest.raises(DBAPIError, match="not the owner"):
            await conn.execute(
                bound_text("select invite_caregiver(:p, :u)"), {"p": patient, "u": name}
            )


async def test_the_owner_cannot_make_a_caregiver_or_revive_one_directly(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient, _ = await _family(app_engine, owner_engine)
    with pytest.raises(DBAPIError, match="row-level security"):
        await grant(app_engine, owner, patient, carer, "caregiver", direct=True)
    await grant(app_engine, owner, patient, carer, "viewer")
    async with as_user(app_engine, owner) as conn:
        with pytest.raises(DBAPIError, match="accepts an invitation"):
            await conn.execute(
                bound_text(
                    "update patient_access set level = 'caregiver'"
                    " where patient_id = :p and user_id = :u"
                ),
                {"p": patient, "u": carer},
            )
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text(
                "update patient_access set revoked_at = now()"
                " where patient_id = :p and user_id = :u"
            ),
            {"p": patient, "u": carer},
        )
    async with as_user(app_engine, owner) as conn:
        with pytest.raises(DBAPIError, match="not revived"):
            await conn.execute(
                bound_text(
                    "update patient_access set revoked_at = null"
                    " where patient_id = :p and user_id = :u"
                ),
                {"p": patient, "u": carer},
            )


async def test_a_new_invitation_brings_back_a_caregiver_who_had_left(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    await _respond(app_engine, carer, await _invite(app_engine, owner, patient, name), True)
    async with as_user(app_engine, carer) as conn:
        await conn.execute(bound_text("select set_caregiver_alerts(:p, 30, true)"), {"p": patient})
        assert await scalar(conn, bound_text("select leave_patient(:p)"), {"p": patient})
    assert not await _reads(app_engine, carer, patient)
    async with as_user(app_engine, owner) as conn:
        assert (
            await scalar(
                conn,
                bound_text("select count(*) from caregiver_alert_settings where patient_id = :p"),
                {"p": patient},
            )
            == 0
        )  # alerts left with them
    await _respond(app_engine, carer, await _invite(app_engine, owner, patient, name), True)
    assert await _reads(app_engine, carer, patient)


# --- alert settings and dose alerts ----------------------------------------------------------


async def _caregiver(app_engine: AsyncEngine, owner_engine: AsyncEngine) -> tuple[UUID, UUID, UUID]:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    await _respond(app_engine, carer, await _invite(app_engine, owner, patient, name), True)
    return owner, carer, patient


async def _medication(app_engine: AsyncEngine, owner: UUID, patient: UUID) -> Any:
    async with as_user(app_engine, owner) as conn:
        return await scalar(
            conn,
            bound_text(
                "insert into medications (patient_id, client_id, name)"
                " values (:p, :c, 'Такролимус') returning id"
            ),
            {"p": patient, "c": uuid4()},
        )


_ALERT = bound_text(
    "insert into dose_alerts (patient_id, medication_id, slot_at, alerted_user_id)"
    " values (:p, :m, '2026-11-10T00:00:00Z', app_user_id()) returning id"
)


async def test_alert_settings_belong_to_the_caregiver_and_the_owner_can_pause_them(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient = await _caregiver(app_engine, owner_engine)
    stranger = await make_user(owner_engine)
    async with as_user(app_engine, carer) as conn:
        assert (
            await scalar(conn, bound_text("select caregiver_alerts_on(:p)"), {"p": patient})
            is False
        )
        await conn.execute(bound_text("select set_caregiver_alerts(:p, 45, true)"), {"p": patient})
        assert await scalar(conn, bound_text("select caregiver_alerts_on(:p)"), {"p": patient})
    # its own transaction: a refused write aborts it (the 45 above stays)
    async with as_user(app_engine, carer) as conn:
        with pytest.raises(DBAPIError, match="caregiver_alert_settings_missed_dose"):
            await conn.execute(
                bound_text("select set_caregiver_alerts(:p, 5, true)"), {"p": patient}
            )
    for who in (owner, stranger):
        async with as_user(app_engine, who) as conn:
            with pytest.raises(DBAPIError, match="not a caregiver"):
                await conn.execute(
                    bound_text("select set_caregiver_alerts(:p, 30, true)"), {"p": patient}
                )
    async with as_user(app_engine, owner) as conn:
        assert (
            await scalar(
                conn,
                bound_text(
                    "select missed_dose_after_min from caregiver_alert_settings"
                    " where patient_id = :p"
                ),
                {"p": patient},
            )
            == 45
        )
        assert await scalar(
            conn,
            bound_text("select pause_caregiver_alerts(:p, :c, true)"),
            {"p": patient, "c": carer},
        )
    async with as_user(app_engine, carer) as conn:
        assert (
            await scalar(conn, bound_text("select caregiver_alerts_on(:p)"), {"p": patient})
            is False
        )
        # changing the delay does not lift the owner's pause
        await conn.execute(bound_text("select set_caregiver_alerts(:p, 30, true)"), {"p": patient})
        assert (
            await scalar(conn, bound_text("select caregiver_alerts_on(:p)"), {"p": patient})
            is False
        )
        with pytest.raises(DBAPIError, match="not the owner"):
            await conn.execute(
                bound_text("select pause_caregiver_alerts(:p, :c, false)"),
                {"p": patient, "c": carer},
            )
    async with as_user(app_engine, stranger) as conn:
        assert await scalar(conn, bound_text("select count(*) from caregiver_alert_settings")) == 0


async def test_one_alert_per_dose_and_caregiver_only_while_alerts_are_on(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient = await _caregiver(app_engine, owner_engine)
    medication = await _medication(app_engine, owner, patient)
    async with as_user(app_engine, carer) as conn:
        with pytest.raises(DBAPIError, match="row-level security"):  # alerts not chosen yet
            await conn.execute(_ALERT, {"p": patient, "m": medication})
    async with as_user(app_engine, carer) as conn:
        await conn.execute(bound_text("select set_caregiver_alerts(:p, 30, true)"), {"p": patient})
        alert = await scalar(conn, _ALERT, {"p": patient, "m": medication})
        await conn.execute(
            bound_text(
                "select notify(app_user_id(), 'dose_overdue', :p, :e, 'notification.dose_overdue')"
            ),
            {"p": patient, "e": str(alert)},
        )
    async with as_user(app_engine, carer) as conn:
        with pytest.raises(DBAPIError, match="dose_alerts_patient_id_medication_id_slot_at"):
            await conn.execute(_ALERT, {"p": patient, "m": medication})
    # never for someone else, never someone else's profile
    other_owner = await make_user(owner_engine)
    other_patient = await make_patient(app_engine, other_owner)
    other_med = await _medication(app_engine, other_owner, other_patient)
    async with as_user(app_engine, carer) as conn:
        with pytest.raises(DBAPIError, match="notification not allowed"):
            await conn.execute(
                bound_text(
                    "select notify(:u, 'dose_overdue', :p, null, 'notification.dose_overdue')"
                ),
                {"u": owner, "p": patient},
            )
    async with as_user(app_engine, carer) as conn:
        with pytest.raises(DBAPIError, match=r"foreign key|row-level security"):
            await conn.execute(_ALERT, {"p": patient, "m": other_med})
    async with as_user(app_engine, owner) as conn:
        assert (
            await scalar(
                conn,
                bound_text("select count(*) from dose_alerts where patient_id = :p"),
                {"p": patient},
            )
            == 1
        )  # the owner sees that an alert went out


async def test_the_worker_gets_only_active_targets_as_ids(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, maint_engine: AsyncEngine
) -> None:
    owner, carer, patient = await _caregiver(app_engine, owner_engine)
    async with as_user(app_engine, carer) as conn:
        await conn.execute(bound_text("select set_caregiver_alerts(:p, 30, true)"), {"p": patient})

    async def targets() -> list[Any]:
        async with maint_engine.connect() as conn:
            rows = (
                await conn.execute(bound_text("select * from maint_caregiver_alert_targets()"))
            ).all()
        return [tuple(r) for r in rows if r.patient_id == patient]

    assert await targets() == [(patient, carer, 30)]
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text("select pause_caregiver_alerts(:p, :c, true)"), {"p": patient, "c": carer}
        )
    assert await targets() == []
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text("select pause_caregiver_alerts(:p, :c, false)"), {"p": patient, "c": carer}
        )
    # only the access ends (arranged as the schema owner; the app goes through revoke_caregiver,
    # which also drops the settings - 0025): the settings alone send nothing
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update patient_access set revoked_at = now()"
                " where patient_id = :p and user_id = :c"
            ),
            {"p": patient, "c": carer},
        )
    assert await targets() == []
    # the worker role reads no health data itself, and the app cannot read the queue
    async with maint_engine.connect() as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(bound_text("select count(*) from dose_alerts"))
    async with as_user(app_engine, owner) as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(bound_text("select * from maint_caregiver_alert_targets()"))


# --- push --------------------------------------------------------------------------------------


async def _session(owner_engine: AsyncEngine, user: UUID) -> Any:
    async with owner_engine.connect() as conn, conn.begin():
        return await scalar(
            conn,
            bound_text(
                "insert into sessions (user_id, family_id, token_hash, expires_at)"
                " values (:u, gen_random_uuid(), :h, now() + interval '1 day') returning id"
            ),
            {"u": user, "h": uuid4().hex},
        )


def _token() -> str:
    return f"ExponentPushToken[{uuid4().hex[:22]}]"


async def test_a_push_token_is_set_on_ones_own_session_and_follows_the_phone(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    alice, bob = await make_user(owner_engine), await make_user(owner_engine)
    a_session, b_session = await _session(owner_engine, alice), await _session(owner_engine, bob)
    token = _token()
    async with as_user(app_engine, alice) as conn:
        assert await scalar(
            conn, bound_text("select set_session_push_token(:s, :t)"), {"s": a_session, "t": token}
        )
        assert not await scalar(  # not someone else's session
            conn, bound_text("select set_session_push_token(:s, :t)"), {"s": b_session, "t": token}
        )
        with pytest.raises(DBAPIError, match="not an Expo push token"):
            await conn.execute(
                bound_text("select set_session_push_token(:s, 'https://evil.example/x')"),
                {"s": a_session},
            )
    # the same phone, now signed in as Bob: Alice's session no longer gets its pushes
    async with as_user(app_engine, bob) as conn:
        await conn.execute(
            bound_text("select set_session_push_token(:s, :t)"), {"s": b_session, "t": token}
        )
    async with owner_engine.connect() as conn:
        rows = (
            await conn.execute(
                bound_text("select id, push_token from sessions where id in (:a, :b)"),
                {"a": a_session, "b": b_session},
            )
        ).all()
    assert {r.id: r.push_token for r in rows} == {a_session: None, b_session: token}
    async with as_user(app_engine, alice) as conn:  # the token column stays unreadable to apps
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(bound_text("select push_token from sessions"))


async def test_the_push_queue_has_keys_and_tokens_only_and_reaches_reset_devices(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, maint_engine: AsyncEngine
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    session, token = await _session(owner_engine, carer), _token()
    async with as_user(app_engine, carer) as conn:
        await conn.execute(
            bound_text("select set_session_push_token(:s, :t)"), {"s": session, "t": token}
        )
    invitation = await _invite(app_engine, owner, patient, name)

    async def queued() -> list[Any]:
        async with maint_engine.connect() as conn:
            rows = (await conn.execute(bound_text("select * from maint_push_queue(500)"))).all()
        return [r for r in rows if r.push_token == token]

    [row] = await queued()
    assert (row.kind, row.title_key, row.entity_id) == (
        "share_invite",
        "notification.caregiver_invite",
        str(invitation),
    )
    assert set(row._mapping) == {
        "notification_id",
        "kind",
        "title_key",
        "entity_id",
        "patient_id",
        "session_id",
        "push_token",
        "locale",  # 0023: the text is in the user's language, the user's row is not read
    }
    async with maint_engine.connect() as conn, conn.begin():
        assert (
            await scalar(
                conn,
                bound_text("select maint_mark_pushed(array[:n]::bigint[])"),
                {"n": row.notification_id},
            )
            == 1
        )
    assert await queued() == []

    # an admin reset signs the device out and still tells it (H12); other kinds do not
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update sessions set revoked_at = now(), revoked_reason = 'admin_reset'"
                " where id = :s"
            ),
            {"s": session},
        )
        await conn.execute(
            bound_text(
                "insert into notifications (user_id, kind, title_key) values"
                " (:u, 'admin_reset', 'notification.admin_reset'),"
                " (:u, 'reminder', 'notification.reminder')"
            ),
            {"u": carer},
        )
    assert [r.kind for r in await queued()] == ["admin_reset"]
    async with maint_engine.connect() as conn, conn.begin():
        await conn.execute(bound_text("select maint_forget_push_token(:t)"), {"t": token})
    assert await queued() == []
    async with as_user(app_engine, carer) as conn:
        with pytest.raises(DBAPIError, match="permission denied"):
            await conn.execute(bound_text("select * from maint_push_queue(10)"))


async def test_no_user_context_and_admin_roles_see_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    await _respond(app_engine, carer, await _invite(app_engine, owner, patient, name), True)
    async with as_user(app_engine, carer) as conn:
        await conn.execute(bound_text("select set_caregiver_alerts(:p, 30, true)"), {"p": patient})
    async with as_user(app_engine, None) as conn:
        for table in ("caregiver_invitations", "caregiver_alert_settings", "dose_alerts"):
            assert await scalar(conn, bound_text(f"select count(*) from {table}")) == 0  # noqa: S608
        assert (
            await conn.execute(bound_text("select * from my_caregiver_invitations()"))
        ).all() == []
        with pytest.raises(DBAPIError, match="not the owner"):
            await conn.execute(
                bound_text("select invite_caregiver(:p, :u)"), {"p": patient, "u": name}
            )
    admin = await make_user(owner_engine, "super_admin")
    for table in (
        "caregiver_invitations",
        "caregiver_alert_settings",
        "dose_alerts",
        "push_receipts",
    ):
        async with as_user(admin_engine, admin) as conn:  # one transaction per refusal
            with pytest.raises(DBAPIError, match="permission denied"):
                await conn.execute(bound_text(f"select count(*) from {table}"))  # noqa: S608


# --- security review of 0020 ------------------------------------------------------------------


async def test_the_owner_cannot_move_a_caregiver_row_or_revive_an_expired_one(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient = await _caregiver(app_engine, owner_engine)
    victim = await make_user(owner_engine)
    other = await make_patient(app_engine, owner, minor=True)
    for column, value in (("user_id", victim), ("patient_id", other)):
        async with as_user(app_engine, owner) as conn:
            with pytest.raises(DBAPIError, match=r"not moved|permission denied"):
                await conn.execute(
                    bound_text(
                        f"update patient_access set {column} = :x"  # noqa: S608
                        " where patient_id = :p and user_id = :c"
                    ),
                    {"x": value, "p": patient, "c": carer},
                )
    assert not await _reads(app_engine, victim, patient)
    assert not await _reads(app_engine, carer, other)

    late, viewer = await make_user(owner_engine), await make_user(owner_engine)
    await grant(
        app_engine, owner, patient, late, "caregiver", expires=datetime.now(UTC) - timedelta(1)
    )
    await grant(
        app_engine, owner, patient, viewer, "viewer", expires=datetime.now(UTC) - timedelta(1)
    )
    for who in (late, viewer):
        async with as_user(app_engine, owner) as conn:
            with pytest.raises(DBAPIError, match="expired access is not revived"):
                await conn.execute(
                    bound_text(
                        "update patient_access set expires_at = null"
                        " where patient_id = :p and user_id = :u"
                    ),
                    {"p": patient, "u": who},
                )


async def test_a_pause_before_any_choice_leaves_alerts_off(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, maint_engine: AsyncEngine
) -> None:
    owner, carer, patient = await _caregiver(app_engine, owner_engine)
    for paused in (True, False):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                bound_text("select pause_caregiver_alerts(:p, :c, :x)"),
                {"p": patient, "c": carer, "x": paused},
            )
    async with as_user(app_engine, carer) as conn:
        assert (
            await scalar(conn, bound_text("select caregiver_alerts_on(:p)"), {"p": patient})
            is False
        )
    async with maint_engine.connect() as conn:
        rows = (
            await conn.execute(bound_text("select * from maint_caregiver_alert_targets()"))
        ).all()
    assert [r for r in rows if r.patient_id == patient] == []


async def test_an_invitation_notice_needs_a_pending_invitation(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    stranger = await make_user(owner_engine)
    invitation = await _invite(app_engine, owner, patient, name)
    for user, entity in ((stranger, str(invitation)), (carer, str(uuid4()))):
        async with as_user(app_engine, owner) as conn:
            with pytest.raises(DBAPIError, match="notification not allowed"):
                await conn.execute(
                    bound_text(
                        "select notify(:u, 'share_invite', :p, :e, 'notification.caregiver_invite')"
                    ),
                    {"u": user, "p": patient, "e": entity},
                )


async def test_after_a_decline_the_same_person_is_not_invited_again_for_30_days(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    await _respond(app_engine, carer, await _invite(app_engine, owner, patient, name), False)
    assert await _invite(app_engine, owner, patient, name) is None
    async with as_user(app_engine, carer) as conn:
        assert (
            await scalar(
                conn, bound_text("select count(*) from notifications where kind = 'share_invite'")
            )
            == 1
        )


async def test_no_accept_after_the_consent_ownership_or_profile_is_gone(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    invitation = await _invite(app_engine, owner, patient, name)
    await _consent(app_engine, owner, granted=False)  # ends the open invitation (trigger)
    async with as_user(app_engine, carer) as conn:
        assert (
            await conn.execute(bound_text("select * from my_caregiver_invitations()"))
        ).all() == []
    assert await _respond(app_engine, carer, invitation, True) is False
    await _consent(app_engine, owner, granted=True)
    assert await _respond(app_engine, carer, invitation, True) is False  # it stays ended
    assert await _respond(app_engine, carer, await _invite(app_engine, owner, patient, name), True)

    owner2, carer2, patient2, name2 = await _family(app_engine, owner_engine)
    lost = await _invite(app_engine, owner2, patient2, name2)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update patient_access set revoked_at = now()"
                " where patient_id = :p and user_id = :o"
            ),
            {"p": patient2, "o": owner2},
        )
    assert await _respond(app_engine, carer2, lost, True) is False

    owner3, carer3, patient3, name3 = await _family(app_engine, owner_engine)
    gone = await _invite(app_engine, owner3, patient3, name3)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update patients set deleted_at = now() where id = :p"), {"p": patient3}
        )
    assert await _respond(app_engine, carer3, gone, True) is False


async def test_an_expired_or_revoked_caregiver_gets_no_alerts_and_sets_none(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient = await _caregiver(app_engine, owner_engine)
    medication = await _medication(app_engine, owner, patient)
    async with as_user(app_engine, carer) as conn:
        await conn.execute(bound_text("select set_caregiver_alerts(:p, 30, true)"), {"p": patient})
        await scalar(conn, _ALERT, {"p": patient, "m": medication})
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update patient_access set expires_at = now() - interval '1 second'"
                " where patient_id = :p and user_id = :c"
            ),
            {"p": patient, "c": carer},
        )
    async with as_user(app_engine, carer) as conn:
        assert (
            await scalar(conn, bound_text("select caregiver_alerts_on(:p)"), {"p": patient})
            is False
        )
        assert await scalar(conn, bound_text("select count(*) from dose_alerts")) == 0
    async with as_user(app_engine, carer) as conn:
        with pytest.raises(DBAPIError, match="not a caregiver"):
            await conn.execute(
                bound_text("select set_caregiver_alerts(:p, 30, true)"), {"p": patient}
            )
    async with as_user(app_engine, carer) as conn:
        with pytest.raises(DBAPIError, match="row-level security"):
            await conn.execute(
                bound_text(
                    "insert into dose_alerts (patient_id, medication_id, slot_at, alerted_user_id)"
                    " values (:p, :m, '2026-11-11T00:00:00Z', app_user_id())"
                ),
                {"p": patient, "m": medication},
            )
    async with as_user(app_engine, carer) as conn:
        with pytest.raises(DBAPIError, match="notification not allowed"):
            await conn.execute(
                bound_text(
                    "select notify(app_user_id(), 'dose_overdue', :p, null,"
                    " 'notification.dose_overdue')"
                ),
                {"p": patient},
            )


async def test_without_a_user_nothing_is_answered_set_or_left(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    invitation = await _invite(app_engine, owner, patient, name)
    session = await _session(owner_engine, carer)
    async with as_user(app_engine, None) as conn:
        assert (
            await scalar(
                conn, bound_text("select respond_caregiver_invitation(:i, true)"), {"i": invitation}
            )
            is False
        )
        assert await scalar(conn, bound_text("select leave_patient(:p)"), {"p": patient}) is False
        assert (
            await scalar(
                conn,
                bound_text("select set_session_push_token(:s, :t)"),
                {"s": session, "t": _token()},
            )
            is False
        )
    async with as_user(app_engine, None) as conn:
        with pytest.raises(DBAPIError, match="not a caregiver"):
            await conn.execute(
                bound_text("select set_caregiver_alerts(:p, 30, true)"), {"p": patient}
            )
    assert not await _reads(app_engine, carer, patient)


async def test_an_admin_account_is_never_invited(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, _, patient, _ = await _family(app_engine, owner_engine)
    admin = await make_user(owner_engine, "super_admin")
    assert await _invite(app_engine, owner, patient, await _username(owner_engine, admin)) is None


async def test_tokens_go_only_on_live_sessions_and_can_be_cleared(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    user = await make_user(owner_engine)
    live, ended, expired = [await _session(owner_engine, user) for _ in range(3)]
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update sessions set revoked_at = now(), revoked_reason = 'logout' where id = :s"
            ),
            {"s": ended},
        )
        await conn.execute(
            bound_text(
                "update sessions set expires_at = now() - interval '1 second' where id = :s"
            ),
            {"s": expired},
        )
    token = _token()
    async with as_user(app_engine, user) as conn:
        for session in (ended, expired):
            assert (
                await scalar(
                    conn,
                    bound_text("select set_session_push_token(:s, :t)"),
                    {"s": session, "t": token},
                )
                is False
            )
        assert await scalar(
            conn, bound_text("select set_session_push_token(:s, :t)"), {"s": live, "t": token}
        )
        assert await scalar(
            conn, bound_text("select set_session_push_token(:s, null)"), {"s": live}
        )
    async with owner_engine.connect() as conn:
        assert (
            await scalar(
                conn,
                bound_text("select count(*) from sessions where push_token = :t"),
                {"t": token},
            )
            == 0
        )


async def test_a_no_is_always_possible_and_hidden_invitations_cannot_be_accepted(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    invitation = await _invite(app_engine, owner, patient, name)
    async with owner_engine.connect() as conn, conn.begin():  # the inviter lost the profile
        await conn.execute(
            bound_text(
                "update patient_access set revoked_at = now()"
                " where patient_id = :p and user_id = :o"
            ),
            {"p": patient, "o": owner},
        )
    async with as_user(app_engine, carer) as conn:
        assert (
            await conn.execute(bound_text("select * from my_caregiver_invitations()"))
        ).all() == []
    assert await _respond(app_engine, carer, invitation, True) is False
    assert await _respond(app_engine, carer, invitation, False) is True  # dismissed for good


async def test_at_most_three_invitations_between_two_people_in_30_days(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    # (over all of the owner's profiles; a child's profile gets no caregivers since 0025)
    for _ in range(3):
        invitation = await _invite(app_engine, owner, patient, name)
        assert invitation is not None
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                bound_text("select revoke_caregiver_invitation(:i)"), {"i": invitation}
            )
    assert await _invite(app_engine, owner, patient, name) is None
    async with as_user(app_engine, carer) as conn:
        assert (
            await scalar(
                conn, bound_text("select count(*) from notifications where kind = 'share_invite'")
            )
            == 3
        )


async def test_an_invitation_or_a_dose_alert_is_announced_only_once(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    invitation = await _invite(app_engine, owner, patient, name)  # its notice went out
    async with as_user(app_engine, owner) as conn:
        with pytest.raises(DBAPIError, match="notification not allowed"):
            await conn.execute(
                bound_text(
                    "select notify(:u, 'share_invite', :p, :e, 'notification.caregiver_invite')"
                ),
                {"u": carer, "p": patient, "e": str(invitation)},
            )
    await _respond(app_engine, carer, invitation, True)
    medication = await _medication(app_engine, owner, patient)
    async with as_user(app_engine, carer) as conn:
        await conn.execute(bound_text("select set_caregiver_alerts(:p, 30, true)"), {"p": patient})
        alert = await scalar(conn, _ALERT, {"p": patient, "m": medication})
    notice = bound_text(
        "select notify(app_user_id(), 'dose_overdue', :p, :e, 'notification.dose_overdue')"
    )
    async with as_user(app_engine, carer) as conn:
        await conn.execute(notice, {"p": patient, "e": str(alert)})
    for entity in (str(alert), "12345"):  # again, or a dose alert that is not theirs
        async with as_user(app_engine, carer) as conn:
            with pytest.raises(DBAPIError, match="notification not allowed"):
                await conn.execute(notice, {"p": patient, "e": entity})


async def test_the_database_itself_keeps_one_notice_per_entity(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer, patient, name = await _family(app_engine, owner_engine)
    invitation = await _invite(app_engine, owner, patient, name)
    # as two concurrent calls would leave it, past notify()'s own check
    async with owner_engine.connect() as conn:
        with pytest.raises(DBAPIError, match="notifications_entity"):
            await conn.execute(
                bound_text(
                    "insert into notifications (user_id, kind, patient_id, entity_id, title_key)"
                    " values (:u, 'share_invite', :p, :e, 'notification.caregiver_invite')"
                ),
                {"u": carer, "p": patient, "e": str(invitation)},
            )
