"""/me: the signed-in user's own account - profile, consents, what admins did to the account,
notifications and the "Би хүсээгүй" report (docs/04 §1, §5; Phase 1.7). RLS scopes every query
to the user; nothing here can reach another account."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Path, Query, Response, status
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.exc import DBAPIError

from labtrack import consents
from labtrack.api.deps import Claims, UserDb
from labtrack.api.errors import AppError, ErrorBody
from labtrack.api.ratelimit import per_user
from labtrack.auth import service as auth_service
from labtrack.config import get_settings
from labtrack.core.text import valid_display_name
from labtrack.db.sql import bound_text

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/me", tags=["me"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorBody},
    403: {"model": ErrorBody},
    404: {"model": ErrorBody},
    409: {"model": ErrorBody},
    422: {"model": ErrorBody},
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _display_name(value: str) -> str:
    if not valid_display_name(value):
        raise ValueError("display_name")
    return value


DisplayName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    AfterValidator(_display_name),
]


class MeOut(BaseModel):
    id: UUID
    username: str
    display_name: str
    locale: str
    role: str
    account_status: str
    password_changed_at: datetime | None
    created_at: datetime


class MeUpdate(_Strict):
    display_name: DisplayName | None = None
    locale: Literal["mn", "en"] | None = None


class ConsentOut(BaseModel):
    kind: str
    current_version: str
    granted: bool
    granted_version: str | None
    at: datetime | None
    required: bool


class ConsentItem(_Strict):
    kind: consents.Kind
    version: Annotated[str, StringConstraints(min_length=1, max_length=20)]
    granted: bool


class ConsentRequest(_Strict):
    items: Annotated[list[ConsentItem], Field(min_length=1, max_length=len(consents.VERSIONS))]
    # a minor's profile the user owns (Q9); omitted = the user's own consents
    patient_id: UUID | None = None


class AdminActionOut(BaseModel):
    at: datetime
    action: str
    actor_role: str | None


class NotificationOut(BaseModel):
    id: int
    kind: str
    title_key: str
    # ids only: the app opens the profile / the item through its own routes (2.8f)
    patient_id: UUID | None
    entity_id: str | None
    created_at: datetime
    read_at: datetime | None


def _sqlstate(exc: DBAPIError) -> str | None:
    pg = getattr(exc.orig, "__cause__", None) or exc.orig
    return getattr(pg, "sqlstate", None)


async def _me(db: UserDb) -> MeOut:
    row = (
        await db.execute(
            bound_text(
                "select id, username::text as username, display_name, locale, role::text as role,"
                " account_status, password_changed_at, created_at from users"
                # Explicit, not RLS alone: later roles (doctors, caregivers) may see more users.
                " where id = app_user_id()"
            )
        )
    ).one()
    return MeOut(**row._mapping)


@router.get("", response_model=MeOut, responses=_ERRORS)
async def me(db: UserDb) -> MeOut:
    return await _me(db)


@router.patch("", response_model=MeOut, responses=_ERRORS)
async def update_me(body: MeUpdate, db: UserDb) -> MeOut:
    await db.execute(
        bound_text(
            "update users set display_name = coalesce(:n, display_name),"
            " locale = coalesce(:l, locale) where id = app_user_id()"
        ),
        {"n": body.display_name, "l": body.locale},
    )
    if body.display_name is not None:
        # Admins identify people partly by display name: record that it changed (never the
        # value itself).
        await db.execute(
            bound_text(
                "select audit_write('user.profile_update', 'user', app_user_id()::text, null,"
                " jsonb_build_object('fields', jsonb_build_array('display_name')))"
            )
        )
    return await _me(db)


@router.get("/consents", response_model=list[ConsentOut], responses=_ERRORS)
async def get_consents(db: UserDb, patient_id: UUID | None = None) -> list[ConsentOut]:
    return [ConsentOut(**s.__dict__) for s in await consents.states(db, patient_id)]


@router.post("/consents", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def give_consents(body: ConsentRequest, db: UserDb) -> Response:
    """Give (only for the text version currently shown) or withdraw (granted=false, any
    version: withdrawing must never be harder than giving)."""
    if len({i.kind for i in body.items}) != len(body.items):
        raise AppError(422, "validation")
    # AI extraction needs both (processing + transfer abroad), so they are given together.
    # Withdrawing either one alone stays possible (it already stops AI extraction).
    ai = [i for i in body.items if i.kind in consents.AI_EXTRACTION]
    if any(i.granted for i in ai) and (
        len(ai) != len(consents.AI_EXTRACTION) or not all(i.granted for i in ai)
    ):
        raise AppError(422, "validation")
    # sharing with caregivers is the user's own choice, never one given for a profile (0023)
    if body.patient_id is not None and any(i.kind == "caregiver_sharing" for i in body.items):
        raise AppError(422, "validation")
    if any(i.granted and i.version != consents.VERSIONS[i.kind] for i in body.items):
        raise AppError(409, "consent.version_outdated")
    # One writer per user at a time, so the latest row is also the last one committed.
    await db.execute(
        bound_text("select pg_advisory_xact_lock(hashtext('consent:' || app_user_id()::text))")
    )
    try:
        for item in body.items:
            await db.execute(
                bound_text(
                    "insert into consents (user_id, patient_id, kind, version, granted)"
                    " values (app_user_id(), :p, :k, :v, :g)"
                ),
                {
                    "p": body.patient_id,
                    "k": item.kind,
                    "v": consents.VERSIONS[item.kind],
                    "g": item.granted,
                },
            )
    except DBAPIError as exc:
        if _sqlstate(exc) != "42501":
            raise
        # RLS: only the owner of a minor's profile consents for it (never for an adult's)
        raise AppError(403, "consent.not_allowed") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin-actions", response_model=list[AdminActionOut], responses=_ERRORS)
async def admin_actions(db: UserDb) -> list[AdminActionOut]:
    """What admins did to this account (when, what, which role) - never who or why."""
    rows = await db.execute(bound_text("select * from my_admin_actions()"))
    return [AdminActionOut(**r._mapping) for r in rows]


@router.get("/notifications", response_model=list[NotificationOut], responses=_ERRORS)
async def notifications(
    db: UserDb,
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[NotificationOut]:
    rows = await db.execute(
        bound_text(
            "select id, kind, title_key, patient_id, entity_id, created_at, read_at"
            " from notifications where (not :u or read_at is null)"
            # a notice about a profile stays only while the user can open it (as 0024 does for
            # push); an invitation's is for someone who has no access yet
            " and (patient_id is null or can_read_patient(patient_id)"
            " or (kind = 'share_invite' and (exists (select 1 from my_caregiver_invitations() i"
            " where i.id::text = notifications.entity_id)"
            " or exists (select 1 from my_access_invitations() j"
            " where j.id::text = notifications.entity_id))))"
            " order by created_at desc limit :n"
        ),
        {"u": unread_only, "n": limit},
    )
    return [NotificationOut(**r._mapping) for r in rows]


@router.post(
    "/notifications/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ERRORS,
)
async def mark_read(
    # bigint range: a larger id would overflow in the database (500) instead of a 422.
    notification_id: Annotated[int, Path(ge=1, le=2**63 - 1)],
    db: UserDb,
) -> Response:
    done = (
        await db.execute(
            bound_text(
                "update notifications set read_at = coalesce(read_at, now())"
                " where id = :i returning id"
            ),
            {"i": notification_id},
        )
    ).scalar_one_or_none()
    if done is None:
        raise AppError(404, "me.notification_not_found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class PushTokenIn(_Strict):
    # Same shape as set_session_push_token() checks (0020); null clears it.
    token: (
        Annotated[
            str,
            StringConstraints(pattern=r"^Expo(nent)?PushToken\[[A-Za-z0-9_-]{10,100}\]$"),
        ]
        | None
    )


_PUSH_LIMIT = Depends(per_user("push_token", lambda: get_settings().rate_push_token_per_minute))


async def _set_push_token(db: UserDb, claims: Claims, token: str | None) -> Response:
    # The token goes on this request's own session (JWT sid) and is never logged or returned.
    try:
        done = (
            await db.execute(
                bound_text("select set_session_push_token(:s, :t)"),
                {"s": claims.session_id, "t": token},
            )
        ).scalar_one()
    except DBAPIError as exc:
        if _sqlstate(exc) != "22023":
            raise
        raise AppError(422, "me.push_token_invalid") from None
    if not done:  # the session ended after the request was authenticated
        raise AppError(401, "auth.session_invalid")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/push-token",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_ERRORS, 429: {"model": ErrorBody}},
    dependencies=[_PUSH_LIMIT],
)
async def put_push_token(body: PushTokenIn, db: UserDb, claims: Claims) -> Response:
    """This device's Expo push token, for this session only. A token another session (account)
    had on the same phone leaves that session (0020)."""
    return await _set_push_token(db, claims, body.token)


@router.delete(
    "/push-token",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_ERRORS, 429: {"model": ErrorBody}},
    dependencies=[_PUSH_LIMIT],
)
async def delete_push_token(db: UserDb, claims: Claims) -> Response:
    return await _set_push_token(db, claims, None)


class DeviceAlarmsIn(_Strict):
    exact_alarms: bool  # this device can schedule exact alarms (iOS always; Android: allowed)


@router.put(
    "/device-alarms",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**_ERRORS, 429: {"model": ErrorBody}},
    dependencies=[_PUSH_LIMIT],
)
async def put_device_alarms(body: DeviceAlarmsIn, db: UserDb, claims: Claims) -> Response:
    """Whether this device's medicine reminders can come on time (Q48): when none of the owner's
    devices can, a caregiver's dose alert waits at least 90 minutes (0046). Kept per session
    family, so it outlives refreshes; nothing about the device but this one flag."""
    done = (
        await db.execute(
            bound_text("select set_device_exact_alarms(:s, :e)"),
            {"s": claims.session_id, "e": body.exact_alarms},
        )
    ).scalar_one()
    if not done:  # the session ended after the request was authenticated
        raise AppError(401, "auth.session_invalid")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/report-unwanted-admin-action",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ERRORS,
)
async def report_unwanted_admin_action(db: UserDb) -> Response:
    """ "Би хүсээгүй": locks the account and ends every session (this one too). The admins get a
    security event; recovery is an identity check and a reset (a new password)."""
    try:
        await db.execute(bound_text("select report_unwanted_admin_action()"))
    except DBAPIError as exc:
        if _sqlstate(exc) != "42501":
            raise
        # Two refusals share the SQLSTATE (0007): tell them apart by the database message, so
        # an already locked account is not told "no admin action in 30 days".
        if "account not active" in str(exc.orig):
            raise AppError(409, "me.account_not_active") from None
        raise AppError(409, "me.no_recent_admin_action") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class DeleteRequest(_Strict):
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class DeletionOut(BaseModel):
    scheduled_for: datetime


@router.post(
    "/delete",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DeletionOut,
    responses={**_ERRORS, 429: {"model": ErrorBody}},
)
async def delete_account(body: DeleteRequest, db: UserDb) -> DeletionOut:
    """Delete the account (App Store / Play requirement). Signs out everywhere at once; the
    data is erased 30 days later. Until then an admin can restore it - as a locked account
    that needs an identity check and a new password."""
    username = (
        await db.execute(bound_text("select username::text from users where id = app_user_id()"))
    ).scalar_one()
    await auth_service.reverify_password(db, username=username, password=body.password)
    try:
        scheduled = (await db.execute(bound_text("select request_account_deletion()"))).scalar_one()
    except DBAPIError as exc:
        if _sqlstate(exc) != "42501":
            raise
        raise AppError(409, "me.deletion_not_allowed") from None  # e.g. not an active account
    # a record outside the database (id only): after a restore from an older backup the request
    # is applied again from the logs (docs/OPS_RUNBOOK.md §5)
    user_id = (await db.execute(bound_text("select app_user_id()"))).scalar_one()
    log.info("account_deletion_requested", user_id=str(user_id))
    return DeletionOut(scheduled_for=scheduled)
