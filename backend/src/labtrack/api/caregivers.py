"""Caregivers (Phase 2.8d; docs/08 "Асран хамгаалагч (opt-in)"; hazards H16, H20; Q42).

Every step is a definer function from 0020/0025 that checks who may do it; these routes only
translate. Three people use them:

- the owner of a profile invites by username, sees the caregivers and open invitations,
  cancels an invitation, ends a caregiver's access, and pauses a caregiver's alerts;
- the invited person sees their open invitations (who asks, for which profile) and answers;
- a caregiver chooses their own alert delay, or leaves.

An invitation is answered the same way whoever the username is (202, no id): whether it
reached anyone shows only in the owner's list, and the lookup behind it is limited to 30 an
hour (0002; user decision (a), 2026-11-11). No caregivers on a child's profile in the MVP
(decision (b); 0025). Names appear only to the people concerned and are never logged.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.api.deps import PatientReadDb, PatientWriteDb, PhiDb
from labtrack.api.errors import AppError, ErrorBody
from labtrack.api.ratelimit import per_user
from labtrack.config import get_settings
from labtrack.core.medications import IntakeRecord, is_taken, merged_all
from labtrack.db.sql import bound_text

router = APIRouter(prefix="/patients/{patient_id}", tags=["caregivers"])
me_router = APIRouter(prefix="/me", tags=["caregivers"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorBody},
    403: {"model": ErrorBody},
    404: {"model": ErrorBody},
    409: {"model": ErrorBody},
    422: {"model": ErrorBody},
    429: {"model": ErrorBody},
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# usernames as the admin creates them (0002); anything else cannot be anyone
Username = Annotated[
    str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[a-z0-9._]{3,32}$")
]


class InviteIn(_Strict):
    username: Username


class CaregiverOut(BaseModel):
    user_id: UUID
    display_name: str
    since: datetime | None
    missed_dose_after_min: int | None  # null: alerts off (or not chosen yet)
    critical_result: bool
    owner_paused: bool


class OwnerInvitationOut(BaseModel):
    id: UUID
    username: str  # as the owner typed it; no name before the person accepts
    created_at: datetime
    expires_at: datetime


class CaregiversOut(BaseModel):
    caregivers: list[CaregiverOut]
    invitations: list[OwnerInvitationOut]


class PauseIn(_Strict):
    paused: bool


class AlertsIn(_Strict):
    # 15-240 minutes after the dose time, or null for off (0020; H16)
    missed_dose_after_min: Annotated[int, Field(ge=15, le=240)] | None
    critical_result: bool


class AlertsOut(BaseModel):
    missed_dose_after_min: int | None
    critical_result: bool
    owner_paused: bool
    chosen: bool  # false until the caregiver picks (the app then offers 30 minutes)
    # current medications with reminders on - the only ones alerts watch (2.8e): the app says
    # so, and that alerts are off for the rest, so no silence is read as "taken"
    watched_medications: int
    # the owner's phone may show reminders late (no exact alarms, Q48): alerts wait >= 90 min
    late_reminders: bool


class MyInvitationOut(BaseModel):
    id: UUID
    inviter_name: str  # who invites; the profile's full name only after accepting (Q45)
    created_at: datetime
    expires_at: datetime


class RespondIn(_Strict):
    invitation_id: UUID
    accept: bool


def _pg(exc: DBAPIError) -> tuple[str | None, str | None]:
    pg = getattr(exc.orig, "__cause__", None) or exc.orig
    return getattr(pg, "sqlstate", None), getattr(pg, "hint", None)


async def _owner_only(db: AsyncSession, patient_id: UUID) -> None:
    owner = (await db.execute(bound_text("select is_owner(:p)"), {"p": patient_id})).scalar_one()
    if not owner:
        raise AppError(403, "caregiver.owner_only")


# --- the owner ---------------------------------------------------------------------------


@router.post(
    "/caregiver-invitations",
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERRORS,
    dependencies=[
        Depends(
            per_user("caregiver_invite", lambda: get_settings().rate_caregiver_invite_per_minute)
        )
    ],
)
async def invite(patient_id: UUID, body: InviteIn, db: PatientWriteDb) -> Response:
    """Invite by username. The answer is the same whether or not the username is anyone's."""
    await _owner_only(db, patient_id)
    try:
        await db.execute(
            bound_text("select invite_caregiver(:p, :u)"), {"p": patient_id, "u": body.username}
        )
    except DBAPIError as exc:
        state, hint = _pg(exc)
        if state == "42501" and hint == "caregiver_sharing":
            raise AppError(409, "caregiver.consent_required") from None
        if state == "42501" and hint == "minor_profile":
            raise AppError(409, "caregiver.minor_profile") from None
        if state == "54000":  # 20 open invitations, or 30 lookups in the last hour
            raise AppError(429, "caregiver.too_many") from None
        raise
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.get("/caregivers", response_model=CaregiversOut, responses=_ERRORS)
async def caregivers(patient_id: UUID, db: PatientReadDb) -> CaregiversOut:
    await _owner_only(db, patient_id)
    people = (
        await db.execute(bound_text("select * from owner_caregivers(:p)"), {"p": patient_id})
    ).all()
    open_ = (
        await db.execute(
            bound_text("select * from owner_caregiver_invitations(:p)"), {"p": patient_id}
        )
    ).all()
    return CaregiversOut(
        caregivers=[CaregiverOut(**r._mapping) for r in people],
        invitations=[OwnerInvitationOut(**r._mapping) for r in open_],
    )


