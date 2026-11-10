"""Expo push delivery as `labtrack_maint` (Phase 2.8b; docs/08 "Мэдэгдэл"; H12, H16).

- send: maint_push_queue() -> Expo (at most 100 messages per request) -> a push_receipts row
  per message (ticket id, token hash) -> maint_mark_pushed(). A notification is marked only
  after Expo accepted the request it was in; a failed request is sent again on the next run
  (at least once - a crash between Expo's answer and the commit can repeat one push, which is
  better than losing a security notice). One run at a time (a Valkey lock in the task).
- receipts: about 15 minutes later Expo reports per ticket. DeviceNotRegistered clears that
  session's token, only if it still is the one the ticket went to (0023).
- payload (security review L3): the visible text names nobody, no medicine, no value; `data`
  holds only the notification id and kind - the app reads the rest through the API once
  signed in. Expo's own error messages repeat the token: only the error code is kept, and
  logs carry counts only (CLAUDE.md rule 3).
- no Expo credentials yet (PROGRESS 2.8 decision (c)): with push disabled nothing is sent and
  nothing is marked as sent.
"""

import asyncio
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal, Protocol

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

log = structlog.get_logger(__name__)

QUEUE_LIMIT: Final = 500
MESSAGES_PER_REQUEST: Final = 100  # Expo's limit per /push/send request
RECEIPTS_PER_RUN: Final = 1000  # Expo's limit per /push/getReceipts request
RECEIPT_DELAY_MINUTES: Final = 15
RECEIPT_GIVE_UP_HOURS: Final = 24  # Expo keeps receipts for a day
ANDROID_CHANNEL: Final = "alerts"  # created by the app (2.8f); the reminders have their own
DEVICE_NOT_REGISTERED: Final = "DeviceNotRegistered"
INVALID_CREDENTIALS: Final = "InvalidCredentials"
# ticket errors that are about the moment or the server setup, not the device: sent again
NOT_SENT: Final = "NotSent"  # ours: Expo became unreachable before this message went
RETRY_LATER: Final = frozenset({"MessageRateExceeded", INVALID_CREDENTIALS, NOT_SENT})
_ERROR_CODE = re.compile(r"^[A-Za-z_]{1,40}$")  # same as push_receipts.error (0023)

Locale = Literal["mn", "en"]

# Generic on purpose: shown on a locked screen, possibly to someone else.
_TITLE: Final = "LabTrack"
_BODY: Final[Mapping[str, Mapping[Locale, str]]] = {
    "default": {
        "mn": "Танд шинэ мэдэгдэл байна.",
        "en": "You have a new notification.",
    },
    # to a caregiver; the server cannot know the dose was missed, only that it is not recorded
    # ("not logged", never "not taken"; nothing that reads as "check the dose amount")
    "dose_overdue": {
        "mn": "Эм уусан тэмдэглэл хараахан бүртгэгдээгүй байна. Аппаас шалгана уу.",
        "en": "A dose has not been logged yet. Please check the app.",
    },
    # an AI draft the user has not confirmed: "may", as in the app (docs/08 "Мэдэгдэл")
    "critical_pending": {
        "mn": "Шинэ хариунд яаралтай хянах утга байж болзошгүй. Аппаас шалгана уу.",
        "en": "A new result may contain a value that needs prompt review. Please check the app.",
    },
    # H12: the person whose password an admin reset learns about it, even on a signed-out phone.
    # Opening the app shows the reset screen with the "not you" steps (Q8); a fraudster who
    # called the victim needs the code, hence the warning.
    "admin_reset": {
        "mn": (
            "Админ таны нууц үгийг сэргээх код олгож, нэвтрэлтийг цуцаллаа. Та хүсээгүй бол"
            " аппаа нээж дэлгэрэнгүйг харна уу. Кодоо хэнд ч бүү хэлээрэй."
        ),
        "en": (
            "An admin issued a password reset code for your account and signed you out. If you"
            " did not ask for this, open the app for what to do. Never share the code."
        ),
    },
}


@dataclass(frozen=True)
class QueuedPush:
    notification_id: int
    kind: str
    session_id: Any
    push_token: str
    locale: str


