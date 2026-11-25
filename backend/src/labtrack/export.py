"""A profile's data for its owner to take elsewhere (Phase 7.5; data portability).

Two shapes, read as the owner under the row policies:

- JSON: every record of the profile as the app keeps it (numbers as strings, rule 7), without
  internal ids of other people (who recorded what) or storage keys;
- FHIR R4: a `collection` Bundle - Patient, AllergyIntolerance (a confirmed "no known
  allergy" as SNOMED 716186003, Q39), MedicationStatement (dose as
  entered, in `dosage.text`), Observation (confirmed lab values: as printed, the lab's range as
  text, the server's flag as interpretation; vital signs) and Procedure (transplants). FHIR
  JSON numbers are numbers: the printed text is kept in `valueString` when the value is not a
  plain number, and the exact decimal is written as a JSON number from its text (no float).

Drafts, rejected reports and documents are left out (rule 4; documents are files of their own).
"""

import json
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, LiteralString
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.db.sql import bound_text
from labtrack.summary import _dose

_TABLES: dict[str, LiteralString] = {
    "profile": "select full_name, birth_date, sex::text as sex, created_at from patients"
    " where id = :p",
    "transplants": "select organ::text as organ, organ_detail, transplant_date, date_precision,"
    " country, city, hospital, surgeon, transplant_number, donor_type::text as donor_type,"
    " donor_relation, recipient_blood_type, donor_blood_type, abo_incompatible, cmv_donor,"
    " cmv_recipient, ebv_donor, ebv_recipient, hla_mismatch, primary_disease,"
    " pre_transplant_dialysis, induction_therapy, graft_status::text as graft_status,"
    " graft_status_date, graft_failure_reason, follow_up_center, follow_up_doctor, notes"
    " from transplants where patient_id = :p order by transplant_date",
    "medications": "select m.name, m.brand, m.form, m.strength, m.route, m.purpose,"
    " m.prescribed_by, m.started_on, m.stopped_on, m.stop_reason, m.planned_end_on, m.notes,"
    " coalesce((select jsonb_agg(jsonb_build_object('effective_from', g.effective_from,"
    " 'dose_amount', g.dose_amount::text, 'dose_unit', g.dose_unit,"
    " 'dose_unit_text', g.dose_unit_text, 'schedule', g.schedule,"
    " 'instructions', g.instructions) order by g.effective_from, g.seq)"
    " from medication_regimens g where g.medication_id = m.id and g.voided_at is null),"
    " '[]'::jsonb) as regimens"
    " from medications m where m.patient_id = :p order by m.started_on nulls first, m.name",
    "intakes": "select m.name as medication, i.scheduled_at, i.taken_at, i.status::text as status"
    " from medication_intakes i join medications m on m.id = i.medication_id"
    " and m.patient_id = i.patient_id where i.patient_id = :p"
    " order by coalesce(i.scheduled_at, i.taken_at)",
    "lab_results": "select r.collected_at, r.collected_precision, r.lab_name, r.specimen,"
    " (r.source = 'typed' or r.collected_edited) as collected_by_user,"
    " v.test_code, t.loinc, coalesce(t.name_en, v.raw_name) as name_en, t.name_mn, v.raw_name,"
    " v.raw_value, v.raw_unit, v.value_canonical::text as value_canonical, v.unit_canonical,"
    " v.comparator, v.ref_text, v.critical_text, v.flag::text as flag, v.lab_flag"
    " from lab_reports r join lab_results v on v.report_id = r.id"
    " and v.patient_id = r.patient_id left join test_catalog t on t.code = v.test_code"
    " where r.patient_id = :p and r.status = 'confirmed'"
    " order by r.collected_at, r.id, v.position",
    "events": "select kind::text as kind, title, started_on, ended_on, place, description,"
    " outcome from clinical_events where patient_id = :p order by started_on",
    "vitals": "select kind::text as kind, value::text as value, unit, measured_at, source, note"
    " from vitals where patient_id = :p order by measured_at",
    "allergies": "select substance, reaction, severity, noted_on from allergies"
    " where patient_id = :p order by substance",
    # a dated "no known allergies" and the steroid emergency card mark (0048; Q39, Q36)
    "no_known_allergies": "select confirmed_on from no_known_allergies where patient_id = :p",
    "steroid_card": "select marked_on, by_doctor from steroid_cards where patient_id = :p",
    "contacts": "select name, relation, phone, is_transplant_center from emergency_contacts"
    " where patient_id = :p order by sort_order",
    "appointments": "select kind::text as kind, title, scheduled_at, place, notes,"
    " status::text as status from appointments where patient_id = :p order by scheduled_at",
    "questions": "select text, answer, status::text as status, created_at from doctor_questions"
    " where patient_id = :p order by created_at",
    "targets": "select test_code, low::text as low, high::text as high, unit, valid_from,"
    " valid_to, note from patient_targets where patient_id = :p order by test_code, valid_from",
}


