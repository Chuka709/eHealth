"""OpenBao as the production key provider (docs/04 §1; SERVER_INSTALL_PLAN S1), against the
dev server: the round trip, AAD binding, rotation, and what each AppRole may not do."""

import base64
from uuid import uuid4

import httpx
import pytest

from labtrack.core.envelope import EnvelopeError, field_aad, parse
from labtrack.keys import (
    SERVICE_KEK,
    SERVICE_KEK_ID,
    TransitKeyProvider,
    decrypt_bytes,
    decrypt_field,
    encrypt_bytes,
    encrypt_field,
)
from labtrack.openbao import KeyServiceError, OpenBaoClient, OpenBaoConfig
from labtrack.openbao_setup import bootstrap
from labtrack.user_keys import kek_id_for, openbao_key_name
from tests.openbao_support import ADDR, ROOT, key_info, needs_openbao, role, root, setup_again

pytestmark = needs_openbao

AAD = field_aad("users", "contact_phone_enc", uuid4())


def _kek(client: OpenBaoClient) -> TransitKeyProvider:
    return TransitKeyProvider(client, SERVICE_KEK, SERVICE_KEK_ID)


async def test_a_field_round_trips_and_is_bound_to_its_row() -> None:
    kek = _kek(await role("api"))
    blob = await encrypt_field(kek, "99112233", AAD)
    assert parse(blob).kek_id == SERVICE_KEK_ID
    assert b"99112233" not in blob
    assert await decrypt_field(kek, blob, AAD) == "99112233"
    # moved to another row (another AAD), the value does not open
    with pytest.raises(EnvelopeError):
        await decrypt_field(kek, blob, field_aad("users", "contact_phone_enc", uuid4()))


async def test_a_damaged_or_foreign_wrapped_key_is_unreadable_not_an_outage() -> None:
    kek = _kek(await role("api"))
    env = parse(await encrypt_field(kek, "x", AAD))
    for wrapped in (env.wrapped_dek[:-4] + b"AAAA", b"vault:v1:bm9pc2U=", b"\xff\xfe"):
        with pytest.raises(EnvelopeError):
            await kek.unwrap(SERVICE_KEK_ID, wrapped, AAD)
    with pytest.raises(EnvelopeError):  # a dev/test KEK id is never sent to OpenBao
        await kek.unwrap("dev1", env.wrapped_dek, AAD)


async def test_the_worker_reads_documents_and_seals_nothing() -> None:
    api, worker = _kek(await role("api")), _kek(await role("worker"))
    doc = field_aad("documents", "file", uuid4())
    sealed = await encrypt_bytes(api, b"%PDF-1.7 ...", doc)
    assert await decrypt_bytes(worker, sealed, doc) == b"%PDF-1.7 ..."
    with pytest.raises(KeyServiceError):
        await encrypt_bytes(worker, b"x", doc)


async def test_rotating_the_kek_keeps_old_values_readable() -> None:
    kek = _kek(await role("api"))
    before = await encrypt_field(kek, "old", AAD)
    r = await root("POST", f"transit/keys/{SERVICE_KEK}/rotate")
    assert r.status_code == httpx.codes.OK
    after = await encrypt_field(kek, "new", AAD)
    assert parse(after).kek_id == SERVICE_KEK_ID  # the version lives inside the ciphertext
    assert parse(before).wrapped_dek.split(b":")[1] != parse(after).wrapped_dek.split(b":")[1]
    assert await decrypt_field(kek, before, AAD) == "old"
    assert await decrypt_field(kek, after, AAD) == "new"


async def test_setup_again_changes_no_key_and_retires_old_secrets() -> None:
    blob = await encrypt_field(_kek(await role("api")), "kept", AAD)
    stale = await setup_again()
    assert await decrypt_field(_kek(await role("api")), blob, AAD) == "kept"
    # the earlier secret ids no longer log in (security review S1 M3)
    for config in stale.values():
        with pytest.raises(KeyServiceError, match="login"):
            await OpenBaoClient(config).encrypt(SERVICE_KEK, b"k" * 32, b"aad")
    info = await key_info(SERVICE_KEK)
    assert info is not None
    assert info["exportable"] is False
    assert info["deletion_allowed"] is False


