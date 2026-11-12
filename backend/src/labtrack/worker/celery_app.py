"""Celery app. Task arguments are IDs only - never PHI (CLAUDE.md rule 3)."""

from typing import Any

from celery import Celery, signals
from celery.schedules import crontab
from sqlalchemy.exc import OperationalError

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
    # a worker parsing untrusted files is replaced when it grows (security review 4.4 M2)
    worker_max_memory_per_child=600_000,  # KiB
    worker_max_tasks_per_child=200,
    # 03:00 Asia/Ulaanbaatar (UTC+8): account purge and auth_attempts retention.
    # Maintenance runs only on the maint worker, the only process with the maint credentials
    # (the default worker parses untrusted uploads).
    # Push delivery runs on the push worker: its own role (labtrack_push, delivery only) and the
    # one outbound route it needs (Expo), so the daily maintenance worker stays without internet.
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
        # objects of deleted documents (3.3): sealed but readable with the KEK - removed soon
        "document-orphans": {
            "task": "labtrack.maintenance.document_orphans",
            "schedule": crontab(hour=20, minute=10),
        },
        "document-deletions": {
            "task": "labtrack.maintenance.document_deletions",
            "schedule": 600.0,
            "options": {"expires": 590},
        },
        # documents stuck in reading (4.4): failed after 10 minutes, a lost task read again
        "extraction-sweep": {
            "task": "labtrack.maintenance.extraction_sweep",
            "schedule": 300.0,
            "options": {"expires": 290},
        },
    },
)

_PUSH_LOCK_SECONDS = 120


def _push_url() -> str:
    url = get_settings().push_database_url
    if url is None:
        raise RuntimeError("PUSH_DATABASE_URL is not set (role labtrack_push)")
    return str(url)


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

    return run_push("send", _push_url(), _PUSH_LOCK_SECONDS)


@app.task(name="labtrack.push.receipts", soft_time_limit=90, time_limit=110)  # type: ignore[untyped-decorator]
def push_receipts() -> dict[str, int]:
    from labtrack.worker.push_tasks import run_push  # noqa: PLC0415

    return run_push("receipts", _push_url(), _PUSH_LOCK_SECONDS)


# --- documents (Phase 3.3) ------------------------------------------------------------------

# retries of a scan that could not run (clamd down): about 1, 2, 4, 8, 16 minutes
_SCAN_RETRIES = 5


@app.task(  # type: ignore[untyped-decorator]
    name="labtrack.documents.process",
    bind=True,
    max_retries=_SCAN_RETRIES + 3,  # Celery's default (3) would stop before the last try
    soft_time_limit=180,
    time_limit=210,
)
def process_document(self: Any, document_id: str, user_id: str) -> str:
    """Ids only (CLAUDE.md rule 3). Runs on the default worker as the uploader."""
    from labtrack.worker.documents import run_sync  # noqa: PLC0415

    last = self.request.retries >= _SCAN_RETRIES
    result = run_sync(str(get_settings().database_url), document_id, user_id, last_try=last)
    if result == "retry" or (result == "missing" and self.request.retries < 2):  # noqa: PLR2004
        # "missing": the upload's transaction may not have committed yet
        raise self.retry(countdown=3 if result == "missing" else 60 * 2**self.request.retries)
    if result == "queued":
        extract_document.delay(document_id, user_id)  # read it (Phase 4.4)
    return result


@app.task(  # type: ignore[untyped-decorator]
    name="labtrack.documents.extract",
    soft_time_limit=120,
    time_limit=150,
    autoretry_for=(OperationalError,),  # the database briefly away: the document stays queued
    max_retries=3,
    retry_backoff=True,
)
def extract_document(document_id: str, user_id: str) -> str:
    """Ids only (rule 3). Reads a scanned document into draft reports, as the uploader."""
    from labtrack.worker.extraction import run_sync  # noqa: PLC0415

    return run_sync(str(get_settings().database_url), document_id, user_id)


@app.task(  # type: ignore[untyped-decorator]
    name="labtrack.maintenance.extraction_sweep", soft_time_limit=60, time_limit=90
)
def extraction_sweep() -> dict[str, int]:
    from labtrack.worker.maintenance import sweep_extractions_sync  # noqa: PLC0415

    again = sweep_extractions_sync(_maint_url())
    for document_id, user_id in again:
        # dropped if not run before the next sweep hands it back again
        extract_document.apply_async((document_id, user_id), expires=290)
    return {"read_again": len(again)}


@app.task(  # type: ignore[untyped-decorator]
    name="labtrack.maintenance.document_deletions", soft_time_limit=500, time_limit=560
)
def document_deletions() -> dict[str, int]:
    from labtrack.worker.maintenance import delete_queued_objects  # noqa: PLC0415

    return delete_queued_objects(_maint_url())


@app.task(  # type: ignore[untyped-decorator]
    name="labtrack.maintenance.document_orphans", soft_time_limit=1200, time_limit=1500
)
def document_orphans() -> dict[str, int]:
    from labtrack.worker.maintenance import delete_orphan_objects  # noqa: PLC0415

    return delete_orphan_objects(_maint_url())
