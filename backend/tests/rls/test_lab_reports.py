"""RLS and shape for extraction runs, lab reports and results (0031; phi-table)."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, LiteralString
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import as_user, grant, make_patient, make_user, scalar

pytestmark = pytest.mark.db

_DOC = bound_text(
    "insert into documents (id, patient_id, client_id, storage_key, mime_type, size_bytes,"
    " sha256) values (:i, :p, :c, :k, 'application/pdf', 1024, :h)"
)
_RUN = bound_text(
    "insert into extraction_runs (id, patient_id, document_id, method, reader,"
    " pipeline_version) values (:i, :p, :d, 'local', 'unte.v1', 'p4.1')"
)
_REPORT = bound_text(
    "insert into lab_reports (id, patient_id, document_id, extraction_run_id, lab_name)"
    " values (:i, :p, :d, :r, 'lab')"
)
_RESULT = bound_text(
    "insert into lab_results (report_id, patient_id, position, raw_name, raw_value,"
    " value_numeric, ref_low, ref_high) values (:r, :p, :n, 'Creatinine', '1.12', 1.12, 0.6, 1.3)"
)
_COUNTS = bound_text(
    "select (select count(*) from extraction_runs where patient_id = :p)"
    " + (select count(*) from lab_reports where patient_id = :p)"
    " + (select count(*) from lab_results where patient_id = :p)"
)


async def _report(
    app_engine: AsyncEngine, user: UUID, patient: UUID, *, results: int = 2
) -> dict[str, UUID]:
    """A document with one run, one draft report and its results, written as `user`."""
    ids = {"doc": uuid4(), "run": uuid4(), "report": uuid4()}
    async with as_user(app_engine, user) as conn:
        await conn.execute(
            _DOC,
            {
                "i": ids["doc"],
                "p": patient,
                "c": uuid4(),
                "k": f"{patient}/{ids['doc']}/original",
                "h": sha256(ids["doc"].bytes).hexdigest(),
            },
        )
        await conn.execute(_RUN, {"i": ids["run"], "p": patient, "d": ids["doc"]})
        await conn.execute(
            _REPORT, {"i": ids["report"], "p": patient, "d": ids["doc"], "r": ids["run"]}
        )
        for n in range(results):
            await conn.execute(_RESULT, {"r": ids["report"], "p": patient, "n": n})
    return ids


async def _confirm(owner_engine: AsyncEngine, report: UUID) -> None:
    """As the review screen will (Phase 5): only the schema owner can here."""
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update lab_reports set status = 'confirmed', confirmed_at = now() where id = :i"
            ),
            {"i": report},
        )


async def _count(app_engine: AsyncEngine, user: UUID | None, patient: UUID) -> int:
    async with as_user(app_engine, user) as conn:
        return int(await scalar(conn, _COUNTS, {"p": patient}))


async def test_owner_writes_a_draft_and_the_database_records_the_writer(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _report(app_engine, owner, patient)
    assert await _count(app_engine, owner, patient) == 4
    async with as_user(app_engine, owner) as conn:
        row = (
            await conn.execute(
                bound_text(
                    "select r.status, r.recorded_by, x.recorded_by as run_by,"
                    " (select array_agg(value_numeric) from lab_results"
                    "   where report_id = r.id) as values"
                    " from lab_reports r join extraction_runs x on x.id = r.extraction_run_id"
                    " where r.id = :i"
                ),
                {"i": ids["report"]},
            )
        ).one()
    assert (row.status, row.recorded_by, row.run_by) == ("needs_review", owner, owner)
    assert [str(v) for v in row.values] == ["1.12", "1.12"]  # numeric, not float


async def test_a_draft_is_never_written_or_turned_confirmed_by_the_app(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """Rule 4: confirmation comes with the review screen (Phase 5), not with the reader."""
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _report(app_engine, owner, patient)
    statements: tuple[LiteralString, ...] = (
        "insert into lab_reports (patient_id, status) values (:p, 'confirmed')",
        "update lab_reports set status = 'confirmed' where patient_id = :p",
        "update lab_results set value_numeric = 9 where patient_id = :p",
        "update extraction_runs set raw_output = '{}' where patient_id = :p",
        "delete from lab_results where patient_id = :p",
    )
    for sql in statements:
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_user(app_engine, owner) as conn:
                await conn.execute(bound_text(sql), {"p": patient})
    async with owner_engine.connect() as conn, conn.begin():
        with pytest.raises(IntegrityError):  # confirmed needs confirmed_at
            await conn.execute(
                bound_text("update lab_reports set status = 'confirmed' where id = :i"),
                {"i": ids["report"]},
            )


async def test_rows_of_another_profile_cannot_be_linked(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    mine = await make_patient(app_engine, owner)
    other = await make_patient(app_engine, owner, minor=True)
    theirs = await _report(app_engine, owner, other)
    links: tuple[tuple[Any, dict[str, Any]], ...] = (
        (_RUN, {"i": uuid4(), "p": mine, "d": theirs["doc"]}),
        (_REPORT, {"i": uuid4(), "p": mine, "d": theirs["doc"], "r": None}),
        (_REPORT, {"i": uuid4(), "p": mine, "d": None, "r": theirs["run"]}),
        (_RESULT, {"r": theirs["report"], "p": mine, "n": 7}),
    )
    for sql, params in links:
        with pytest.raises(DBAPIError, match=r"foreign key|row-level security"):
            async with as_user(app_engine, owner) as conn:
                await conn.execute(sql, params)


async def test_the_database_refuses_odd_values(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _report(app_engine, owner, patient, results=0)
    statements: tuple[LiteralString, ...] = (
        "insert into lab_results (report_id, patient_id, position, raw_name, raw_value, issues)"
        " values (:r, :p, 0, 'x', '1', array['made_up'])",
        "insert into lab_results (report_id, patient_id, position, raw_name, raw_value,"
        " comparator) values (:r, :p, 0, 'x', '1', '~')",
        "insert into lab_results (report_id, patient_id, position, raw_name, raw_value)"
        " values (:r, :p, 0, 'x', '')",
        "insert into lab_results (report_id, patient_id, position, raw_name, raw_value,"
        " test_code) values (:r, :p, 0, 'x', '1', 'no_such_test')",
    )
    for sql in statements:
        with pytest.raises(IntegrityError):
            async with as_user(app_engine, owner) as conn:
                await conn.execute(bound_text(sql), {"r": ids["report"], "p": patient})


async def test_stranger_sees_and_changes_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, stranger = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _report(app_engine, owner, patient)
    assert await _count(app_engine, stranger, patient) == 0
    async with as_user(app_engine, stranger) as conn:
        for sql in (
            "delete from lab_reports where id = :i",
            "delete from extraction_runs where patient_id = :p",
        ):
            result = await conn.execute(bound_text(sql), {"i": ids["report"], "p": patient})
            assert result.rowcount == 0
    with pytest.raises(DBAPIError, match="row-level security"):
        async with as_user(app_engine, stranger) as conn:
            await conn.execute(
                bound_text("insert into lab_reports (patient_id) values (:p)"), {"p": patient}
            )
    assert await _count(app_engine, owner, patient) == 4


@pytest.mark.parametrize(
    ("expires", "revoked", "visible"),
    [(None, False, 3), (datetime.now(UTC) - timedelta(minutes=1), False, 0), (None, True, 0)],
)
async def test_shared_access_respects_expiry_and_revocation(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    expires: datetime | None,
    revoked: bool,
    visible: int,
) -> None:
    owner, doctor = await make_user(owner_engine), await make_user(owner_engine, "doctor")
    patient = await make_patient(app_engine, owner)
    ids = await _report(app_engine, owner, patient)
    await _confirm(owner_engine, ids["report"])
    await grant(app_engine, owner, patient, doctor, "doctor", expires=expires, revoked=revoked)
    assert await _count(app_engine, doctor, patient) == visible  # the report and its results


@pytest.mark.parametrize("level", ["doctor", "viewer"])
async def test_readers_cannot_write_or_delete(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, level: str
) -> None:
    owner, reader = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _report(app_engine, owner, patient)
    await grant(app_engine, owner, patient, reader, level)
    async with as_user(app_engine, reader) as conn:
        assert (
            await conn.execute(
                bound_text("delete from lab_reports where id = :i"), {"i": ids["report"]}
            )
        ).rowcount == 0
    with pytest.raises(DBAPIError, match="row-level security"):
        async with as_user(app_engine, reader) as conn:
            await conn.execute(
                bound_text("insert into lab_reports (patient_id) values (:p)"), {"p": patient}
            )


async def test_caregiver_adds_but_never_deletes_the_owners_report(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    mine = await _report(app_engine, carer, patient)
    owners = await _report(app_engine, owner, patient)
    async with as_user(app_engine, carer) as conn:
        for ids, expected in ((owners, 0), (mine, 1)):
            result = await conn.execute(
                bound_text("delete from lab_reports where id = :i"), {"i": ids["report"]}
            )
            assert result.rowcount == expected
        # runs belong to the profile's owner alone
        assert (
            await conn.execute(
                bound_text("delete from extraction_runs where id = :i"), {"i": mine["run"]}
            )
        ).rowcount == 0


async def test_no_user_context_admins_and_other_roles_see_nothing(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    admin_engine: AsyncEngine,
    admin_login_engine: AsyncEngine,
    maint_engine: AsyncEngine,
    push_engine: AsyncEngine,
) -> None:
    owner = await make_user(owner_engine)
    admins = (
        await make_user(owner_engine, "super_admin"),
        await make_user(owner_engine, "support"),
    )
    patient = await make_patient(app_engine, owner)
    ids = await _report(app_engine, owner, patient)
    await _confirm(owner_engine, ids["report"])
    assert await _count(app_engine, None, patient) == 0
    for admin in admins:
        assert await _count(app_engine, admin, patient) == 0  # rule 2a
    engines: Any = (admin_engine, admin_login_engine, maint_engine, push_engine)
    for engine in engines:
        selects: tuple[LiteralString, ...] = (
            "select count(*) from extraction_runs",
            "select count(*) from lab_reports",
            "select count(*) from lab_results",
        )
        for sql in selects:
            with pytest.raises(DBAPIError, match="permission denied"):
                async with engine.connect() as conn:
                    await conn.execute(bound_text(sql))


async def test_deleting_a_document_keeps_its_reports_and_drops_its_runs(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _report(app_engine, owner, patient)
    async with as_user(app_engine, owner) as conn:
        await conn.execute(bound_text("delete from documents where id = :i"), {"i": ids["doc"]})
        row = (
            await conn.execute(
                bound_text(
                    "select document_id, extraction_run_id, patient_id,"
                    " (select count(*) from lab_results where report_id = :i) as results,"
                    " (select count(*) from extraction_runs where patient_id = :p) as runs"
                    " from lab_reports where id = :i"
                ),
                {"i": ids["report"], "p": patient},
            )
        ).one()
    assert (row.document_id, row.extraction_run_id, row.patient_id) == (None, None, patient)
    assert (row.results, row.runs) == (2, 0)


async def test_deleting_a_report_or_the_profile_deletes_everything(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    first = await _report(app_engine, owner, patient)
    await _report(app_engine, owner, patient)
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text("delete from lab_reports where id = :i"), {"i": first["report"]}
        )
    assert await _count(app_engine, owner, patient) == 5  # its results went, the runs stay
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(bound_text("delete from patients where id = :p"), {"p": patient})
        assert await scalar(conn, _COUNTS, {"p": patient}) == 0


async def test_readers_see_confirmed_reports_only_never_drafts_or_runs(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """Rule 4: an unchecked draft reaches no one but the profile's writers."""
    owner, doctor = await make_user(owner_engine), await make_user(owner_engine, "doctor")
    patient = await make_patient(app_engine, owner)
    await _report(app_engine, owner, patient)
    await grant(app_engine, owner, patient, doctor, "doctor")
    assert await _count(app_engine, doctor, patient) == 0
    assert await _count(app_engine, owner, patient) == 4


