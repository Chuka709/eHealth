"""Sentry configured so that no PHI can leave the server (CLAUDE.md rule 3).

`data_collection` defaults are MORE permissive than the old `send_default_pii=False`, so every
category is switched off explicitly. Sentry always sends the request URL; `strip_url_query`
removes query strings (share tokens, search terms) before an event leaves the process.
"""

from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

import sentry_sdk

if TYPE_CHECKING:
    from sentry_sdk.types import DataCollectionUserOptions

from labtrack import __version__
from labtrack.config import Settings

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


def strip_url_query(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    request = event.get("request")
    if isinstance(request, dict):
        if isinstance(request.get("url"), str):
            request["url"] = _strip(request["url"])
        request.pop("query_string", None)
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
        before_send=strip_url_query,  # type: ignore[arg-type]
        before_send_transaction=strip_url_query,  # type: ignore[arg-type]
    )
    return True
