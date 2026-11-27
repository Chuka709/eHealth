"""The dev OpenBao server (compose `openbao`, test profile), set up once per run with the same
bootstrap production uses (labtrack.openbao_setup). Tests skip without OPENBAO_TEST_ADDR."""

import os
from typing import Any

import httpx
import pytest

from labtrack.openbao import OpenBaoClient, OpenBaoConfig
from labtrack.openbao_setup import bootstrap

ADDR = os.environ.get("OPENBAO_TEST_ADDR", "")
ROOT = os.environ.get("OPENBAO_TEST_ROOT_TOKEN", "")

needs_openbao = pytest.mark.skipif(not ADDR, reason="OPENBAO_TEST_ADDR is not set")

_configs: dict[str, OpenBaoConfig] = {}


async def role(name: str) -> OpenBaoClient:
    """A fresh client (no cached token) for the api, worker or maint AppRole."""
    if not _configs:
        for cred in await bootstrap(ADDR, ROOT, allow_http=True):
            _configs[cred.role] = OpenBaoConfig(ADDR, cred.role_id, cred.secret_id)
    return OpenBaoClient(_configs[name])


async def root(method: str, path: str, body: dict[str, object] | None = None) -> httpx.Response:
    async with httpx.AsyncClient(
        base_url=f"{ADDR}/v1/", headers={"X-Vault-Token": ROOT}, trust_env=False
    ) as http:
        return await http.request(method, path, json=body)


async def key_info(name: str) -> dict[str, Any] | None:
    r = await root("GET", f"transit/keys/{name}")
    return r.json()["data"] if r.status_code == httpx.codes.OK else None


async def setup_again() -> dict[str, OpenBaoConfig]:
    """Runs the bootstrap again (as an operator would); returns the configs it made stale."""
    await role("api")  # the first setup, if none ran yet
    old = dict(_configs)
    for cred in await bootstrap(ADDR, ROOT, allow_http=True):
        _configs[cred.role] = OpenBaoConfig(ADDR, cred.role_id, cred.secret_id)
    return old
