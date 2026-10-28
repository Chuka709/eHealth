from hypothesis import given
from hypothesis import strategies as st

from labtrack.logging import REDACTED, is_sensitive_key, redact_phi


def test_sensitive_top_level_keys_are_redacted() -> None:
    event = {
        "event": "login_failed",
        "username": "bold",
        "password": "hunter2",
        "patient_id": "8b0e…",
        "raw_value": "12,4",
    }
    out = redact_phi(None, "info", dict(event))
    assert out["event"] == "login_failed"
    assert out["username"] == REDACTED
    assert out["password"] == REDACTED
    assert out["raw_value"] == REDACTED
    assert out["patient_id"] == "8b0e…"  # IDs are allowed


def test_nested_structures_are_redacted() -> None:
    out = redact_phi(None, "info", {"event": "x", "ctx": {"items": [{"full_name": "Б. Болд"}]}})
    assert out["ctx"] == {"items": [{"full_name": REDACTED}]}


@given(
    st.from_regex(r"[a-z]{1,12}_", fullmatch=True),
    st.sampled_from(["name", "value", "text", "phone", "date", "raw", "note", "snippet"]),
)
def test_any_field_with_a_sensitive_suffix_is_redacted(prefix: str, stem: str) -> None:
    assert is_sensitive_key(prefix + stem)
    assert is_sensitive_key((prefix + stem).upper())
