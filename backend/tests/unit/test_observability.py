import pytest

from labtrack.config import Settings
from labtrack.observability import DATA_COLLECTION, init_sentry, scrub_event

_DB = "postgresql+asyncpg://u@h/d"


def test_empty_dsn_disables_sentry() -> None:
    settings = Settings.model_validate({"database_url": _DB, "sentry_dsn": ""})
    assert settings.sentry_dsn is None
    assert init_sentry(settings) is False


def test_url_query_and_query_string_are_removed() -> None:
    event = {
        "request": {
            "url": "https://api.example.mn/api/v1/s/abc?token=SECRET&pin=123456",
            "query_string": "token=SECRET&pin=123456",
        }
    }
    out = scrub_event(event, {})
    assert out["request"]["url"] == "https://api.example.mn/api/v1/s/abc"
    assert "query_string" not in out["request"]
    assert "SECRET" not in repr(out)


def test_event_without_request_passes_through() -> None:
    assert scrub_event({"message": "x"}, {}) == {"message": "x"}


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("user_info", False),
        ("cookies", {"mode": "off"}),
        ("http_headers", {"request": {"mode": "off"}}),
        ("url_query_params", {"mode": "off"}),
        ("http_bodies", []),
        ("stack_frame_variables", False),
        ("database_query_data", False),
        ("queues", False),
    ],
)
def test_every_personal_data_category_is_off(key: str, expected: object) -> None:
    # Omitted categories fall back to permissive defaults, so each must be explicit.
    assert dict(DATA_COLLECTION)[key] == expected


def test_exception_values_breadcrumbs_and_log_messages_are_scrubbed() -> None:
    event = {
        "exception": {
            "values": [
                {
                    "type": "UniqueViolationError",
                    "value": "duplicate key\nDETAIL:  Key (national_id)=(УБ90010101) exists.",
                }
            ]
        },
        "breadcrumbs": {"values": [{"message": "SELECT ... Бат-Эрдэнэ"}]},
        "logentry": {"message": "login failed for %s", "params": ["bold"]},
    }
    out = scrub_event(event, {})
    assert "УБ90010101" not in repr(out)
    assert "Бат-Эрдэнэ" not in repr(out)
    assert "bold" not in repr(out)
    assert out["exception"]["values"][0]["type"] == "UniqueViolationError"
