"""Review rights on draft lab reports (0036): who edits, deletes, confirms - drafts only."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import as_user, grant, make_patient, make_user, scalar

pytestmark = pytest.mark.db


async def _draft(owner_engine: AsyncEngine, patient: UUID, *, issues: list[str]) -> UUID:
    report = uuid4()
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into lab_reports (id, patient_id, collected_at) values (:r, :p, now())"
            ),
            {"r": report, "p": patient},
        )
        await conn.execute(
            bound_text(
                "insert into lab_results (report_id, patient_id, position, raw_name, raw_value,"
                " issues) values (:r, :p, 0, 'x', '1', cast(:i as text[]))"
            ),
            {"r": report, "p": patient, "i": issues},
        )
    return report


_EDIT = bound_text("update lab_results set raw_value = '2' where report_id = :r")
_DELETE = bound_text("delete from lab_results where report_id = :r")
_ADD = bound_text(
    "insert into lab_results (report_id, patient_id, position, raw_name, raw_value)"
    " values (:r, :p, 1, 'y', '3')"
)


async def test_a_caregiver_edits_adds_and_deletes_rows_of_a_draft(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    report = await _draft(owner_engine, patient, issues=[])
    async with as_user(app_engine, carer) as conn:
        assert (await conn.execute(_EDIT, {"r": report})).rowcount == 1
        await conn.execute(_ADD, {"r": report, "p": patient})
        assert (await conn.execute(_DELETE, {"r": report})).rowcount == 2


@pytest.mark.parametrize("level", ["doctor", "viewer", None])
async def test_readers_and_strangers_change_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, level: str | None
) -> None:
    owner, other = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    if level:
        await grant(app_engine, owner, patient, other, level)
    report = await _draft(owner_engine, patient, issues=[])
    async with as_user(app_engine, other) as conn:
        assert (await conn.execute(_EDIT, {"r": report})).rowcount == 0
        assert (await conn.execute(_DELETE, {"r": report})).rowcount == 0
    for sql in (_ADD, bound_text("select confirm_lab_report(:r)")):
        with pytest.raises(DBAPIError):
            async with as_user(app_engine, other) as conn:
                await conn.execute(sql, {"r": report, "p": patient})


async def test_a_confirmed_report_is_never_edited_again(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    report = await _draft(owner_engine, patient, issues=[])
    async with as_user(app_engine, owner) as conn:
        await conn.execute(bound_text("select confirm_lab_report(:r)"), {"r": report})
    async with as_user(app_engine, owner) as conn:
        assert (await conn.execute(_EDIT, {"r": report})).rowcount == 0
        assert (await conn.execute(_DELETE, {"r": report})).rowcount == 0
        changed = await conn.execute(
            bound_text("update lab_reports set collected_at = now() where id = :r"), {"r": report}
        )
        assert changed.rowcount == 0
        row = (
            await conn.execute(
                bound_text("select status::text as s, confirmed_by from lab_reports where id = :r"),
                {"r": report},
            )
        ).one()
    assert (row.s, row.confirmed_by) == ("confirmed", owner)
    with pytest.raises(DBAPIError, match="report not a draft"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(bound_text("select reject_lab_report(:r)"), {"r": report})
    async with owner_engine.connect() as conn:
        audited = await scalar(
            conn,
            bound_text(
                "select count(*) from audit_logs where action = 'report.confirm' and entity_id = :r"
            ),
            {"r": str(report)},
        )
    assert audited == 1


async def test_the_database_refuses_to_confirm_open_issues(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    report = await _draft(owner_engine, patient, issues=["implausible"])
    with pytest.raises(DBAPIError, match="report has open issues"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(bound_text("select confirm_lab_report(:r)"), {"r": report})
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text("update lab_results set acknowledged = issues where report_id = :r"),
            {"r": report},
        )
        await conn.execute(bound_text("select confirm_lab_report(:r)"), {"r": report})
    # an acknowledged issue must be one of the known codes
    other = await _draft(owner_engine, patient, issues=[])
    with pytest.raises(DBAPIError):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                bound_text(
                    "update lab_results set acknowledged = array['made_up'] where report_id = :r"
                ),
                {"r": other},
            )


async def test_a_rows_date_follows_its_report(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    report = await _draft(owner_engine, patient, issues=[])
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text(
                "update lab_reports set collected_at = '2025-01-02T03:04:00Z' where id = :r"
            ),
            {"r": report},
        )
        moved = await scalar(
            conn,
            bound_text(
                "select collected_at = '2025-01-02T03:04:00Z' from lab_results where report_id = :r"
            ),
            {"r": report},
        )
    assert moved


async def test_rows_never_move_and_status_is_never_written(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    a = await _draft(owner_engine, patient, issues=[])
    b = await _draft(owner_engine, patient, issues=[])
    for sql in (
        "update lab_results set report_id = :b where report_id = :a",
        "update lab_results set patient_id = gen_random_uuid() where report_id = :a",
        "update lab_reports set status = 'confirmed' where id = :a",
        "update lab_reports set confirmed_by = app_user_id() where id = :a",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_user(app_engine, owner) as conn:
                await conn.execute(bound_text(sql), {"a": a, "b": b})
