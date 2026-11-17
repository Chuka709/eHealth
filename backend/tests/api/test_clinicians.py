"""A doctor's targets and notes, and level statistics (Phase 7.4)."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import ClientFactory
from .test_caregivers import _username
from .test_dashboard import seeded  # noqa: F401 - fixture (the catalog)
from .test_patients import _create, _signed_in

pytestmark = pytest.mark.db


def _today() -> date:
    """Ulaanbaatar's day, as the database's local_today() reads it."""
    return datetime.now(ZoneInfo("Asia/Ulaanbaatar")).date()


async def _doctor_on(
    c: AsyncClient, owner_engine: AsyncEngine
) -> tuple[dict[str, str], str, dict[str, str]]:
    _, owner = await _signed_in(c, owner_engine)
    _, profile = await _create(c, owner, full_name="Бат", relation="self")
    base = f"/api/v1/patients/{profile['id']}"
    doc_id, doc = await _signed_in(c, owner_engine)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update users set role = 'doctor' where id = :u"), {"u": doc_id}
        )
    r = await c.post(
        f"{base}/share-invitations",
        json={"username": await _username(owner_engine, doc_id), "level": "doctor", "days": 30},
        headers=owner,
    )
    assert r.status_code == 202
    [inv] = (await c.get("/api/v1/me/share-invitations", headers=doc)).json()
    await c.post(
        "/api/v1/me/share-invitations/respond",
        json={"invitation_id": inv["id"], "accept": True},
        headers=doc,
    )
    return owner, base, doc


async def test_doctor_sets_a_target_and_a_note_the_owner_reads_them(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, doc = await _doctor_on(c, owner_engine)
        pid = base.rsplit("/", 1)[1]
        r = await c.post(
            "/api/v1/me/doctor/targets",
            json={"patient_id": pid, "test_code": "TAC", "low": "5", "high": "8,5",
                  "valid_from": _today().isoformat(), "note": "trough"},
            headers=doc,
        )  # fmt: skip
        assert r.status_code == 201
        r = await c.post(
            "/api/v1/me/doctor/notes", json={"patient_id": pid, "body": "Recheck"}, headers=doc
        )
        assert r.status_code == 201
        [t] = (await c.get(f"{base}/targets", headers=owner)).json()
        assert (t["low"], t["high"], t["unit"]) == ("5", "8.5", "ng/mL")
        [n] = (await c.get(f"{base}/doctor-notes", headers=owner)).json()
        assert (n["body"], n["mine"]) == ("Recheck", False)
        # the owner cannot write either
        r = await c.post(
            "/api/v1/me/doctor/notes", json={"patient_id": pid, "body": "x"}, headers=owner
        )
        assert r.status_code == 403
        for bad in ({"low": "9", "high": "5"}, {}):
            r = await c.post(
                "/api/v1/me/doctor/targets",
                json={
                    "patient_id": pid,
                    "test_code": "TAC",
                    "valid_from": _today().isoformat(),
                    **bad,
                },
                headers=doc,
            )
            assert r.status_code == 422, bad


async def test_level_stats_are_numbers_only_with_a_reason_when_too_few(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, doc = await _doctor_on(c, owner_engine)
        pid = UUID(base.rsplit("/", 1)[1])
        r = await c.get(f"{base}/level-stats/TAC", headers=owner)
        assert r.status_code == 200
        assert r.json()["reason"] == "no_transplant"
        now = datetime.now(UTC)
        async with owner_engine.connect() as conn, conn.begin():
            await conn.execute(
                bound_text(
                    "insert into transplants (patient_id, client_id, organ, transplant_date,"
                    " date_precision, country, hospital)"
                    " values (:p, :c, 'kidney', :d, 'day', 'MN', 'H')"
                ),
                {"p": pid, "c": uuid4(), "d": (now - timedelta(days=700)).date()},
            )
            for i, v in enumerate(["6.0", "7.5", "9.1", "5.4", "8.2", "7.0"]):
                report = uuid4()
                at = now - timedelta(days=30 * (i + 1))
                await conn.execute(
                    bound_text(
                        "insert into lab_reports (id, patient_id, lab_name, collected_at, status,"
                        " confirmed_at) values (:r, :p, 'lab', :at, 'confirmed', now())"
                    ),
                    {"r": report, "p": pid, "at": at},
                )
                await conn.execute(
                    bound_text(
                        "insert into lab_results (report_id, patient_id, position, test_code,"
                        " raw_name, raw_value, value_numeric, value_canonical, unit_canonical,"
                        " flag, collected_at) values (:r, :p, 0, 'TAC', 'TAC', cast(:v as text),"
                        " cast(:v as numeric), cast(:v as numeric), 'ng/mL', 'normal', :at)"
                    ),
                    {"r": report, "p": pid, "v": v, "at": at},
                )
        body = (await c.get(f"{base}/level-stats/TAC", headers=doc)).json()
        assert body["reason"] is None
        assert body["n"] == 6
        assert body["cv_percent"] is not None
        assert isinstance(body["mean"], str)
        assert isinstance(body["sd"], str)
        assert len(body["values"]) == 6
        assert {v["lab"] for v in body["values"]} == {"lab"}
        assert body["labs"] == ["lab"]
        assert body["lab_unknown"] == 0
        assert body["settle_months"] == 6
        assert body["in_target_percent"] is None  # no target set
        # the patient gets CV% alone: no mean, SD or values (Q63-7)
        mine = (await c.get(f"{base}/level-stats/TAC", headers=owner)).json()
        assert mine["cv_percent"] == body["cv_percent"]
        assert (mine["mean"], mine["sd"], mine["values"]) == (None, None, [])
        assert (mine["with_target"], mine["in_target_percent"], mine["labs"]) == (0, None, [])
        # only tacrolimus for now (Q63): another test gives no number
        assert (await c.get(f"{base}/level-stats/CREA", headers=owner)).status_code == 422
