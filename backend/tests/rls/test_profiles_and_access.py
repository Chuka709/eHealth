"""RLS for patients, patient_access, consents, notifications (docs/03, docs/04 §6)."""

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import as_user, grant, make_patient, make_user, scalar

pytestmark = pytest.mark.db

_COUNT_PATIENT = bound_text("select count(*) from patients where id = :p")


async def _sees(app_engine: AsyncEngine, user: UUID | None, patient: UUID) -> int:
    async with as_user(app_engine, user) as conn:
        n: int = await scalar(conn, _COUNT_PATIENT, {"p": patient})
        return n


async def test_owner_reads_and_updates_own_profile(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    assert await _sees(app_engine, owner, patient) == 1
    async with as_user(app_engine, owner) as conn:
        r = await conn.execute(
            bound_text("update patients set full_name = 'Renamed' where id = :p"), {"p": patient}
        )
        assert r.rowcount == 1


async def test_stranger_cannot_read_write_or_delete(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    owner, stranger = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    assert await _sees(app_engine, stranger, patient) == 0
    async with as_user(app_engine, stranger) as conn:
        upd = await conn.execute(
            bound_text("update patients set full_name = 'x' where id = :p"), {"p": patient}
        )
        dele = await conn.execute(bound_text("delete from patients where id = :p"), {"p": patient})
        assert (upd.rowcount, dele.rowcount) == (0, 0)


async def test_no_user_context_sees_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    patient = await make_patient(app_engine, await make_user(owner_engine))
    assert await _sees(app_engine, None, patient) == 0


async def test_patients_cannot_be_inserted_directly(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    user = await make_user(owner_engine)
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(app_engine, user) as conn:
            await conn.execute(bound_text("insert into patients (full_name) values ('x')"))


@pytest.mark.parametrize(
    ("expires", "revoked", "visible"),
    [
        (None, False, 1),
        (datetime(2000, 1, 1, tzinfo=UTC), False, 0),  # expired
        (None, True, 0),  # revoked
    ],
)
async def test_shared_access_respects_expiry_and_revocation(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    admin_engine: AsyncEngine,
    expires: datetime | None,
    revoked: bool,
    visible: int,
) -> None:
    owner, doctor = await make_user(owner_engine), await make_user(owner_engine, "doctor")
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, doctor, "doctor", expires=expires, revoked=revoked)
    assert await _sees(app_engine, doctor, patient) == visible


@pytest.mark.parametrize("level", ["doctor", "viewer"])
async def test_readers_cannot_modify(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, admin_engine: AsyncEngine, level: str
) -> None:
    owner, reader = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, reader, level)
    async with as_user(app_engine, reader) as conn:
        r = await conn.execute(
            bound_text("update patients set full_name = 'x' where id = :p"), {"p": patient}
        )
        assert r.rowcount == 0


async def test_nobody_grants_access_to_themselves(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    owner, attacker = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    with pytest.raises(DBAPIError, match="row-level security"):
        await grant(app_engine, attacker, patient, attacker, "caregiver", direct=True)


async def test_owner_cannot_create_a_second_owner(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    owner, other = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    with pytest.raises(DBAPIError, match="row-level security"):
        await grant(app_engine, owner, patient, other, "owner")


async def test_caregiver_cannot_escalate_or_regrant(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    owner, carer, friend = [await make_user(owner_engine) for _ in range(3)]
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    with pytest.raises(DBAPIError, match="row-level security"):
        await grant(app_engine, carer, patient, friend, "viewer")
    async with as_user(app_engine, carer) as conn:
        r = await conn.execute(
            bound_text(
                "update patient_access set level = 'owner' where patient_id = :p and user_id = :u"
            ),
            {"p": patient, "u": carer},
        )
        assert r.rowcount == 0


async def test_admin_role_has_no_access_to_patient_data(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    await make_patient(app_engine, await make_user(owner_engine))
    for sql in (
        bound_text("select count(*) from patients"),
        bound_text("select count(*) from patient_access"),
        bound_text("select count(*) from consents"),
        bound_text("select count(*) from notifications"),
        bound_text("select count(*) from audit_logs"),
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with admin_engine.connect() as conn:
                await conn.execute(sql)


async def test_consent_for_an_adult_profile_cannot_be_given_by_a_caregiver(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    adult = await make_patient(app_engine, owner)
    child = await make_patient(app_engine, owner, minor=True)
    await grant(app_engine, owner, adult, carer, "caregiver")
    insert = bound_text(
        "insert into consents (user_id, patient_id, kind, version, granted)"
        " values (:u, :p, 'sensitive_data', '1', true)"
    )
    with pytest.raises(DBAPIError, match="row-level security"):
        async with as_user(app_engine, carer) as conn:
            await conn.execute(insert, {"u": carer, "p": adult})
    with pytest.raises(DBAPIError, match="row-level security"):  # adult profile, even by owner
        async with as_user(app_engine, owner) as conn:
            await conn.execute(insert, {"u": owner, "p": adult})
    async with as_user(app_engine, owner) as conn:  # the parent of a minor may
        await conn.execute(insert, {"u": owner, "p": child})


async def test_consents_are_append_only(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    user = await make_user(owner_engine)
    async with as_user(app_engine, user) as conn:
        await conn.execute(
            bound_text(
                "insert into consents (user_id, kind, version, granted)"
                " values (:u, 'terms', '1', true)"
            ),
            {"u": user},
        )
    for sql in ("update consents set granted = false", "delete from consents"):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_user(app_engine, user) as conn:
                await conn.execute(bound_text(sql))


async def test_notifications_are_private_and_only_read_at_is_writable(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    alice, bob = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, alice)
    async with as_user(app_engine, alice) as conn:
        await conn.execute(
            bound_text(
                "insert into consents (user_id, kind, version, granted)"
                " values (app_user_id(), 'caregiver_sharing', '1', true)"
            )
        )
    async with owner_engine.connect() as conn:
        bob_name = await scalar(
            conn, bound_text("select username::text from users where id = :u"), {"u": bob}
        )
    async with as_user(app_engine, alice) as conn:  # the invitation sends Bob its notice
        await conn.execute(
            bound_text("select invite_caregiver(:p, :n)"), {"p": patient, "n": bob_name}
        )
    async with as_user(app_engine, alice) as conn:
        assert await scalar(conn, bound_text("select count(*) from notifications")) == 0
    async with as_user(app_engine, bob) as conn:
        assert await scalar(conn, bound_text("select count(*) from notifications")) == 1
        await conn.execute(bound_text("update notifications set read_at = now()"))
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(app_engine, bob) as conn:
            await conn.execute(bound_text("update notifications set title_key = 'x'"))
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(app_engine, bob) as conn:
            await conn.execute(
                bound_text(
                    "insert into notifications (user_id, kind, title_key)"
                    " values (:u, 'reminder', 'x')"
                ),
                {"u": alice},
            )


@pytest.mark.parametrize(
    ("kind", "own_patient", "message"),
    [
        ("share_invite", False, "share_invite for someone else's profile"),
        ("review_ready", True, "recipient has no access to the patient"),
        ("reminder", True, "reminder to another user"),
        ("admin_reset", True, "admin kinds are not for users"),
    ],
)
async def test_users_cannot_send_unrelated_notifications(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    admin_engine: AsyncEngine,
    kind: str,
    own_patient: bool,
    message: str,
) -> None:
    owner, attacker, victim = [await make_user(owner_engine) for _ in range(3)]
    patient = await make_patient(app_engine, attacker if own_patient else owner)
    with pytest.raises(DBAPIError, match="notification not allowed"):
        async with as_user(app_engine, attacker) as conn:
            await conn.execute(
                bound_text("select notify(:u, :k, :p, null, 'x.y')"),
                {"u": victim, "k": kind, "p": patient},
            )


async def test_result_notification_reaches_a_caregiver_with_access(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text("select notify(:u, 'critical_pending', :p, null, 'result.critical')"),
            {"u": carer, "p": patient},
        )
    async with as_user(app_engine, carer) as conn:
        assert await scalar(conn, bound_text("select count(*) from notifications")) == 1


async def test_birth_date_cannot_be_rewritten_to_unlock_proxy_consent(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    adult = await make_patient(app_engine, owner)
    set_born = bound_text("update patients set birth_date = :d where id = :p")
    async with as_user(app_engine, owner) as conn:  # first time: allowed
        await conn.execute(set_born, {"d": date(1960, 5, 1), "p": adult})
    with pytest.raises(DBAPIError, match="birth date cannot be changed"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(set_born, {"d": date(2015, 5, 1), "p": adult})


async def test_an_empty_birth_date_cannot_be_filled_with_a_minor_date(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    adult = await make_patient(app_engine, owner)  # created without a birth date
    insert_consent = bound_text(
        "insert into consents (user_id, patient_id, kind, version, granted)"
        " values (:u, :p, 'cross_border', '1', true)"
    )
    with pytest.raises(DBAPIError, match="invalid birth date"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                bound_text("update patients set birth_date = :d where id = :p"),
                {"d": date(2015, 5, 1), "p": adult},
            )
    with pytest.raises(DBAPIError, match="row-level security"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(insert_consent, {"u": owner, "p": adult})


async def test_minor_status_ends_at_eighteen(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    child = await make_patient(app_engine, owner, minor=True)
    async with as_user(app_engine, owner) as conn:
        assert await scalar(conn, bound_text("select is_minor_patient(:p)"), {"p": child})
    async with owner_engine.connect() as conn, conn.begin():  # time passes (support correction)
        await conn.execute(
            bound_text(
                "update patients set birth_date = current_date - interval '18 years 1 day'"
                " where id = :p"
            ),
            {"p": child},
        )
    async with as_user(app_engine, owner) as conn:
        assert not await scalar(conn, bound_text("select is_minor_patient(:p)"), {"p": child})


async def test_audit_rows_cannot_be_attached_to_a_foreign_patient(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    owner, stranger = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    for sql, params in (
        (
            bound_text("select audit_write('profile.view', 'patient', null, :p, null)"),
            {"p": patient},
        ),
        (bound_text("select audit_write('Bad Action!', null, null, null, null)"), {}),
    ):
        with pytest.raises(DBAPIError, match="audit entry not allowed"):
            async with as_user(app_engine, stranger) as conn:
                await conn.execute(sql, params)
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text("select audit_write('profile.view', 'patient', null, :p, null)"),
            {"p": patient},
        )
    # Count with the owner role (the only one that can read audit_logs directly).
    async with owner_engine.connect() as conn:
        count = bound_text("select count(*) from audit_logs where actor_id = :a")
        assert await scalar(conn, count, {"a": stranger}) == 0
        assert await scalar(conn, count, {"a": owner}) == 1


async def test_create_patient_allows_one_own_profile_and_minor_children_only(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """0013: the database enforces what the API validates (a bypassed API changes nothing)."""
    user = await make_user(owner_engine)
    create = bound_text("select create_patient(:n, :r, :b, 'unknown'::sex)")
    adult_born = date(datetime.now(UTC).date().year - 30, 1, 1)
    await make_patient(app_engine, user)
    for name, rel, born, message in (
        ("Second self", "self", None, "own profile exists"),
        ("Parent", "parent", None, "invalid profile"),
        ("Grown child", "child", adult_born, "invalid profile"),
        ("Undated child", "child", None, "invalid profile"),
        ("Minor self", "self", date(datetime.now(UTC).date().year - 5, 1, 1), "invalid profile"),
        ("Ancient", "self", date(1850, 1, 1), "invalid profile"),
        ("   ", "child", date(datetime.now(UTC).date().year - 5, 1, 1), "invalid profile"),
    ):
        with pytest.raises(DBAPIError, match=message):
            async with as_user(app_engine, user) as conn:
                await conn.execute(create, {"n": name, "r": rel, "b": born})
    for _ in range(9):
        await make_patient(app_engine, user, minor=True)
    with pytest.raises(DBAPIError, match="too many profiles"):
        await make_patient(app_engine, user, minor=True)
    with pytest.raises(DBAPIError, match="no user context"):
        async with as_user(app_engine, None) as conn:
            await conn.execute(create, {"n": "X", "r": "self", "b": None})


async def test_minor_status_is_no_oracle_and_relation_is_fixed(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """0013: is_minor_patient answers only for readable profiles; relation cannot be edited."""
    owner, stranger = await make_user(owner_engine), await make_user(owner_engine)
    child = await make_patient(app_engine, owner, minor=True)
    is_minor = bound_text("select is_minor_patient(:p)")
    async with as_user(app_engine, owner) as conn:
        assert await scalar(conn, is_minor, {"p": child}) is True
    async with as_user(app_engine, stranger) as conn:
        assert await scalar(conn, is_minor, {"p": child}) is False
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                bound_text("update patients set relation = 'self' where id = :p"), {"p": child}
            )
