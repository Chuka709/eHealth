"""Account administration (docs/04 §1): register, search, status, unlock, identity, tokens,
phone. Every change is one admin_* database function; the database decides who may do what
(support vs super_admin, admins never targeted) and writes the audit entry. This module adds
what only Python can do: field encryption, token generation and sending SMS.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal
from uuid import UUID, uuid4

import structlog
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.admin import csv_import
from labtrack.api.errors import AppError
from labtrack.config import get_settings
from labtrack.core.envelope import field_aad
from labtrack.core.security import new_opaque_token
from labtrack.db.sql import bound_text
from labtrack.sms import SmsSender, SmsTemplate, SmsUnavailableError
from labtrack.user_keys import decrypt_user_field, encrypt_user_field, get_user_key_store

log = structlog.get_logger(__name__)

Purpose = Literal["activation", "admin_reset"]
Channel = Literal["in_person_qr", "sms"]

# Raised by the 0004/0006 functions (our own messages, never user data) -> API errors.
_DB_ERRORS: Final = (
    ("target not allowed", 404, "admin.user_not_found"),
    ("admin not allowed", 403, "admin.forbidden"),
    ("password reset required", 409, "admin.reset_required"),
    ("no pending deletion", 409, "admin.no_pending_deletion"),
    ("already activated", 409, "admin.already_activated"),
    ("account is disabled", 409, "admin.account_disabled"),
    ("identity check is required", 409, "admin.identity_check_required"),
    ("another admin must reset", 409, "admin.reset_needs_other_admin"),
    ("identity already set", 409, "admin.identity_already_set"),
    ("no identity data", 409, "admin.identity_in_person"),
    ("identity check limit reached", 429, "admin.identity_check_limit"),
    ("phone reveal limit reached", 429, "admin.phone_reveal_limit"),
    ("lockout clear limit reached", 429, "admin.lockout_clear_limit"),
    ("status change not allowed", 409, "admin.status_change_not_allowed"),
    ("reason required", 422, "admin.reason_required"),
    ("admin address required", 400, "admin.address_required"),
)
# Constraint violations by constraint name (never by message: driver text carries row values).
_CONSTRAINTS: Final = {
    "users_username_key": (409, "admin.username_taken"),
    "users_username_check": (422, "validation"),
}


def _db_error(exc: DBAPIError) -> AppError:
    # asyncpg's own exception (sqlstate, constraint_name) sits behind SQLAlchemy's adapter
    pg = getattr(exc.orig, "__cause__", None) or exc.orig
    constraint = getattr(pg, "constraint_name", None)
    if constraint in _CONSTRAINTS:
        return AppError(*_CONSTRAINTS[constraint])
    sqlstate = getattr(pg, "sqlstate", None)
    if sqlstate in {"42501", "22023", "54000", "28000"}:
        # raised by our own definer functions: their messages hold no user data
        text = str(getattr(pg, "message", "") or "")
        for needle, status, code in _DB_ERRORS:
            if needle in text:
                return AppError(status, code)
    # Anything else: no driver text anywhere (it may contain "Failing row contains (...)").
    log.error("admin_db_error", sqlstate=sqlstate, constraint=constraint)
    return AppError(500, "internal")


def normalise_phone(raw: str) -> str:
    phone = csv_import.normalise_phone(raw)
    if phone is None:
        raise ValueError("phone")
    return phone


# Phone numbers are sealed under the user's own key: purging the account shreds every copy.
async def _phone_enc(db: AsyncSession, user_id: UUID, phone: str) -> bytes:
    return await encrypt_user_field(
        get_user_key_store(db),
        user_id,
        phone,
        field_aad("users", "contact_phone_enc", user_id),
    )


async def _phone_dec(db: AsyncSession, user_id: UUID, blob: bytes) -> str:
    return await decrypt_user_field(
        get_user_key_store(db),
        user_id,
        blob,
        field_aad("users", "contact_phone_enc", user_id),
    )


def _pepper() -> str:
    pepper = get_settings().identity_pepper
    if pepper is None:
        raise RuntimeError("IDENTITY_PEPPER is not set")
    return pepper.get_secret_value()


async def create_user(
    db: AsyncSession,
    *,
    username: str,
    display_name: str,
    role: Literal["user", "doctor"],
    phone: str | None,
    national_id: str | None,
) -> UUID:
    uid = uuid4()
    try:
        await db.execute(
            bound_text(
                "select admin_create_user(:id, :u, :n, cast(:r as user_role), :ph, :last4,"
                " :nid, :pep)"
            ),
            {
                "id": uid,
                "u": username,
                "n": display_name,
                "r": role,
                "ph": await _phone_enc(db, uid, phone) if phone else None,
                "last4": phone[-4:] if phone else None,
                "nid": national_id,
                "pep": _pepper() if national_id else None,
            },
        )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return uid


@dataclass(frozen=True)
class UserRow:
    id: UUID
    username: str
    display_name: str
    role: str
    account_status: str
    phone_last4: str | None
    created_at: datetime
    deletion_scheduled_for: datetime | None = None  # deleted by the user, erased on this date


_LIKE = str.maketrans({"\\": "\\\\", "%": "\\%", "_": "\\_"})


async def search_users(
    db: AsyncSession,
    *,
    query: str | None,
    status: str | None,
    after: str | None,
    limit: int,
    deletion_pending: bool = False,
) -> list[UserRow]:
    """Users and doctors only, by username; `after` is the last username of the previous page.

    Deleted accounts appear only with `deletion_pending` (until they are erased)."""
    pattern = f"%{query.translate(_LIKE)}%" if query else None
    rows = await db.execute(
        bound_text(
            "select id, username::text as username, display_name, role::text as role,"
            " account_status, contact_phone_last4, created_at,"
            " deleted_at + interval '30 days' as deletion_scheduled_for from users"
            " where role in ('user','doctor') and (deleted_at is not null) = :d"
            " and (cast(:q as text) is null or username::text ilike :q"
            "      or display_name ilike :q)"
            " and (cast(:s as text) is null or account_status = :s)"
            " and (cast(:a as text) is null or username::text > :a)"
            " order by username limit :lim"
        ),
        {"q": pattern, "s": status, "a": after, "lim": limit, "d": deletion_pending},
    )
    return [
        UserRow(
            r.id,
            r.username,
            r.display_name,
            r.role,
            r.account_status,
            r.contact_phone_last4,
            r.created_at,
            deletion_scheduled_for=r.deletion_scheduled_for,
        )
        for r in rows
    ]


@dataclass(frozen=True)
class UserDetail:
    user: UserRow
    live_token: tuple[str, str, datetime] | None  # purpose, channel, expires_at
    active_sessions: int
    identity_checks_today: int


async def get_user(db: AsyncSession, user_id: UUID) -> UserDetail:
    row = (
        await db.execute(
            bound_text(
                "select id, username::text as username, display_name, role::text as role,"
                " account_status, contact_phone_last4, created_at,"
                " deleted_at + interval '30 days' as deletion_scheduled_for,"
                " (select count(*) from sessions s where s.user_id = u.id"
                "  and s.revoked_at is null) as sessions,"
                " (select count(*) from identity_checks c where c.user_id = u.id"
                "  and c.at > now() - interval '1 day') as checks"
                " from users u where id = :id and role in ('user','doctor')"
            ),
            {"id": user_id},
        )
    ).one_or_none()
    if row is None:
        raise AppError(404, "admin.user_not_found")
    token = (
        await db.execute(
            bound_text(
                "select purpose, channel, expires_at from activation_tokens"
                " where user_id = :id and used_at is null and revoked_at is null"
                " and expires_at > now()"
            ),
            {"id": user_id},
        )
    ).one_or_none()
    return UserDetail(
        UserRow(
            row.id,
            row.username,
            row.display_name,
            row.role,
            row.account_status,
            row.contact_phone_last4,
            row.created_at,
            deletion_scheduled_for=row.deletion_scheduled_for,
        ),
        (token.purpose, token.channel, token.expires_at) if token else None,
        int(row.sessions),
        int(row.checks),
    )


async def set_status(db: AsyncSession, user_id: UUID, status: str, reason: str) -> None:
    try:
        await db.execute(
            bound_text("select admin_set_status(:u, :s, :r)"),
            {"u": user_id, "s": status, "r": reason},
        )
    except DBAPIError as exc:
        raise _db_error(exc) from exc


async def clear_lockout(db: AsyncSession, user_id: UUID) -> None:
    try:
        await db.execute(bound_text("select admin_clear_lockout(:u)"), {"u": user_id})
    except DBAPIError as exc:
        raise _db_error(exc) from exc


async def identity_check(db: AsyncSession, user_id: UUID, national_id: str) -> tuple[int, bool]:
    try:
        row = (
            await db.execute(
                bound_text("select * from admin_identity_check(:u, :n, :p)"),
                {"u": user_id, "n": national_id, "p": _pepper()},
            )
        ).one()
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return int(row.check_id), bool(row.success)


async def set_identity(db: AsyncSession, user_id: UUID, national_id: str) -> None:
    try:
        await db.execute(
            bound_text("select admin_set_identity(:u, :n, :p)"),
            {"u": user_id, "n": national_id, "p": _pepper()},
        )
    except DBAPIError as exc:
        raise _db_error(exc) from exc


@dataclass(frozen=True)
class IssuedToken:
    expires_at: datetime
    # Only for an in-person QR shown on the admin's screen; an SMS token never comes back.
    link: str | None
    # SMS link delivered, or for an in-person reset the notice to the registered phone. False
    # means the user was not told by SMS (no gateway yet - Q13 - or it failed): the admin
    # tells them another way.
    notice_sent: bool = False


def activation_link(token: str) -> str:
    return f"{get_settings().activation_link_base}#{token}"


async def issue_token(
    db: AsyncSession,
    sms: SmsSender,
    *,
    user_id: UUID,
    purpose: Purpose,
    channel: Channel,
    identity_check_id: int | None,
    reason: str | None,
    admin_ip: str | None,
) -> IssuedToken:
    """Issue a one-time activation/reset token (docs/04 §1 step 3-5).

    The database checks everything (pending account, fresh identity check by this admin,
    reason, enrolling admin) and, for a reset, kills the old password and every session. The
    transaction is committed before any SMS goes out, so no message carries a token that does
    not exist; a failed send leaves a live token the admin replaces by issuing again.
    """
    if channel == "sms":
        if not sms.available:
            raise AppError(503, "admin.sms_unavailable")
        has_phone = (
            await db.execute(
                bound_text(
                    "select contact_phone_last4 is not null from users"
                    " where id = :u and role in ('user','doctor') and deleted_at is null"
                ),
                {"u": user_id},
            )
        ).scalar_one_or_none()
        if has_phone is False:
            raise AppError(409, "admin.no_phone")
    raw, token_hash = new_opaque_token()
    try:
        expires: datetime = (
            await db.execute(
                bound_text("select admin_issue_token(:u, :p, :c, :h, :ic, :r, cast(:ip as inet))"),
                {
                    "u": user_id,
                    "p": purpose,
                    "c": channel,
                    "h": token_hash,
                    "ic": identity_check_id,
                    "r": reason,
                    "ip": admin_ip,
                },
            )
        ).scalar_one()
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    phone: str | None = None
    if sms.available and (channel == "sms" or purpose == "admin_reset"):
        # Only now, for the token just issued (admin_sms_target checks that, and audits).
        try:
            blob = (
                await db.execute(bound_text("select admin_sms_target(:u)"), {"u": user_id})
            ).scalar_one()
        except DBAPIError as exc:
            raise _db_error(exc) from exc
        phone = await _phone_dec(db, user_id, blob) if blob is not None else None
    if channel == "sms" and phone is None:
        raise AppError(409, "admin.no_phone")  # rolls the token back
    await db.commit()

    if channel == "sms" and phone is not None:
        template = (
            SmsTemplate.RESET_LINK if purpose == "admin_reset" else SmsTemplate.ACTIVATION_LINK
        )
        try:
            await sms.send(
                user_id=user_id, phone=phone, template=template, link=activation_link(raw)
            )
        except SmsUnavailableError as exc:
            raise AppError(503, "admin.sms_unavailable") from exc
        except Exception as exc:  # gateway errors: the token stands, the admin may issue again
            raise AppError(502, "admin.sms_failed") from exc
        return IssuedToken(expires, None, notice_sent=True)

    notice_sent = False
    if purpose == "admin_reset" and phone is not None:
        # In-person reset: the registered phone still learns about it (docs/04 §1 step 5b).
        # A failed notice must not lose the QR the user is standing in front of.
        try:
            await sms.send(
                user_id=user_id, phone=phone, template=SmsTemplate.RESET_NOTICE, link=None
            )
            notice_sent = True
        except Exception:
            log.warning("reset_notice_failed", user_id=str(user_id))
    return IssuedToken(expires, activation_link(raw), notice_sent=notice_sent)


async def reveal_phone(db: AsyncSession, user_id: UUID) -> str | None:
    try:
        blob = (
            await db.execute(bound_text("select admin_reveal_phone(:u)"), {"u": user_id})
        ).scalar_one()
    except DBAPIError as exc:
        raise _db_error(exc) from exc
    return await _phone_dec(db, user_id, blob) if blob is not None else None


async def log_import(db: AsyncSession, file_sha256: str, rows: int) -> None:
    await db.execute(bound_text("select admin_log_import(:h, :n)"), {"h": file_sha256, "n": rows})


@dataclass(frozen=True)
class SecurityEvent:
    id: int
    at: datetime
    action: str
    actor_id: UUID | None
    target_user_id: UUID | None
    details: dict[str, object]


async def security_events(db: AsyncSession, limit: int) -> list[SecurityEvent]:
    rows = await db.execute(bound_text("select * from admin_security_events(:n)"), {"n": limit})
    return [
        SecurityEvent(r.id, r.at, r.action, r.actor_id, r.target_user_id, dict(r.diff or {}))
        for r in rows
    ]


async def import_users(db: AsyncSession, parsed: csv_import.Parsed) -> list[csv_import.Problem]:
    """Create every row in this transaction, or none: returns the problems that stop it."""
    if parsed.problems:
        return parsed.problems
    taken = set(
        (
            await db.execute(
                bound_text("select username::text from users where username = any(:names)"),
                {"names": [r.username for r in parsed.rows]},
            )
        ).scalars()
    )
    if taken:
        return [
            csv_import.Problem(r.line, "username_taken") for r in parsed.rows if r.username in taken
        ]
    for row in parsed.rows:
        await create_user(
            db,
            username=row.username,
            display_name=row.display_name,
            role=row.role,
            phone=row.phone,
            national_id=None,
        )
    await log_import(db, parsed.sha256, len(parsed.rows))
    return []


async def cancel_deletion(db: AsyncSession, user_id: UUID, reason: str) -> None:
    """Restores a deleted account within 30 days as locked + reset_required (0008)."""
    try:
        await db.execute(
            bound_text("select admin_cancel_deletion(:u, :r)"), {"u": user_id, "r": reason}
        )
    except DBAPIError as exc:
        raise _db_error(exc) from exc