async def test_caregiver_adds_results_only_to_their_own_draft(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    owners = await _report(app_engine, owner, patient)
    with pytest.raises(DBAPIError, match="row-level security"):
        async with as_user(app_engine, carer) as conn:
            await conn.execute(_RESULT, {"r": owners["report"], "p": patient, "n": 9})
    # nor to a confirmed report, even the owner's own
    await _confirm(owner_engine, owners["report"])
    with pytest.raises(DBAPIError, match="row-level security"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(_RESULT, {"r": owners["report"], "p": patient, "n": 9})


async def test_caregiver_never_deletes_a_confirmed_report_even_their_own(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    mine = await _report(app_engine, carer, patient)
    await _confirm(owner_engine, mine["report"])
    for user, deleted in ((carer, 0), (owner, 1)):
        async with as_user(app_engine, user) as conn:
            result = await conn.execute(
                bound_text("delete from lab_reports where id = :i"), {"i": mine["report"]}
            )
            assert result.rowcount == deleted


async def test_writer_columns_cannot_be_spoofed(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, other = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _report(app_engine, owner, patient, results=0)
    statements: tuple[LiteralString, ...] = (
        "insert into lab_reports (patient_id, recorded_by) values (:p, :u)",
        "insert into lab_reports (patient_id, confirmed_by) values (:p, :u)",
        "insert into lab_reports (patient_id, confirmed_at) values (:p, now())",
        "insert into extraction_runs (patient_id, document_id, method, reader,"
        " pipeline_version, recorded_by) values (:p, :d, 'local', 'x', 'x', :u)",
        "insert into lab_results (report_id, patient_id, position, raw_name, raw_value,"
        " recorded_by) values (:r, :p, 0, 'x', '1', :u)",
        "insert into lab_results (report_id, patient_id, position, raw_name, raw_value,"
        " collected_at) values (:r, :p, 0, 'x', '1', now())",
    )
    for sql in statements:
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_user(app_engine, owner) as conn:
                await conn.execute(
                    bound_text(sql),
                    {"p": patient, "u": other, "d": ids["doc"], "r": ids["report"]},
                )


async def test_a_result_takes_its_reports_date_and_writer(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    report = uuid4()
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text(
                "insert into lab_reports (id, patient_id, collected_at)"
                " values (:i, :p, '2025-08-18T03:00:00Z')"
            ),
            {"i": report, "p": patient},
        )
        await conn.execute(_RESULT, {"r": report, "p": patient, "n": 0})
        row = (
            await conn.execute(
                bound_text(
                    "select collected_at, recorded_by from lab_results where report_id = :r"
                ),
                {"r": report},
            )
        ).one()
    assert row.collected_at == datetime(2025, 8, 18, 3, tzinfo=UTC)
    assert row.recorded_by == owner


@pytest.mark.parametrize("level", ["doctor", "viewer"])
async def test_readers_write_no_run_or_result(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, level: str
) -> None:
    owner, reader = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _report(app_engine, owner, patient)
    await grant(app_engine, owner, patient, reader, level)
    writes: tuple[tuple[Any, dict[str, Any]], ...] = (
        (_RUN, {"i": uuid4(), "p": patient, "d": ids["doc"]}),
        (_RESULT, {"r": ids["report"], "p": patient, "n": 9}),
    )
    for sql, params in writes:
        with pytest.raises(DBAPIError, match="row-level security"):
            async with as_user(app_engine, reader) as conn:
                await conn.execute(sql, params)
    async with as_user(app_engine, reader) as conn:
        assert (
            await conn.execute(
                bound_text("delete from extraction_runs where id = :i"), {"i": ids["run"]}
            )
        ).rowcount == 0


async def test_stranger_adds_no_run_or_result(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, stranger = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _report(app_engine, owner, patient)
    writes: tuple[tuple[Any, dict[str, Any]], ...] = (
        (_RUN, {"i": uuid4(), "p": patient, "d": ids["doc"]}),
        (_RESULT, {"r": ids["report"], "p": patient, "n": 9}),
    )
    for sql, params in writes:
        with pytest.raises(DBAPIError, match="row-level security"):
            async with as_user(app_engine, stranger) as conn:
                await conn.execute(sql, params)


_END_ACCESS: dict[str, Any] = {
    "expired": bound_text(
        "update patient_access set expires_at = now() - interval '1 minute'"
        " where patient_id = :p and user_id = :u"
    ),
    "revoked": bound_text(
        "update patient_access set revoked_at = now() where patient_id = :p and user_id = :u"
    ),
}


@pytest.mark.parametrize("ended", ["expired", "revoked"])
async def test_a_caregiver_whose_access_ended_writes_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, ended: str
) -> None:
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    mine = await _report(app_engine, carer, patient)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(_END_ACCESS[ended], {"p": patient, "u": carer})
    assert await _count(app_engine, carer, patient) == 0
    async with as_user(app_engine, carer) as conn:
        assert (
            await conn.execute(
                bound_text("delete from lab_reports where id = :i"), {"i": mine["report"]}
            )
        ).rowcount == 0
    with pytest.raises(DBAPIError, match="row-level security"):
        await _report(app_engine, carer, patient)


async def test_a_deleted_profile_is_closed_even_to_its_owner(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    ids = await _report(app_engine, owner, patient)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update patients set deleted_at = now() where id = :p"), {"p": patient}
        )
    assert await _count(app_engine, owner, patient) == 0
    with pytest.raises(DBAPIError, match="row-level security"):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(_RESULT, {"r": ids["report"], "p": patient, "n": 9})