@dataclass(frozen=True)
class Ticket:
    ok: bool
    ticket_id: str | None
    error: str | None  # an Expo error code (letters, "_"), never Expo's message


@dataclass(frozen=True)
class Receipt:
    ok: bool
    error: str | None


class PushRejectedError(Exception):
    """Expo refused the whole request (a 4xx answer), e.g. for one bad message in it."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PushGateway(Protocol):
    def send(self, messages: Sequence[Mapping[str, Any]]) -> list[Ticket]:
        """One Expo request. Raises PushRejectedError if Expo refused it (4xx), any other
        exception if it could not be sent; either way nothing was sent."""
        ...

    def receipts(self, ticket_ids: Sequence[str]) -> dict[str, Receipt]:
        """Receipts Expo has; a ticket it does not know yet is missing from the result."""
        ...


def error_code(details: object) -> str:
    """Expo's `details.error`, if it is a plain code; anything else is reduced to "Unknown"."""
    if isinstance(details, Mapping):
        code = details.get("error")
        if isinstance(code, str) and _ERROR_CODE.fullmatch(code):
            return code
    return "Unknown"


def message_for(push: QueuedPush) -> dict[str, Any]:
    """The whole payload Expo gets: the token, generic text and two ids."""
    locale: Locale = "en" if push.locale == "en" else "mn"
    body = _BODY.get(push.kind, _BODY["default"])[locale]
    return {
        "to": push.push_token,
        "title": _TITLE,
        "body": body,
        "data": {"notification_id": push.notification_id, "kind": push.kind},
        "sound": "default",
        "priority": "high",
        "channelId": ANDROID_CHANNEL,
    }


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _requests(pushes: Sequence[QueuedPush]) -> list[list[QueuedPush]]:
    """Groups of at most 100 messages. A notification's devices stay in one request where they
    fit, so it is marked only when all of them were sent."""
    groups: dict[int, list[QueuedPush]] = {}
    for push in pushes:
        groups.setdefault(push.notification_id, []).append(push)
    batches: list[list[QueuedPush]] = []
    current: list[QueuedPush] = []
    for group in groups.values():
        if current and len(current) + len(group) > MESSAGES_PER_REQUEST:
            batches.append(current)
            current = []
        for push in group:  # a group larger than a request is split (more devices than 100)
            if len(current) == MESSAGES_PER_REQUEST:
                batches.append(current)
                current = []
            current.append(push)
    if current:
        batches.append(current)
    return batches


@dataclass(frozen=True)
class SendResult:
    sent: int = 0
    failed_tickets: int = 0
    failed_requests: int = 0
    marked: int = 0


async def _queue(engine: AsyncEngine) -> list[QueuedPush]:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                bound_text(
                    "select notification_id, kind, session_id, push_token, locale"
                    " from maint_push_queue(:n)"
                ),
                {"n": QUEUE_LIMIT},
            )
        ).all()
    pushes = [QueuedPush(**r._mapping) for r in rows]
    if len(pushes) == QUEUE_LIMIT and pushes[0].notification_id != pushes[-1].notification_id:
        # the last notification may have more devices past the limit: it waits for the next run
        last = pushes[-1].notification_id
        pushes = [p for p in pushes if p.notification_id != last]
    return pushes


async def _record(engine: AsyncEngine, batch: Sequence[QueuedPush], tickets: list[Ticket]) -> None:
    """A receipt row per device that is done with this notice (sent, or failed for good). A
    device whose send should be retried gets none, so the queue offers it again."""
    async with engine.connect() as conn, conn.begin():
        for push, ticket in zip(batch, tickets, strict=True):
            if not ticket.ok and ticket.error in RETRY_LATER:
                continue
            await conn.execute(
                bound_text(
                    "insert into push_receipts"
                    " (notification_id, session_id, ticket_id, status, error, token_sha256)"
                    " values (:n, :s, :t, :st, :e, :h)"
                ),
                {
                    "n": push.notification_id,
                    "s": push.session_id,
                    "t": ticket.ticket_id if ticket.ok else None,
                    "st": "sent" if ticket.ok else "error",
                    "e": None if ticket.ok else ticket.error,
                    "h": token_hash(push.push_token),
                },
            )
            if not ticket.ok and ticket.error == DEVICE_NOT_REGISTERED:
                await conn.execute(
                    bound_text("select maint_forget_push_token(:t)"), {"t": push.push_token}
                )