async def test_the_api_cannot_take_or_weaken_a_key() -> None:
    api = await role("api")
    user = uuid4()
    name = openbao_key_name(user)
    await api.create_key(name)
    calls: list[tuple[str, str, dict[str, object] | None]] = [
        ("GET", f"transit/export/encryption-key/{name}", None),
        ("GET", f"transit/export/encryption-key/{SERVICE_KEK}", None),
        ("GET", f"transit/backup/{name}", None),
        ("GET", f"transit/keys/{name}", None),
        ("POST", f"transit/keys/{name}/config", {"exportable": True}),
        ("POST", f"transit/keys/{name}/config", {"deletion_allowed": True}),
        ("POST", f"transit/keys/{name}/config", {"min_decryption_version": 2}),
        ("POST", f"transit/keys/{name}/trim", {"min_available_version": 1}),
        ("DELETE", f"transit/keys/{name}", None),
        ("POST", f"transit/keys/{SERVICE_KEK}/config", {"deletion_allowed": True}),
        ("POST", f"transit/keys/{SERVICE_KEK}/rotate", None),
        ("POST", f"transit/keys/u-{uuid4().hex}", {"type": "aes256-gcm96", "exportable": True}),
        ("POST", "transit/keys/other", {"type": "aes256-gcm96"}),
        ("POST", f"transit/datakey/plaintext/{SERVICE_KEK}", None),
        ("LIST", "transit/keys", None),
        ("GET", "sys/policies/acl/labtrack-api", None),
    ]
    for method, path, body in calls:
        with pytest.raises(KeyServiceError, match="403"):
            await api._call(method, path, body)
    info = await key_info(name)
    assert info is not None
    assert info["exportable"] is False
    assert info["deletion_allowed"] is False
    assert await key_info("other") is None


async def test_a_missing_service_kek_is_an_outage_not_unreadable() -> None:
    # a wrong mount or key name, or an emptied OpenBao, must not turn every document
    # "unreadable" (security review S1 M1); a missing user key is a purged account
    api = await role("api")
    blob = await encrypt_bytes(_kek(api), b"x", AAD)
    missing = openbao_key_name(uuid4())  # a name the api may use, with no key behind it
    lost = TransitKeyProvider(api, missing, SERVICE_KEK_ID, missing_is_outage=True)
    with pytest.raises(KeyServiceError):
        await decrypt_bytes(lost, blob, AAD)
    shredded = TransitKeyProvider(api, missing, SERVICE_KEK_ID)
    with pytest.raises(EnvelopeError):
        await decrypt_bytes(shredded, blob, AAD)


async def test_setup_refuses_plain_http() -> None:
    with pytest.raises(ValueError, match="https"):
        await bootstrap(ADDR, ROOT)


async def test_encrypting_under_a_missing_user_key_never_creates_it() -> None:
    api = await role("api")
    name = openbao_key_name(uuid4())
    with pytest.raises(KeyServiceError):
        await api.encrypt(name, b"k" * 32, b"aad")
    assert await key_info(name) is None


async def test_maintenance_destroys_user_keys_and_nothing_else() -> None:
    api, maint = await role("api"), await role("maint")
    user = uuid4()
    name = openbao_key_name(user)
    await api.create_key(name)
    mine = TransitKeyProvider(api, name, kek_id_for(user))
    blob = await encrypt_field(mine, "99112233", AAD)
    for method, path in (
        ("POST", f"transit/encrypt/{name}"),
        ("POST", f"transit/decrypt/{SERVICE_KEK}"),
        ("POST", f"transit/keys/{SERVICE_KEK}/config"),
        ("DELETE", f"transit/keys/{SERVICE_KEK}"),
    ):
        with pytest.raises(KeyServiceError, match="403"):
            await maint._call(method, path, {"deletion_allowed": True})
    # It can make a key (OpenBao: creating and configuring are both `update` on `u-*`, and a
    # glob cannot stop mid-path) - one it cannot use, read or export: accepted (review S1 L8).
    other = openbao_key_name(uuid4())
    await maint._call("POST", f"transit/keys/{other}", {"deletion_allowed": True})
    for method, path in (
        ("POST", f"transit/encrypt/{other}"),
        ("GET", f"transit/keys/{other}"),
        ("GET", f"transit/export/encryption-key/{other}"),
    ):
        with pytest.raises(KeyServiceError, match="403"):
            await maint._call(method, path, {"plaintext": "QQ=="})
    made = await key_info(other)
    assert made is not None
    assert made["exportable"] is False
    await maint.destroy_key(name)
    await maint.destroy_key(name)  # already gone: fine (a purge batch that is run again)
    assert await key_info(name) is None
    with pytest.raises(EnvelopeError):  # shredded: unreadable, not an outage
        await decrypt_field(mine, blob, AAD)
    assert await key_info(SERVICE_KEK) is not None


async def test_a_revoked_token_is_replaced_by_logging_in_again() -> None:
    api = await role("api")
    kek = _kek(api)
    blob = await encrypt_field(kek, "x", AAD)
    assert api._token is not None
    r = await root("POST", "auth/token/revoke", {"token": api._token})
    assert r.status_code == httpx.codes.NO_CONTENT
    assert await decrypt_field(kek, blob, AAD) == "x"


async def test_wrong_credentials_or_no_server_are_an_outage() -> None:
    bad = OpenBaoClient(OpenBaoConfig(ADDR, "nobody", "nothing"))
    with pytest.raises(KeyServiceError):
        await bad.encrypt(SERVICE_KEK, b"k" * 32, b"aad")
    gone = OpenBaoClient(OpenBaoConfig("http://127.0.0.1:9", "r", "s"))
    with pytest.raises(KeyServiceError):
        await gone.decrypt(SERVICE_KEK, b"vault:v1:" + base64.b64encode(b"x"), b"aad")
