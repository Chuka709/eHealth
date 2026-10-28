"""Celery app. Task arguments are IDs only - never PHI (CLAUDE.md rule 3)."""

from typing import Any

from celery import Celery, signals

from labtrack.config import get_settings
from labtrack.logging import configure_logging

_redis = str(get_settings().redis_url)

app = Celery("labtrack", broker=_redis, backend=_redis)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_expires=3600,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    timezone="UTC",
    worker_hijack_root_logger=False,
)


@signals.setup_logging.connect  # type: ignore[untyped-decorator]
def _setup_logging(**_: Any) -> None:
    # Replaces Celery's own logging so worker records go through the PHI redaction chain.
    configure_logging(json=get_settings().environment != "dev")


@app.task(name="labtrack.ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    return "pong"
