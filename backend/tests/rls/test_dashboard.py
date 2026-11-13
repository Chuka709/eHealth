"""RLS and shape for `latest_results` and `dashboard_cards` (0038; phi-table; rule 4, 2a)."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, LiteralString
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text
from labtrack.seed import run

from .conftest import as_user, grant, make_patient, make_user, scalar

pytestmark = pytest.mark.db

_NOW = datetime.now(UTC)
_LATEST = bound_text(
    "select test_code, raw_value from latest_results where patient_id = :p order by test_code"
)
_CARDS = bound_text("select test_codes from dashboard_cards where patient_id = :p")
_PUT = bound_text("insert into dashboard_cards (patient_id, test_codes) values (:p, :c)")


@pytest.fixture(scope="module", autouse=True)
async def seeded() -> None:
    """The catalog (test codes are foreign keys)."""
    await run(os.environ["MIGRATION_DATABASE_URL"], Path(os.environ.get("SEED_DIR", "/seed")))


async def _report(
    owner_engine: AsyncEngine,
    patient: UUID,
    at: datetime,
    values: dict[str, str],
    *,
    status: str = "confirmed",
) -> UUID:
    """A report with one result per test, as review leaves it (only the schema owner here)."""
    report = uuid4()
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into lab_reports (id, patient_id, lab_name, collected_at, status,"
                " confirmed_at) values (:i, :p, 'lab', :at, cast(:s as report_status),"
                " case when :s = 'confirmed' then now() end)"
            ),
            {"i": report, "p": patient, "at": at, "s": status},
        )
        for n, (code, value) in enumerate(values.items()):
            await conn.execute(
                bound_text(
                    "insert into lab_results (report_id, patient_id, position, test_code,"
                    " raw_name, raw_value, value_numeric, value_canonical, flag)"
                    " values (:r, :p, :n, :c, :c, cast(:v as text), cast(:v as numeric),"
                    " cast(:v as numeric), 'normal')"
                ),
                {"r": report, "p": patient, "n": n, "c": code, "v": value},
            )
    return report


async def _cards(conn: Any, patient: UUID) -> Any:
    return (await conn.execute(_CARDS, {"p": patient})).scalar_one_or_none()


async def _latest(app_engine: AsyncEngine, user: UUID | None, patient: UUID) -> list[Any]:
    async with as_user(app_engine, user) as conn:
        return [tuple(r) for r in (await conn.execute(_LATEST, {"p": patient})).all()]


async def test_latest_is_the_newest_confirmed_value_of_each_test(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await _report(owner_engine, patient, _NOW - timedelta(days=30), {"CREA": "1.40", "K": "4.1"})
    await _report(owner_engine, patient, _NOW - timedelta(days=10), {"CREA": "1.20"})
    # newer, but not confirmed: a draft or a rejected report never reaches the dashboard (rule 4)
    await _report(owner_engine, patient, _NOW - timedelta(days=1), {"CREA": "9.90"},
                  status="needs_review")  # fmt: skip
    await _report(owner_engine, patient, _NOW, {"K": "7.70"}, status="rejected")
    assert await _latest(app_engine, owner, patient) == [("CREA", "1.20"), ("K", "4.1")]


async def test_a_result_without_a_test_or_date_is_not_latest(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    report = await _report(owner_engine, patient, _NOW, {"CREA": "1.10"})
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into lab_results (report_id, patient_id, position, raw_name, raw_value)"
                " values (:r, :p, 9, 'Unknown test', '5')"
            ),
            {"r": report, "p": patient},
        )
    assert await _latest(app_engine, owner, patient) == [("CREA", "1.10")]


async def test_latest_follows_the_reader_rules(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await _report(owner_engine, patient, _NOW, {"CREA": "1.10"})
    doctor, carer, viewer, stranger = [await make_user(owner_engine) for _ in range(4)]
    expired, revoked = await make_user(owner_engine), await make_user(owner_engine)
    await grant(app_engine, owner, patient, doctor, "doctor")
    await grant(app_engine, owner, patient, viewer, "viewer")
    await grant(app_engine, owner, patient, carer, "caregiver")
    soon = _NOW + timedelta(seconds=1)
    await grant(app_engine, owner, patient, expired, "viewer", expires=soon)
    await grant(app_engine, owner, patient, revoked, "viewer", revoked=True)
    for reader in (doctor, carer, viewer):
        assert await _latest(app_engine, reader, patient) == [("CREA", "1.10")]
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update patient_access set expires_at = now() - interval '1 minute'"
                " where user_id = :u"
            ),
            {"u": expired},
        )
    for user in (stranger, expired, revoked, None):
        assert await _latest(app_engine, user, patient) == []
    for role in ("super_admin", "support"):
        admin = await make_user(owner_engine, role)
        assert await _latest(app_engine, admin, patient) == []  # rule 2a


async def test_the_view_is_not_a_snapshot_and_runs_as_the_caller(
    owner_engine: AsyncEngine,
) -> None:
    async with owner_engine.connect() as conn:
        kind = await scalar(
            conn, bound_text("select relkind::text from pg_class where relname = 'latest_results'")
        )
        options = await scalar(
            conn,
            bound_text("select reloptions from pg_class where relname = 'latest_results'"),
        )
    assert kind == "v"  # not a materialized view: it would bypass RLS
    assert "security_invoker=true" in options
    assert "security_barrier=true" in options


async def test_database_roles_other_than_the_app_have_no_access(
    owner_engine: AsyncEngine,
) -> None:
    async with owner_engine.connect() as conn:
        for role in ("labtrack_admin", "labtrack_admin_login", "labtrack_maint", "labtrack_push"):
            for rel in ("latest_results", "dashboard_cards"):
                for priv in ("select", "insert", "update", "delete"):
                    assert not await scalar(
                        conn,
                        bound_text("select has_table_privilege(:r, :t, :p)"),
                        {"r": role, "t": rel, "p": priv},
                    ), (role, rel, priv)


async def test_writers_keep_the_cards_and_the_database_records_who(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    async with as_user(app_engine, owner) as conn:
        await conn.execute(_PUT, {"p": patient, "c": ["CREA", "TAC"]})
    async with as_user(app_engine, carer) as conn:
        await conn.execute(
            bound_text("update dashboard_cards set test_codes = :c where patient_id = :p"),
            {"p": patient, "c": ["TAC", "CREA", "K"]},
        )
        assert await _cards(conn, patient) == ["TAC", "CREA", "K"]
    async with owner_engine.connect() as conn:
        row = (
            await conn.execute(
                bound_text(
                    "select recorded_by, updated_by, updated_at from dashboard_cards"
                    " where patient_id = :p"
                ),
                {"p": patient},
            )
        ).one()
    assert (row.recorded_by, row.updated_by) == (owner, carer)
    assert row.updated_at is not None
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text("delete from dashboard_cards where patient_id = :p"), {"p": patient}
        )
        assert await _cards(conn, patient) is None


async def test_readers_strangers_and_admins_neither_see_nor_write_the_cards(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    async with as_user(app_engine, owner) as conn:
        await conn.execute(_PUT, {"p": patient, "c": ["CREA"]})
    doctor, viewer, stranger = [await make_user(owner_engine) for _ in range(3)]
    await grant(app_engine, owner, patient, doctor, "doctor")
    await grant(app_engine, owner, patient, viewer, "viewer")
    admins = [await make_user(owner_engine, r) for r in ("super_admin", "support")]
    for user in (doctor, viewer, stranger, None, *admins):
        async with as_user(app_engine, user) as conn:
            assert await _cards(conn, patient) is None
            for sql in (
                "update dashboard_cards set test_codes = '{}' where patient_id = :p",
                "delete from dashboard_cards where patient_id = :p",
            ):
                assert (await conn.execute(bound_text(sql), {"p": patient})).rowcount == 0
        with pytest.raises(DBAPIError, match="row-level security"):
            async with as_user(app_engine, user) as conn:
                await conn.execute(_PUT, {"p": patient, "c": ["K"]})
    async with as_user(app_engine, owner) as conn:
        assert await _cards(conn, patient) == ["CREA"]


async def test_a_former_carer_or_a_deleted_profile_neither_sees_nor_writes(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, expired, revoked = [await make_user(owner_engine) for _ in range(3)]
    patient = await make_patient(app_engine, owner)
    async with as_user(app_engine, owner) as conn:
        await conn.execute(_PUT, {"p": patient, "c": ["CREA"]})
    soon = _NOW + timedelta(seconds=1)
    await grant(app_engine, owner, patient, expired, "caregiver", expires=soon)
    await grant(app_engine, owner, patient, revoked, "caregiver", revoked=True)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update patient_access set expires_at = now() - interval '1 minute'"
                " where user_id = :u"
            ),
            {"u": expired},
        )

    async def shut_out(user: UUID) -> None:
        async with as_user(app_engine, user) as conn:
            assert await _cards(conn, patient) is None
            for sql in (
                "update dashboard_cards set test_codes = '{}' where patient_id = :p",
                "delete from dashboard_cards where patient_id = :p",
            ):
                assert (await conn.execute(bound_text(sql), {"p": patient})).rowcount == 0

    for user in (expired, revoked):
        await shut_out(user)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update patients set deleted_at = now() where id = :p"), {"p": patient}
        )
    await shut_out(owner)


async def test_a_retired_test_does_not_block_other_changes(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    child = await make_patient(app_engine, owner, minor=True)
    async with as_user(app_engine, owner) as conn:
        await conn.execute(_PUT, {"p": patient, "c": ["CREA", "ESR"]})
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update test_catalog set is_active = false where code = 'ESR'")
        )
    try:
        upd = bound_text("update dashboard_cards set test_codes = :c where patient_id = :p")
        async with as_user(app_engine, owner) as conn:
            await conn.execute(upd, {"p": patient, "c": ["ESR", "CREA", "K"]})
        with pytest.raises(DBAPIError, match="dashboard_cards"):
            async with as_user(app_engine, owner) as conn:  # not newly added
                await conn.execute(_PUT, {"p": child, "c": ["ESR"]})
    finally:
        async with owner_engine.connect() as conn, conn.begin():
            await conn.execute(
                bound_text("update test_catalog set is_active = true where code = 'ESR'")
            )


async def test_the_database_checks_the_list(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    bad: tuple[list[str | None], ...] = (
        ["CREA", "CREA"],
        ["NOPE"],
        ["CREA", None],
        ["CREA", *(f"X{n}" for n in range(24))],
    )
    for codes in bad:
        with pytest.raises(DBAPIError, match="dashboard_cards"):
            async with as_user(app_engine, owner) as conn:
                await conn.execute(_PUT, {"p": patient, "c": codes})
    async with as_user(app_engine, owner) as conn:
        await conn.execute(_PUT, {"p": patient, "c": []})  # chose none: not the organ's cards
        assert await _cards(conn, patient) == []


async def test_writer_columns_and_truncate_belong_to_the_database(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, other = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    head: LiteralString = "insert into dashboard_cards (patient_id, test_codes, "
    tail: LiteralString = ") values (:p, '{}', :v)"
    cases: tuple[tuple[LiteralString, object], ...] = (
        (head + "recorded_by" + tail, other),
        (head + "updated_by" + tail, other),
        (head + "created_at" + tail, _NOW),
    )
    for sql, value in cases:
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_user(app_engine, owner) as conn:
                await conn.execute(bound_text(sql), {"p": patient, "v": value})
    for sql in (
        "update dashboard_cards set patient_id = :p",
        "truncate dashboard_cards",
        "insert into latest_results (id) values (gen_random_uuid())",
    ):
        with pytest.raises(DBAPIError, match=r"permission denied|cannot insert into view"):
            async with as_user(app_engine, owner) as conn:
                await conn.execute(bound_text(sql), {"p": patient})
