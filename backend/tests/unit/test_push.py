"""Push payload, batching, the on/off switch, the run lock and the Expo adapter (Phase 2.8b).

Nothing here reaches the network: Expo's HTTP session is a fake.
"""

import re
from collections.abc import Mapping, Sequence
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st

from labtrack.logging import scrub_text
from labtrack.worker import push_tasks
from labtrack.worker.push import (
    MESSAGES_PER_REQUEST,
    NOT_SENT,
    ExpoGateway,
    PushRejectedError,
    QueuedPush,
    Receipt,
    Ticket,
    _requests,
    _send,
    error_code,
    message_for,
)

KINDS = ["share_invite", "dose_overdue", "admin_reset", "review_ready", "critical_pending"]
TOKEN = "ExponentPushToken[abcdefghij0123456789xy]"


def _push(notification_id: int = 1, kind: str = "share_invite", locale: str = "mn") -> QueuedPush:
    return QueuedPush(notification_id, kind, uuid4(), TOKEN, locale)


@given(
    kind=st.sampled_from(KINDS),
    locale=st.sampled_from(["mn", "en", "xx"]),
    notification_id=st.integers(min_value=1, max_value=2**63 - 1),
)
def test_the_payload_is_generic_and_carries_two_ids_only(
    kind: str, locale: str, notification_id: int
) -> None:
    m = message_for(_push(notification_id, kind, locale))
    assert set(m) == {"to", "title", "body", "data", "sound", "priority", "channelId"}
    assert m["data"] == {"notification_id": notification_id, "kind": kind}
    assert m["to"] == TOKEN
    assert m["title"] == "LabTrack"
    # nothing about a person, a medicine or a value (security review L3)
    words = set(re.findall(r"\w+", m["body"].lower()))  # whole words ("нээж" is not "ээж")
    for word in ("такролимус", "tacrolimus", "ээж", "тань", "mother", "mg", "ммоль", "patient"):
        assert word not in words
    assert not any(ch.isdigit() for ch in m["body"])


def test_texts_follow_the_users_language_and_the_kind() -> None:
    assert message_for(_push(kind="dose_overdue")).get("body") == (
        "Эм уусан тэмдэглэл хараахан бүртгэгдээгүй байна. Аппаас шалгана уу."
    )
    assert message_for(_push(kind="dose_overdue", locale="en"))["body"] == (
        "A dose has not been logged yet. Please check the app."
    )
    assert message_for(_push(kind="share_invite"))["body"] == "Танд шинэ мэдэгдэл байна."
    assert message_for(_push(kind="review_ready"))["body"] == (
        "Шинэ шинжилгээний хариу уншигдлаа. Аппаас шалгаж батална уу."
    )
    reset = message_for(_push(kind="admin_reset"))["body"]
    assert "нууц үг" in reset
    assert "Кодоо хэнд ч бүү хэлээрэй." in reset  # H12: a caller asking for the code
    assert "уугаагүй" not in message_for(_push(kind="dose_overdue"))["body"]


def test_only_a_plain_error_code_is_kept() -> None:
    assert error_code({"error": "DeviceNotRegistered"}) == "DeviceNotRegistered"
    assert error_code({"error": "PUSH_TOO_MANY_EXPERIENCE_IDS"}) == "PUSH_TOO_MANY_EXPERIENCE_IDS"
    for details in (
        None,
        "DeviceNotRegistered",
        {"error": f'"{TOKEN}" is not a registered push notification recipient'},
        {"error": "x" * 41},
        {"error": 3},
        {"fault": "developer"},
    ):
        assert error_code(details) == "Unknown"


def test_requests_hold_at_most_100_and_keep_a_notifications_devices_together() -> None:
    pushes = [_push(n) for n in range(1, 99)]  # 98 notices with one device each
    pushes += [_push(200), _push(200), _push(200)]  # one notice, three devices
    batches = _requests(pushes)
    assert [len(b) for b in batches] == [98, 3]
    big = [_push(7) for _ in range(MESSAGES_PER_REQUEST + 5)]
    assert [len(b) for b in _requests(big)] == [100, 5]
    assert _requests([]) == []


