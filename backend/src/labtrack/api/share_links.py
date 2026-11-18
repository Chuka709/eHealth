"""Sharing by link or QR with someone without an account (Phase 7.2; docs/04 §2, §6.7;
hazard H37; decision Q62; migration 0041).

The owner makes a link for chosen sections and a time; the server makes the token and a 6-digit
PIN and shows both once (only hashes are kept). Whoever has the link opens it with the PIN:
the attempt is counted before the PIN is checked, the 5th wrong PIN revokes the link and tells
the owner. A right PIN opens a 30-minute viewing session. A session reads nothing through the
row policies: every share route calls a definer function of its own that checks the session
and applies the link's sections and dates in the database (0041; 7.3 adds the sections).
"""

import secrets
from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.api.caregivers import _owner_only
from labtrack.api.deps import AnonymousDb, PatientReadDb, PatientWriteDb
from labtrack.api.errors import AppError, ErrorBody
from labtrack.api.numbers import num
from labtrack.api.ratelimit import per_ip, per_user
from labtrack.auth.service import run_hashing
from labtrack.config import get_settings
from labtrack.core.security import hash_password, new_opaque_token, sha256_hex, verify_password
from labtrack.db.sql import bound_text

router = APIRouter(prefix="/patients/{patient_id}", tags=["share-links"])


async def _no_store(response: Response) -> None:
    """Nothing a share route answers is kept by a browser or a proxy."""
    response.headers["Cache-Control"] = "no-store"


public_router = APIRouter(prefix="/share", tags=["share-links"], dependencies=[Depends(_no_store)])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorBody},
    403: {"model": ErrorBody},
    404: {"model": ErrorBody},
    422: {"model": ErrorBody},
    429: {"model": ErrorBody},
}

Scope = Literal["summary", "labs", "meds", "transplant", "events", "vitals"]
# what new_opaque_token() makes: 32 random bytes, base64url without padding
Token = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{43}$")]
Pin = Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ShareLinkIn(_Strict):
    scopes: Annotated[list[Scope], Field(min_length=1, max_length=6)]
    days: Literal[1, 7, 30]
    max_views: Annotated[int, Field(ge=1, le=100)] | None = None
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def _check(self) -> "ShareLinkIn":
        if len(set(self.scopes)) != len(self.scopes):
            raise ValueError("scopes repeat")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from after date_to")
        return self


class ShareLinkCreatedOut(BaseModel):
    """Shown once: neither the token nor the PIN can be read again."""

    id: UUID
    token: str  # goes in the link's URL fragment (#), never in a query or a path
    pin: str  # said or written separately from the link
    expires_at: datetime


class ShareLinkOut(BaseModel):
    id: UUID
    scopes: list[Scope]
    date_from: date | None
    date_to: date | None
    created_at: datetime
    expires_at: datetime
    max_views: int | None
    view_count: int
    revoked_at: datetime | None
    revoked_reason: Literal["owner", "pin_locked"] | None
    last_viewed_at: datetime | None


class ShareLinkViewOut(BaseModel):
    opened_at: datetime


class OpenIn(_Strict):
    token: Token
    pin: Pin


class ShareSessionOut(BaseModel):
    session: str  # sent back as X-Share-Session on every share route
    expires_at: datetime
    scopes: list[Scope]
    date_from: date | None
    date_to: date | None


class SharedProfileOut(BaseModel):
    full_name: str  # who the record is about (the viewer must know)
    scopes: list[Scope]
    date_from: date | None
    date_to: date | None
    expires_at: datetime


# --- the owner ---------------------------------------------------------------------------


