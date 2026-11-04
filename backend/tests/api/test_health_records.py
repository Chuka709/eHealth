"""Clinical events, vitals, allergies, contacts, appointments and questions over the API
(Phase 2.6)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.health import service

from .conftest import ClientFactory
from .test_patients import _signed_in
from .test_records import _audit, _grant, _profile, _transplant

pytestmark = pytest.mark.db


@pytest.fixture
async def client(client_from: ClientFactory) -> AsyncIterator[AsyncClient]:
    async with client_from() as c:
        yield c


def _now(**delta: float) -> str:
    return (datetime.now(UTC) + timedelta(**delta)).isoformat()


BODIES: dict[str, dict[str, Any]] = {
    "events": {"kind": "biopsy", "title": "Бөөрний биопси", "started_on": "2026-10-01"},
    "allergies": {"substance": "Пенициллин", "severity": "severe"},
    "contacts": {"name": "Дорж", "relation": "ах", "phone": "+976 9911 2233"},
    "appointments": {"kind": "lab", "title": "Такролимусын түвшин", "scheduled_at": ""},
    "questions": {"text": "Вакцин хийлгэж болох уу?"},
}
EDITS: dict[str, dict[str, Any]] = {
    "events": {"outcome": "Татгалзал илрээгүй"},
    "allergies": {"reaction": "Тууралт"},
    "contacts": {"is_transplant_center": True},
    "appointments": {"place": "Улсын нэгдүгээр төв эмнэлэг"},
    "questions": {"answer": "Тийм", "status": "answered"},
}


def _body(kind: str) -> dict[str, Any]:
    body = {**BODIES[kind], "client_id": str(uuid4())}
    if kind == "appointments":
        body["scheduled_at"] = _now(days=2)
    return body


@pytest.mark.parametrize("kind", list(BODIES))
async def test_create_retry_edit_delete_and_audit_ids_only(
    client: AsyncClient, owner_engine: AsyncEngine, kind: str
) -> None:
    _, h, base = await _profile(client, owner_engine)
    body = _body(kind)
    first = await client.post(f"{base}/{kind}", json=body, headers=h)
    assert first.status_code == 201, first.text
    again = await client.post(f"{base}/{kind}", json=body, headers=h)
    assert (again.status_code, again.json()["id"]) == (200, first.json()["id"])
    url = f"{base}/{kind}/{first.json()['id']}"
    edited = {k: v for k, v in {**body, **EDITS[kind]}.items() if k != "client_id"}
    r = await client.put(url, json=edited, headers=h)
    assert r.status_code == 200, r.text
    for key, value in EDITS[kind].items():
        assert r.json()[key] == value
    listed = (await client.get(f"{base}/{kind}", headers=h)).json()
    assert [x["id"] for x in listed] == [first.json()["id"]]
    assert (await client.delete(url, headers=h)).status_code == 204
    assert (await client.delete(url, headers=h)).status_code == 404
    log = await _audit(owner_engine, base)
    actions = [a for a, _ in log if a.split(".")[0] != "patient"]
    assert len([a for a in actions if a.endswith(".create")]) == 1
    assert any(a.endswith(".update") for a in actions)
    texts = [str(v) for v in BODIES[kind].values() if isinstance(v, str) and len(v) > 3]
    assert all(t not in (d or "") for _, d in log for t in texts)


async def test_an_event_links_only_this_profiles_transplant(
    client: AsyncClient, client_from: ClientFactory, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    mine = (await client.post(f"{base}/transplants", json=_transplant(), headers=h)).json()
    body = {**_body("events"), "transplant_id": mine["id"], "ended_on": "2026-10-03"}
    assert (await client.post(f"{base}/events", json=body, headers=h)).status_code == 201
    async with client_from("203.0.113.30") as other:
        _, oh, obase = await _profile(other, owner_engine)
        theirs = (await other.post(f"{obase}/transplants", json=_transplant(), headers=oh)).json()
    r = await client.post(
        f"{base}/events", json={**_body("events"), "transplant_id": theirs["id"]}, headers=h
    )
    assert (r.status_code, r.json()["code"]) == (422, "transplant.not_found")
    r = await client.post(
        f"{base}/events", json={**_body("events"), "ended_on": "2026-09-01"}, headers=h
    )
    assert r.status_code == 422


@pytest.mark.parametrize(
    "bad",
    [
        {"phone": "9911"},
        {"phone": "call me"},
        {"phone": "+976 9911 2233; drop"},
        {"sort_order": 101},
    ],
)
async def test_contacts_are_checked(
    client: AsyncClient, owner_engine: AsyncEngine, bad: dict[str, object]
) -> None:
    _, h, base = await _profile(client, owner_engine)
    r = await client.post(f"{base}/contacts", json={**_body("contacts"), **bad}, headers=h)
    assert r.status_code == 422


@pytest.mark.parametrize(
    "bad",
    [
        {"scheduled_at": "2026-12-01T09:00:00"},  # no zone
        {"scheduled_at": _now(days=1000)},
        {"reminder_offsets_min": [1440, 1440]},
        {"reminder_offsets_min": [20000]},
        {"reminder_offsets_min": [1, 2, 3, 4, 5]},
        {"status": "missed"},
    ],
)
async def test_appointments_are_checked(
    client: AsyncClient, owner_engine: AsyncEngine, bad: dict[str, object]
) -> None:
    _, h, base = await _profile(client, owner_engine)
    r = await client.post(f"{base}/appointments", json={**_body("appointments"), **bad}, headers=h)
    assert r.status_code == 422


async def test_appointment_reminders_default_to_a_day_and_two_hours(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    r = await client.post(f"{base}/appointments", json=_body("appointments"), headers=h)
    assert r.json()["reminder_offsets_min"] == [1440, 120]
    assert r.json()["scheduled_at"].endswith(":00Z") or r.json()["scheduled_at"].endswith(
        ":00+00:00"
    )


async def test_a_question_links_only_this_profiles_appointment(
    client: AsyncClient, client_from: ClientFactory, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    appt = (await client.post(f"{base}/appointments", json=_body("appointments"), headers=h)).json()
    q = {**_body("questions"), "appointment_id": appt["id"]}
    assert (await client.post(f"{base}/questions", json=q, headers=h)).status_code == 201
    async with client_from("203.0.113.31") as other:
        _, oh, obase = await _profile(other, owner_engine)
        theirs = (
            await other.post(f"{obase}/appointments", json=_body("appointments"), headers=oh)
        ).json()
    r = await client.post(
        f"{base}/questions", json={**_body("questions"), "appointment_id": theirs["id"]}, headers=h
    )
    assert (r.status_code, r.json()["code"]) == (422, "appointment.not_found")


def _reading(*items: tuple[str, str], **extra: object) -> dict[str, Any]:
    return {
        "client_id": str(uuid4()),
        "measured_at": _now(minutes=-5),
        "items": [{"kind": k, "value": v} for k, v in items],
        **extra,
    }


async def test_a_blood_pressure_reading_is_one_group_with_fixed_units(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    body = _reading(("bp_systolic", "128"), ("bp_diastolic", "82"), ("pulse", "71"))
    r = await client.post(f"{base}/vitals", json=body, headers=h)
    assert r.status_code == 201, r.text
    rows = r.json()
    assert {(x["kind"], x["value"], x["unit"]) for x in rows} == {
        ("bp_systolic", "128", "mmHg"),
        ("bp_diastolic", "82", "mmHg"),
        ("pulse", "71", "bpm"),
    }
    assert len({x["group_id"] for x in rows}) == 1
    again = await client.post(f"{base}/vitals", json=body, headers=h)
    assert again.status_code == 200
    assert sorted(x["id"] for x in again.json()) == sorted(x["id"] for x in rows)
    temp = await client.post(f"{base}/vitals", json=_reading(("temperature", "36,6")), headers=h)
    assert (temp.json()[0]["value"], temp.json()[0]["group_id"]) == ("36.6", None)
    latest = (await client.get(f"{base}/vitals/latest", headers=h)).json()
    assert {x["kind"] for x in latest} == {"bp_systolic", "bp_diastolic", "pulse", "temperature"}
    window = {"from": _now(days=-1), "to": _now(minutes=1)}
    listed = (await client.get(f"{base}/vitals", params=window, headers=h)).json()
    assert len(listed) == 4
    one = (await client.get(f"{base}/vitals", params={**window, "kind": "pulse"}, headers=h)).json()
    assert [x["kind"] for x in one] == ["pulse"]
    assert (await client.delete(f"{base}/vitals/{one[0]['id']}", headers=h)).status_code == 204


@pytest.mark.parametrize(
    ("items", "code"),
    [
        ((("bp_systolic", "1200"), ("bp_diastolic", "80")), "vital.implausible"),
        ((("bp_systolic", "80"), ("bp_diastolic", "120")), "vital.bp_order"),  # swapped
        ((("glucose", "120"),), "vital.glucose_unit"),  # mg/dL as mmol/L
        ((("weight", "1,000"),), "vital.format"),
        ((("pulse", "72.5"),), "vital.format"),
        ((("weight", "7.455"),), "vital.format"),
    ],
)
async def test_implausible_vitals_say_so(
    client: AsyncClient, owner_engine: AsyncEngine, items: tuple[tuple[str, str], ...], code: str
) -> None:
    _, h, base = await _profile(client, owner_engine)
    r = await client.post(f"{base}/vitals", json=_reading(*items), headers=h)
    assert (r.status_code, r.json()["code"]) == (422, code)


@pytest.mark.parametrize(
    "items",
    [
        (("bp_systolic", "120"),),  # systolic without diastolic
        (("weight", "70"), ("pulse", "70")),  # not one blood-pressure reading
        (("pulse", "70"), ("pulse", "71")),
    ],
)
async def test_a_reading_has_a_known_shape(
    client: AsyncClient, owner_engine: AsyncEngine, items: tuple[tuple[str, str], ...]
) -> None:
    _, h, base = await _profile(client, owner_engine)
    r = await client.post(f"{base}/vitals", json=_reading(*items), headers=h)
    assert r.status_code == 422


async def test_future_readings_and_long_windows_are_refused(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    r = await client.post(
        f"{base}/vitals", json=_reading(("pulse", "70"), measured_at=_now(hours=2)), headers=h
    )
    assert r.status_code == 422
    r = await client.get(
        f"{base}/vitals", params={"from": _now(days=-500), "to": _now()}, headers=h
    )
    assert r.status_code == 422


async def test_readers_see_but_do_not_write_and_strangers_see_nothing(
    client: AsyncClient, client_from: ClientFactory, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    assert (await client.post(f"{base}/allergies", json=_body("allergies"), headers=h)).is_success
    async with client_from("203.0.113.32") as other:
        uid, oh = await _signed_in(other, owner_engine)
        assert (await other.get(f"{base}/allergies", headers=oh)).status_code == 404
        await _grant(owner_engine, base, uid, "viewer")
        assert len((await other.get(f"{base}/allergies", headers=oh)).json()) == 1
        r = await other.post(f"{base}/allergies", json=_body("allergies"), headers=oh)
        assert (r.status_code, r.json()["code"]) == (403, "patient.read_only")


async def test_each_kind_is_capped(
    client: AsyncClient, owner_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    table, _, entity, missing = service.KINDS["contacts"]
    monkeypatch.setitem(service.KINDS, "contacts", (table, 1, entity, missing))
    _, h, base = await _profile(client, owner_engine)
    first = _body("contacts")
    assert (await client.post(f"{base}/contacts", json=first, headers=h)).status_code == 201
    r = await client.post(f"{base}/contacts", json=_body("contacts"), headers=h)
    assert (r.status_code, r.json()["code"]) == (409, "record.too_many")
    assert (await client.post(f"{base}/contacts", json=first, headers=h)).status_code == 200


async def test_a_caregiver_cannot_delete_the_owners_allergy(
    client: AsyncClient, client_from: ClientFactory, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    allergy = (await client.post(f"{base}/allergies", json=_body("allergies"), headers=h)).json()
    async with client_from("203.0.113.33") as other:
        uid, ch = await _signed_in(other, owner_engine)
        await _grant(owner_engine, base, uid, "caregiver")
        r = await other.delete(f"{base}/allergies/{allergy['id']}", headers=ch)
        assert (r.status_code, r.json()["code"]) == (403, "record.delete_not_allowed")
        own = (await other.post(f"{base}/allergies", json=_body("allergies"), headers=ch)).json()
        assert (await other.delete(f"{base}/allergies/{own['id']}", headers=ch)).status_code == 204


async def test_a_vitals_client_id_reused_for_another_reading_is_a_conflict(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    body = _reading(("bp_systolic", "128"), ("bp_diastolic", "82"))
    assert (await client.post(f"{base}/vitals", json=body, headers=h)).status_code == 201
    other = {**_reading(("pulse", "70")), "client_id": body["client_id"]}
    r = await client.post(f"{base}/vitals", json=other, headers=h)
    assert (r.status_code, r.json()["code"]) == (409, "record.conflict")
