"""The emergency card (Phase 2.7; docs/08 "Яаралтай тусламжийн карт", hazards H17, H27).

One read gives the phone what it keeps offline (encrypted): the profile, transplants, the
medicines currently taken, allergies and emergency contacts. Immunosuppressants and
corticosteroids come with the dose the user recorded and every recorded change ahead (a
taper has several); the others come by name. The route reads the
same rows, under the same RLS and profile gate, as the routes that write them. A dose is
shown as recorded, never computed or suggested (CLAUDE.md rule 10).

Only what the card shows is returned. There are no row ids (the phone may show this while the
app is locked, and an id would link a copy of it back to the records), and no HLA, notes or
other history; of the donor only the ABO type and CMV status, for blood products (Q35).
Reads are not audited, as with every other read here (2.7a, see
docs/PROGRESS.md).
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from labtrack.api.deps import PatientReadDb
from labtrack.api.errors import ErrorBody
from labtrack.api.health_records import _LIST_MAX
from labtrack.api.patients import _one
from labtrack.api.records import (
    DoseOut,
    Elapsed,
    RegimenOut,
    _medications,
    _regimen_out,
    _today,
    _transplant_out,
)
from labtrack.core.emergency import (
    BloodRecord,
    DosedCategory,
    card_blood_type,
    dosed_category,
    order_allergies,
    order_dosed,
    order_transplants,
    recently_stopped,
)
from labtrack.core.medications import upcoming_regimens
from labtrack.health import repository as health_repo
from labtrack.records import repository as records_repo

router = APIRouter(prefix="/patients/{patient_id}", tags=["emergency"])

_ERRORS: dict[int | str, dict[str, object]] = {s: {"model": ErrorBody} for s in (401, 403, 404)}


class CardPatient(BaseModel):
    full_name: str
    birth_date: date | None
    sex: str | None


class CardTransplant(BaseModel):
    organ: str
    organ_detail: str | None
    transplant_date: date
    date_precision: str
    elapsed: Elapsed | None
    transplant_number: int
    graft_status: str
    country: str
    city: str | None
    hospital: str
    follow_up_center: str | None
    follow_up_doctor: str | None
    # for blood products (Q35, physician 2026-11-18): both ABO types, ABO-incompatible, CMV
    recipient_blood_type: str | None
    donor_blood_type: str | None
    abo_incompatible: bool | None
    cmv_donor: str | None  # pos | neg | unknown
    cmv_recipient: str | None


class CardDose(BaseModel):
    """A regimen as the user recorded it from the doctor's instructions. A `schedule.type` of
    "prn" means as needed: the app must say so, not show it as a fixed dose."""

    effective_from: date
    dose_amount: DoseOut | None
    dose_unit: str | None
    dose_unit_text: str | None
    schedule: dict[str, object]
    instructions: str | None


class CardDosedMedication(BaseModel):
    category: DosedCategory
    name: str
    brand: str | None
    form: str | None
    strength: str | None
    dose: CardDose | None  # in force today; none recorded, or the first one starts later
    # every recorded change ahead, earliest first: a card kept offline outlives today
    upcoming_doses: list[CardDose]
    planned_end_on: date | None


class CardMedication(BaseModel):
    name: str
    brand: str | None


class CardStoppedMedication(BaseModel):
    """An immunosuppressant stopped in the last 14 days (Q37): its name and stop day."""

    name: str
    brand: str | None
    stopped_on: date  # the first day it was not taken


class CardAllergy(BaseModel):
    substance: str
    reaction: str | None
    severity: str | None


class CardSteroidCard(BaseModel):
    """Marked as needing a steroid emergency card (Q36), by a treating doctor or by the owner
    as their doctor told them - never inferred from the medicines."""

    marked_on: date
    by_doctor: bool


class CardContact(BaseModel):
    name: str
    relation: str | None
    phone: str
    is_transplant_center: bool


class EmergencyCardOut(BaseModel):
    patient: CardPatient
    blood_type: str | None
    # a type is recorded but not shown: records disagree, or an HSCT may have changed it
    blood_type_withheld: Literal["conflict", "hsct"] | None
    transplants: list[CardTransplant]
    dosed_medications: list[CardDosedMedication]
    # current, by name only: neither the catalogue nor the user (Q34, user_category) calls it an
    # immunosuppressant or a corticosteroid
    other_medications: list[CardMedication]
    recently_stopped: list[CardStoppedMedication]
    # none recorded is not "no known allergies": the app says so only on this dated statement
    # (Q39), which never stands beside a recorded allergy (H17)
    allergies: list[CardAllergy]
    no_known_allergies_on: date | None
    steroid_card: CardSteroidCard | None
    contacts: list[CardContact]  # transplant centres first, then as the user ordered them
    generated_at: datetime


def _dose(regimen: RegimenOut | None) -> CardDose | None:
    if regimen is None:
        return None
    return CardDose.model_validate(regimen.model_dump())


def _upcoming(rows: list[Any], today: date, planned_end_on: date | None) -> list[CardDose]:
    # a change starting after the course ends is never in force (as in records._medications)
    return [
        CardDose.model_validate(_regimen_out(r).model_dump())
        for r in upcoming_regimens(rows, today)
        if planned_end_on is None or r.effective_from <= planned_end_on
    ]


def _first_day_off(m: Any) -> date | None:
    """The first day a medicine was not taken: its stop day, or the day after a course's planned
    last day (a course that simply ran out stops too - Q37)."""
    if m.stopped_on is not None:
        return cast(date, m.stopped_on)
    if m.planned_end_on is not None:
        return cast(date, m.planned_end_on) + timedelta(days=1)
    return None


@router.get("/emergency-card", response_model=EmergencyCardOut, responses=_ERRORS)
async def get_emergency_card(patient_id: UUID, db: PatientReadDb) -> EmergencyCardOut:
    """Everything the card shows, in its order. The phone keeps it (encrypted) to show offline
    and, if the user allows it, while the app is locked. A 404 or 403 here means the access is
    gone: the phone deletes its copy."""
    patient = await _one(db, patient_id)
    transplants = order_transplants(
        [_transplant_out(r) for r in await records_repo.transplants(db, patient_id)],
        lambda t: t.graft_status,
        lambda t: t.transplant_date,
        lambda t: t.transplant_number,
    )
    blood = card_blood_type(
        BloodRecord(t.organ, t.recipient_blood_type, t.donor_blood_type) for t in transplants
    )

    every = await _medications(db, patient_id)
    current = [m for m in every if m.is_current]
    dosed = order_dosed(
        [(c, m) for m in current if (c := dosed_category(m.category)) is not None],
        lambda pair: pair[0],
    )
    history: dict[UUID, list[Any]] = {}
    for r in await records_repo.regimens(db, patient_id, [m.id for _, m in dosed]):
        history.setdefault(r.medication_id, []).append(r)
    today = _today()
    allergies = await health_repo.rows(db, health_repo.ALLERGY_LIST, patient_id, n=_LIST_MAX)
    contacts = await health_repo.rows(db, health_repo.CONTACT_LIST, patient_id, n=_LIST_MAX)
    nka = await health_repo.rows(db, health_repo.NO_KNOWN_ALLERGIES, patient_id)
    steroid = await health_repo.rows(db, health_repo.STEROID_CARD, patient_id)

    return EmergencyCardOut(
        patient=CardPatient(
            full_name=patient.full_name, birth_date=patient.birth_date, sex=patient.sex
        ),
        blood_type=blood.value,
        blood_type_withheld=blood.withheld,
        transplants=[CardTransplant.model_validate(t.model_dump()) for t in transplants],
        dosed_medications=[
            CardDosedMedication(
                category=category,
                name=m.name,
                brand=m.brand,
                form=m.form,
                strength=m.strength,
                dose=_dose(m.current_regimen),
                upcoming_doses=_upcoming(history.get(m.id, []), today, m.planned_end_on),
                planned_end_on=m.planned_end_on,
            )
            for category, m in dosed
        ],
        other_medications=[
            CardMedication(name=m.name, brand=m.brand)
            for m in current
            if dosed_category(m.category) is None
        ],
        recently_stopped=[
            CardStoppedMedication(name=m.name, brand=m.brand, stopped_on=first_off)
            for m in every
            if (first_off := _first_day_off(m)) is not None
            and dosed_category(m.category) == "immunosuppressant"
            # started again (a new record of the same medicine): it is taken now, not stopped
            and m.name.casefold() not in {c.name.casefold() for c in current}
            and recently_stopped(first_off, today)
        ],
        allergies=[
            CardAllergy.model_validate(r._mapping)
            for r in order_allergies(allergies, lambda r: r.severity)
        ],
        no_known_allergies_on=nka[0].confirmed_on if nka and not allergies else None,
        steroid_card=CardSteroidCard(marked_on=steroid[0].marked_on, by_doctor=steroid[0].by_doctor)
        if steroid
        else None,
        contacts=[
            CardContact.model_validate(r._mapping)
            for r in sorted(contacts, key=lambda c: not c.is_transplant_center)  # stable
        ],
        generated_at=datetime.now(UTC),
    )
