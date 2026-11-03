"""/me: the signed-in user's own account - profile, consents, what admins did to the account,
notifications and the "Би хүсээгүй" report (docs/04 §1, §5; Phase 1.7). RLS scopes every query
to the user; nothing here can reach another account."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Path, Query, Response, status
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.exc import DBAPIError

from labtrack import consents
from labtrack.api.deps import UserDb
from labtrack.api.errors import AppError, ErrorBody
from labtrack.auth import service as auth_service
from labtrack.core.text import valid_display_name
from labtrack.db.sql import bound_text

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
    items: Annotated[list[ConsentItem], Field(min_length=1, max_length=5)]
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
            "select id, kind, title_key, created_at, read_at from notifications"
            " where (not :u or read_at is null) order by created_at desc limit :n"
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
    username = (await db.execute(bound_text("select username::text from users"))).scalar_one()
    await auth_service.reverify_password(db, username=username, password=body.password)
    try:
        scheduled = (await db.execute(bound_text("select request_account_deletion()"))).scalar_one()
    except DBAPIError as exc:
        if _sqlstate(exc) != "42501":
            raise
        raise AppError(409, "me.deletion_not_allowed") from None  # e.g. not an active account
    return DeletionOut(scheduled_for=scheduled)