async def _send(gateway: PushGateway, batch: Sequence[QueuedPush]) -> list[Ticket] | None:
    """Expo's tickets for a request, or None when it could not be sent (retried next run).

    Expo refuses a whole request for one bad message (e.g. a token of another Expo project):
    the request is then sent one message at a time, so one bad token holds up nobody else's
    notices (security review H1) and is itself recorded as a failure."""
    try:
        tickets = await asyncio.to_thread(gateway.send, [message_for(p) for p in batch])
    except PushRejectedError as exc:
        if len(batch) == 1:
            return [Ticket(False, None, exc.code)]
        singles: list[Ticket] = []
        for push in batch:
            one = await _send(gateway, [push])
            if one is None:
                # Expo is now unreachable: keep what it accepted, the rest waits for the next
                # run (no repeat to the devices already reached; no 100 more timeouts now)
                return singles + [Ticket(False, None, NOT_SENT)] * (len(batch) - len(singles))
            singles.extend(one)
        return singles
    except Exception as exc:  # unreachable, timeout, 5xx: everything stays queued
        # no traceback or text: Expo's errors can repeat the tokens
        log.warning("push_request_failed", error=type(exc).__name__, messages=len(batch))
        return None
    if len(tickets) != len(batch):
        log.warning("push_ticket_mismatch", messages=len(batch), tickets=len(tickets))
        return None
    return tickets


async def send_pending(engine: AsyncEngine, gateway: PushGateway) -> SendResult:
    pushes = await _queue(engine)
    due: dict[int, int] = {}
    for push in pushes:
        due[push.notification_id] = due.get(push.notification_id, 0) + 1
    done: dict[int, int] = {}
    sent = failed_tickets = failed_requests = 0
    for batch in _requests(pushes):
        tickets = await _send(gateway, batch)
        if tickets is None:
            failed_requests += 1
            continue
        await _record(engine, batch, tickets)
        for push, ticket in zip(batch, tickets, strict=True):
            if ticket.ok or ticket.error not in RETRY_LATER:
                done[push.notification_id] = done.get(push.notification_id, 0) + 1
        sent += sum(t.ok for t in tickets)
        failed_tickets += sum(not t.ok for t in tickets)
        if any(t.error == INVALID_CREDENTIALS for t in tickets):
            # the FCM/APNs credentials in EAS are wrong: every device fails until fixed
            log.error("push_invalid_credentials")
    # a notice is done once every device it was due for is done; the others stay queued
    finished = sorted(n for n, count in due.items() if done.get(n) == count)
    marked = 0
    if finished:
        async with engine.connect() as conn, conn.begin():
            marked = int(
                (
                    await conn.execute(
                        bound_text("select maint_mark_pushed(cast(:ids as bigint[]))"),
                        {"ids": finished},
                    )
                ).scalar_one()
            )
    result = SendResult(sent, failed_tickets, failed_requests, marked)
    if pushes:
        log.info(
            "push_sent",
            sent=result.sent,
            failed_tickets=result.failed_tickets,
            failed_requests=result.failed_requests,
            marked=result.marked,
        )
    return result


@dataclass(frozen=True)
class ReceiptResult:
    ok: int = 0
    errors: int = 0
    forgotten_tokens: int = 0
    expired: int = 0


