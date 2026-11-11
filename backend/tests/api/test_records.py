"""Transplants, medications, dose history and intakes over the API (Phase 2.2; H8, H20)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text
from labtrack.records import service

from .conftest import ClientFactory
from .test_patients import _create, _signed_in

pytestmark = pytest.mark.db

Headers = dict[str, str]


async def _profile(c: AsyncClient, owner_engine: AsyncEngine) -> tuple[UUID, Headers, str]:
    uid, h = await _signed_in(c, owner_engine)
    _, me = await _create(c, h, full_name="Бат", relation="self")
    return uid, h, f"/api/v1/patients/{me['id']}"


def _transplant(**extra: object) -> dict[str, Any]:
    return {
        "client_id": str(uuid4()),
        "organ": "kidney",
        "transplant_date": "2021-06-14",
        "country": "MN",
        "hospital": "Улсын нэгдүгээр төв эмнэлэг",
        **extra,
    }


def _medication(**extra: object) -> dict[str, Any]:
    return {
        "client_id": str(uuid4()),
        "catalog_code": None,
        "name": "Такролимус",
        "strength": "1 мг",
        "regimen": {
            "client_id": str(uuid4()),
            "effective_from": "2026-01-01",
            "dose_unit": "mg",
            # tacrolimus 2 mg in the morning, 1.5 mg in the evening: one regimen
            "schedule": {
                "type": "daily",
                "times": [{"at": "20:00", "amount": "1,5"}, {"at": "08:00", "amount": "2"}],
            },
        },
        **extra,
    }


async def _grant(owner_engine: AsyncEngine, base: str, user: UUID, level: str) -> None:
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into patient_access (patient_id, user_id, level, granted_by)"
                " select cast(:p as uuid), :u, cast(:l as access_level), a.user_id"
                " from patient_access a where a.patient_id = cast(:p as uuid)"
                " and a.level = 'owner'"
            ),
            {"p": base.rsplit("/", 1)[1], "u": user, "l": level},
        )


async def _audit(owner_engine: AsyncEngine, base: str) -> list[tuple[str, str | None]]:
    async with owner_engine.connect() as conn:
        rows = await conn.execute(
            bound_text(
                "select action, diff::text from audit_logs where patient_id = cast(:p as uuid)"
                " order by id"
            ),
            {"p": base.rsplit("/", 1)[1]},
        )
        return [(r.action, r.diff) for r in rows]


# --- transplants --------------------------------------------------------------------------------


async def test_transplant_create_is_idempotent_and_partial_dates_are_approximate(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, h, base = await _profile(c, owner_engine)
        body = _transplant(transplant_date="2019-05-20", date_precision="month")
        r = await c.post(f"{base}/transplants", json=body, headers=h)
        assert r.status_code == 201
        created = r.json()
        assert created["transplant_date"] == "2019-05-01"  # stored as the month's first day
        assert created["elapsed"]["approximate"] is True
        again = await c.post(f"{base}/transplants", json=body, headers=h)
        assert (again.status_code, again.json()["id"]) == (200, created["id"])
        assert len((await c.get(f"{base}/transplants", headers=h)).json()) == 1

        future = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
        for bad in (
            {"transplant_date": future},
            {"country": "mn"},
            {"hospital": ""},
            {"recipient_blood_type": "C+"},
            {"graft_status_date": "2010-01-01"},  # before the transplant
            {"notes": "a" + chr(0x202E) + "b"},
        ):
            r = await c.post(f"{base}/transplants", json=_transplant(**bad), headers=h)
            assert r.status_code == 422, bad


async def test_transplant_edit_and_delete(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, h, base = await _profile(c, owner_engine)
        carer, carer_h = await _signed_in(c, owner_engine)
        await _grant(owner_engine, base, carer, "caregiver")
        t = (await c.post(f"{base}/transplants", json=_transplant(), headers=h)).json()
        url = f"{base}/transplants/{t['id']}"
        body = {k: v for k, v in _transplant(cmv_donor="pos").items() if k != "client_id"}
        r = await c.put(url, json=body, headers=carer_h)
        assert (r.status_code, r.json()["cmv_donor"]) == (200, "pos")
        r = await c.delete(url, headers=carer_h)  # history is the owner's to erase
        assert (r.status_code, r.json()["code"]) == (403, "record.delete_not_allowed")
        assert (await c.delete(url, headers=h)).status_code == 204
        r = await c.get(url, headers=h)
        assert (r.status_code, r.json()["code"]) == (404, "transplant.not_found")
        log = await _audit(owner_engine, base)
        assert [a for a, _ in log if a.startswith("transplant.")] == [
            "transplant.create",
            "transplant.update",
            "transplant.delete",
        ]
        assert all("Улсын" not in (d or "") and "pos" not in (d or "") for _, d in log)


# --- medications and dose history (H8) ------------------------------------------------------------


def _amounts(regimen: dict[str, Any]) -> list[tuple[str, str]]:
    return [(t["at"], t["amount"]) for t in regimen["schedule"]["times"]]


def _change(days_from_today: int, morning: str, evening: str) -> dict[str, Any]:
    return {
        "client_id": str(uuid4()),
        "effective_from": (datetime.now(UTC) + timedelta(days=days_from_today)).date().isoformat(),
        "dose_unit": "mg",
        "schedule": {
            "type": "daily",
            "times": [{"at": "08:00", "amount": morning}, {"at": "20:00", "amount": evening}],
        },
        "changed_by_note": "такролимусын түвшнээр",
    }


async def test_dose_changes_add_history_and_never_edit_it(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, h, base = await _profile(c, owner_engine)
        r = await c.post(f"{base}/medications", json=_medication(), headers=h)
        assert r.status_code == 201
        med = r.json()
        assert med["is_current"] is True
        assert _amounts(med["current_regimen"]) == [("08:00", "2"), ("20:00", "1.5")]
        assert med["current_regimen"]["dose_unit"] == "mg"

        url = f"{base}/medications/{med['id']}/regimens"
        change = _change(-1, "1,5", "1")
        r = await c.post(url, json=change, headers=h)
        assert r.status_code == 201
        assert _amounts(r.json()["current_regimen"]) == [("08:00", "1.5"), ("20:00", "1")]
        assert len(r.json()["regimens"]) == 2
        assert (await c.post(url, json=change, headers=h)).status_code == 200  # a retry

        # a change from a coming day: not today's dose, but announced for reminders ahead
        r = await c.post(url, json=_change(3, "1", "1"), headers=h)
        body = r.json()
        assert _amounts(body["current_regimen"]) == [("08:00", "1.5"), ("20:00", "1")]
        assert _amounts(body["next_regimen"]) == [("08:00", "1"), ("20:00", "1")]

        for bad in (
            {"schedule": {"type": "daily", "times": [{"at": "08:00", "amount": 2.5}]}},
            {"schedule": {"type": "daily", "times": [{"at": "08:00", "amount": "1,000"}]}},
            {"schedule": {"type": "daily", "times": [{"at": "08:00", "amount": "0"}]}},
            {"schedule": {"type": "daily", "times": [{"at": "08:00", "amount": "0.00001"}]}},
            {"schedule": {"type": "daily", "times": [{"at": "8:00"}]}},
            {"schedule": {"type": "weekly", "times": [{"at": "08:00"}]}},
            {"dose_unit": None},  # amounts without a unit
            {"dose_unit": "мкг"},  # one spelling per unit
            {"dose_unit": "other"},  # needs its text
            {"dose_amount": "2"},  # amounts go on the times (dose_amount is prn's)
            {"effective_from": "2099-01-01"},
        ):
            body = {**change, "client_id": str(uuid4()), **bad}
            assert (await c.post(url, json=body, headers=h)).status_code == 422, bad
        prn = {
            "client_id": str(uuid4()),
            "effective_from": "2026-01-01",
            "dose_amount": "50000",
            "dose_unit": "iu",
            "schedule": {"type": "prn"},
        }
        assert (await c.post(url, json=prn, headers=h)).status_code == 201


async def test_a_future_change_entered_by_mistake_is_voided(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, h, base = await _profile(c, owner_engine)
        med = (await c.post(f"{base}/medications", json=_medication(), headers=h)).json()
        url = f"{base}/medications/{med['id']}"
        r = await c.post(f"{url}/regimens", json=_change(200, "9", "9"), headers=h)
        mistake = r.json()["next_regimen"]
        r = await c.post(
            f"{url}/regimens/{mistake['id']}/void", json={"reason": "он буруу"}, headers=h
        )
        assert r.status_code == 200
        assert r.json()["next_regimen"] is None
        voided = next(x for x in r.json()["regimens"] if x["id"] == mistake["id"])
        assert (voided["void_reason"], voided["voided_at"] is not None) == ("он буруу", True)
        again = await c.post(
            f"{url}/regimens/{mistake['id']}/void", json={"reason": "x"}, headers=h
        )
        assert (again.status_code, again.json()["code"]) == (404, "regimen.not_found")
        other = (await c.post(f"{base}/medications", json=_medication(name="B"), headers=h)).json()
        fresh = (await c.post(f"{url}/regimens", json=_change(150, "8", "8"), headers=h)).json()
        fresh_id = fresh["next_regimen"]["id"]
        # another medication's path with this regimen's id: not found, and it stays unvoided
        r = await c.post(
            f"{base}/medications/{other['id']}/regimens/{fresh_id}/void",
            json={"reason": "x"},
            headers=h,
        )
        assert (r.status_code, r.json()["code"]) == (404, "regimen.not_found")
        started = med["current_regimen"]["id"]
        r = await c.post(f"{url}/regimens/{started}/void", json={"reason": "x"}, headers=h)
        assert (r.status_code, r.json()["code"]) == (409, "regimen.not_voidable")


async def test_stopped_or_finished_medications_have_no_current_dose(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, h, base = await _profile(c, owner_engine)
        yesterday = (datetime.now(UTC) - timedelta(days=2)).date().isoformat()
        soon = (datetime.now(UTC) + timedelta(days=30)).date().isoformat()
        finished = _medication(
            name="Валганцикловир", started_on="2026-01-01", planned_end_on=yesterday
        )
        course = _medication(name="Ко-тримоксазол", started_on="2026-01-01", planned_end_on=soon)
        stopped = _medication(name="Өмнөх", started_on="2025-01-01", stopped_on="2025-06-01")
        for body in (finished, course, stopped):
            assert (await c.post(f"{base}/medications", json=body, headers=h)).status_code == 201
        listed = {m["name"]: m for m in (await c.get(f"{base}/medications", headers=h)).json()}
        assert listed["Ко-тримоксазол"]["is_current"] is True
        assert listed["Ко-тримоксазол"]["current_regimen"] is not None
        for name in ("Валганцикловир", "Өмнөх"):
            assert (listed[name]["is_current"], listed[name]["current_regimen"]) == (False, None)
        too_far = _medication(planned_end_on="2099-01-01")
        assert (await c.post(f"{base}/medications", json=too_far, headers=h)).status_code == 422


async def test_a_client_id_reused_for_another_record_is_a_conflict(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, h, base = await _profile(c, owner_engine)
        a = (await c.post(f"{base}/medications", json=_medication(name="A"), headers=h)).json()
        b = (await c.post(f"{base}/medications", json=_medication(name="B"), headers=h)).json()
        change = _change(-1, "1", "1")
        r = await c.post(f"{base}/medications/{a['id']}/regimens", json=change, headers=h)
        assert r.status_code == 201
        r = await c.post(f"{base}/medications/{b['id']}/regimens", json=change, headers=h)
        assert (r.status_code, r.json()["code"]) == (409, "record.conflict")
        dose = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=1)
        intake = {
            "client_id": str(uuid4()),
            "medication_id": a["id"],
            "scheduled_at": dose.isoformat(),
            "taken_at": dose.isoformat(),
            "status": "taken",
        }
        assert (await c.post(f"{base}/intakes", json=intake, headers=h)).status_code == 201
        other_dose = {**intake, "scheduled_at": (dose - timedelta(hours=1)).isoformat()}
        r = await c.post(f"{base}/intakes", json=other_dose, headers=h)
        assert (r.status_code, r.json()["code"]) == (409, "record.conflict")


async def test_records_of_one_dose_meet_on_the_minute(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    """Two devices' clocks differ by seconds: still one dose, and taken still wins (H20)."""
    async with client_from() as c:
        _, h, base = await _profile(c, owner_engine)
        med = (await c.post(f"{base}/medications", json=_medication(), headers=h)).json()
        slot = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=1)
        taken = {
            "client_id": str(uuid4()),
            "medication_id": med["id"],
            "scheduled_at": (slot + timedelta(seconds=0.25)).isoformat(),
            "taken_at": slot.isoformat(),
            "status": "taken",
        }
        first = (await c.post(f"{base}/intakes", json=taken, headers=h)).json()
        assert datetime.fromisoformat(first["scheduled_at"]) == slot
        skipped = {
            **taken,
            "client_id": str(uuid4()),
            "scheduled_at": (slot + timedelta(seconds=40)).isoformat(),
            "taken_at": None,
            "status": "skipped",
        }
        r = await c.post(f"{base}/intakes", json=skipped, headers=h)
        assert (r.status_code, r.json()["id"], r.json()["status"]) == (200, first["id"], "taken")


