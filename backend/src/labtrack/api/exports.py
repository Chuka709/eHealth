"""The doctor's summary PDF and the owner's data export (Phase 7.5; docs/06 §8; H38).

- GET …/summary.pdf: anyone who reads the profile (the owner shows it to a doctor; a doctor
  with access may print it). Read under the row policies; A4, Noto Sans;
- GET …/export.json and …/export.fhir.json: the profile's owner only - their data to take
  elsewhere (FHIR R4 Bundle). Every answer: no-store, a file name without anyone's name.
"""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack import export, summary
from labtrack.api.caregivers import _owner_only
from labtrack.api.deps import PatientReadDb
from labtrack.api.errors import AppError, ErrorBody
from labtrack.api.ratelimit import per_user
from labtrack.config import get_settings
from labtrack.db.sql import bound_text

router = APIRouter(prefix="/patients/{patient_id}", tags=["exports"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorBody},
    403: {"model": ErrorBody},
    404: {"model": ErrorBody},
    422: {"model": ErrorBody},
    429: {"model": ErrorBody},
}
_LIMIT = [Depends(per_user("export", lambda: get_settings().rate_export_per_minute))]


async def _audit(db: AsyncSession, action: str, patient_id: UUID) -> None:
    """Who took the profile out, as which file (ids only)."""
    await db.execute(
        bound_text("select audit_write(:a, 'patient', :id, :p, null)"),
        {"a": action, "id": str(patient_id), "p": patient_id},
    )


async def _gather(db: AsyncSession, patient_id: UUID) -> dict[str, Any]:
    try:
        return await export.gather(db, patient_id)
    except export.ExportTooLargeError:
        raise AppError(422, "export.too_large") from None


def _file(body: bytes, media: str, name: str) -> Response:
    return Response(
        content=body,
        media_type=media,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/summary.pdf",
    responses={**_ERRORS, 200: {"content": {"application/pdf": {}}}},
    response_class=Response,
    dependencies=_LIMIT,
)
async def summary_pdf(
    patient_id: UUID,
    db: PatientReadDb,
    months: Annotated[int, Query(ge=1, le=24)] = 6,
    lang: Literal["mn", "en"] = "mn",
) -> Response:
    pdf = await summary.summary_pdf(db, patient_id, months, lang)
    await _audit(db, "summary.pdf", patient_id)
    return _file(pdf, "application/pdf", "labtrack-summary.pdf")


@router.get(
    "/export.json",
    responses={**_ERRORS, 200: {"content": {"application/json": {}}}},
    response_class=Response,
    dependencies=_LIMIT,
)
async def export_json(patient_id: UUID, db: PatientReadDb) -> Response:
    await _owner_only(db, patient_id)
    data = await _gather(db, patient_id)
    await _audit(db, "export.json", patient_id)
    return _file(export.to_json(data), "application/json", "labtrack-export.json")


@router.get(
    "/export.fhir.json",
    responses={**_ERRORS, 200: {"content": {"application/fhir+json": {}}}},
    response_class=Response,
    dependencies=_LIMIT,
)
async def export_fhir(patient_id: UUID, db: PatientReadDb) -> Response:
    await _owner_only(db, patient_id)
    data = await _gather(db, patient_id)
    await _audit(db, "export.fhir", patient_id)
    return _file(export.to_fhir(data), "application/fhir+json", "labtrack-fhir.json")