MAX_ROWS = 100_000  # per kind of record: far beyond any real profile (5 years of doses ~11 000)


class ExportTooLargeError(Exception):
    """More records of one kind than an export carries."""


async def gather(db: AsyncSession, patient_id: UUID) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, sql in _TABLES.items():
        result = await db.execute(
            bound_text(sql + " limit :n"), {"p": patient_id, "n": MAX_ROWS + 1}
        )
        rows = [dict(r._mapping) for r in result]
        if len(rows) > MAX_ROWS:
            raise ExportTooLargeError(key)
        out[key] = rows[0] if key == "profile" and rows else rows
    return out


def local_today() -> date:
    """Today in Ulaanbaatar (the app's day for "taken now")."""
    return datetime.now(ZoneInfo("Asia/Ulaanbaatar")).date()


def last_day(medication: dict[str, Any]) -> date | None:
    """FHIR `effectivePeriod.end` is the last day taken (an inclusive bound); the app keeps the
    first day NOT taken (`stopped_on`, Q21, physician 2026-11-18) - one day earlier, never
    before the start. Without a stop, a course's planned last day (`planned_end_on`, already
    a last day taken). The JSON export keeps the app's own `stopped_on`: one day later."""
    stopped = medication["stopped_on"]
    if not isinstance(stopped, date):
        planned = medication.get("planned_end_on")
        return planned if isinstance(planned, date) else None
    last = stopped - timedelta(days=1)
    started = medication["started_on"]
    return max(last, started) if isinstance(started, date) else last


def _plain(value: object) -> object:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    return value


def to_json(data: dict[str, Any]) -> bytes:
    body = {"format": "labtrack-export", "version": 1, **data}
    return json.dumps(body, ensure_ascii=False, default=_plain, indent=1).encode()


# --- FHIR R4 ---------------------------------------------------------------------------------

_INTERPRETATION = {
    "normal": ("N", "Normal"),
    "low": ("L", "Low"),
    "high": ("H", "High"),
    "critical_low": ("LL", "Critical low"),
    "critical_high": ("HH", "Critical high"),
    "abnormal": ("A", "Abnormal"),
}
_SEX = {"male": "male", "female": "female"}
_CATEGORY_SYSTEM = "http://terminology.hl7.org/CodeSystem/observation-category"
_LAB, _VITAL = "laboratory", "vital-signs"


def _category(value: str) -> dict[str, object]:
    return {"coding": [{"system": _CATEGORY_SYSTEM, "code": value}]}


class _Raw(str):
    """A JSON number written exactly from its decimal text (never through a float)."""

    __slots__ = ()


_JSON_NUMBER = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?")


def _number(text: str | None) -> _Raw | None:
    """A plain decimal as a JSON number; anything else (NaN, 1_000, .5) is not one."""
    if text is None or not _JSON_NUMBER.fullmatch(text):
        return None
    return _Raw(text)


