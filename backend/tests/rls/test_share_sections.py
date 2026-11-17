"""What a share link shows (0042; Phase 7.3, H37): each section only when the link includes it,
within its dates, confirmed results only, and a minor's profile only with its consents."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.core.security import new_opaque_token
from labtrack.db.sql import bound_text

from .conftest import as_user, make_patient, make_user, scalar
from .test_dashboard import _report, seeded  # noqa: F401 - the catalog (autouse)
from .test_share_links import PIN_HASH, _consented, _open, _owner

pytestmark = pytest.mark.db

_NOW = datetime.now(UTC)


async def _link(
    app_engine: AsyncEngine,
    owner: UUID,
    patient: UUID,
    scopes: list[str],
    date_from: date | None = None,
) -> str:
    _, token_hash = new_opaque_token()
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text(
                "select create_share_link(:p, :t, :h, cast(:s as text[]), :f, null, 7, null)"
            ),
            {"p": patient, "t": token_hash, "h": PIN_HASH, "s": scopes, "f": date_from},
        )
    session = await _open(app_engine, token_hash)
    assert session is not None
    return session


async def _section(app_engine: AsyncEngine, function: str, session: str) -> list[dict[str, object]]:
    async with as_user(app_engine, None) as conn:
        rows = await conn.execute(
            bound_text(f"select * from {function}(:s)"),  # noqa: S608
            {"s": session},
        )
        return [dict(r._mapping) for r in rows]


async def test_only_the_sections_of_the_link(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient = await _owner(app_engine, owner_engine)
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text(
                "insert into allergies (patient_id, client_id, substance) values (:p, :c, 'X')"
            ),
            {"p": patient, "c": uuid4()},
        )
    await _report(owner_engine, patient, _NOW - timedelta(days=3), {"CREA": "1.20"})
    labs_only = await _link(app_engine, owner, patient, ["labs"])
    assert [r["raw_value"] for r in await _section(app_engine, "share_labs", labs_only)] == ["1.20"]
    for function in (
        "share_summary",
        "share_allergies",
        "share_medications",
        "share_transplants",
        "share_events",
        "share_vitals",
    ):
        assert await _section(app_engine, function, labs_only) == [], function
    summary = await _link(app_engine, owner, patient, ["summary"])
    assert await _section(app_engine, "share_labs", summary) == []
    assert [r["substance"] for r in await _section(app_engine, "share_allergies", summary)] == ["X"]
    # a wrong or no session: nothing
    assert await _section(app_engine, "share_labs", new_opaque_token()[1]) == []


async def test_dates_and_confirmed_results_only(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient = await _owner(app_engine, owner_engine)
    await _report(owner_engine, patient, _NOW - timedelta(days=40), {"CREA": "1.40"})
    await _report(owner_engine, patient, _NOW - timedelta(days=5), {"CREA": "1.20"})
    await _report(owner_engine, patient, _NOW - timedelta(days=1), {"CREA": "9.90"},
                  status="needs_review")  # fmt: skip
    since = (_NOW - timedelta(days=10)).date()
    session = await _link(app_engine, owner, patient, ["labs"], date_from=since)
    assert [r["raw_value"] for r in await _section(app_engine, "share_labs", session)] == ["1.20"]


async def test_a_minors_profile_needs_its_own_consents(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    await _consented(owner_engine, owner)
    child = await make_patient(app_engine, owner, minor=True)
    _, token_hash = new_opaque_token()
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text(
                "select create_share_link(:p, :t, :h, array['summary'], null, null, 7, null)"
            ),
            {"p": child, "t": token_hash, "h": PIN_HASH},
        )
    # no consents given for the child's profile: the link does not open
    assert await _open(app_engine, token_hash) is None
    async with owner_engine.connect() as conn, conn.begin():
        for kind in ("terms", "privacy", "sensitive_data"):
            await conn.execute(
                bound_text(
                    "insert into consents (user_id, patient_id, kind, version, granted)"
                    " values (:u, :p, :k, 'v1', true)"
                ),
                {"u": owner, "p": child, "k": kind},
            )
    session = await _open(app_engine, token_hash)
    assert session is not None
    async with as_user(app_engine, None) as conn:
        assert await scalar(conn, bound_text("select share_profile(:s)"), {"s": session})


async def test_medicines_show_only_the_doses_of_the_range(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient = await _owner(app_engine, owner_engine)
    med = uuid4()
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into medications (id, patient_id, client_id, name, started_on, stopped_on)"
                " values (:m, :p, :c, 'Takro', '2026-01-01', '2026-06-01')"
            ),
            {"m": med, "p": patient, "c": uuid4()},
        )
        for day in (date(2026, 1, 1), date(2026, 2, 1), date(2026, 5, 1)):
            await conn.execute(
                bound_text(
                    "insert into medication_regimens (patient_id, medication_id, client_id,"
                    " effective_from, dose_unit, schedule) values (:p, :m, :c, :d,"
                    " 'mg', cast(:s as jsonb))"
                ),
                {
                    "p": patient,
                    "m": med,
                    "c": uuid4(),
                    "d": day,
                    "s": '{"type": "daily", "times": [{"at": "08:00", "amount": "1"}]}',
                },
            )
    _, token_hash = new_opaque_token()
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text(
                "select create_share_link(:p, :t, :h, array['meds'], cast('2026-01-15' as date),"
                " cast('2026-03-31' as date), 7, null)"
            ),
            {"p": patient, "t": token_hash, "h": PIN_HASH},
        )
    session = await _open(app_engine, token_hash)
    assert session is not None
    [m] = await _section(app_engine, "share_medications", session)
    # the dose in force on 15 Jan and the change of 1 Feb; not the change of May; no later stop
    regimens = m["regimens"]
    assert isinstance(regimens, list)
    assert [g["effective_from"] for g in regimens] == ["2026-01-01", "2026-02-01"]
    assert m["stopped_on"] is None
    assert "id" not in m


async def test_a_finished_session_and_a_signed_in_caller_read_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, patient = await _owner(app_engine, owner_engine)
    _, other = await _owner(app_engine, owner_engine)
    await _report(owner_engine, other, _NOW - timedelta(days=1), {"CREA": "7.77"})
    await _report(owner_engine, patient, _NOW - timedelta(days=1), {"CREA": "1.10"})
    session = await _link(app_engine, owner, patient, ["labs"])
    assert [r["raw_value"] for r in await _section(app_engine, "share_labs", session)] == ["1.10"]
    async with as_user(app_engine, owner) as conn:
        rows = await conn.execute(bound_text("select * from share_labs(:s)"), {"s": session})
        assert rows.first() is None
    async with as_user(app_engine, None) as conn:
        await conn.execute(bound_text("select share_session_end(:s)"), {"s": session})
    assert await _section(app_engine, "share_labs", session) == []
