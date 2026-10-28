"""Authentication primitives: password hashing and policy, refresh tokens, lockout policy.

Pure functions (no I/O) so every rule is unit- and property-tested. docs/04 §1, §6.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError
from pwdlib.hashers.argon2 import Argon2Hasher
from zxcvbn import zxcvbn  # type: ignore[import-untyped]

# --- passwords -----------------------------------------------------------------------------

_hasher: Final = PasswordHash((Argon2Hasher(),))  # argon2id
# Verified against when the username does not exist, so the response time does not reveal it.
_DUMMY_HASH: Final = _hasher.hash(secrets.token_urlsafe(16))

MIN_PASSWORD_LENGTH: Final = 10
MAX_PASSWORD_LENGTH: Final = 128
MIN_STRENGTH: Final = 3  # zxcvbn score 0-4


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-work verification; a missing hash (unknown user, reset account) never matches."""
    if not password_hash:
        _hasher.verify(password, _DUMMY_HASH)
        return False
    try:
        return _hasher.verify(password, password_hash)
    except (PwdlibError, ValueError):  # malformed hash: a failed attempt, never an error page
        _hasher.verify(password, _DUMMY_HASH)
        return False


def password_problems(password: str, username: str, display_name: str = "") -> list[str]:
    """Message keys (`password.*`) for every rule the password breaks; empty = acceptable."""
    problems: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append("password.too_short")
    if len(password) > MAX_PASSWORD_LENGTH:
        return [*problems, "password.too_long"]  # do not feed huge input to zxcvbn
    lowered = password.casefold()
    if username and username.casefold() in lowered:
        problems.append("password.contains_username")
    if zxcvbn(password, user_inputs=[username, display_name])["score"] < MIN_STRENGTH:
        problems.append("password.too_weak")
    return problems


# --- opaque tokens (refresh, activation, device) -------------------------------------------


def sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_opaque_token() -> tuple[str, str]:
    """(raw token for the client, sha256 hex stored server-side). 256 bits of entropy."""
    raw = secrets.token_urlsafe(32)
    return raw, sha256_hex(raw)


# --- lockout (OWASP device-cookie model) ---------------------------------------------------

PER_IP_THRESHOLD: Final = 5
BASE_LOCK: Final = timedelta(minutes=15)
MAX_LOCK: Final = timedelta(hours=24)
UNTRUSTED_THRESHOLD: Final = 10
UNTRUSTED_WINDOW: Final = timedelta(hours=24)


@dataclass(frozen=True)
class LockoutDecision:
    allowed: bool
    retry_after: timedelta = timedelta(0)


def lockout_decision(
    *,
    failures_username_ip: int,
    failures_username_untrusted: int,
    last_failure: datetime | None,
    device_trusted: bool,
    now: datetime,
) -> LockoutDecision:
    """Decide whether a login attempt may proceed.

    - (username, IP): every 5 failures lock for 15 min, doubling, at most 24 h.
    - Untrusted devices: 10 failures in 24 h for the username block untrusted devices entirely
      (rotating IPs does not help), while a device that logged in before keeps working.
    Counts are since the last successful login (auth_failure_counts).
    """
    if last_failure is None:
        return LockoutDecision(allowed=True)
    if not device_trusted and failures_username_untrusted >= UNTRUSTED_THRESHOLD:
        remaining = last_failure + UNTRUSTED_WINDOW - now
        if remaining > timedelta(0):
            return LockoutDecision(allowed=False, retry_after=remaining)
    if failures_username_ip >= PER_IP_THRESHOLD:
        # Cap the exponent: 15 min * 2**7 already exceeds 24 h, and an attacker controls the
        # failure count (unbounded 2**n would overflow timedelta and crash the login endpoint).
        steps = min(failures_username_ip // PER_IP_THRESHOLD - 1, 7)
        lock = min(BASE_LOCK * (2**steps), MAX_LOCK)
        remaining = last_failure + lock - now
        if remaining > timedelta(0):
            return LockoutDecision(allowed=False, retry_after=remaining)
    return LockoutDecision(allowed=True)
