"""Structured logging that never emits PHI (CLAUDE.md rule 3: IDs only)."""

import logging
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

REDACTED = "[redacted]"

# Keys that may carry names, values, dates, free text or credentials.
_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "token",
        "refresh_token",
        "access_token",
        "authorization",
        "cookie",
        "pin",
        "username",
        "display_name",
        "full_name",
        "name",
        "phone",
        "national_id",
        "birth_date",
        "value",
        "text",
        "note",
        "notes",
        "description",
        "body",
        "query",
    }
)
_SENSITIVE_SUFFIXES = ("_name", "_value", "_text", "_phone", "_date", "_raw", "_note", "_snippet")


def is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return k in _SENSITIVE_KEYS or k.endswith(_SENSITIVE_SUFFIXES)


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: REDACTED if is_sensitive_key(str(k)) else _redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact(v) for v in value]
    return value


def redact_phi(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if key == "event":
            continue
        event_dict[key] = REDACTED if is_sensitive_key(key) else _redact(event_dict[key])
    return event_dict


def configure_logging(*, json: bool = True, level: int = logging.INFO) -> None:
    renderer: Any = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_phi,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
