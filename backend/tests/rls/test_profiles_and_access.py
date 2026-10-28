"""RLS for patients, patient_access, consents, notifications (docs/03, docs/04 §6)."""

from datetime import UTC, datetime
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
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    owner = await make_user(admin_engine)
    patient = await make_patient(app_engine, owner)
    assert await _sees(app_engine, owner, patient) == 1
    async with as_user(app_engine, owner) as conn:
        r = await conn.execute(
            bound_text("update patients set full_name = 'Renamed' where id = :p"), {"p": patient}
        )
        assert r.rowcount == 1


async def test_stranger_cannot_read_write_or_delete(
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    owner, stranger = await make_user(admin_engine), await make_user(admin_engine)
    patient = await make_patient(app_engine, owner)
    assert await _sees(app_engine, stranger, patient) == 0
    async with as_user(app_engine, stranger) as conn:
        upd = await conn.execute(
            bound_text("update patients set full_name = 'x' where id = :p"), {"p": patient}
        )
        dele = await conn.execute(bound_text("delete from patients where id = :p"), {"p": patient})
        assert (upd.rowcount, dele.rowcount) == (0, 0)


async def test_no_user_context_sees_nothing(
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    patient = await make_patient(app_engine, await make_user(admin_engine))
    assert await _sees(app_engine, None, patient) == 0


async def test_patients_cannot_be_inserted_directly(
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    user = await make_user(admin_engine)
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
    admin_engine: AsyncEngine,
    expires: datetime | None,
    revoked: bool,
    visible: int,
) -> None:
    owner, doctor = await make_user(admin_engine), await make_user(admin_engine, "doctor")
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, doctor, "doctor", expires=expires, revoked=revoked)
    assert await _sees(app_engine, doctor, patient) == visible


@pytest.mark.parametrize("level", ["doctor", "viewer"])
async def test_readers_cannot_modify(
    app_engine: AsyncEngine, admin_engine: AsyncEngine, level: str
) -> None:
    owner, reader = await make_user(admin_engine), await make_user(admin_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, reader, level)
    async with as_user(app_engine, reader) as conn:
        r = await conn.execute(
            bound_text("update patients set full_name = 'x' where id = :p"), {"p": patient}
        )
        assert r.rowcount == 0


async def test_nobody_grants_access_to_themselves(
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    owner, attacker = await make_user(admin_engine), await make_user(admin_engine)
    patient = await make_patient(app_engine, owner)
    with pytest.raises(DBAPIError, match="row-level security"):
        await grant(app_engine, attacker, patient, attacker, "caregiver")


async def test_owner_cannot_create_a_second_owner(
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    owner, other = await make_user(admin_engine), await make_user(admin_engine)
    patient = await make_patient(app_engine, owner)
    with pytest.raises(DBAPIError, match="row-level security"):
        await grant(app_engine, owner, patient, other, "owner")


async def test_caregiver_cannot_escalate_or_regrant(
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    owner, carer, friend = [await make_user(admin_engine) for _ in range(3)]
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
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    await make_patient(app_engine, await make_user(admin_engine))
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


async def test_self_profile_created_by_admin_is_owned_by_the_user_not_the_admin(
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    admin, user = await make_user(admin_engine, "super_admin"), await make_user(admin_engine)
    async with admin_engine.connect() as conn, conn.begin():
        patient: UUID = await scalar(
            conn, bound_text("select create_self_profile(:u)"), {"u": user}
        )
    assert await _sees(app_engine, user, patient) == 1
    assert await _sees(app_engine, admin, patient) == 0


async def test_consent_for_an_adult_profile_cannot_be_given_by_a_caregiver(
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    owner, carer = await make_user(admin_engine), await make_user(admin_engine)
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


async def test_consents_are_append_only(app_engine: AsyncEngine, admin_engine: AsyncEngine) -> None:
    user = await make_user(admin_engine)
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
    app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    alice, bob = await make_user(admin_engine), await make_user(admin_engine)
    async with as_user(app_engine, alice) as conn:
        await conn.execute(
            bound_text("select notify(:u, 'share_invite', null, null, 'share.invite')"),
            {"u": bob},
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
