"""Passing de-identified text to the AI worker and its answer back (Phase 4.5; Q50).

The default worker holds the database and the field-encryption key and no route out; the AI
worker holds the API key and one route out but neither the database nor the key, and shares
only Valkey with the rest (its own network). Between them, for 15 minutes at most and read
once (GETDEL):
- `ai-input:{document}`: the text `deidentify` left, with a random nonce;
- `ai-output:{document}:{nonce}`: the answer (rows as printed) or an error code, written once.
The nonce and the user who asked are kept in the database (`ai_requests`, 0033): the default
worker saves only an answer under its own nonce, as its own user - never what the AI worker
says about who or which document. Celery carries only ids (rule 3).
`reserve` counts a document against the daily caps when it is sent (atomic INCR), so a
refusal, an error, a burst of uploads or a deleted document never frees a place.
"""

import json
from datetime import UTC, datetime
from typing import Any, Final, Protocol
from uuid import UUID

from labtrack.config import get_settings

TTL_SECONDS: Final = 15 * 60
_INPUT: Final = "ai-input:{}"
_OUTPUT: Final = "ai-output:{}:{}"
_CAP_USER: Final = "ai-cap:{}:{}"
_CAP_ALL: Final = "ai-cap:all:{}"
_CAP_TTL: Final = 2 * 24 * 3600


class Handoff(Protocol):
    """The default worker's side."""

    async def reserve(self, user_id: UUID) -> bool: ...

    async def put_input(self, document_id: UUID, nonce: str, text: str) -> None: ...

    async def take_output(self, document_id: UUID, nonce: str) -> dict[str, Any] | None: ...

    def send(self, document_id: UUID, user_id: UUID) -> None: ...


class ValkeyHandoff:
    def __init__(self) -> None:
        from redis.asyncio import Redis  # noqa: PLC0415

        self._valkey = Redis.from_url(str(get_settings().redis_url))

    async def reserve(self, user_id: UUID) -> bool:
        settings = get_settings()
        day = datetime.now(UTC).strftime("%Y%m%d")
        mine, everyone = _CAP_USER.format(user_id, day), _CAP_ALL.format(day)
        async with self._valkey.pipeline(transaction=True) as pipe:
            pipe.incr(mine)
            pipe.expire(mine, _CAP_TTL)
            pipe.incr(everyone)
            pipe.expire(everyone, _CAP_TTL)
            used, _, used_all, _ = await pipe.execute()
        return int(used) <= settings.ai_daily_documents and (
            int(used_all) <= settings.ai_daily_documents_total
        )

    async def put_input(self, document_id: UUID, nonce: str, text: str) -> None:
        payload = json.dumps({"nonce": nonce, "text": text}, ensure_ascii=False)
        await self._valkey.set(_INPUT.format(document_id), payload.encode(), ex=TTL_SECONDS)

    async def take_output(self, document_id: UUID, nonce: str) -> dict[str, Any] | None:
        raw = await self._valkey.getdel(_OUTPUT.format(document_id, nonce))
        if raw is None:
            return None
        answer: dict[str, Any] = json.loads(raw)
        return answer

    def send(self, document_id: UUID, user_id: UUID) -> None:
        from labtrack.worker.celery_app import app  # noqa: PLC0415

        app.send_task("labtrack.ai.read", args=[str(document_id)], ignore_result=True)
        # saved by the default worker itself, once the answer is there (it polls)
        app.send_task(
            "labtrack.documents.save_ai", args=[str(document_id), str(user_id)], countdown=15
        )

    async def close(self) -> None:
        await self._valkey.aclose()


# --- the AI worker's side (sync, inside its Celery task) -------------------------------------


def take_input(document_id: str) -> tuple[str, str] | None:
    """(nonce, text), once."""
    from redis import Redis  # noqa: PLC0415

    with Redis.from_url(str(get_settings().redis_url)) as valkey:
        raw = valkey.getdel(_INPUT.format(document_id))
    if raw is None:
        return None
    payload = json.loads(bytes(raw))
    return str(payload["nonce"]), str(payload["text"])


def put_output(document_id: str, nonce: str, answer: dict[str, Any]) -> None:
    from redis import Redis  # noqa: PLC0415

    with Redis.from_url(str(get_settings().redis_url)) as valkey:
        valkey.set(
            _OUTPUT.format(document_id, nonce),
            json.dumps(answer, ensure_ascii=False).encode(),
            ex=TTL_SECONDS,
            nx=True,  # the first answer stands: a redelivered task never overwrites it
        )
