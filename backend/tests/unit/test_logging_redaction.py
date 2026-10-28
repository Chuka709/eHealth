import json
import logging

import pytest
from hypothesis import given
from hypothesis import strategies as st

from labtrack.logging import REDACTED, configure_logging, is_sensitive_key, redact_phi, scrub_text


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
    st.sampled_from(
        [
            "name",
            "value",
            "text",
            "phone",
            "date",
            "raw",
            "note",
            "snippet",
            "token",
            "secret",
            "key",
        ]
    ),
)
def test_any_field_with_a_sensitive_suffix_is_redacted(prefix: str, stem: str) -> None:
    assert is_sensitive_key(prefix + stem)
    assert is_sensitive_key((prefix + stem).upper())


def test_driver_messages_lose_their_values() -> None:
    msg = "insert failed DETAIL:  Key (national_id)=(УБ90010101) already exists."
    assert "УБ90010101" not in scrub_text(msg)
    assert "УБ90010101" not in scrub_text("Key (national_id)=(УБ90010101)")
    assert "SECRET" not in scrub_text("GET /api/v1/s/x?token=SECRET HTTP/1.1")
    assert "Б. Болд" not in scrub_text("input_value='Б. Болд', input_type=str")


def test_stdlib_loggers_go_through_redaction(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(json=True)
    try:
        raise ValueError("DETAIL: Key (full_name)=(Б. Болд) violates constraint")  # noqa: TRY301
    except ValueError:
        logging.getLogger("asyncpg.pool").exception("query failed ?token=SECRET")
    line = capsys.readouterr().err.strip().splitlines()[-1]
    record = json.loads(line)
    assert record["logger"] == "asyncpg.pool"
    assert "Б. Болд" not in line
    assert "SECRET" not in line
