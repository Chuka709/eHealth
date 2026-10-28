from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from labtrack.auth.tokens import (
    AccessClaims,
    InvalidTokenError,
    decode_access_token,
    issue_access_token,
)
from labtrack.core.security import (
    BASE_LOCK,
    MAX_LOCK,
    PER_IP_THRESHOLD,
    UNTRUSTED_THRESHOLD,
    hash_password,
    lockout_decision,
    new_opaque_token,
    password_problems,
    sha256_hex,
    verify_password,
)

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)

# --- passwords ---------------------------------------------------------------------------------


def test_hash_is_argon2id_and_verifies() -> None:
    h = hash_password("Ногоон-уул 2026!")
    assert h.startswith("$argon2id$")
    assert verify_password("Ногоон-уул 2026!", h)
    assert not verify_password("ногоон-уул 2026!", h)


@pytest.mark.parametrize("stored", [None, "", "not-a-hash", "$argon2id$garbage"])
def test_missing_or_malformed_hash_never_verifies(stored: str | None) -> None:
    assert verify_password("anything", stored) is False


@pytest.mark.parametrize(
    ("password", "problem"),
    [
        ("short1!", "password.too_short"),
        ("x" * 129, "password.too_long"),
        ("bold.2026.bold", "password.contains_username"),
        ("password123", "password.too_weak"),
        ("aaaaaaaaaaaa", "password.too_weak"),
    ],
)
def test_password_policy_rejects(password: str, problem: str) -> None:
    assert problem in password_problems(password, "bold")


def test_password_policy_accepts_a_long_passphrase() -> None:
    assert password_problems("Хөвсгөл нуур зун 2026 гэрэлтэй", "bold") == []


# --- opaque tokens -----------------------------------------------------------------------------


def test_opaque_tokens_are_unique_and_only_the_hash_is_stored() -> None:
    raw1, h1 = new_opaque_token()
    raw2, h2 = new_opaque_token()
    assert raw1 != raw2
    assert h1 == sha256_hex(raw1) != h2
    assert len(h1) == 64
    assert raw1 not in h1


# --- lockout -----------------------------------------------------------------------------------


def test_no_failures_is_allowed() -> None:
    d = lockout_decision(
        failures_username_ip=0,
        failures_username_untrusted=0,
        last_failure=None,
        device_trusted=False,
        now=NOW,
    )
    assert d.allowed


def test_five_failures_from_one_ip_lock_for_fifteen_minutes() -> None:
    kwargs = {"failures_username_untrusted": 5, "device_trusted": False, "now": NOW}
    locked = lockout_decision(failures_username_ip=5, last_failure=NOW, **kwargs)  # type: ignore[arg-type]
    assert not locked.allowed
    assert locked.retry_after == BASE_LOCK
    later = lockout_decision(
        failures_username_ip=5,
        last_failure=NOW - BASE_LOCK - timedelta(seconds=1),
        **kwargs,  # type: ignore[arg-type]
    )
    assert later.allowed


def test_untrusted_devices_are_blocked_but_a_trusted_device_still_logs_in() -> None:
    common = {
        "failures_username_ip": 1,  # attacker rotates IPs
        "failures_username_untrusted": UNTRUSTED_THRESHOLD,
        "last_failure": NOW,
        "now": NOW,
    }
    assert not lockout_decision(device_trusted=False, **common).allowed  # type: ignore[arg-type]
    assert lockout_decision(device_trusted=True, **common).allowed  # type: ignore[arg-type]


@settings(max_examples=200)
@given(
    st.integers(min_value=0, max_value=10**9),  # attacker-controlled counts
    st.integers(min_value=0, max_value=10**9),
    st.booleans(),
    st.integers(min_value=0, max_value=3 * 24 * 3600),
)
def test_lock_is_bounded_and_monotonic(
    per_ip: int, untrusted: int, trusted: bool, ago: int
) -> None:
    last = NOW - timedelta(seconds=ago)
    d = lockout_decision(
        failures_username_ip=per_ip,
        failures_username_untrusted=untrusted,
        last_failure=last,
        device_trusted=trusted,
        now=NOW,
    )
    # never longer than 24 h, and never locked below the thresholds
    assert d.retry_after <= MAX_LOCK
    if per_ip < PER_IP_THRESHOLD and (trusted or untrusted < UNTRUSTED_THRESHOLD):
        assert d.allowed
    # more failures never shorten the lock
    more = lockout_decision(
        failures_username_ip=per_ip + PER_IP_THRESHOLD,
        failures_username_untrusted=untrusted,
        last_failure=last,
        device_trusted=trusted,
        now=NOW,
    )
    assert more.retry_after >= d.retry_after


# --- access tokens -----------------------------------------------------------------------------


def _claims() -> AccessClaims:
    return AccessClaims(user_id=uuid4(), session_id=uuid4(), token_version=3, role="user")


def test_access_token_round_trip() -> None:
    claims = _claims()
    token, ttl = issue_access_token(claims)
    assert ttl == 15 * 60
    assert decode_access_token(token) == claims


def test_expired_token_is_rejected() -> None:
    token, _ = issue_access_token(_claims(), now=datetime.now(UTC) - timedelta(hours=1))
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_tampered_or_unsigned_tokens_are_rejected() -> None:
    import jwt  # noqa: PLC0415

    token, _ = issue_access_token(_claims())
    header, payload, _sig = token.split(".")
    for bad in (
        f"{header}.{payload}.",  # stripped signature
        jwt.encode({"sub": str(uuid4())}, "k" * 32, algorithm="HS256"),  # HMAC with a guess
        jwt.encode({"sub": "x"}, "", algorithm="none"),  # alg=none
        "not-a-jwt",
    ):
        with pytest.raises(InvalidTokenError):
            decode_access_token(bad)
