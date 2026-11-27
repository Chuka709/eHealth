"""OpenBao settings (SERVER_INSTALL_PLAN S1): complete or absent, https outside dev/test, and the
secret id in no repr (a traceback, a log line)."""

import httpx
import pytest
from pydantic import ValidationError

from labtrack.config import Settings
from labtrack.openbao import KeyServiceError, OpenBaoClient, OpenBaoConfig

BASE = {"database_url": "postgresql+asyncpg://u:p@db:5432/x", "clamd_host": "clamav"}


def _settings(**values: str) -> Settings:
    return Settings(**BASE, **values)  # type: ignore[arg-type]


def test_the_secret_id_is_in_no_repr() -> None:
    config = OpenBaoConfig("https://bao:8200", "role-1", "s3cr3t-value")
    client = OpenBaoClient(config)
    client._token = "t0k3n-value"
    for text in (repr(config), repr(client), str(client)):
        assert "s3cr3t-value" not in text
        assert "t0k3n-value" not in text


def test_an_address_needs_its_role_and_secret() -> None:
    with pytest.raises(ValidationError, match="OPENBAO_ROLE_ID"):
        _settings(environment="production", openbao_addr="https://bao:8200")
    with pytest.raises(ValidationError, match="OPENBAO_ROLE_ID"):
        _settings(environment="test", openbao_addr="http://bao:8200", openbao_role_id="r")


def test_keys_never_cross_the_network_in_the_clear_outside_dev() -> None:
    plain = {"openbao_addr": "http://bao:8200", "openbao_role_id": "r", "openbao_secret_id": "s"}
    for environment in ("staging", "production"):
        with pytest.raises(ValidationError, match="https"):
            _settings(environment=environment, **plain)
    assert _settings(environment="test", **plain).openbao() is not None  # the dev server
    secure = _settings(
        environment="production",
        openbao_addr="https://bao:8200",
        openbao_role_id="r",
        openbao_secret_id="s",
    ).openbao()
    assert secure is not None
    assert secure.secret_id == "s"


def test_no_address_no_openbao() -> None:
    assert _settings(environment="production", openbao_addr="").openbao() is None


def _answering(replies: dict[tuple[str, str], tuple[int, list[str]]]) -> OpenBaoClient:
    """A client whose OpenBao answers `replies` ((method, path end) -> (status, errors))."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/approle/login"):
            return httpx.Response(200, json={"auth": {"client_token": "t", "lease_duration": 3600}})
        for (method, end), (status, errors) in replies.items():
            if request.method == method and request.url.path.endswith(end):
                return httpx.Response(status, json={"errors": errors} if errors else {})
        return httpx.Response(500)

    client = OpenBaoClient(OpenBaoConfig("https://bao:8200", "r", "s"))
    client._client = lambda: httpx.AsyncClient(  # type: ignore[method-assign]
        base_url="https://bao:8200/v1/", transport=httpx.MockTransport(handle)
    )
    return client


async def test_a_key_already_gone_is_destroyed_enough() -> None:
    gone = ["no existing key named u-1 could be found"]
    await _answering({("POST", "/keys/u-1/config"): (400, gone)}).destroy_key("u-1")
    await _answering(
        {
            ("POST", "/keys/u-1/config"): (204, []),
            ("DELETE", "/keys/u-1"): (400, ["could not delete key; not found"]),
        }
    ).destroy_key("u-1")


async def test_a_refused_deletion_never_passes_for_shredded() -> None:
    # the purge must not commit while the key lives (commit security review: fail closed)
    for replies in (
        {("POST", "/keys/u-1/config"): (400, ["invalid request"])},
        {
            ("POST", "/keys/u-1/config"): (204, []),
            ("DELETE", "/keys/u-1"): (400, ["deletion is not allowed for this key"]),
        },
    ):
        with pytest.raises(KeyServiceError):
            await _answering(replies).destroy_key("u-1")


def test_admin_networks_never_include_dockers_private_ranges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # any container that reaches the API past Caddy would pass as an admin (review S2 M2)
    for private in ('["172.30.0.0/24"]', '["192.168.1.0/24"]', '["10.0.0.0/8"]', '["0.0.0.0/0"]'):
        monkeypatch.setenv("ADMIN_ALLOWED_NETWORKS", private)
        with pytest.raises(ValidationError, match="ADMIN_ALLOWED_NETWORKS"):
            _settings(environment="production")
    monkeypatch.setenv("ADMIN_ALLOWED_NETWORKS", '["203.0.113.0/24"]')
    assert _settings(environment="production").admin_allowed_networks is not None
    monkeypatch.setenv("ADMIN_ALLOWED_NETWORKS", '["10.0.0.0/8"]')
    assert _settings(environment="dev").admin_allowed_networks is not None


def test_an_empty_variable_is_no_value(monkeypatch: pytest.MonkeyPatch) -> None:
    # compose's `${X:-}` must not hide a secret file or a default (review S2 L7)
    monkeypatch.setenv("JWT_KID", "")
    assert _settings(environment="production").jwt_kid == "k1"


async def test_setup_refuses_an_unaudited_openbao_and_still_revokes_the_admin_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from labtrack import openbao_setup  # noqa: PLC0415

    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path.endswith("/sys/audit"):
            return httpx.Response(200, json={"request_id": "x", "data": {}})
        return httpx.Response(204)

    real = httpx.AsyncClient

    def client(**kwargs: object) -> httpx.AsyncClient:
        return real(**kwargs, transport=httpx.MockTransport(handle))  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", client)
    with pytest.raises(RuntimeError, match="audit device"):
        await openbao_setup.bootstrap(
            "https://bao:8200", "root", require_audit=True, revoke_admin=True
        )
    # nothing was made on it, and the admin token went anyway (review S3 L4)
    assert calls == ["GET /v1/sys/audit", "POST /v1/auth/token/revoke-self"]