@router.post(
    "/share-links",
    response_model=ShareLinkCreatedOut,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    dependencies=[
        Depends(per_user("share_link", lambda: get_settings().rate_share_link_per_minute))
    ],
)
async def create_link(
    patient_id: UUID, body: ShareLinkIn, db: PatientWriteDb, response: Response
) -> ShareLinkCreatedOut:
    await _owner_only(db, patient_id)
    token, token_hash = new_opaque_token()
    pin = f"{secrets.randbelow(10**6):06d}"
    pin_hash = await run_hashing(hash_password, pin)
    try:
        row = (
            await db.execute(
                bound_text(
                    "select create_share_link(:p, :t, :h, cast(:s as text[]), :f, :u, :d, :m)"
                ),
                {
                    "p": patient_id,
                    "t": token_hash,
                    "h": pin_hash,
                    "s": list(body.scopes),
                    "f": body.date_from,
                    "u": body.date_to,
                    "d": body.days,
                    "m": body.max_views,
                },
            )
        ).scalar_one()
    except DBAPIError as exc:
        pg = getattr(exc.orig, "__cause__", None) or exc.orig
        if getattr(pg, "sqlstate", None) == "54000":
            raise AppError(429, "share.too_many_links") from None
        raise
    expires_at = (
        await db.execute(
            bound_text("select expires_at from owner_share_links(:p) where id = :l"),
            {"p": patient_id, "l": row},
        )
    ).scalar_one()
    response.headers["Cache-Control"] = "no-store"
    return ShareLinkCreatedOut(id=row, token=token, pin=pin, expires_at=expires_at)


@router.get("/share-links", response_model=list[ShareLinkOut], responses=_ERRORS)
async def links(patient_id: UUID, db: PatientReadDb) -> list[ShareLinkOut]:
    """The profile's links of the last 90 days, live or not."""
    await _owner_only(db, patient_id)
    rows = (
        await db.execute(bound_text("select * from owner_share_links(:p)"), {"p": patient_id})
    ).all()
    return [ShareLinkOut(**r._mapping) for r in rows]


@router.get(
    "/share-links/{link_id}/views", response_model=list[ShareLinkViewOut], responses=_ERRORS
)
async def link_views(patient_id: UUID, link_id: UUID, db: PatientReadDb) -> list[ShareLinkViewOut]:
    """When the link was opened (each right PIN)."""
    await _owner_only(db, patient_id)
    rows = (
        await db.execute(
            bound_text(
                "select v.opened_at from owner_share_links(:p) l, owner_share_link_views(l.id) v"
                " where l.id = :l"
            ),
            {"l": link_id, "p": patient_id},
        )
    ).all()
    return [ShareLinkViewOut(opened_at=r.opened_at) for r in rows]


