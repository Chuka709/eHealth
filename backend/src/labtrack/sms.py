"""Outgoing SMS (docs/04 §1: activation/reset links, the victim notice after a reset).

The gateway is still open (OPEN_QUESTIONS Q13). Until it is chosen, dev and test use a sender
that never writes the number, the link or the token anywhere: the log line carries the user id
and the template only. Elsewhere SMS is unavailable and the admin API offers in-person QR only.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from typing import Protocol
from uuid import UUID

import structlog

from labtrack.config import get_settings

log = structlog.get_logger(__name__)


class SmsTemplate(StrEnum):
    ACTIVATION_LINK = "activation_link"
    RESET_LINK = "reset_link"
    RESET_NOTICE = "reset_notice"  # "your account was reset; if this was not you, call ..."


class SmsUnavailableError(Exception):
    """No gateway configured: SMS channels are refused before anything is issued."""


class SmsSender(Protocol):
    @property
    def available(self) -> bool: ...

    async def send(
        self, *, user_id: UUID, phone: str, template: SmsTemplate, link: str | None
    ) -> None: ...


@dataclass
class ConsoleSmsSender:
    """Dev/test: logs that an SMS would go out, without its content or recipient.

    `outbox` keeps the messages in process memory so tests can follow the link a user would
    receive; it is never written out.
    """

    outbox: list[tuple[UUID, str, SmsTemplate, str | None]] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return True

    async def send(
        self, *, user_id: UUID, phone: str, template: SmsTemplate, link: str | None
    ) -> None:
        self.outbox.append((user_id, phone, template, link))
        del self.outbox[:-100]
        log.info("sms_sent", user_id=str(user_id), template=template.value)


class UnavailableSmsSender:
    @property
    def available(self) -> bool:
        return False

    async def send(
        self, *, user_id: UUID, phone: str, template: SmsTemplate, link: str | None
    ) -> None:
        raise SmsUnavailableError


@lru_cache
def get_sms_sender() -> SmsSender:
    if get_settings().environment in {"dev", "test"}:
        return ConsoleSmsSender()
    return UnavailableSmsSender()
