"""Celery app. Task arguments are IDs only - never PHI (CLAUDE.md rule 3)."""

from typing import Any

from celery import Celery, signals
from celery.schedules import crontab

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
    # 03:00 Asia/Ulaanbaatar (UTC+8): account purge and auth_attempts retention.
    # Maintenance runs only on the maint worker, the only process with the maint credentials
    # (the default worker parses untrusted uploads).
    task_routes={"labtrack.maintenance.*": {"queue": "maintenance"}},
    beat_schedule={
        "maintenance-daily": {
            "task": "labtrack.maintenance.daily",
            "schedule": crontab(hour=19, minute=0),
        }
    },
)


@signals.setup_logging.connect  # type: ignore[untyped-decorator]
def _setup_logging(**_: Any) -> None:
    # Replaces Celery's own logging so worker records go through the PHI redaction chain.
    configure_logging(json=get_settings().environment != "dev")


@app.task(name="labtrack.ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    return "pong"


@app.task(name="labtrack.maintenance.daily")  # type: ignore[untyped-decorator]
def maintenance_daily() -> dict[str, int]:
    from labtrack.worker.maintenance import run_daily_sync  # noqa: PLC0415

    url = get_settings().maint_database_url
    if url is None:
        raise RuntimeError("MAINT_DATABASE_URL is not set (role labtrack_maint)")
    result = run_daily_sync(str(url))
    return {
        "purged_accounts": result.purged_accounts,
        "auth_attempts_removed": result.auth_attempts_removed,
    }
