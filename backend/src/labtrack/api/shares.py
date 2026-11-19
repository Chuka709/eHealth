"""Sharing a profile by username with a doctor or a viewer (Phase 7.1; docs/04 §2, docs/06 §6;
hazard H36; migration 0040).

Every step is a definer function that checks who may do it; these routes only translate, as
the caregiver routes do. Three people use them:

- the owner invites by username as doctor or viewer for 1, 7 or 30 days or until revoked,
  sees who has the profile and until when, cancels an invitation, ends an access, and sees who
  opened the profile on which days (the last 90);
- the invited person sees open invitations (who asks, as what, for how long) and answers;
- a doctor or a viewer steps back.

An invitation is answered the same way whoever the username is (202, no id). Access is
read-only and covers the whole profile; it starts when the person accepts.
"""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import DBAPIError

from labtrack.api.caregivers import Username, _owner_only, _pg
from labtrack.api.deps import PatientReadDb, PatientWriteDb, PhiDb
from labtrack.api.errors import AppError, ErrorBody
from labtrack.api.ratelimit import per_user
from labtrack.config import get_settings
from labtrack.db.sql import bound_text

router = APIRouter(prefix="/patients/{patient_id}", tags=["shares"])
me_router = APIRouter(prefix="/me", tags=["shares"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorBody},
    403: {"model": ErrorBody},
    404: {"model": ErrorBody},
    422: {"model": ErrorBody},
    429: {"model": ErrorBody},
}

Level = Literal["doctor", "viewer"]
Days = Literal[1, 7, 30]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ShareInviteIn(_Strict):
    username: Username
    level: Level
    days: Days | None  # None: until the owner revokes it


class ShareOut(BaseModel):
    user_id: UUID
    display_name: str
    level: Level
    since: datetime | None
    expires_at: datetime | None  # None: until revoked
    last_viewed_at: datetime | None


class ShareInvitationOut(BaseModel):
    id: UUID
    username: str  # as the owner typed it; no name before the person accepts
    level: Level
    access_days: int | None
    created_at: datetime
    expires_at: datetime  # the invitation's own deadline (14 days)


class SharesOut(BaseModel):
    shares: list[ShareOut]
    invitations: list[ShareInvitationOut]


class ShareViewOut(BaseModel):
    user_id: UUID
    display_name: str
    day: date  # Ulaanbaatar day
    first_at: datetime
    last_at: datetime


class MyShareInvitationOut(BaseModel):
    id: UUID
    inviter_name: str  # the profile's name only after accepting (Q45)
    level: Level
    access_days: int | None
    created_at: datetime
    expires_at: datetime


class RespondIn(_Strict):
    invitation_id: UUID
    accept: bool


# --- the owner ---------------------------------------------------------------------------


@router.post(
    "/share-invitations",
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERRORS,
    dependencies=[
        Depends(per_user("share_invite", lambda: get_settings().rate_caregiver_invite_per_minute))
    ],
)
async def invite(patient_id: UUID, body: ShareInviteIn, db: PatientWriteDb) -> Response:
    """Invite by username. The answer is the same whether or not the username is anyone's."""
    await _owner_only(db, patient_id)
    try:
        await db.execute(
            bound_text("select invite_access(:p, :u, :l, :d)"),
            {"p": patient_id, "u": body.username, "l": body.level, "d": body.days},
        )
    except DBAPIError as exc:
        state, _ = _pg(exc)
        if state == "54000":  # 20 open invitations, or 30 lookups in the last hour
            raise AppError(429, "share.too_many") from None
        raise
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.get("/shares", response_model=SharesOut, responses=_ERRORS)
async def shares(patient_id: UUID, db: PatientReadDb) -> SharesOut:
    await _owner_only(db, patient_id)
    people = (
        await db.execute(bound_text("select * from owner_shares(:p)"), {"p": patient_id})
    ).all()
    open_ = (
        await db.execute(
            bound_text("select * from owner_access_invitations(:p)"), {"p": patient_id}
        )
    ).all()
    return SharesOut(
        shares=[ShareOut(**r._mapping) for r in people],
        invitations=[ShareInvitationOut(**r._mapping) for r in open_],
    )


@router.get("/share-views", response_model=list[ShareViewOut], responses=_ERRORS)
async def share_views(patient_id: UUID, db: PatientReadDb) -> list[ShareViewOut]:
    """Who opened the profile through a share, by day (the last 90 days)."""
    await _owner_only(db, patient_id)
    rows = (
        await db.execute(bound_text("select * from owner_profile_views(:p)"), {"p": patient_id})
    ).all()
    return [ShareViewOut(**r._mapping) for r in rows]


@router.delete(
    "/share-invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS
)
async def cancel_invitation(patient_id: UUID, invitation_id: UUID, db: PatientWriteDb) -> Response:
    await _owner_only(db, patient_id)
    done = (
        await db.execute(
            bound_text(
                "select revoke_access_invitation(i.id) from access_invitations i"
                " where i.id = :i and i.patient_id = :p"
            ),
            {"i": invitation_id, "p": patient_id},
        )
    ).scalar_one_or_none()
    if not done:
        raise AppError(404, "share.invitation_not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/shares/{user_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def end_share(patient_id: UUID, user_id: UUID, db: PatientWriteDb) -> Response:
    await _owner_only(db, patient_id)
    done = (
        await db.execute(bound_text("select revoke_share(:p, :u)"), {"p": patient_id, "u": user_id})
    ).scalar_one()
    if not done:
        raise AppError(404, "share.not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- a doctor or a viewer ----------------------------------------------------------------


class LeaveIn(_Strict):
    patient_id: UUID


@me_router.post("/shares/leave", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def leave(body: LeaveIn, db: PhiDb) -> Response:
    """The doctor or viewer steps back. A /me route: their access is read-only, so the profile's
    write gate would refuse them, and leave_share() acts only on the caller's own access."""
    done = (
        await db.execute(bound_text("select leave_share(:p)"), {"p": body.patient_id})
    ).scalar_one()
    if not done:
        raise AppError(403, "share.not_shared")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- the invited person ------------------------------------------------------------------


@me_router.get("/share-invitations", response_model=list[MyShareInvitationOut], responses=_ERRORS)
async def my_invitations(db: PhiDb) -> list[MyShareInvitationOut]:
    rows = (await db.execute(bound_text("select * from my_access_invitations()"))).all()
    return [MyShareInvitationOut(**r._mapping) for r in rows]


@me_router.post(
    "/share-invitations/respond", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS
)
async def respond(body: RespondIn, db: PhiDb) -> Response:
    """Accept or decline. A "no" is always possible; a "yes" only while the invitation stands."""
    done = (
        await db.execute(
            bound_text("select respond_access_invitation(:i, :a)"),
            {"i": body.invitation_id, "a": body.accept},
        )
    ).scalar_one()
    if not done:
        raise AppError(404, "share.invitation_not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