@router.delete("/share-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def revoke_link(patient_id: UUID, link_id: UUID, db: PatientWriteDb) -> Response:
    await _owner_only(db, patient_id)
    done = (
        await db.execute(
            bound_text(
                "select revoke_share_link(l.id) from owner_share_links(:p) l where l.id = :l"
            ),
            {"l": link_id, "p": patient_id},
        )
    ).scalar_one_or_none()
    if not done:
        raise AppError(404, "share.link_not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- whoever holds the link --------------------------------------------------------------


@public_router.post(
    "/open",
    response_model=ShareSessionOut,
    responses=_ERRORS,
    dependencies=[Depends(per_ip("share_open", lambda: get_settings().rate_share_open_per_minute))],
)
async def open_link(body: OpenIn, db: AnonymousDb) -> ShareSessionOut:
    """Open a link with its PIN. Every failure answers the same (no link, ended, wrong PIN)."""
    attempt = (
        await db.execute(
            bound_text("select * from share_link_attempt(:t)"), {"t": sha256_hex(body.token)}
        )
    ).one_or_none()
    # the same work for a link that does not exist: no timing difference
    ok = await run_hashing(verify_password, body.pin, attempt.pin_hash if attempt else None)
    if attempt is None or not ok:
        if attempt is not None:
            await db.execute(bound_text("select share_link_failed(:l)"), {"l": attempt.link_id})
        await db.commit()  # the counted attempt stays (04 §6.7)
        raise AppError(401, "share.open_failed")
    session, session_hash = new_opaque_token()
    opened = (
        await db.execute(
            bound_text("select share_link_open(:t, :s)"),
            {"t": sha256_hex(body.token), "s": session_hash},
        )
    ).scalar_one()
    if not opened:  # ended meanwhile (revoked, last open used)
        await db.commit()
        raise AppError(401, "share.open_failed")
    scope = (
        await db.execute(bound_text("select * from share_session_scope(:s)"), {"s": session_hash})
    ).one()
    return ShareSessionOut(
        session=session,
        expires_at=scope.expires_at,
        scopes=scope.scopes,
        date_from=scope.date_from,
        date_to=scope.date_to,
    )


@dataclass(frozen=True)
class ShareContext:
    db: AsyncSession
    session_hash: str
    link_id: UUID
    scopes: tuple[str, ...]
    date_from: date | None
    date_to: date | None
    expires_at: datetime


async def share_context(
    db: AnonymousDb,
    x_share_session: Annotated[str | None, Header()] = None,
) -> ShareContext:
    """The gate of every share route: a live viewing session (its link and maker still
    standing). The route's own definer function reads with the session's hash; nothing is
    readable through the row policies."""
    if not x_share_session or len(x_share_session) != 43:  # noqa: PLR2004
        raise AppError(401, "share.session_invalid")
    session_hash = sha256_hex(x_share_session)
    scope = (
        await db.execute(bound_text("select * from share_session_scope(:s)"), {"s": session_hash})
    ).one_or_none()
    if scope is None:
        raise AppError(401, "share.session_invalid")
    return ShareContext(
        db=db,
        session_hash=session_hash,
        link_id=scope.link_id,
        scopes=tuple(scope.scopes),
        date_from=scope.date_from,
        date_to=scope.date_to,
        expires_at=scope.expires_at,
    )


Share = Annotated[ShareContext, Depends(share_context)]


@public_router.post("/close", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def close_session(share: Share) -> Response:
    """The viewer finishes: the session ends on the server too."""
    await share.db.execute(bound_text("select share_session_end(:s)"), {"s": share.session_hash})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public_router.get("/profile", response_model=SharedProfileOut, responses=_ERRORS)
async def shared_profile(share: Share) -> SharedProfileOut:
    """Whose record this is and what the link shows."""
    name = (
        await share.db.execute(bound_text("select share_profile(:s)"), {"s": share.session_hash})
    ).scalar_one_or_none()
    if name is None:
        raise AppError(401, "share.session_invalid")
    return SharedProfileOut(
        full_name=name,
        scopes=list(share.scopes),
        date_from=share.date_from,
        date_to=share.date_to,
        expires_at=share.expires_at,
    )


# --- what the link shows (Phase 7.3; 0042) ------------------------------------------------


class SharedAllergyOut(BaseModel):
    substance: str
    reaction: str | None
    severity: str | None
    noted_on: date | None


class SharedSummaryOut(BaseModel):
    full_name: str
    birth_date: date | None
    sex: str
    allergies: list[SharedAllergyOut]
    # a dated "no known allergies" (Q39); null is "none recorded", never "no allergy" (H17)
    no_known_allergies_on: date | None = None


class SharedLabOut(BaseModel):
    collected_at: datetime
    collected_precision: str  # 'day': no time of day is known
    lab_name: str | None
    test_code: str | None
    test_name_mn: str | None
    test_name_en: str | None
    raw_name: str
    raw_value: str | None  # as printed
    raw_unit: str | None
    ref_text: str | None  # the lab's own range, as printed
    critical_text: str | None
    flag: str | None
    lab_flag: str | None


class SharedRegimenOut(BaseModel):
    effective_from: date
    dose_amount: str | None
    dose_unit: str | None
    dose_unit_text: str | None
    schedule: dict[str, object] | list[object] | None
    instructions: str | None


class SharedMedicationOut(BaseModel):
    name: str
    brand: str | None
    form: str | None
    strength: str | None
    route: str | None
    purpose: str | None
    started_on: date | None
    stopped_on: date | None
    planned_end_on: date | None
    regimens: list[SharedRegimenOut]


class SharedTransplantOut(BaseModel):
    organ: str
    organ_detail: str | None
    transplant_date: date | None
    date_precision: str
    country: str | None
    hospital: str | None
    transplant_number: int | None
    donor_type: str | None
    recipient_blood_type: str | None
    donor_blood_type: str | None
    abo_incompatible: bool | None
    cmv_donor: str | None
    cmv_recipient: str | None
    ebv_donor: str | None
    ebv_recipient: str | None
    primary_disease: str | None
    induction_therapy: str | None
    graft_status: str | None
    graft_status_date: date | None
    follow_up_center: str | None
    follow_up_doctor: str | None


class SharedEventOut(BaseModel):
    kind: str
    title: str | None
    started_on: date
    ended_on: date | None
    place: str | None
    outcome: str | None


class SharedVitalOut(BaseModel):
    kind: str
    value: str
    unit: str | None
    measured_at: datetime
    group_no: int | None  # the parts of one reading share it


class SharedRecordOut(BaseModel):
    """Only the sections the link includes are present (the others are null)."""

    full_name: str
    scopes: list[Scope]
    date_from: date | None
    date_to: date | None
    expires_at: datetime
    summary: SharedSummaryOut | None = None
    labs: list[SharedLabOut] | None = None
    medications: list[SharedMedicationOut] | None = None
    transplants: list[SharedTransplantOut] | None = None
    events: list[SharedEventOut] | None = None
    vitals: list[SharedVitalOut] | None = None


_SECTION_SQL = {
    name: bound_text(f"select * from {name}(:s)")  # noqa: S608 - constant names only
    for name in (
        "share_summary",
        "share_allergies",
        "share_labs",
        "share_medications",
        "share_transplants",
        "share_events",
        "share_vitals",
    )
}


_NKA_SQL = bound_text("select share_no_known_allergies(:s)")


async def _rows(share: ShareContext, function: str) -> list[dict[str, Any]]:
    rows = await share.db.execute(_SECTION_SQL[function], {"s": share.session_hash})
    return [dict(r._mapping) for r in rows]


@public_router.get("/record", response_model=SharedRecordOut, responses=_ERRORS)
async def shared_record(share: Share) -> SharedRecordOut:
    """Everything the link shows, each section read by its own database function (which
    checks the session, the section and the dates again)."""
    name = (
        await share.db.execute(bound_text("select share_profile(:s)"), {"s": share.session_hash})
    ).scalar_one_or_none()
    if name is None:
        raise AppError(401, "share.session_invalid")
    out = SharedRecordOut(
        full_name=name,
        scopes=list(share.scopes),
        date_from=share.date_from,
        date_to=share.date_to,
        expires_at=share.expires_at,
    )
    if "summary" in share.scopes:
        people = await _rows(share, "share_summary")
        if people:
            person = people[0]
            allergies = [SharedAllergyOut(**a) for a in await _rows(share, "share_allergies")]
            nka = (await share.db.execute(_NKA_SQL, {"s": share.session_hash})).scalar_one_or_none()
            out.summary = SharedSummaryOut(
                **person,
                allergies=allergies,
                no_known_allergies_on=None if allergies else nka,
            )
    if "labs" in share.scopes:
        out.labs = [SharedLabOut(**r) for r in await _rows(share, "share_labs")]
    if "meds" in share.scopes:
        out.medications = [
            SharedMedicationOut(
                **{k: v for k, v in m.items() if k != "regimens"},
                regimens=[SharedRegimenOut(**g) for g in m["regimens"]],
            )
            for m in await _rows(share, "share_medications")
        ]
    if "transplant" in share.scopes:
        out.transplants = [
            SharedTransplantOut(**r) for r in await _rows(share, "share_transplants")
        ]
    if "events" in share.scopes:
        out.events = [SharedEventOut(**r) for r in await _rows(share, "share_events")]
    if "vitals" in share.scopes:
        out.vitals = [
            SharedVitalOut(**{**r, "value": num(r["value"])})
            for r in await _rows(share, "share_vitals")
        ]
    return out