@router.delete(
    "/caregiver-invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ERRORS,
)
async def cancel_invitation(patient_id: UUID, invitation_id: UUID, db: PatientWriteDb) -> Response:
    await _owner_only(db, patient_id)
    done = (
        await db.execute(
            bound_text(
                "select revoke_caregiver_invitation(i.id) from caregiver_invitations i"
                " where i.id = :i and i.patient_id = :p"
            ),
            {"i": invitation_id, "p": patient_id},
        )
    ).scalar_one_or_none()
    if not done:
        raise AppError(404, "caregiver.invitation_not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/caregivers/{user_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def end_access(patient_id: UUID, user_id: UUID, db: PatientWriteDb) -> Response:
    await _owner_only(db, patient_id)
    done = (
        await db.execute(
            bound_text("select revoke_caregiver(:p, :u)"), {"p": patient_id, "u": user_id}
        )
    ).scalar_one()
    if not done:
        raise AppError(404, "caregiver.not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/caregivers/{user_id}/pause", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS
)
async def pause(patient_id: UUID, user_id: UUID, body: PauseIn, db: PatientWriteDb) -> Response:
    await _owner_only(db, patient_id)
    done = (
        await db.execute(
            bound_text("select pause_caregiver_alerts(:p, :u, :x)"),
            {"p": patient_id, "u": user_id, "x": body.paused},
        )
    ).scalar_one()
    if not done:
        raise AppError(404, "caregiver.not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- the caregiver -----------------------------------------------------------------------


_WATCHED = bound_text(
    "select count(*) from medications where patient_id = :p and reminders_enabled"
    " and (stopped_on is null or stopped_on > local_today())"
    " and (planned_end_on is null or planned_end_on >= local_today())"
)


async def _alerts(db: AsyncSession, patient_id: UUID) -> AlertsOut:
    watched = int((await db.execute(_WATCHED, {"p": patient_id})).scalar_one())
    late = bool(
        (
            await db.execute(
                bound_text("select owner_reminders_may_be_late(:p)"), {"p": patient_id}
            )
        ).scalar_one()
    )
    row = (
        await db.execute(
            bound_text(
                "select missed_dose_after_min, critical_result, owner_paused"
                " from caregiver_alert_settings"
                " where patient_id = :p and caregiver_user_id = app_user_id()"
            ),
            {"p": patient_id},
        )
    ).one_or_none()
    if row is None:
        return AlertsOut(
            missed_dose_after_min=None,
            critical_result=False,
            owner_paused=False,
            chosen=False,
            watched_medications=watched,
            late_reminders=late,
        )
    # a pause before any choice leaves a row with nothing chosen (0020)
    chosen = row.missed_dose_after_min is not None or row.critical_result
    return AlertsOut(
        **row._mapping, chosen=chosen, watched_medications=watched, late_reminders=late
    )


async def _caregiver_only(db: AsyncSession, patient_id: UUID) -> None:
    level = (
        await db.execute(
            bound_text(
                "select level::text from patient_access where patient_id = :p"
                " and user_id = app_user_id() and revoked_at is null"
                " and (expires_at is null or expires_at > now())"
            ),
            {"p": patient_id},
        )
    ).scalar_one_or_none()
    if level != "caregiver":
        raise AppError(403, "caregiver.not_caregiver")


@router.get("/caregiver-alerts", response_model=AlertsOut, responses=_ERRORS)
async def my_alerts(patient_id: UUID, db: PatientReadDb) -> AlertsOut:
    await _caregiver_only(db, patient_id)
    return await _alerts(db, patient_id)


@router.put("/caregiver-alerts", response_model=AlertsOut, responses=_ERRORS)
async def set_alerts(patient_id: UUID, body: AlertsIn, db: PatientWriteDb) -> AlertsOut:
    await _caregiver_only(db, patient_id)
    await db.execute(
        bound_text("select set_caregiver_alerts(:p, :m, :c)"),
        {"p": patient_id, "m": body.missed_dose_after_min, "c": body.critical_result},
    )
    return await _alerts(db, patient_id)


@router.post("/leave", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def leave(patient_id: UUID, db: PatientWriteDb) -> Response:
    """The caregiver steps back; their alerts go with them."""
    done = (
        await db.execute(bound_text("select leave_patient(:p)"), {"p": patient_id})
    ).scalar_one()
    if not done:
        raise AppError(403, "caregiver.not_caregiver")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class DoseAlertOut(BaseModel):
    """What a dose alert was about, and what is recorded for that dose now (decision 3: a push
    already sent is not withdrawn; the app shows the current state instead)."""

    slot_at: datetime
    medication_id: UUID
    medication_name: str
    recorded: Literal["taken", "skipped"] | None  # None: still nothing recorded


_DOSE_ALERT = bound_text(
    "select a.slot_at, a.medication_id, m.name as medication_name from dose_alerts a"
    " join medications m on m.id = a.medication_id and m.patient_id = a.patient_id"
    " where a.id = :i and a.patient_id = :p"
)
_DOSE_RECORDS = bound_text(
    "select status, taken_at from medication_intakes"
    " where patient_id = :p and medication_id = :m and scheduled_at = :at"
)


@router.get("/dose-alerts/{alert_id}", response_model=DoseAlertOut, responses=_ERRORS)
async def dose_alert(
    patient_id: UUID,
    # bigint range: a larger id would overflow in the database (500) instead of a 422
    alert_id: Annotated[int, Path(ge=1, le=2**63 - 1)],
    db: PatientReadDb,
) -> DoseAlertOut:
    """For the caregiver it was sent to, or the profile's owner (RLS on dose_alerts)."""
    row = (await db.execute(_DOSE_ALERT, {"i": alert_id, "p": patient_id})).one_or_none()
    if row is None:
        raise AppError(404, "caregiver.alert_not_found")
    records = [
        IntakeRecord(r.status, r.taken_at)
        for r in await db.execute(
            _DOSE_RECORDS, {"p": patient_id, "m": row.medication_id, "at": row.slot_at}
        )
    ]
    recorded: Literal["taken", "skipped"] | None = None
    if records:
        recorded = "taken" if is_taken(merged_all(records)) else "skipped"
    return DoseAlertOut(**row._mapping, recorded=recorded)


# --- the invited person ------------------------------------------------------------------


@me_router.get("/caregiver-invitations", response_model=list[MyInvitationOut], responses=_ERRORS)
async def my_invitations(db: PhiDb) -> list[MyInvitationOut]:
    """Open invitations that could still be accepted, and who asks."""
    rows = (await db.execute(bound_text("select * from my_caregiver_invitations()"))).all()
    return [MyInvitationOut(**r._mapping) for r in rows]


@me_router.post(
    "/caregiver-invitations/respond", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS
)
async def respond(body: RespondIn, db: PhiDb) -> Response:
    """Accept or decline. A "no" is always possible; a "yes" only while the invitation still
    stands (the inviter owns the profile and consents to sharing it)."""
    done = (
        await db.execute(
            bound_text("select respond_caregiver_invitation(:i, :a)"),
            {"i": body.invitation_id, "a": body.accept},
        )
    ).scalar_one()
    if not done:
        raise AppError(404, "caregiver.invitation_not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
