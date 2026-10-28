"""Sentry configured so that no PHI can leave the server (CLAUDE.md rule 3).

`data_collection` defaults are MORE permissive than the old `send_default_pii=False`, so every
category is switched off explicitly. Sentry always sends the request URL and exception text;
`scrub_event` removes query strings and value-bearing message fragments before an event leaves
the process.
"""

from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

import sentry_sdk

if TYPE_CHECKING:
    from sentry_sdk.types import DataCollectionUserOptions

from labtrack import __version__
from labtrack.config import Settings
from labtrack.logging import scrub_text

DATA_COLLECTION: "DataCollectionUserOptions" = {
    "user_info": False,
    "cookies": {"mode": "off"},
    "http_headers": {"request": {"mode": "off"}},
    "url_query_params": {"mode": "off"},
    "http_bodies": [],
    "stack_frame_variables": False,
    "gen_ai": {"inputs": False, "outputs": False},
    "graphql": {"document": False, "variables": False},
    "database_query_data": False,
    "queues": False,
}


def _strip(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def scrub_event(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    """Last line of defence before an event leaves the process.

    - request URL without query string;
    - exception messages scrubbed (driver errors embed row values, e.g. asyncpg DETAIL);
    - breadcrumbs dropped (they carry stdlib log messages and HTTP/DB details);
    - log-message events scrubbed.
    """
    request = event.get("request")
    if isinstance(request, dict):
        if isinstance(request.get("url"), str):
            request["url"] = _strip(request["url"])
        request.pop("query_string", None)
    exception = event.get("exception")
    if isinstance(exception, dict):
        for item in exception.get("values") or []:
            if isinstance(item, dict) and isinstance(item.get("value"), str):
                item["value"] = scrub_text(item["value"])
    event.pop("breadcrumbs", None)
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        for key in ("message", "formatted"):
            if isinstance(logentry.get(key), str):
                logentry[key] = scrub_text(logentry[key])
        logentry.pop("params", None)
    if isinstance(event.get("message"), str):
        event["message"] = scrub_text(event["message"])
    return event


def init_sentry(settings: Settings) -> bool:
    if settings.sentry_dsn is None:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.environment,
        release=__version__,
        data_collection=DATA_COLLECTION,
        max_request_body_size="never",
        before_send=scrub_event,  # type: ignore[arg-type]
        before_send_transaction=scrub_event,  # type: ignore[arg-type]
    )
    return True
