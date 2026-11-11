"""Uploaded documents of a profile (Phase 3.1; docs/08 "Хариу оруулах", Q49).

POST takes the file itself (multipart: `file`, `client_id`): it is checked, sealed and stored
by the API, so the phone never learns a storage address. GET .../file returns the original,
decrypted, never cached. No route reveals the storage key or the file's hash.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from pydantic import BaseModel

from labtrack.api.deps import Claims, PatientReadDb, PatientWriteDb
from labtrack.api.errors import AppError, ErrorBody
from labtrack.api.ratelimit import per_user
from labtrack.config import get_settings
from labtrack.documents import service
from labtrack.documents.files import MAX_BYTES
from labtrack.storage import ObjectStore, get_store

router = APIRouter(prefix="/patients/{patient_id}/documents", tags=["documents"])

_ERRORS: dict[int | str, dict[str, object]] = {
    s: {"model": ErrorBody} for s in (401, 403, 404, 409, 413, 415, 422, 429, 503)
}
Store = Annotated[ObjectStore, Depends(get_store)]
_UPLOAD_LIMIT = Depends(per_user("upload", lambda: get_settings().rate_upload_per_minute))
# the app polls a new document's status
_READ_LIMIT = Depends(
    per_user("document_read", lambda: get_settings().rate_document_read_per_minute)
)
# each read unwraps a key and decrypts up to 20 MB
_FILE_LIMIT = Depends(
    per_user("document_file", lambda: get_settings().rate_document_file_per_minute)
)


class DocumentOut(BaseModel):
    id: UUID
    mime_type: str
    size_bytes: int
    page_count: int | None
    has_text_layer: bool | None
    status: str
    error_code: str | None
    created_at: datetime


def _out(document: service.Document) -> DocumentOut:
    return DocumentOut(**document.__dict__)


@router.post(
    "",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": DocumentOut}, **_ERRORS},
    dependencies=[_UPLOAD_LIMIT],
)
async def upload_document(  # noqa: PLR0917 - FastAPI parameters
    patient_id: UUID,
    db: PatientWriteDb,
    claims: Claims,
    store: Store,
    response: Response,
    file: Annotated[UploadFile, File()],
    client_id: Annotated[UUID, Form()],
) -> DocumentOut:
    # the body was already received (Caddy and the middleware in main.py cap its size);
    # still read at most one byte past the limit
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise AppError(413, "document.too_large")
    uploaded = await service.upload(db, store, patient_id, client_id, data)
    if not uploaded.created:
        response.status_code = status.HTTP_200_OK  # a retry or the same file: the stored one
    else:
        await service.enqueue(uploaded.document.id, claims.user_id)
    return _out(uploaded.document)


@router.get("", response_model=list[DocumentOut], responses=_ERRORS)
async def list_documents(patient_id: UUID, db: PatientReadDb) -> list[DocumentOut]:
    return [_out(d) for d in await service.list_documents(db, patient_id)]


@router.get(
    "/{document_id}", response_model=DocumentOut, responses=_ERRORS, dependencies=[_READ_LIMIT]
)
async def get_document(
    patient_id: UUID, document_id: UUID, db: PatientReadDb, claims: Claims
) -> DocumentOut:
    document = await service.get(db, patient_id, document_id)
    await service.enqueue_if_stuck(db, patient_id, document, claims.user_id)
    return _out(document)


@router.get(
    "/{document_id}/file",
    dependencies=[_FILE_LIMIT],
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}, "image/jpeg": {}, "image/png": {}}},
        **_ERRORS,
    },
)
async def get_document_file(
    patient_id: UUID, document_id: UUID, db: PatientReadDb, store: Store
) -> Response:
    data, mime = await service.read_file(db, store, patient_id, document_id)
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
            # an uploaded PDF never runs anything in the app's origin (security review 3.2)
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cross-Origin-Resource-Policy": "same-origin",
        },
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
async def delete_document(patient_id: UUID, document_id: UUID, db: PatientWriteDb) -> Response:
    await service.delete(db, patient_id, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
