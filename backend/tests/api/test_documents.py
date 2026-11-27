"""Uploading documents over the API (Phase 3.1; Q49)."""

import io
from collections.abc import AsyncIterator
from uuid import uuid4

import pypdfium2 as pdfium
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import ClientFactory
from .test_patients import _signed_in
from .test_records import _audit, _grant, _profile

pytestmark = pytest.mark.db


@pytest.fixture
async def client(client_from: ClientFactory) -> AsyncIterator[AsyncClient]:
    async with client_from() as c:
        yield c


def _pdf(pages: int = 1) -> bytes:
    doc = pdfium.PdfDocument.new()
    for _ in range(pages):
        doc.new_page(595, 842)
    out = io.BytesIO()
    doc.save(out)
    doc.close()
    # every call a different file: a unique comment after the end marker
    return out.getvalue() + f"\n% {uuid4()}\n".encode()


async def _scanned(owner_engine: AsyncEngine, document_id: str, status: str = "queued") -> None:
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update documents set status = cast(:s as doc_status) where id = cast(:d as uuid)"
            ),
            {"s": status, "d": document_id},
        )


def _files(data: bytes, client_id: str | None = None) -> dict[str, object]:
    return {
        "files": {"file": ("scan.pdf", data, "application/pdf")},
        "data": {"client_id": client_id or str(uuid4())},
    }


