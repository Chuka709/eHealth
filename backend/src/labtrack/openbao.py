"""OpenBao client for the transit engine (docs/04 §1: production key management).

Keys never leave OpenBao: the app sends a data key to wrap (encrypt) or unwrap (decrypt), with
the field's AAD as `associated_data` (checked by OpenBao 2.7: a different AAD, or none, fails).
Logs in with AppRole; the token is kept in memory until shortly before it expires and fetched
again on a 403.

A new HTTP client per call: Celery runs each task in its own event loop (`asyncio.run`), and an
httpx client is bound to the loop it was made in. Nothing here is logged - not the key names
(they carry user ids), not OpenBao's error text.
"""

import base64
import time
from dataclasses import dataclass, field
from typing import Final

import httpx

from labtrack.core.envelope import EnvelopeError

_TIMEOUT: Final = httpx.Timeout(5.0)
# fetch a new token this long before the old one expires
_TOKEN_MARGIN_S: Final = 60.0


class KeyServiceError(RuntimeError):
    """OpenBao could not be reached or refused the app: never "this value is unreadable"."""


class KeyNotFoundError(EnvelopeError):
    """OpenBao has no key of that name: a user's key means a purged account (shredded); the
    service KEK means a misconfigured or emptied OpenBao (TransitKeyProvider: an outage)."""


@dataclass(frozen=True)
class OpenBaoConfig:
    addr: str
    role_id: str = field(repr=False)
    secret_id: str = field(repr=False)  # never in a traceback or a log
    mount: str = "transit"
    ca_cert: str | None = None

    def __post_init__(self) -> None:
        if not self.addr.startswith(("https://", "http://")):
            raise ValueError("OpenBao address must be http(s)")


@dataclass
class OpenBaoClient:
    config: OpenBaoConfig
    _token: str | None = field(default=None, repr=False)
    _expires: float = 0.0

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=f"{self.config.addr.rstrip('/')}/v1/",
            timeout=_TIMEOUT,
            verify=self.config.ca_cert or True,
            follow_redirects=False,
            trust_env=False,  # never through a proxy from the environment
        )

    async def _login(self, http: httpx.AsyncClient) -> str:
        try:
            r = await http.post(
                "auth/approle/login",
                json={"role_id": self.config.role_id, "secret_id": self.config.secret_id},
            )
        except httpx.HTTPError as exc:
            raise KeyServiceError("openbao unreachable") from exc
        if r.status_code != httpx.codes.OK:
            raise KeyServiceError("openbao login refused")
        try:
            auth = r.json()["auth"]
            token = str(auth["client_token"])
            lease = float(auth["lease_duration"])
        except (KeyError, TypeError, ValueError) as exc:
            raise KeyServiceError("openbao login answer") from exc
        self._token = token
        self._expires = time.monotonic() + lease - _TOKEN_MARGIN_S
        return token

    async def _call(
        self, method: str, path: str, body: dict[str, object] | None = None
    ) -> httpx.Response:
        async with self._client() as http:
            token = self._token
            if token is None or time.monotonic() >= self._expires:
                token = await self._login(http)
            for attempt in range(2):
                try:
                    r = await http.request(
                        method, path, json=body, headers={"X-Vault-Token": token}
                    )
                except httpx.HTTPError as exc:
                    raise KeyServiceError("openbao unreachable") from exc
                # a token revoked or expired early: log in once more
                if r.status_code == httpx.codes.FORBIDDEN and attempt == 0:
                    token = await self._login(http)
                    continue
                if (
                    r.status_code in {403, 429}
                    or r.status_code >= httpx.codes.INTERNAL_SERVER_ERROR
                ):
                    raise KeyServiceError(f"openbao {r.status_code}")
                return r
        raise KeyServiceError("openbao refused")  # pragma: no cover - the loop returns

    async def encrypt(self, key: str, plaintext: bytes, aad: bytes) -> bytes:
        r = await self._call(
            "POST",
            f"{self.config.mount}/encrypt/{key}",
            {"plaintext": _b64(plaintext), "associated_data": _b64(aad)},
        )
        if r.status_code != httpx.codes.OK:
            # with the app's policy a missing key is not created on encrypt: it is an error
            raise KeyServiceError(f"openbao encrypt {r.status_code}")
        return str(r.json()["data"]["ciphertext"]).encode("ascii")

    async def decrypt(self, key: str, ciphertext: bytes, aad: bytes) -> bytes:
        try:
            text = ciphertext.decode("ascii")
        except UnicodeDecodeError as exc:
            raise EnvelopeError from exc
        r = await self._call(
            "POST",
            f"{self.config.mount}/decrypt/{key}",
            {"ciphertext": text, "associated_data": _b64(aad)},
        )
        if r.status_code == httpx.codes.BAD_REQUEST:
            # the key is gone (OpenBao 2.7: "encryption key not found"), or a wrong AAD or a
            # damaged ciphertext ("message authentication failed", "invalid ciphertext")
            if "not found" in _errors(r):
                raise KeyNotFoundError
            raise EnvelopeError
        if r.status_code != httpx.codes.OK:
            raise KeyServiceError(f"openbao decrypt {r.status_code}")
        try:
            return base64.b64decode(r.json()["data"]["plaintext"], validate=True)
        except (KeyError, ValueError) as exc:
            raise EnvelopeError from exc

    async def create_key(self, key: str) -> None:
        """A new AES-256-GCM key, not exportable (an existing key is left as it is)."""
        r = await self._call(
            # `type` is the one parameter the api policy allows: never exportable (the default)
            "POST",
            f"{self.config.mount}/keys/{key}",
            {"type": "aes256-gcm96"},
        )
        if r.status_code not in {200, 204}:
            raise KeyServiceError(f"openbao create {r.status_code}")

    async def destroy_key(self, key: str) -> None:
        """Deletes a key for good (crypto-shredding); a key already gone is fine.

        OpenBao 2.7 answers both calls for a missing key with 400 ("no existing key", "not
        found"); the maintenance policy allows nothing else that could give a 400 here."""
        r = await self._call(
            "POST", f"{self.config.mount}/keys/{key}/config", {"deletion_allowed": True}
        )
        if r.status_code == httpx.codes.BAD_REQUEST:
            return  # already gone (an earlier run destroyed it, then its transaction failed)
        if r.status_code not in {200, 204}:
            raise KeyServiceError(f"openbao destroy {r.status_code}")
        r = await self._call("DELETE", f"{self.config.mount}/keys/{key}")
        if r.status_code not in {200, 204, 400}:
            raise KeyServiceError(f"openbao destroy {r.status_code}")


def _errors(r: httpx.Response) -> str:
    try:
        return " ".join(str(e) for e in r.json().get("errors", [])).lower()
    except ValueError:
        return ""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
