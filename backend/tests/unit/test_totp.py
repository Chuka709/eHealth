from datetime import UTC, datetime, timedelta

from hypothesis import given
from hypothesis import strategies as st

from labtrack.core.totp import DRIFT_STEPS, PERIOD, code_at, matching_step, new_secret

SECRET = new_secret()
NOW = datetime(2026, 10, 28, 12, 0, 7, tzinfo=UTC)
STEP = int(NOW.timestamp()) // PERIOD


def test_rfc6238_vector() -> None:
    # RFC 6238 appendix B, SHA-1, T = 59 s -> 94287082 (8 digits); 6-digit suffix.
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32("12345678901234567890")
    assert code_at(secret, 59 // PERIOD) == "287082"


def test_secret_has_160_bits() -> None:
    assert len(new_secret()) == 32  # base32: 5 bits per character


@given(st.integers(min_value=-DRIFT_STEPS, max_value=DRIFT_STEPS))
def test_codes_within_drift_match_their_step(offset: int) -> None:
    code = code_at(SECRET, STEP + offset)
    step = matching_step(SECRET, code, NOW)
    # the same 6 digits can recur in a neighbouring step; then the newest step wins
    assert step is not None
    assert code_at(SECRET, step) == code
    assert step >= STEP + offset


@given(st.integers(min_value=2, max_value=10_000))
def test_codes_outside_drift_are_rejected_unless_they_collide(distance: int) -> None:
    for step in (STEP - distance, STEP + distance):
        code = code_at(SECRET, step)
        collides = any(code_at(SECRET, STEP + d) == code for d in (-1, 0, 1))
        assert (matching_step(SECRET, code, NOW) is not None) == collides


@given(st.text(max_size=12))
def test_malformed_codes_never_match(code: str) -> None:
    if len(code) == 6 and code.isascii() and code.isdigit():
        return
    assert matching_step(SECRET, code, NOW) is None


def test_another_secret_does_not_match() -> None:
    code = code_at(SECRET, STEP)
    other = new_secret()
    if code not in {code_at(other, STEP + d) for d in (-1, 0, 1)}:
        assert matching_step(other, code, NOW) is None


def test_drift_window_is_one_step() -> None:
    late = NOW + timedelta(seconds=PERIOD * 2)
    assert matching_step(SECRET, code_at(SECRET, STEP), late) in {
        None,
        STEP + 1,
        STEP + 2,
        STEP + 3,
    }