async def test_upload_retry_same_file_read_and_delete(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    data = _pdf(2)
    client_id = str(uuid4())
    first = await client.post(f"{base}/documents", headers=h, **_files(data, client_id))  # type: ignore[arg-type]
    assert first.status_code == 201, first.text
    doc = first.json()
    assert (doc["mime_type"], doc["page_count"], doc["status"]) == (
        "application/pdf",
        2,
        "uploaded",
    )
    assert "storage_key" not in doc
    assert "sha256" not in doc
    # a retry from the offline queue, and the same file sent again: the stored document
    retry = await client.post(f"{base}/documents", headers=h, **_files(data, client_id))  # type: ignore[arg-type]
    again = await client.post(f"{base}/documents", headers=h, **_files(data))  # type: ignore[arg-type]
    assert (retry.status_code, again.status_code) == (200, 200)
    assert retry.json()["id"] == again.json()["id"] == doc["id"]
    listed = (await client.get(f"{base}/documents", headers=h)).json()
    assert [d["id"] for d in listed] == [doc["id"]]
    # not handed out before the virus scan
    early = await client.get(f"{base}/documents/{doc['id']}/file", headers=h)
    assert (early.status_code, early.json()["code"]) == (409, "document.not_ready")
    await _scanned(owner_engine, doc["id"])
    file = await client.get(f"{base}/documents/{doc['id']}/file", headers=h)
    assert file.status_code == 200
    assert file.content == data
    assert file.headers["cache-control"] == "no-store"
    assert file.headers["content-type"] == "application/pdf"
    gone = await client.delete(f"{base}/documents/{doc['id']}", headers=h)
    assert gone.status_code == 204
    assert (await client.get(f"{base}/documents/{doc['id']}", headers=h)).status_code == 404
    actions = [a for a, _ in await _audit(owner_engine, base) if a.startswith("document.")]
    assert actions == ["document.upload", "document.view", "document.delete"]


async def test_the_stored_object_is_sealed(client: AsyncClient, owner_engine: AsyncEngine) -> None:
    from labtrack.storage import get_store  # noqa: PLC0415

    _, h, base = await _profile(client, owner_engine)
    data = _pdf()
    doc = (await client.post(f"{base}/documents", headers=h, **_files(data))).json()  # type: ignore[arg-type]
    stored = await get_store().get(f"{base.rsplit('/', 1)[1]}/{doc['id']}/original")
    assert stored != data
    assert b"%PDF" not in stored


async def test_refused_files_store_nothing(client: AsyncClient, owner_engine: AsyncEngine) -> None:
    _, h, base = await _profile(client, owner_engine)
    text = await client.post(
        f"{base}/documents",
        headers=h,
        files={"file": ("scan.pdf", b"not a pdf at all", "application/pdf")},
        data={"client_id": str(uuid4())},
    )
    assert (text.status_code, text.json()["code"]) == (415, "document.unsupported_type")
    async with owner_engine.connect() as conn:
        count = (
            await conn.execute(
                bound_text("select count(*) from documents where patient_id = cast(:p as uuid)"),
                {"p": base.rsplit("/", 1)[1]},
            )
        ).scalar_one()
    assert count == 0


async def test_others_cannot_see_or_upload_and_readers_cannot_write(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    doc = (await client.post(f"{base}/documents", headers=h, **_files(_pdf()))).json()  # type: ignore[arg-type]
    stranger, hs = await _signed_in(client, owner_engine)
    for path in (f"{base}/documents", f"{base}/documents/{doc['id']}/file"):
        assert (await client.get(path, headers=hs)).status_code == 404
    assert (await client.post(f"{base}/documents", headers=hs, **_files(_pdf()))).status_code == 404  # type: ignore[arg-type]
    await _grant(owner_engine, base, stranger, "viewer")
    await _scanned(owner_engine, doc["id"])
    assert (await client.get(f"{base}/documents/{doc['id']}/file", headers=hs)).status_code == 200
    assert (await client.post(f"{base}/documents", headers=hs, **_files(_pdf()))).status_code == 403  # type: ignore[arg-type]
    assert (await client.delete(f"{base}/documents/{doc['id']}", headers=hs)).status_code == 403


async def test_a_document_of_another_profile_is_not_found(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    doc = (await client.post(f"{base}/documents", headers=h, **_files(_pdf()))).json()  # type: ignore[arg-type]
    _, h2, other = await _profile(client, owner_engine)
    for path in (f"{other}/documents/{doc['id']}", f"{other}/documents/{doc['id']}/file"):
        assert (await client.get(path, headers=h2)).status_code == 404
    assert (await client.delete(f"{other}/documents/{doc['id']}", headers=h2)).status_code == 404


async def test_a_storage_failure_keeps_no_row(
    client: AsyncClient, owner_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from labtrack.storage import S3ObjectStore, StorageError  # noqa: PLC0415

    async def broken(self: object, key: str, data: bytes) -> None:
        raise StorageError

    monkeypatch.setattr(S3ObjectStore, "put", broken)
    _, h, base = await _profile(client, owner_engine)
    r = await client.post(f"{base}/documents", headers=h, **_files(_pdf()))  # type: ignore[arg-type]
    assert (r.status_code, r.json()["code"]) == (503, "document.storage_unavailable")
    async with owner_engine.connect() as conn:
        count = (
            await conn.execute(
                bound_text("select count(*) from documents where patient_id = cast(:p as uuid)"),
                {"p": base.rsplit("/", 1)[1]},
            )
        ).scalar_one()
    assert count == 0


async def test_deleting_queues_the_object_for_removal(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    """The sealed object stays readable with the KEK: its key is queued in the same transaction
    (user delete and profile cascade alike) for the maintenance worker."""
    _, h, base = await _profile(client, owner_engine)
    patient = base.rsplit("/", 1)[1]
    first = (await client.post(f"{base}/documents", headers=h, **_files(_pdf()))).json()  # type: ignore[arg-type]
    second = (await client.post(f"{base}/documents", headers=h, **_files(_pdf()))).json()  # type: ignore[arg-type]
    assert (await client.delete(f"{base}/documents/{first['id']}", headers=h)).status_code == 204
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("delete from patients where id = cast(:p as uuid)"), {"p": patient}
        )
        queued = set(
            (
                await conn.execute(
                    bound_text(
                        "select storage_key from document_deletions where storage_key like :k"
                    ),
                    {"k": f"{patient}/%"},
                )
            ).scalars()
        )
    assert queued == {f"{patient}/{first['id']}/original", f"{patient}/{second['id']}/original"}


async def test_an_oversized_body_is_refused_before_parsing(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    _, h, base = await _profile(client, owner_engine)
    r = await client.post(
        f"{base}/documents",
        headers={
            **h,
            "content-length": str(30 * 1024 * 1024),
            "content-type": "multipart/form-data; boundary=x",
        },
        content=b"--x--",
    )
    assert (r.status_code, r.json()["code"]) == (413, "document.too_large")


@pytest.mark.parametrize("status", ["rejected", "failed"])
async def test_a_rejected_or_failed_file_is_never_handed_out(
    client: AsyncClient, owner_engine: AsyncEngine, status: str
) -> None:
    _, h, base = await _profile(client, owner_engine)
    doc = (await client.post(f"{base}/documents", headers=h, **_files(_pdf()))).json()  # type: ignore[arg-type]
    await _scanned(owner_engine, doc["id"], status)
    r = await client.get(f"{base}/documents/{doc['id']}/file", headers=h)
    assert (r.status_code, r.json()["code"]) == (409, "document.not_available")
