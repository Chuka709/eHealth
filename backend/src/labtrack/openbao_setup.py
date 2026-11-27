"""One-time OpenBao setup (docs/SERVER_INSTALL_PLAN.md §3): the transit engine, the service
KEK, one policy and AppRole per process. Idempotent - running it again changes nothing but the
policies (kept equal to these) and issues new secret ids.

Least privilege, as checked against OpenBao 2.7 (tests/openbao):
- api: encrypt/decrypt under the service KEK and the users' keys; create a user's key with
  `type` as its only allowed parameter (so never exportable, never re-configured). A user key
  can be rotated (adds a version; old values still decrypt) - nothing worse.
- worker: decrypt under the service KEK only (it reads uploaded documents, writes none).
- maint: destroy users' keys only (`deletion_allowed`, then delete) - it can read nothing. It
  can also make a `u-*` key (creating and configuring are one capability in OpenBao), never one
  it could use or export: accepted (security review S1 L8).
Nobody may export a key, back one up, read its config, or touch the service KEK's config.
`*` is a glob only at the end of an OpenBao path, so `u-*` covers `u-<id>/config` as well:
`allowed_parameters` is what keeps the api off it.

Runs with an admin token (the root token, only during setup, then revoked - `revoke_admin`);
the token, role ids and secret ids are never printed. Each run destroys the roles' earlier
secret ids, so only the ones just written work (security review S1 M3). Over https only, but
for the local dev server (`allow_http`).
"""

from dataclasses import dataclass
from typing import Any, Final

import httpx

from labtrack.keys import SERVICE_KEK

POLICIES: Final = {
    "labtrack-api": f"""
path "transit/encrypt/{SERVICE_KEK}" {{ capabilities = ["update"] }}
path "transit/decrypt/{SERVICE_KEK}" {{ capabilities = ["update"] }}
path "transit/encrypt/u-*" {{ capabilities = ["update"] }}
path "transit/decrypt/u-*" {{ capabilities = ["update"] }}
path "transit/keys/u-*" {{
  capabilities = ["update"]
  allowed_parameters = {{ "type" = ["aes256-gcm96"] }}
}}
""",
    "labtrack-worker": f"""
path "transit/decrypt/{SERVICE_KEK}" {{ capabilities = ["update"] }}
""",
    "labtrack-maint": """
path "transit/keys/u-*" {
  capabilities = ["update", "delete"]
  allowed_parameters = { "deletion_allowed" = [true] }
}
""",
}
# token lifetimes: short, renewed by logging in again (the app does, a minute before expiry)
_ROLE: Final = {"token_ttl": "1h", "token_max_ttl": "4h", "token_no_default_policy": True}


@dataclass(frozen=True)
class RoleCredentials:
    role: str
    role_id: str
    secret_id: str


async def bootstrap(
    addr: str,
    admin_token: str,
    *,
    ca_cert: str | None = None,
    bound_cidrs: list[str] | None = None,
    audit_file: str | None = None,
    allow_http: bool = False,
    revoke_admin: bool = False,
) -> list[RoleCredentials]:
    """Sets everything up; returns a fresh secret id for each role (api, worker, maint)."""
    if not addr.startswith("https://") and not allow_http:
        raise ValueError("OpenBao over https only (the admin token would cross in the clear)")
    async with httpx.AsyncClient(
        base_url=f"{addr.rstrip('/')}/v1/",
        headers={"X-Vault-Token": admin_token},
        timeout=httpx.Timeout(10.0),
        verify=ca_cert or True,
        trust_env=False,
    ) as http:

        async def call(
            method: str, path: str, body: dict[str, object] | None = None
        ) -> dict[str, Any]:
            r = await http.request(method, path, json=body)
            if r.status_code >= httpx.codes.BAD_REQUEST:
                # OpenBao's message names paths, never secrets
                raise RuntimeError(f"openbao {method} {path}: {r.status_code} {r.text[:200]}")
            data = r.json() if r.content else {}
            if not isinstance(data, dict):
                raise TypeError(f"openbao {method} {path}: unexpected answer")
            return data

        try:
            mounts = await call("GET", "sys/mounts")
            if "transit/" not in mounts.get("data", mounts):
                await call("POST", "sys/mounts/transit", {"type": "transit"})
            # an existing key is left exactly as it is
            await call("POST", f"transit/keys/{SERVICE_KEK}", {"type": "aes256-gcm96"})
            for name, policy in POLICIES.items():
                await call("PUT", f"sys/policies/acl/{name}", {"policy": policy})
            if audit_file:
                # who encrypted, decrypted or destroyed what, when (values HMAC'd by OpenBao)
                audits = await call("GET", "sys/audit")
                if "file/" not in audits.get("data", audits):
                    await call(
                        "PUT",
                        "sys/audit/file",
                        {"type": "file", "options": {"file_path": audit_file}},
                    )
            auths = await call("GET", "sys/auth")
            if "approle/" not in auths.get("data", auths):
                await call("POST", "sys/auth/approle", {"type": "approle"})
            out: list[RoleCredentials] = []
            for role in ("api", "worker", "maint"):
                body: dict[str, object] = {**_ROLE, "token_policies": [f"labtrack-{role}"]}
                if bound_cidrs:
                    body |= {"secret_id_bound_cidrs": bound_cidrs, "token_bound_cidrs": bound_cidrs}
                await call("POST", f"auth/approle/role/labtrack-{role}", body)
                role_id = await call("GET", f"auth/approle/role/labtrack-{role}/role-id")
                await _retire_secret_ids(http, role)
                secret = await call("POST", f"auth/approle/role/labtrack-{role}/secret-id")
                out.append(
                    RoleCredentials(
                        role, str(role_id["data"]["role_id"]), str(secret["data"]["secret_id"])
                    )
                )
        finally:
            # also when setup fails half-way: the root token must not outlive it (review S1)
            if revoke_admin:
                await call("POST", "auth/token/revoke-self")
        return out


async def _retire_secret_ids(http: httpx.AsyncClient, role: str) -> None:
    """Every earlier secret id of the role stops working (security review S1 M3)."""
    path = f"auth/approle/role/labtrack-{role}"
    listed = await http.request("LIST", f"{path}/secret-id")
    if listed.status_code == httpx.codes.NOT_FOUND:
        return  # none yet
    if listed.status_code != httpx.codes.OK:
        raise RuntimeError(f"openbao LIST secret-id: {listed.status_code}")
    for accessor in listed.json()["data"]["keys"]:
        r = await http.post(
            f"{path}/secret-id-accessor/destroy", json={"secret_id_accessor": accessor}
        )
        if r.status_code >= httpx.codes.BAD_REQUEST:
            raise RuntimeError(f"openbao destroy secret-id: {r.status_code}")