async def check_receipts(engine: AsyncEngine, gateway: PushGateway) -> ReceiptResult:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                bound_text(
                    "select id, ticket_id,"
                    " created_at < now() - make_interval(hours => :g) as too_old"
                    " from push_receipts where status = 'sent' and ticket_id is not null"
                    " and created_at < now() - make_interval(mins => :d)"
                    " order by id limit :n"
                ),
                {"g": RECEIPT_GIVE_UP_HOURS, "d": RECEIPT_DELAY_MINUTES, "n": RECEIPTS_PER_RUN},
            )
        ).all()
    if not rows:
        return ReceiptResult()
    try:
        receipts = await asyncio.to_thread(gateway.receipts, [r.ticket_id for r in rows])
    except Exception as exc:  # asked again on the next run
        log.warning("push_receipts_failed", error=type(exc).__name__, tickets=len(rows))
        return ReceiptResult()
    ok = errors = forgotten = expired = 0
    async with engine.connect() as conn, conn.begin():
        for row in rows:
            receipt = receipts.get(row.ticket_id)
            if receipt is None:
                if not row.too_old:
                    continue  # not ready yet
                status, code = "error", "Expired"
                expired += 1
            elif receipt.ok:
                status, code = "ok", None
                ok += 1
            else:
                status, code = "error", receipt.error or "Unknown"
                errors += 1
                if code == INVALID_CREDENTIALS:  # FCM/APNs say so here, not on the ticket
                    log.error("push_invalid_credentials")
            await conn.execute(
                bound_text(
                    "update push_receipts set status = :s, error = :e, checked_at = now()"
                    " where id = :i"
                ),
                {"s": status, "e": code, "i": row.id},
            )
            if code == DEVICE_NOT_REGISTERED:
                forgotten += (
                    await conn.execute(
                        bound_text("select maint_forget_receipt_token(:i)"), {"i": row.id}
                    )
                ).scalar_one()
    result = ReceiptResult(ok, errors, forgotten, expired)
    log.info(
        "push_receipts_checked",
        ok=result.ok,
        errors=result.errors,
        forgotten_tokens=result.forgotten_tokens,
        expired=result.expired,
    )
    return result


class ExpoGateway:
    """exponent-server-sdk (MIT) over HTTPS to Expo. Built only when push is enabled."""

    # (connect, read) seconds; the task's time limit bounds the whole run (celery_app.py)
    def __init__(
        self, access_token: str | None, timeout: tuple[float, float] = (5.0, 15.0)
    ) -> None:
        import requests  # noqa: PLC0415
        from exponent_server_sdk import PushClient  # noqa: PLC0415

        session = requests.Session()
        session.headers.update(
            {
                "accept": "application/json",
                "accept-encoding": "gzip, deflate",
                "content-type": "application/json",
            }
        )
        if access_token:
            session.headers["authorization"] = f"Bearer {access_token}"
        self._client = PushClient(session=session, timeout=timeout)

    def send(self, messages: Sequence[Mapping[str, Any]]) -> list[Ticket]:
        from exponent_server_sdk import PushMessage, PushServerError  # noqa: PLC0415

        pms = [
            PushMessage(
                to=m["to"],
                title=m["title"],
                body=m["body"],
                data=m["data"],
                sound=m["sound"],
                priority=m["priority"],
                channel_id=m["channelId"],
            )
            for m in messages
        ]
        # one request: the caller already keeps to 100 messages (the SDK's own chunk size)
        try:
            tickets = self._client.publish_multiple(pms)
        except PushServerError as exc:
            status = getattr(exc.response, "status_code", None)
            # 400 is about the messages; 429 (Expo's rate limit), 401/403 (access token) and
            # 5xx are about the moment or the setup: re-raised, so the notices stay queued
            if status == 400:  # noqa: PLR2004
                errors = exc.errors if isinstance(exc.errors, list) else []
                first = errors[0] if errors and isinstance(errors[0], Mapping) else {}
                raise PushRejectedError(error_code({"error": first.get("code")})) from None
            if status in {401, 403}:
                # no traceback: Expo's error text can repeat the tokens
                log.error("push_access_denied", status=status)  # noqa: TRY400
            raise
        return [
            Ticket(ok=True, ticket_id=str(t.id), error=None)
            if t.is_success() and t.id
            else Ticket(ok=False, ticket_id=None, error=error_code(t.details))
            for t in tickets
        ]

    def receipts(self, ticket_ids: Sequence[str]) -> dict[str, Receipt]:
        from exponent_server_sdk import PushTicket  # noqa: PLC0415

        tickets = [PushTicket(None, "ok", None, None, i) for i in ticket_ids]
        return {
            str(r.id): Receipt(ok=True, error=None)
            if r.is_success()
            else Receipt(ok=False, error=error_code(r.details))
            for r in self._client.check_receipts_multiple(tickets)
        }