async def test_readers_and_other_profiles_cannot_write(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, h, base = await _profile(c, owner_engine)
        viewer, viewer_h = await _signed_in(c, owner_engine)
        _, other_h, other = await _profile(c, owner_engine)
        await _grant(owner_engine, base, viewer, "viewer")
        med = (await c.post(f"{base}/medications", json=_medication(), headers=h)).json()
        t = (await c.post(f"{base}/transplants", json=_transplant(), headers=h)).json()
        r = await c.post(f"{base}/medications", json=_medication(), headers=viewer_h)
        assert (r.status_code, r.json()["code"]) == (403, "patient.read_only")
        assert (await c.get(f"{base}/medications", headers=viewer_h)).status_code == 200
        # another profile's record ids, under one's own profile: not found, nothing changed
        body = {k: v for k, v in _transplant().items() if k != "client_id"}
        for verb, url, payload in (
            ("PUT", f"{other}/transplants/{t['id']}", body),
            ("DELETE", f"{other}/transplants/{t['id']}", None),
            ("DELETE", f"{other}/medications/{med['id']}", None),
            ("POST", f"{other}/medications/{med['id']}/regimens", _change(-1, "1", "1")),
        ):
            r = await c.request(verb, url, json=payload, headers=other_h)
            assert r.status_code == 404, (verb, url)
        still = (await c.get(f"{base}/medications/{med['id']}", headers=h)).json()
        assert len(still["regimens"]) == 1


async def test_medication_links_stay_within_the_profile(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, h, base = await _profile(c, owner_engine)
        _, other_h, other = await _profile(c, owner_engine)
        foreign = (await c.post(f"{other}/transplants", json=_transplant(), headers=other_h)).json()
        r = await c.post(
            f"{base}/medications", json=_medication(transplant_id=foreign["id"]), headers=h
        )
        assert (r.status_code, r.json()["code"]) == (422, "transplant.not_found")
        r = await c.post(f"{base}/medications", json=_medication(catalog_code="NOPE"), headers=h)
        assert (r.status_code, r.json()["code"]) == (422, "medication.unknown_catalog_code")
        med = (await c.post(f"{other}/medications", json=_medication(), headers=other_h)).json()
        r = await c.get(f"{base}/medications/{med['id']}", headers=h)
        assert (r.status_code, r.json()["code"]) == (404, "medication.not_found")


async def test_catalog_search_and_listing_order(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, h, base = await _profile(c, owner_engine)
        # the test database is not seeded: arrange one catalog row (reference data, owner role)
        async with owner_engine.connect() as conn, conn.begin():
            await conn.execute(
                bound_text(
                    "insert into medication_catalog (code, generic_mn, generic_en, brands,"
                    " category, forms) values ('TEST_TAC', 'Такролимус', 'Tacrolimus',"
                    " '{Prograf}', 'immunosuppressant', '{capsule}') on conflict do nothing"
                )
            )
        found = (await c.get("/api/v1/medication-catalog?q=так", headers=h)).json()
        assert [i["code"] for i in found] == ["TEST_TAC"]
        by_brand = (await c.get("/api/v1/medication-catalog?q=prog", headers=h)).json()
        assert [i["code"] for i in by_brand] == ["TEST_TAC"]
        # LIKE wildcards are literal
        assert (await c.get("/api/v1/medication-catalog?q=%25", headers=h)).json() == []
        assert any(i["category"] == "immunosuppressant" for i in found)
        code = found[0]["code"]
        await c.post(f"{base}/medications", json=_medication(name="Витамин Д"), headers=h)
        await c.post(
            f"{base}/medications",
            json=_medication(catalog_code=code, name="Програф"),
            headers=h,
        )
        stopped = _medication(name="Өмнөх", started_on="2025-01-01", stopped_on="2025-06-01")
        await c.post(f"{base}/medications", json=stopped, headers=h)
        names = [m["name"] for m in (await c.get(f"{base}/medications", headers=h)).json()]
        assert names == ["Програф", "Витамин Д", "Өмнөх"]  # immunosuppressants first, then stopped


# --- intakes (H20) -------------------------------------------------------------------------------


async def test_taken_always_wins_and_retries_are_safe(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, h, base = await _profile(c, owner_engine)
        carer, carer_h = await _signed_in(c, owner_engine)
        await _grant(owner_engine, base, carer, "caregiver")
        med = (await c.post(f"{base}/medications", json=_medication(), headers=h)).json()
        dose = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
        taken = {
            "client_id": str(uuid4()),
            "medication_id": med["id"],
            "scheduled_at": dose.isoformat(),
            "taken_at": (dose + timedelta(minutes=4)).isoformat(),
            "status": "taken",
        }
        r = await c.post(f"{base}/intakes", json=taken, headers=h)
        assert r.status_code == 201
        first = r.json()
        assert (await c.post(f"{base}/intakes", json=taken, headers=h)).json() == first
        # the caregiver's phone says "skipped" for the same dose: the record stays taken
        skipped = {**taken, "client_id": str(uuid4()), "status": "skipped", "taken_at": None}
        r = await c.post(f"{base}/intakes", json=skipped, headers=carer_h)
        assert (r.status_code, r.json()["status"], r.json()["id"]) == (200, "taken", first["id"])
        # Q24: a second "taken" (another person, another time) is kept beside the first, which
        # stays as it was - who, when; each side sees who in relative terms, never a name
        earlier = {**taken, "client_id": str(uuid4()), "taken_at": dose.isoformat()}
        r = await c.post(f"{base}/intakes", json=earlier, headers=carer_h)
        body = r.json()
        assert (r.status_code, body["id"], body["recorded_by"]) == (200, first["id"], "owner")
        assert datetime.fromisoformat(body["taken_at"]) == dose + timedelta(minutes=4)
        assert [
            (x["by"], datetime.fromisoformat(x["taken_at"])) for x in body["also_recorded"]
        ] == [("you", dose)]
        assert first["recorded_by"] == "you"
        assert first["also_recorded"] == []
        # the same request again adds nothing
        r = await c.post(f"{base}/intakes", json=earlier, headers=carer_h)
        assert len(r.json()["also_recorded"]) == 1
        # more than the database keeps is never an error (the first ten stay)
        for n in range(12):
            more = {
                **taken,
                "client_id": str(uuid4()),
                "taken_at": (dose + timedelta(minutes=10 + n)).isoformat(),
            }
            assert (await c.post(f"{base}/intakes", json=more, headers=carer_h)).status_code == 200
        r = await c.post(f"{base}/intakes", json=earlier, headers=carer_h)
        assert len(r.json()["also_recorded"]) == 10

        since = (dose - timedelta(days=1)).isoformat()
        until = (dose + timedelta(days=1)).isoformat()
        listed = await c.get(f"{base}/intakes", params={"from": since, "to": until}, headers=h)
        assert [i["id"] for i in listed.json()] == [first["id"]]
        assert [x["by"] for x in listed.json()[0]["also_recorded"]] == ["caregiver"] * 10
        too_long = {"from": (dose - timedelta(days=100)).isoformat(), "to": until}
        assert (await c.get(f"{base}/intakes", params=too_long, headers=h)).status_code == 422

        # undo: a dose others logged too cannot be undone (their records would go with it);
        # each removes only their own extra record, then the recorder (or the owner) may undo
        url = f"{base}/intakes/{first['id']}"
        r = await c.delete(url, headers=h)
        assert (r.status_code, r.json()["code"]) == (409, "intake.has_other_records")
        assert (await c.delete(f"{url}/mine", headers=h)).status_code == 404  # none of the owner's
        assert (await c.delete(f"{url}/mine", headers=carer_h)).status_code == 204
        r = await c.delete(url, headers=carer_h)
        assert (r.status_code, r.json()["code"]) == (403, "intake.delete_not_allowed")
        assert (await c.delete(url, headers=h)).status_code == 204


async def test_skipped_then_taken_becomes_taken_and_bad_records_are_refused(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, h, base = await _profile(c, owner_engine)
        _, other_h, other = await _profile(c, owner_engine)
        med = (await c.post(f"{base}/medications", json=_medication(), headers=h)).json()
        foreign = (await c.post(f"{other}/medications", json=_medication(), headers=other_h)).json()
        dose = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=2)
        skipped = {
            "client_id": str(uuid4()),
            "medication_id": med["id"],
            "scheduled_at": dose.isoformat(),
            "status": "skipped",
        }
        assert (await c.post(f"{base}/intakes", json=skipped, headers=h)).status_code == 201
        late = {
            **skipped,
            "client_id": str(uuid4()),
            "status": "late",
            "taken_at": (dose + timedelta(hours=1)).isoformat(),
        }
        r = await c.post(f"{base}/intakes", json=late, headers=h)
        assert (r.status_code, r.json()["status"]) == (200, "late")

        r = await c.post(
            f"{base}/intakes",
            json={**late, "client_id": str(uuid4()), "medication_id": foreign["id"]},
            headers=h,
        )
        assert (r.status_code, r.json()["code"]) == (404, "medication.not_found")
        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        for bad in (
            {"status": "taken"},  # no taken_at
            {"status": "skipped", "taken_at": dose.isoformat()},
            {"status": "taken", "taken_at": future},
            {"status": "skipped", "scheduled_at": None},  # as-needed doses are only taken
            {"status": "taken", "taken_at": "2026-11-04T08:00:00"},  # no time zone
        ):
            body = {**skipped, "client_id": str(uuid4()), **bad}
            assert (await c.post(f"{base}/intakes", json=body, headers=h)).status_code == 422, bad


async def test_a_caregiver_cannot_delete_a_medication_and_its_history(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    """Security review 2.5b L7: the full list and history are readable; erasing is the owner's."""
    async with client_from() as c:
        _, h, base = await _profile(c, owner_engine)
        carer, carer_h = await _signed_in(c, owner_engine)
        await _grant(owner_engine, base, carer, "caregiver")
        med = (await c.post(f"{base}/medications", json=_medication(), headers=h)).json()
        listed = (await c.get(f"{base}/medications", headers=carer_h)).json()
        assert [len(m["regimens"]) for m in listed] == [1]  # the list carries the history
        r = await c.delete(f"{base}/medications/{med['id']}", headers=carer_h)
        assert (r.status_code, r.json()["code"]) == (403, "record.delete_not_allowed")
        assert (await c.delete(f"{base}/medications/{med['id']}", headers=h)).status_code == 204


async def test_medications_and_dose_changes_are_capped(
    owner_engine: AsyncEngine, client_from: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Security review 2.5b M2: the list the phone caches stays bounded; a retry still works."""
    monkeypatch.setattr(service, "MAX_MEDICATIONS", 2)
    monkeypatch.setattr(service, "MAX_REGIMENS", 2)
    async with client_from() as c:
        _, h, base = await _profile(c, owner_engine)
        first = _medication()
        med = (await c.post(f"{base}/medications", json=first, headers=h)).json()
        assert (
            await c.post(f"{base}/medications", json=_medication(), headers=h)
        ).status_code == 201
        r = await c.post(f"{base}/medications", json=_medication(), headers=h)
        assert (r.status_code, r.json()["code"]) == (409, "medication.too_many")
        assert (await c.post(f"{base}/medications", json=first, headers=h)).status_code == 200
        change = _change(1, "2", "1,5")
        url = f"{base}/medications/{med['id']}/regimens"
        assert (await c.post(url, json=change, headers=h)).status_code == 201
        r = await c.post(url, json=_change(2, "3", "1"), headers=h)
        assert (r.status_code, r.json()["code"]) == (409, "medication.too_many")
        assert (await c.post(url, json=change, headers=h)).status_code == 200
        monkeypatch.setattr(service, "MAX_REGIMENS", 10)
        monkeypatch.setattr(service, "MAX_PROFILE_REGIMENS", 3)  # 2 + 1 in the profile
        r = await c.post(url, json=_change(3, "3", "1"), headers=h)
        assert (r.status_code, r.json()["code"]) == (409, "medication.too_many")
