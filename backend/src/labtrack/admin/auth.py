"""Admin sign-in: password + TOTP -> a short admin session (docs/04 §1 "Супер админ").

Same lockout policy as user login (core/security.lockout_decision) under its own attempt kind,
one answer for every failure (unknown name, wrong password, wrong or replayed code, inactive
account) and one argon2 verification on every path. The session token is opaque; only its
sha256 is stored (admin_sessions). Sessions last 8 h and end after 15 min without a request
(enforced by the database in admin_session_begin / admin_actor).
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.api.errors import AppError
from labtrack.auth.service import INVALID_CREDENTIALS, client_network, run_hashing
from labtrack.core.envelope import EnvelopeError, field_aad
from labtrack.core.security import (
    UNTRUSTED_WINDOW,
    lockout_decision,
    new_opaque_token,
    sha256_hex,
    verify_password,
)
from labtrack.core.totp import matching_step, new_secret
from labtrack.db.sql import bound_text
from labtrack.keys import decrypt_field, encrypt_field, get_key_provider


@dataclass(frozen=True)
class AdminLogin:
    session_token: str
    expires_at: datetime


_DUMMY: list[tuple[bytes, bytes]] = []


async def _dummy_secret() -> tuple[bytes, bytes]:
    if not _DUMMY:
        aad = field_aad("users", "totp_secret_enc", "dummy")
        _DUMMY.append((await encrypt_field(get_key_provider(), new_secret(), aad), aad))
    return _DUMMY[0]


async def _record_failure(db: AsyncSession, username: str, net: str | None) -> None:
    await db.execute(
        bound_text("select admin_login_failure(:u, cast(:ip as inet))"),
        {"u": username, "ip": net},
    )
    await db.commit()  # keep the failed attempt even though we raise


async def login(
    db: AsyncSession, *, username: str, password: str, totp_code: str, ip: str | None
) -> AdminLogin:
    net = client_network(ip)
    await db.execute(
        bound_text("select pg_advisory_xact_lock(hashtext('admin:' || lower(:u)))"),
        {"u": username},
    )
    counts = (
        await db.execute(
            bound_text(
                "select * from auth_failure_counts('admin_login', :u, cast(:ip as inet), null, :w)"
            ),
            {"u": username, "ip": net, "w": UNTRUSTED_WINDOW},
        )
    ).one()
    now = datetime.now(UTC)
    decision = lockout_decision(
        failures_username_ip=counts.by_username_ip,
        failures_username_untrusted=counts.by_username_untrusted,
        last_failure=counts.last_failure,
        device_trusted=False,
        now=now,
    )
    if not decision.allowed:
        raise AppError(429, "auth.locked", retry_after=decision.retry_after)

    row = (
        await db.execute(bound_text("select * from admin_login_lookup(:u)"), {"u": username})
    ).one_or_none()
    ok = await run_hashing(verify_password, password, row.password_hash if row else None)
    usable = ok and row is not None and row.account_status == "active" and row.totp_secret_enc
    # The TOTP work (decrypt via the KeyProvider + compare) runs on every path, so its latency
    # does not tell whether the password was right.
    blob, aad = (
        (row.totp_secret_enc, field_aad("users", "totp_secret_enc", row.user_id))
        if usable and row is not None
        else await _dummy_secret()
    )
    try:
        secret: str | None = await decrypt_field(get_key_provider(), blob, aad)
    except EnvelopeError:
        secret = None  # a tampered or misplaced secret signs nobody in
    step = matching_step(secret, totp_code, now) if secret is not None else None
    if not usable or row is None or step is None:
        await _record_failure(db, username, net)
        raise AppError(401, INVALID_CREDENTIALS)

    raw, token_hash = new_opaque_token()
    try:
        expires: datetime = (
            await db.execute(
                bound_text("select admin_session_create(:u, :h, cast(:ip as inet), :s)"),
                {"u": row.user_id, "h": token_hash, "ip": ip, "s": step},
            )
        ).scalar_one()
    except DBAPIError as exc:  # the code was already used (replay) or the account changed
        await db.rollback()
        await _record_failure(db, username, net)
        raise AppError(401, INVALID_CREDENTIALS) from exc
    return AdminLogin(raw, expires)


async def logout(db: AsyncSession, *, session_token: str) -> None:
    await db.execute(bound_text("select admin_session_end(:h)"), {"h": sha256_hex(session_token)})
