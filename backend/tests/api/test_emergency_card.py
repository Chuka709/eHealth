"""The emergency card over the API (Phase 2.7; H17, H27)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import ClientFactory
from .test_patients import _signed_in
from .test_records import _change, _grant, _medication, _profile, _transplant

pytestmark = pytest.mark.db

# The whole shape: the phone may show this while the app is locked, so a field added to a
# Card* model must be a decision, never a side effect (no ids, donor, HLA or notes).
CARD_KEYS = {
    "patient",
    "blood_type",
    "blood_type_withheld",
    "transplants",
    "dosed_medications",
    "other_medications",
    "allergies",
    "contacts",
    "generated_at",
}
PATIENT_KEYS = {"full_name", "birth_date", "sex"}
TRANSPLANT_KEYS = {
    "organ",
    "organ_detail",
    "transplant_date",
    "date_precision",
    "elapsed",
    "transplant_number",
    "graft_status",
    "country",
    "city",
    "hospital",
    "follow_up_center",
    "follow_up_doctor",
}
DOSED_KEYS = {
    "category",
    "name",
    "brand",
    "form",
    "strength",
    "dose",
    "upcoming_doses",
    "planned_end_on",
}
DOSE_KEYS = {
    "effective_from",
    "dose_amount",
    "dose_unit",
    "dose_unit_text",
    "schedule",
    "instructions",
}


@pytest.fixture
async def client(client_from: ClientFactory) -> AsyncIterator[AsyncClient]:
    async with client_from() as c:
        yield c


async def _catalog(owner_engine: AsyncEngine) -> None:
    # the test database is not seeded: two catalog rows (reference data, owner role)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into medication_catalog (code, generic_mn, generic_en, brands,"
                " category, forms) values"
                " ('TEST_TAC', 'Такролимус', 'Tacrolimus', '{Prograf}', 'immunosuppressant',"
                " '{capsule}'),"
                " ('TEST_PRED', 'Преднизолон', 'Prednisolone', '{}', 'corticosteroid',"
                " '{tablet}') on conflict do nothing"
            )
        )


async def _post(c: AsyncClient, url: str, body: dict[str, object], h: dict[str, str]) -> None:
    r = await c.post(url, json={"client_id": str(uuid4()), **body}, headers=h)
    assert r.status_code == 201, r.text


def _dose(regimen: dict[str, object]) -> dict[str, object]:
    return {k: regimen[k] for k in DOSE_KEYS}


async def test_the_card_gathers_the_profile_in_its_order(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    await _catalog(owner_engine)
    old = _transplant(
        transplant_date="2012-03-01", graft_status="failed", recipient_blood_type="A+"
    )
    assert (await client.post(f"{base}/transplants", json=old, headers=h)).status_code == 201
    new = _transplant(
        organ="liver",
        transplant_date="2021-06-14",
        date_precision="month",
        recipient_blood_type="A+",
        donor_blood_type="O-",  # a solid organ: the recipient's type stands
        follow_up_center="Улсын нэгдүгээр төв эмнэлэг",
        notes="хувийн тэмдэглэл",
    )
    assert (await client.post(f"{base}/transplants", json=new, headers=h)).status_code == 201
    tac = await client.post(
        f"{base}/medications", json=_medication(catalog_code="TEST_TAC", name="Програф"), headers=h
    )
    assert tac.status_code == 201, tac.text
    # a dose change recorded for a coming day: a cached card must not outlive it silently
    changed = await client.post(
        f"{base}/medications/{tac.json()['id']}/regimens", json=_change(3, "1", "1"), headers=h
    )
    assert changed.status_code == 201, changed.text
    pred = _medication(catalog_code="TEST_PRED", name="Преднизолон", strength="5 мг")
    assert (await client.post(f"{base}/medications", json=pred, headers=h)).status_code == 201
    await client.post(f"{base}/medications", json=_medication(name="Витамин Д"), headers=h)
    stopped = _medication(name="Өмнөх", started_on="2025-01-01", stopped_on="2025-06-01")
    await client.post(f"{base}/medications", json=stopped, headers=h)
    await _post(client, f"{base}/allergies", {"substance": "Тоос", "severity": "mild"}, h)
    await _post(client, f"{base}/allergies", {"substance": "Пенициллин", "severity": "severe"}, h)
    await _post(client, f"{base}/contacts", {"name": "Дорж", "phone": "+976 9911 2233"}, h)
    center = {"name": "Төв", "phone": "7000 1234", "is_transplant_center": True, "sort_order": 5}
    await _post(client, f"{base}/contacts", center, h)

    r = await client.get(f"{base}/emergency-card", headers=h)
    assert r.status_code == 200, r.text
    card = r.json()
    assert set(card) == CARD_KEYS
    assert set(card["patient"]) == PATIENT_KEYS
    assert card["patient"]["full_name"] == "Бат"
    assert (card["blood_type"], card["blood_type_withheld"]) == ("A+", None)

    assert [(t["organ"], t["graft_status"]) for t in card["transplants"]] == [
        ("liver", "functioning"),
        ("kidney", "failed"),
    ]
    assert all(set(t) == TRANSPLANT_KEYS for t in card["transplants"])
    assert card["transplants"][0]["elapsed"]["approximate"] is True  # a month-only date

    tac_card, pred_card = card["dosed_medications"]
    assert all(set(m) == DOSED_KEYS for m in card["dosed_medications"])
    assert (tac_card["category"], tac_card["name"]) == ("immunosuppressant", "Програф")
    # as the user recorded it, never computed; and the change already recorded for later
    assert tac_card["dose"] == _dose(changed.json()["current_regimen"])
    assert tac_card["upcoming_doses"] == [_dose(changed.json()["next_regimen"])]
    assert set(tac_card["dose"]) == DOSE_KEYS
    assert (pred_card["category"], pred_card["strength"]) == ("corticosteroid", "5 мг")
    assert pred_card["dose"] is not None  # a steroid course matters to an emergency team

    assert card["other_medications"] == [{"name": "Витамин Д", "brand": None}]  # not stopped
    assert card["allergies"] == [
        {"substance": "Пенициллин", "reaction": None, "severity": "severe"},
        {"substance": "Тоос", "reaction": None, "severity": "mild"},
    ]
    assert [c["name"] for c in card["contacts"]] == ["Төв", "Дорж"]
    assert all(
        set(c) == {"name", "relation", "phone", "is_transplant_center"} for c in card["contacts"]
    )
    assert "хувийн тэмдэглэл" not in r.text


async def test_a_dose_that_starts_later_is_not_shown_as_todays(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    await _catalog(owner_engine)
    later = _medication(catalog_code="TEST_TAC", name="Програф")
    later["regimen"] = _change(2, "2", "2")
    r = await client.post(f"{base}/medications", json=later, headers=h)
    assert r.status_code == 201, r.text
    [med] = (await client.get(f"{base}/emergency-card", headers=h)).json()["dosed_medications"]
    assert med["dose"] is None
    assert med["upcoming_doses"] == [_dose(r.json()["next_regimen"])]


async def test_every_step_of_a_taper_is_on_the_card(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    await _catalog(owner_engine)
    pred = _medication(catalog_code="TEST_PRED", name="Преднизолон")
    med = (await client.post(f"{base}/medications", json=pred, headers=h)).json()
    url = f"{base}/medications/{med['id']}/regimens"
    steps = []
    for days, amount in ((7, "1,5"), (14, "1"), (21, "0,5")):
        r = await client.post(url, json=_change(days, amount, amount), headers=h)
        assert r.status_code == 201, r.text
        steps.append(r.json()["regimens"])
    [card] = (await client.get(f"{base}/emergency-card", headers=h)).json()["dosed_medications"]
    ahead = [d["effective_from"] for d in card["upcoming_doses"]]
    assert ahead == sorted(ahead)
    assert len(ahead) == 3
    amounts = [d["schedule"]["times"][0]["amount"] for d in card["upcoming_doses"]]
    assert amounts == ["1.5", "1", "0.5"]


async def test_a_change_after_the_course_ends_is_not_on_the_card(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    await _catalog(owner_engine)
    end = (datetime.now(UTC) + timedelta(days=5)).date().isoformat()
    pred = _medication(catalog_code="TEST_PRED", name="Преднизолон", planned_end_on=end)
    med = (await client.post(f"{base}/medications", json=pred, headers=h)).json()
    url = f"{base}/medications/{med['id']}/regimens"
    for days in (3, 10):
        r = await client.post(url, json=_change(days, "1", "1"), headers=h)
        assert r.status_code == 201, r.text
    [card] = (await client.get(f"{base}/emergency-card", headers=h)).json()["dosed_medications"]
    assert len(card["upcoming_doses"]) == 1
    assert card["planned_end_on"] == end


@pytest.mark.parametrize(
    ("records", "shown", "withheld"),
    [
        ([("kidney", "A+", None), ("liver", "B+", None)], None, "conflict"),
        ([("hsct", "A+", "O+")], None, "hsct"),  # the blood type itself changes
        ([("hsct", "A+", None)], None, "hsct"),  # the donor's type is unknown
        ([("hsct", "A+", "A+")], "A+", None),
    ],
)
async def test_a_doubtful_blood_type_is_withheld_and_says_why(
    client: AsyncClient,
    owner_engine: AsyncEngine,
    records: list[tuple[str, str, str | None]],
    shown: str | None,
    withheld: str | None,
) -> None:
    _, h, base = await _profile(client, owner_engine)
    for organ, recipient, donor in records:
        body = _transplant(organ=organ, recipient_blood_type=recipient, donor_blood_type=donor)
        r = await client.post(f"{base}/transplants", json=body, headers=h)
        assert r.status_code == 201, r.text
    card = (await client.get(f"{base}/emergency-card", headers=h)).json()
    assert (card["blood_type"], card["blood_type_withheld"]) == (shown, withheld)


async def test_an_empty_profile_has_an_empty_card(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    card = (await client.get(f"{base}/emergency-card", headers=h)).json()
    assert (card["blood_type"], card["blood_type_withheld"]) == (None, None)
    for key in ("transplants", "dosed_medications", "other_medications", "allergies", "contacts"):
        assert card[key] == []


async def test_strangers_see_nothing_and_a_missing_profile_looks_the_same(
    client: AsyncClient, client_from: ClientFactory, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    await _post(client, f"{base}/allergies", {"substance": "Пенициллин"}, h)
    async with client_from("203.0.113.41") as other:
        _, oh = await _signed_in(other, owner_engine)
        stranger = await other.get(f"{base}/emergency-card", headers=oh)
        missing = await other.get(f"/api/v1/patients/{uuid4()}/emergency-card", headers=oh)
        # a profile not shared and one that does not exist look the same
        assert (stranger.status_code, stranger.json()) == (missing.status_code, missing.json())
        assert stranger.json()["code"] == "patient.not_found"


# the ways access ends, as can_read_patient reads them
_ENDED = {
    "revoked": bound_text(
        "update patient_access set revoked_at = now()"
        " where patient_id = cast(:p as uuid) and user_id = :u"
    ),
    "expired": bound_text(
        "update patient_access set expires_at = now() - interval '1 second'"
        " where patient_id = cast(:p as uuid) and user_id = :u"
    ),
}


@pytest.mark.parametrize(("level", "ended"), [("viewer", "revoked"), ("caregiver", "expired")])
async def test_the_card_closes_when_access_ends(
    client: AsyncClient,
    client_from: ClientFactory,
    owner_engine: AsyncEngine,
    level: str,
    ended: str,
) -> None:
    _, h, base = await _profile(client, owner_engine)
    await _post(client, f"{base}/allergies", {"substance": "Пенициллин"}, h)
    async with client_from("203.0.113.42") as other:
        uid, oh = await _signed_in(other, owner_engine)
        await _grant(owner_engine, base, uid, level)
        r = await other.get(f"{base}/emergency-card", headers=oh)
        assert r.status_code == 200
        assert [a["substance"] for a in r.json()["allergies"]] == ["Пенициллин"]
        async with owner_engine.connect() as conn, conn.begin():
            await conn.execute(_ENDED[ended], {"p": base.rsplit("/", 1)[1], "u": uid})
        # the phone deletes its copy on this answer (2.7b)
        r = await other.get(f"{base}/emergency-card", headers=oh)
        assert (r.status_code, r.json()["code"]) == (404, "patient.not_found")


async def test_reading_the_card_writes_nothing(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)

    async def audit_count() -> int:
        async with owner_engine.connect() as conn:
            row = (
                await conn.execute(
                    bound_text("select count(*) as n from audit_logs where patient_id = :p"),
                    {"p": base.rsplit("/", 1)[1]},
                )
            ).one()
            return int(row.n)

    before = await audit_count()
    assert (await client.get(f"{base}/emergency-card", headers=h)).status_code == 200
    assert await audit_count() == before


async def test_an_uncatalogued_medicine_the_user_calls_an_immunosuppressant_shows_its_dose(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    """Q34 (physician 2026-11-18): a hand-typed medicine is on the card with its dose only when
    the user said what it is - never guessed from its name; a catalogue entry keeps its own."""
    _, h, base = await _profile(client, owner_engine)
    await _catalog(owner_engine)
    typed = _medication(name="Такролимус (гараар)", user_category="immunosuppressant")
    typed["regimen"] = _change(0, "1", "1")
    r = await client.post(f"{base}/medications", json=typed, headers=h)
    assert r.status_code == 201, r.text
    assert (r.json()["category"], r.json()["user_category"]) == ("immunosuppressant",) * 2
    unsure = _medication(name="Такролимус (мэдэхгүй)")
    unsure["regimen"] = _change(0, "1", "1")
    assert (await client.post(f"{base}/medications", json=unsure, headers=h)).status_code == 201
    card = (await client.get(f"{base}/emergency-card", headers=h)).json()
    [dosed] = card["dosed_medications"]
    assert (dosed["name"], dosed["category"]) == ("Такролимус (гараар)", "immunosuppressant")
    assert dosed["dose"] is not None
    assert card["other_medications"] == [{"name": "Такролимус (мэдэхгүй)", "brand": None}]
    # the catalogue says what a catalogued medicine is: no second answer
    both = _medication(catalog_code="TEST_TAC", name="Програф", user_category="corticosteroid")
    assert (await client.post(f"{base}/medications", json=both, headers=h)).status_code == 422
