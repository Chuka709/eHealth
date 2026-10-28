"""TOTP for admin sign-in (RFC 6238: SHA-1, 6 digits, 30 s; docs/04 §1 "Супер админ").

Pure functions. `matching_step` returns the time step a code belongs to, so the database can
accept each step once (admin_session_create): a code seen on the wire cannot be replayed.
"""

import hmac
from datetime import datetime
from typing import Final

import pyotp

PERIOD: Final = 30
DIGITS: Final = 6
# One step either side: clock drift between the server and the admin's phone.
DRIFT_STEPS: Final = 1
ISSUER: Final = "LabTrack MN Admin"


def new_secret() -> str:
    return pyotp.random_base32(length=32)  # 160 bits


def provisioning_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret, digits=DIGITS, interval=PERIOD).provisioning_uri(
        name=username, issuer_name=ISSUER
    )


def code_at(secret: str, step: int) -> str:
    return pyotp.TOTP(secret, digits=DIGITS, interval=PERIOD).at(step * PERIOD)


def matching_step(secret: str, code: str, now: datetime) -> int | None:
    """The time step whose code equals `code`, newest first; None if none matches."""
    if len(code) != DIGITS or not code.isascii() or not code.isdigit():
        return None
    current = int(now.timestamp()) // PERIOD
    match: int | None = None
    # Compare against every candidate (no early exit) so timing does not reveal the offset.
    for step in range(current + DRIFT_STEPS, current - DRIFT_STEPS - 1, -1):
        if hmac.compare_digest(code_at(secret, step), code) and match is None:
            match = step
    return match
