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
    # Push delivery runs on the push worker: maint credentials too, plus the one outbound route
    # it needs (Expo), so the daily maintenance worker stays without internet.
    task_routes={
        "labtrack.maintenance.*": {"queue": "maintenance"},
        "labtrack.push.*": {"queue": "push"},
    },
    beat_schedule={
        "maintenance-daily": {
            "task": "labtrack.maintenance.daily",
            "schedule": crontab(hour=19, minute=0),
        },
        # caregivers' dose alerts (2.8e): every 5 minutes, alerts are due within an hour
        "missed-doses": {
            "task": "labtrack.maintenance.missed_doses",
            "schedule": 300.0,
            "options": {"expires": 290},
        },
        # a late run is dropped, not queued up behind the next one
        "push-send": {"task": "labtrack.push.send", "schedule": 30.0, "options": {"expires": 25}},
        "push-receipts": {
            "task": "labtrack.push.receipts",
            "schedule": 300.0,
            "options": {"expires": 290},
        },
    },
)

_PUSH_LOCK_SECONDS = 120


def _maint_url() -> str:
    url = get_settings().maint_database_url
    if url is None:
        raise RuntimeError("MAINT_DATABASE_URL is not set (role labtrack_maint)")
    return str(url)


@signals.setup_logging.connect  # type: ignore[untyped-decorator]
def _setup_logging(**_: Any) -> None:
    # Replaces Celery's own logging so worker records go through the PHI redaction chain.
    configure_logging(json=get_settings().environment != "dev")


@app.task(name="labtrack.ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    return "pong"


# Bounded, so a slow purge never holds the queue for long (the maint worker runs two at a time,
# so caregivers' dose alerts keep running beside it - security review M3).
@app.task(name="labtrack.maintenance.daily", soft_time_limit=1200, time_limit=1500)  # type: ignore[untyped-decorator]
def maintenance_daily() -> dict[str, int]:
    from labtrack.worker.maintenance import run_daily_sync  # noqa: PLC0415

    result = run_daily_sync(_maint_url())
    return {
        "purged_accounts": result.purged_accounts,
        "auth_attempts_removed": result.auth_attempts_removed,
        "push_receipts_removed": result.push_receipts_removed,
    }


@app.task(name="labtrack.maintenance.missed_doses", soft_time_limit=240, time_limit=280)  # type: ignore[untyped-decorator]
def missed_doses() -> dict[str, int]:
    from labtrack.worker.missed_doses import run_sync  # noqa: PLC0415

    result = run_sync(_maint_url(), str(get_settings().database_url))
    return {
        "targets": result.targets,
        "alerts": result.alerts,
        "notices": result.notices,
        "failed": result.failed,
        "skipped": result.skipped,
    }


# Both end well before the run lock expires (120 s), so a stuck run never overlaps the next.
@app.task(name="labtrack.push.send", soft_time_limit=90, time_limit=110)  # type: ignore[untyped-decorator]
def push_send() -> dict[str, int]:
    from labtrack.worker.push_tasks import run_push  # noqa: PLC0415

    return run_push("send", _maint_url(), _PUSH_LOCK_SECONDS)


@app.task(name="labtrack.push.receipts", soft_time_limit=90, time_limit=110)  # type: ignore[untyped-decorator]
def push_receipts() -> dict[str, int]:
    from labtrack.worker.push_tasks import run_push  # noqa: PLC0415

    return run_push("receipts", _maint_url(), _PUSH_LOCK_SECONDS)
