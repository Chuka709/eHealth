"""OpenBao settings (SERVER_INSTALL_PLAN S1): complete or absent, https outside dev/test, and the
secret id in no repr (a traceback, a log line)."""

import pytest
from pydantic import ValidationError

from labtrack.config import Settings
from labtrack.openbao import OpenBaoClient, OpenBaoConfig

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