class _Redis:
    def __init__(self, free: bool = True) -> None:
        self.free, self.released = free, False

    def set(self, *_: Any, **__: Any) -> bool:
        return self.free

    def eval(self, *_: Any) -> int:
        self.released = True
        return 1


class _NoExpo:
    def send(self, messages: Sequence[Mapping[str, Any]]) -> list[Ticket]:
        raise AssertionError("nothing may be sent")

    def receipts(self, ticket_ids: Sequence[str]) -> dict[str, Receipt]:
        raise AssertionError("nothing may be asked")


def _settings(
    monkeypatch: pytest.MonkeyPatch, enabled: bool, env: str = "test", token: object = None
) -> None:
    fake = SimpleNamespace(
        push_enabled=enabled, redis_url="redis://unused", expo_access_token=token, environment=env
    )
    monkeypatch.setattr(push_tasks, "get_settings", lambda: fake)


def test_without_credentials_nothing_is_sent_or_marked(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch, enabled=False)

    def no_redis() -> Any:
        raise AssertionError("not even the lock")

    for job in ("send", "receipts"):
        assert push_tasks.run_push(
            job, "postgresql+asyncpg://unused/x", 60, gateway=_NoExpo, redis=no_redis
        ) == {"disabled": 1}


def test_a_second_run_waits_for_the_first(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch, enabled=True)
    busy = _Redis(free=False)
    assert push_tasks.run_push(
        "send", "postgresql+asyncpg://unused/x", 60, gateway=_NoExpo, redis=lambda: busy
    ) == {"busy": 1}
    assert not busy.released


