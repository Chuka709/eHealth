import os

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from labtrack.core.envelope import EnvelopeError, field_aad, parse
from labtrack.keys import LocalKeyProvider, decrypt_field, encrypt_field

KEK = os.urandom(32)
PROVIDER = LocalKeyProvider({"k1": KEK}, "k1")
AAD = field_aad("users", "contact_phone_enc", "0b7f3c9a-1111-4a4a-8888-000000000001")


@settings(deadline=None)  # AES-GCM + key wrap; slow first call on Windows
@given(st.text(max_size=500))
async def test_round_trip(plaintext: str) -> None:
    blob = await encrypt_field(PROVIDER, plaintext, AAD)
    assert await decrypt_field(PROVIDER, blob, AAD) == plaintext


async def test_ciphertext_is_randomised_and_hides_plaintext() -> None:
    a = await encrypt_field(PROVIDER, "99112233", AAD)
    b = await encrypt_field(PROVIDER, "99112233", AAD)
    assert a != b
    assert b"99112233" not in a


@pytest.mark.parametrize(
    "other",
    [
        field_aad("users", "contact_phone_enc", "0b7f3c9a-1111-4a4a-8888-000000000002"),
        field_aad("users", "totp_secret_enc", "0b7f3c9a-1111-4a4a-8888-000000000001"),
        field_aad("patients", "contact_phone_enc", "0b7f3c9a-1111-4a4a-8888-000000000001"),
    ],
)
async def test_value_copied_to_another_row_column_or_table_does_not_decrypt(other: bytes) -> None:
    blob = await encrypt_field(PROVIDER, "99112233", AAD)
    with pytest.raises(EnvelopeError):
        await decrypt_field(PROVIDER, blob, other)


async def test_wrong_or_unknown_kek_fails() -> None:
    blob = await encrypt_field(PROVIDER, "secret", AAD)
    with pytest.raises(EnvelopeError):
        await decrypt_field(LocalKeyProvider({"k1": os.urandom(32)}, "k1"), blob, AAD)
    with pytest.raises(EnvelopeError):
        await decrypt_field(LocalKeyProvider({"k2": KEK}, "k2"), blob, AAD)


async def test_rotation_keeps_old_values_readable() -> None:
    old = await encrypt_field(PROVIDER, "before", AAD)
    rotated = LocalKeyProvider({"k1": KEK, "k2": os.urandom(32)}, "k2")
    new = await encrypt_field(rotated, "after", AAD)
    assert parse(new).kek_id == "k2"
    assert await decrypt_field(rotated, old, AAD) == "before"
    assert await decrypt_field(rotated, new, AAD) == "after"


@settings(deadline=None)
@given(st.binary(max_size=300), st.integers(min_value=0))
async def test_any_tampering_is_rejected(noise: bytes, position: int) -> None:
    blob = bytearray(await encrypt_field(PROVIDER, "secret", AAD))
    if noise:
        i = position % len(blob)
        blob[i] ^= noise[0] or 1
    else:
        del blob[position % len(blob) :]
    with pytest.raises(EnvelopeError):
        await decrypt_field(PROVIDER, bytes(blob), AAD)


@given(st.binary(max_size=200))
async def test_garbage_never_decrypts(blob: bytes) -> None:
    with pytest.raises(EnvelopeError):
        await decrypt_field(PROVIDER, blob, AAD)


@pytest.mark.parametrize(
    ("table", "column", "row"),
    [("Users", "x", "1"), ("users", "a:b", "1"), ("users", "x", ""), ("users", "x", "1:2")],
)
def test_aad_parts_are_strict(table: str, column: str, row: str) -> None:
    with pytest.raises(ValueError, match="must"):
        field_aad(table, column, row)


def test_provider_rejects_bad_kek_sets() -> None:
    with pytest.raises(ValueError, match="KEK"):
        LocalKeyProvider({"k1": b"short"}, "k1")
    with pytest.raises(ValueError, match="KEK"):
        LocalKeyProvider({"k1": KEK}, "k2")
