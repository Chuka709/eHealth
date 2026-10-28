"""Celery app. Task arguments are IDs only - never PHI (CLAUDE.md rule 3)."""

from celery import Celery

from labtrack.config import get_settings

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
)


@app.task(name="labtrack.ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    return "pong"
