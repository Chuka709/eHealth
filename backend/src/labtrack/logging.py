"""Structured logging that never emits PHI (CLAUDE.md rule 3: IDs only).

Two layers:
- structured fields are redacted by key (`redact_phi`);
- free text (the event message, stdlib records from uvicorn/sqlalchemy/asyncpg/celery, exception
  text) is scrubbed of the patterns that carry values (`scrub_text`), e.g. the asyncpg
  `DETAIL: Key (national_id)=(...)` of an integrity error.
All stdlib loggers are routed through the same processor chain.
"""

import logging
import re
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

REDACTED = "[redacted]"

# Keys that may carry names, values, dates, free text or credentials.
_SENSITIVE_KEYS = frozenset(
    {
        "password",
        "token",
        "secret",
        "otp",
        "totp",
        "pin",
        "api_key",
        "dsn",
        "authorization",
        "cookie",
        "email",
        "username",
        "display_name",
        "full_name",
        "name",
        "phone",
        "national_id",
        "register",
        "regno",
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
_SENSITIVE_SUFFIXES = (
    "_name",
    "_value",
    "_text",
    "_phone",
    "_date",
    "_raw",
    "_note",
    "_snippet",
    "_token",
    "_secret",
    "_key",
    "_email",
    "_password",
)

# Value-bearing fragments in driver / framework messages.
_TEXT_PATTERNS = (
    (re.compile(r"DETAIL:.*", re.DOTALL), "DETAIL: [redacted]"),
    (re.compile(r"(Key \([^)]*\))=\([^)]*\)"), r"\1=([redacted])"),
    (re.compile(r"input_value=('[^']*'|\"[^\"]*\"|\S+)"), "input_value=[redacted]"),
    (re.compile(r"(\?)[^\s\"']+"), r"\1[redacted]"),  # URL query strings
    # Expo push tokens (Expo's own error messages repeat them)
    (re.compile(r"(Expo(?:nent)?PushToken\[)[^\]]*\]"), r"\1[redacted]]"),
)


def is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return k in _SENSITIVE_KEYS or k.endswith(_SENSITIVE_SUFFIXES)


def scrub_text(text: str) -> str:
    for pattern, replacement in _TEXT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: REDACTED if is_sensitive_key(str(k)) else _redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact(v) for v in value]
    if isinstance(value, str):
        return scrub_text(value)
    return value


def redact_phi(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if key == "event":
            if isinstance(event_dict[key], str):
                event_dict[key] = scrub_text(event_dict[key])
            continue
        event_dict[key] = REDACTED if is_sensitive_key(key) else _redact(event_dict[key])
    return event_dict


def configure_logging(*, json: bool = True, level: int = logging.INFO) -> None:
    renderer: Any = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            redact_phi,  # after exception formatting, so tracebacks are scrubbed too
            renderer,
        ],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # SQL echo would print statements with bound values.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    for name in ("uvicorn", "uvicorn.error", "celery"):
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = True
