"""Authentication use cases (docs/04 §1, §6). Database work goes through the 0005 functions."""

import functools
import ipaddress
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import anyio
import anyio.to_thread
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.api.errors import AppError
from labtrack.auth.tokens import AccessClaims, issue_access_token
from labtrack.config import get_settings
from labtrack.core.security import (
    UNTRUSTED_WINDOW,
    hash_password,
    lockout_decision,
    new_opaque_token,
    password_problems,
    sha256_hex,
    verify_password,
)
from labtrack.db.sql import bound_text

# argon2 is CPU-bound (~50-100 ms): run it off the event loop, at most 4 at a time per
# process, so a burst of logins cannot stall every other request.
_hashing = anyio.CapacityLimiter(4)


async def run_hashing[**P, T](fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    return await anyio.to_thread.run_sync(functools.partial(fn, *args, **kwargs), limiter=_hashing)


Platform = Literal["ios", "android", "web"]

INVALID_CREDENTIALS = "auth.invalid_credentials"


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    expires_in: int
    refresh_token: str
    device_token: str | None = None  # returned once, when a device becomes trusted


def client_network(ip: str | None) -> str | None:
    """Lockout key for an address: IPv4 as is, IPv6 by /64 (one subscriber's prefix)."""
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if addr.version == 6:  # noqa: PLR2004 - IP version number
        return str(ipaddress.ip_network(f"{addr}/64", strict=False).network_address)
    return str(addr)


def _refresh_ttl() -> timedelta:
    return timedelta(days=get_settings().refresh_token_ttl_days)


def _access(user_id: UUID, session_id: UUID, token_version: int, role: str) -> tuple[str, int]:
    return issue_access_token(
        AccessClaims(user_id=user_id, session_id=session_id, token_version=token_version, role=role)
    )


async def login(
    db: AsyncSession,
    *,
    username: str,
    password: str,
    device_name: str | None,
    platform: Platform,
    device_token: str | None,
    ip: str | None,
) -> TokenPair:
    net = client_network(ip)
    # Serialise attempts per username so parallel requests cannot all pass the lockout check
    # before any failure is recorded (released at commit/rollback).
    await db.execute(
        bound_text("select pg_advisory_xact_lock(hashtext(lower(:u)))"), {"u": username}
    )
    device_hash = sha256_hex(device_token) if device_token else None
    trusted = bool(
        device_hash
        and (
            await db.execute(
                bound_text("select device_is_trusted(:u, :d)"), {"u": username, "d": device_hash}
            )
        ).scalar_one()
    )
    counts = (
        await db.execute(
            bound_text("select * from auth_failure_counts('login', :u, cast(:ip as inet), :d, :w)"),
            {"u": username, "ip": net, "d": device_hash, "w": UNTRUSTED_WINDOW},
        )
    ).one()
    decision = lockout_decision(
        # A trusted device is counted on its own, so others behind the same address
        # (CGNAT) cannot lock the owner's phone.
        failures_username_ip=counts.by_username_device if trusted else counts.by_username_ip,
        failures_username_untrusted=counts.by_username_untrusted,
        last_failure=counts.last_failure,
        device_trusted=trusted,
        now=datetime.now(UTC),
    )
    if not decision.allowed:
        # Same for existing and unknown usernames (counts are keyed by the submitted name).
        raise AppError(429, "auth.locked", retry_after=decision.retry_after)

    row = (
        await db.execute(bound_text("select * from auth_login_lookup(:u)"), {"u": username})
    ).one_or_none()
    # Always run one argon2 verification so timing does not reveal whether the user exists.
    ok = await run_hashing(verify_password, password, row.password_hash if row else None)
    ok = ok and row is not None and row.account_status == "active"
    await db.execute(
        bound_text("select auth_record_attempt('login', :u, cast(:ip as inet), :d, :t, :ok)"),
        {"u": username, "ip": net, "d": device_hash if trusted else None, "t": trusted, "ok": ok},
    )
    if not ok or row is None:
        await db.commit()  # keep the failed attempt even though we raise
        raise AppError(401, INVALID_CREDENTIALS)

    refresh_raw, refresh_hash = new_opaque_token()
    # After a successful login this device becomes (or stays) trusted.
    new_device: str | None = None
    if trusted and device_hash:
        trust_hash = device_hash
    else:
        new_device, trust_hash = new_opaque_token()
    session = (
        await db.execute(
            bound_text("select * from session_create(:u, :h, :n, :p, :d, :ttl)"),
            {
                "u": row.user_id,
                "h": refresh_hash,
                "n": device_name,
                "p": platform,
                "d": trust_hash,
                "ttl": _refresh_ttl(),
            },
        )
    ).one()
    access, expires_in = _access(row.user_id, session.session_id, session.token_version, row.role)
    return TokenPair(access, expires_in, refresh_raw, new_device)


async def refresh(db: AsyncSession, *, refresh_token: str) -> TokenPair:
    new_raw, new_hash = new_opaque_token()
    result = (
        await db.execute(
            bound_text("select * from session_rotate(:old, :new, :ttl)"),
            {"old": sha256_hex(refresh_token), "new": new_hash, "ttl": _refresh_ttl()},
        )
    ).one()
    if result.status != "ok":
        await db.commit()  # persist family revocation on reuse
        # The old device learns that an admin reset its account (docs/04 §1 step 5).
        code = (
            "auth.admin_reset" if result.status == "revoked:admin_reset" else "auth.session_invalid"
        )
        raise AppError(401, code)
    access, expires_in = _access(
        result.user_id, result.session_id, result.token_version, str(result.role)
    )
    return TokenPair(access, expires_in, new_raw)


async def logout(db: AsyncSession, *, refresh_token: str) -> None:
    await db.execute(
        bound_text("select session_revoke_by_token(:h)"), {"h": sha256_hex(refresh_token)}
    )


async def activate(db: AsyncSession, *, token: str, new_password: str) -> None:
    token_hash = sha256_hex(token)
    owner = (
        await db.execute(bound_text("select * from activation_token_user(:h)"), {"h": token_hash})
    ).one_or_none()
    if owner is None:
        raise AppError(400, "auth.activation_invalid")
    problems = password_problems(new_password, owner.username, owner.display_name)
    if problems:
        raise AppError(422, problems[0])
    password_hash = await run_hashing(hash_password, new_password)
    try:
        await db.execute(
            bound_text("select activation_consume(:h, :pw)"),
            {"h": token_hash, "pw": password_hash},
        )
    except DBAPIError as exc:  # invalid/expired/used token or inactive account: one answer
        raise AppError(400, "auth.activation_invalid") from exc


async def change_password(
    db: AsyncSession,
    *,
    username: str,
    display_name: str,
    current_password: str,
    new_password: str,
    current_session: UUID,
    sign_out_other_devices: bool,
) -> None:
    # Re-verifying the current password is a password oracle too: same lockout as login.
    await db.execute(
        bound_text("select pg_advisory_xact_lock(hashtext(lower(:u)))"), {"u": username}
    )
    counts = (
        await db.execute(
            bound_text("select * from auth_failure_counts('change_password', :u, null, null, :w)"),
            {"u": username, "w": UNTRUSTED_WINDOW},
        )
    ).one()
    decision = lockout_decision(
        failures_username_ip=counts.by_username_untrusted,  # per account, any address
        failures_username_untrusted=0,
        last_failure=counts.last_failure,
        device_trusted=True,
        now=datetime.now(UTC),
    )
    if not decision.allowed:
        raise AppError(429, "auth.locked", retry_after=decision.retry_after)
    stored = (await db.execute(bound_text("select auth_own_password_hash()"))).scalar_one()
    ok = await run_hashing(verify_password, current_password, stored)
    await db.execute(
        bound_text("select auth_record_attempt('change_password', :u, null, null, false, :ok)"),
        {"u": username, "ok": ok},
    )
    if not ok:
        await db.commit()  # keep the failure even though we raise
        raise AppError(401, INVALID_CREDENTIALS)
    problems = password_problems(new_password, username, display_name)
    if problems:
        raise AppError(422, problems[0])
    await db.execute(
        bound_text("select auth_change_password(:pw, :keep, :others)"),
        {
            "pw": await run_hashing(hash_password, new_password),
            "keep": current_session,
            "others": sign_out_other_devices,
        },
    )