def _dumps(value: object) -> str:
    """json.dumps with _Raw numbers written verbatim."""
    if isinstance(value, _Raw):
        return str(value)
    if isinstance(value, dict):
        return "{" + ",".join(f"{json.dumps(k)}:{_dumps(v)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_dumps(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False, default=_plain)


_SNOMED = "http://snomed.info/sct"
NKA_SNOMED = "716186003"  # No known allergy (situation)
_NKA_TEXT = "No known allergy (situation)"
# FHIR codes are constants: error_codes.py reads quoted code literals as API errors
_ACTIVE, _CONFIRMED = "active", "confirmed"
_AUTHOR = "author"  # provenance-participant-type (a FHIR code, not an API error code)
_BY_PERSON = (
    "Sample date/time entered or corrected by a person (patient or caregiver),"
    " not read from the lab report"
)
_CLINICAL = "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical"
_VERIFY = "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification"


def to_fhir(data: dict[str, Any]) -> bytes:
    person = data.get("profile") or {}
    patient_ref = "urn:uuid:patient"
    entries: list[dict[str, Any]] = [
        {
            "fullUrl": patient_ref,
            "resource": {
                "resourceType": "Patient",
                "name": [{"text": person.get("full_name")}],
                "gender": _SEX.get(person.get("sex") or "", "unknown"),
                **({"birthDate": _plain(person["birth_date"])} if person.get("birth_date") else {}),
            },
        }
    ]
    subject = {"reference": patient_ref}
    for a in data["allergies"]:
        entries.append(
            {
                "resource": {
                    "resourceType": "AllergyIntolerance",
                    "patient": subject,
                    "code": {"text": a["substance"]},
                    **({"reaction": [{"description": a["reaction"]}]} if a["reaction"] else {}),
                }
            }
        )
    if not data["allergies"] and data["no_known_allergies"]:
        # stated, dated "no known allergy" (AU Core / IPS) - never written for "none recorded";
        # the patient's (or their caregiver's) statement, not a clinician's (asserter)
        entries.append(
            {
                "resource": {
                    "resourceType": "AllergyIntolerance",
                    "patient": subject,
                    "asserter": subject,
                    "clinicalStatus": {"coding": [{"system": _CLINICAL, "code": _ACTIVE}]},
                    "verificationStatus": {"coding": [{"system": _VERIFY, "code": _CONFIRMED}]},
                    "code": {
                        "coding": [{"system": _SNOMED, "code": NKA_SNOMED, "display": _NKA_TEXT}],
                        "text": "No known allergy",
                    },
                    "recordedDate": _plain(data["no_known_allergies"][0]["confirmed_on"]),
                }
            }
        )
    for m in data["medications"]:
        end = last_day(m)
        # a stopped medicine, or a course whose planned last day has passed, is not taken now
        status = "completed" if end is not None and end < local_today() else "active"
        dosage = [{"text": _dose(g)} for g in m["regimens"][-1:]]  # the dose in force last
        entries.append(
            {
                "resource": {
                    "resourceType": "MedicationStatement",
                    "status": status,
                    "subject": subject,
                    "medicationCodeableConcept": {
                        "text": " ".join(v for v in (m["name"], m["strength"], m["form"]) if v)
                    },
                    "effectivePeriod": {
                        k: _plain(v) for k, v in (("start", m["started_on"]), ("end", end)) if v
                    },
                    **({"dosage": dosage} if dosage else {}),
                }
            }
        )
    for r in data["lab_results"]:
        code: dict[str, Any] = {"text": r["name_en"] or r["raw_name"]}
        if r["loinc"]:
            code["coding"] = [{"system": "http://loinc.org", "code": r["loinc"]}]
        value: dict[str, Any]
        exact = _number(r["value_canonical"]) if r["comparator"] is None else None
        if exact is not None and r["unit_canonical"]:
            value = {"valueQuantity": {"value": exact, "unit": r["unit_canonical"]}}
        else:
            value = {"valueString": " ".join(v for v in (r["raw_value"], r["raw_unit"]) if v)}
        obs: dict[str, Any] = {
            "resourceType": "Observation",
            "status": "final",
            "category": [_category(_LAB)],
            "subject": subject,
            "code": code,
            "effectiveDateTime": _plain(r["collected_at"]),
            **value,
        }
        if r["ref_text"]:
            obs["referenceRange"] = [{"text": r["ref_text"]}]
        if r["flag"] in _INTERPRETATION:
            c, d = _INTERPRETATION[r["flag"]]
            obs["interpretation"] = [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                            "code": c,
                            "display": d,
                        }
                    ]
                }
            ]
        if not r.get("collected_by_user"):
            entries.append({"resource": obs})
            continue
        # the sample's date/time was typed in or changed by the patient, not printed by the lab
        # (Q65): said in the resource and by a Provenance with the patient as author (HL7)
        ref = f"urn:uuid:{uuid4()}"  # a valid urn:uuid (security review L2)
        obs["note"] = [{"text": _BY_PERSON}]
        entries.append({"fullUrl": ref, "resource": obs})
        entries.append(
            {
                "resource": {
                    "resourceType": "Provenance",
                    "target": [{"reference": ref}],
                    "recorded": datetime.now(UTC).isoformat(),
                    "agent": [
                        {
                            "type": {
                                "coding": [
                                    {
                                        "system": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
                                        "code": _AUTHOR,
                                    }
                                ]
                            },
                            "who": subject,
                        }
                    ],
                }
            }
        )
    for v in data["vitals"]:
        quantity = _number(v["value"])
        entries.append(
            {
                "resource": {
                    "resourceType": "Observation",
                    "status": "final",
                    "category": [_category(_VITAL)],
                    "subject": subject,
                    "code": {"text": v["kind"]},
                    "effectiveDateTime": _plain(v["measured_at"]),
                    **(
                        {"valueQuantity": {"value": quantity, "unit": v["unit"]}}
                        if quantity is not None and v["unit"]
                        else {"valueString": v["value"]}
                    ),
                }
            }
        )
    for x in data["transplants"]:
        entries.append(
            {
                "resource": {
                    "resourceType": "Procedure",
                    "status": "completed",
                    "subject": subject,
                    "code": {"text": f"{x['organ']} transplant"},
                    **(
                        {
                            "performedDateTime": str(_plain(x["transplant_date"]))[
                                : {"year": 4, "month": 7}.get(x["date_precision"], 10)
                            ]
                        }
                        if x["transplant_date"]
                        else {}
                    ),
                }
            }
        )
    bundle = {"resourceType": "Bundle", "type": "collection", "entry": entries}
    return _dumps(bundle).encode()