def test_the_lock_is_released_after_a_run(monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(monkeypatch, enabled=True)
    lock = _Redis()

    async def fake_run(*_: Any) -> dict[str, int]:
        return {"sent": 0}

    monkeypatch.setattr(push_tasks, "_run", fake_run)
    assert push_tasks.run_push(
        "send", "postgresql+asyncpg://unused/x", 60, gateway=_NoExpo, redis=lambda: lock
    ) == {"sent": 0}
    assert lock.released


class _Response:
    def __init__(self, data: dict[str, Any], status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._data

    def raise_for_status(self) -> None:
        return None


class _Session:
    """Stands in for requests.Session: records what would go to Expo."""

    def __init__(self, reply: dict[str, Any], status_code: int = 200) -> None:
        self.reply = reply
        self.status_code = status_code
        self.posts: list[tuple[str, Any]] = []
        self.headers: dict[str, str] = {}

    def post(self, url: str, data: Any = None, json: Any = None, timeout: Any = None) -> _Response:
        self.posts.append((url, data if data is not None else json))
        return _Response(self.reply, self.status_code)


def _gateway(reply: dict[str, Any], status_code: int = 200) -> tuple[ExpoGateway, _Session]:
    gateway = ExpoGateway(access_token="secret-access")
    session = _Session(reply, status_code)
    gateway._client.session = session
    return gateway, session


def test_the_expo_adapter_maps_tickets_and_keeps_codes_only() -> None:
    gateway, session = _gateway(
        {
            "data": [
                {"status": "ok", "id": "tk-1"},
                {
                    "status": "error",
                    "message": f'"{TOKEN}" is not a registered push notification recipient',
                    "details": {"error": "DeviceNotRegistered"},
                },
            ]
        }
    )
    messages = [message_for(_push(1)), message_for(_push(2))]
    tickets = gateway.send(messages)
    assert tickets == [
        Ticket(True, "tk-1", None),
        Ticket(False, None, "DeviceNotRegistered"),
    ]
    [(url, sent)] = session.posts
    assert url == "https://exp.host/--/api/v2/push/send"
    assert '"channelId": "alerts"' in sent
    assert '"notification_id": 1' in sent


def test_the_expo_adapter_reads_receipts() -> None:
    gateway, session = _gateway(
        {
            "data": {
                "tk-1": {"status": "ok"},
                "tk-2": {"status": "error", "details": {"error": "MessageRateExceeded"}},
            }
        }
    )
    assert gateway.receipts(["tk-1", "tk-2", "tk-3"]) == {
        "tk-1": Receipt(True, None),
        "tk-2": Receipt(False, "MessageRateExceeded"),
    }
    [(url, body)] = session.posts
    assert url.endswith("/push/getReceipts")
    assert body == {"ids": ["tk-1", "tk-2", "tk-3"]}


def test_the_access_token_goes_in_the_header() -> None:
    gateway = ExpoGateway(access_token="secret-access")
    assert gateway._client.session.headers["authorization"] == "Bearer secret-access"
    assert "authorization" not in ExpoGateway(None)._client.session.headers


def test_push_tokens_are_scrubbed_from_log_text() -> None:
    text = f'"{TOKEN}" is not a registered push notification recipient'
    assert "abcdefghij" not in scrub_text(text)
    assert "ExpoPushToken[xyz0123456789]" not in scrub_text("ExpoPushToken[xyz0123456789]")


def test_production_without_an_access_token_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Security review M4: without Expo's access token anyone holding a token could push."""
    _settings(monkeypatch, enabled=True, env="production")

    def no_redis() -> Any:
        raise AssertionError("not even the lock")

    assert push_tasks.run_push(
        "send", "postgresql+asyncpg://unused/x", 60, gateway=_NoExpo, redis=no_redis
    ) == {"misconfigured": 1}


def test_a_refused_request_is_reported_as_rejected_with_its_code_only() -> None:
    gateway, _ = _gateway(
        {"errors": [{"code": "PUSH_TOO_MANY_EXPERIENCE_IDS", "message": f"{TOKEN} and others"}]},
        status_code=400,
    )
    with pytest.raises(PushRejectedError) as caught:
        gateway.send([message_for(_push(1))])
    assert caught.value.code == "PUSH_TOO_MANY_EXPERIENCE_IDS"
    assert "abcdefghij" not in str(caught.value)


def test_a_server_error_is_not_a_rejection() -> None:
    gateway, _ = _gateway({"errors": [{"code": "INTERNAL_SERVER_ERROR"}]}, status_code=503)
    from exponent_server_sdk import PushServerError  # noqa: PLC0415

    with pytest.raises(PushServerError) as caught:
        gateway.send([message_for(_push(1))])
    assert not isinstance(caught.value, PushRejectedError)  # stays queued, sent again


@pytest.mark.parametrize("status_code", [429, 401, 403])
def test_a_rate_limit_or_an_access_refusal_is_not_a_rejection(status_code: int) -> None:
    """Re-review M: these are about the moment or the setup - the notices stay queued."""
    from exponent_server_sdk import PushServerError  # noqa: PLC0415

    gateway, _ = _gateway({"errors": [{"code": "TOO_MANY_REQUESTS"}]}, status_code=status_code)
    with pytest.raises(PushServerError) as caught:
        gateway.send([message_for(_push(1))])
    assert not isinstance(caught.value, PushRejectedError)


class _SplitThenDown:
    """Refuses the whole request, accepts the first single message, then is unreachable."""

    def __init__(self) -> None:
        self.calls = 0

    def send(self, messages: Sequence[Mapping[str, Any]]) -> list[Ticket]:
        self.calls += 1
        if len(messages) > 1:
            raise PushRejectedError("VALIDATION_ERROR")
        if self.calls == 2:
            return [Ticket(True, "tk-1", None)]
        raise ConnectionError("down")

    def receipts(self, ticket_ids: Sequence[str]) -> dict[str, Receipt]:
        return {}


async def test_a_split_request_keeps_what_expo_accepted_before_it_went_down() -> None:
    expo = _SplitThenDown()
    tickets = await _send(expo, [_push(1), _push(2), _push(3)])
    assert tickets == [
        Ticket(True, "tk-1", None),
        Ticket(False, None, NOT_SENT),
        Ticket(False, None, NOT_SENT),
    ]
    assert expo.calls == 3  # the third message is not tried once Expo is unreachable
