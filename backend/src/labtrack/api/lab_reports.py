"""Review of a draft lab report by the profile's writers (Phase 5.3; docs/06 §4, docs/08).

Every change is recomputed on the server (rule 6) and answered with the whole report as it
now is, so the app shows only what the server computed. Confirming needs every issue looked
at (409 `review.open_issues` otherwise); a confirmed or rejected report is not edited again.
"""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from labtrack.api.deps import PatientReadDb, PatientWriteDb
from labtrack.api.documents import LabReportOut, report_out
from labtrack.api.errors import AppError, ErrorBody
from labtrack.api.ratelimit import per_user
from labtrack.config import get_settings
from labtrack.documents import reports, review

router = APIRouter(prefix="/patients/{patient_id}/reports", tags=["lab-reports"])

_ERRORS: dict[int | str, dict[str, object]] = {
    s: {"model": ErrorBody} for s in (401, 403, 404, 409, 422, 429)
}
_READ_LIMIT = Depends(
    per_user("document_read", lambda: get_settings().rate_document_read_per_minute)
)
_WRITE_LIMIT = Depends(per_user("lab_review", lambda: get_settings().rate_lab_review_per_minute))
Text = Annotated[str, Field(max_length=200)]
Short = Annotated[str, Field(max_length=50)]
Long = Annotated[str, Field(max_length=300)]
Issue = Annotated[str, Field(pattern=r"^[a-z_]{1,40}$")]
Cleared = Literal["raw_unit", "ref_text", "critical_text"]


class ResultPatch(BaseModel):
    """Only the fields sent change; `clear` empties a field. `acknowledge`: issues the person
    looked at and keeps as they are - sent alone or with a test pick, never with new text."""

    raw_value: Text | None = Field(default=None, min_length=1)
    raw_unit: Short | None = None
    ref_text: Long | None = None
    critical_text: Long | None = None
    test_code: Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,32}$")] | None = None
    acknowledge: list[Issue] = Field(default_factory=list, max_length=30)
    clear: list[Cleared] = Field(default_factory=list, max_length=3)


class ResultNew(BaseModel):
    raw_name: Text = Field(min_length=1)
    raw_value: Text = Field(min_length=1)
    raw_unit: Short | None = None
    ref_text: Long | None = None
    critical_text: Long | None = None
    test_code: Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,32}$")] | None = None


class RejectBody(BaseModel):
    """`critical_seen`: the person saw that the draft may hold a critical value (H5)."""

    critical_seen: bool = False


class ReportPatch(BaseModel):
    lab_name: Text | None = None
    collected_at: datetime | None = None
    collected_precision: Literal["day", "minute"] | None = None
    acknowledge: list[Issue] = Field(default_factory=list, max_length=10)


async def _out(db: PatientReadDb, patient_id: UUID, report_id: UUID) -> LabReportOut:
    found = await reports.for_report(db, patient_id, report_id)
    if found is None:
        raise AppError(404, "review.not_found")
    return report_out(found)


@router.get(
    "/{report_id}", response_model=LabReportOut, responses=_ERRORS, dependencies=[_READ_LIMIT]
)
async def get_report(patient_id: UUID, report_id: UUID, db: PatientReadDb) -> LabReportOut:
    """A draft for the profile's writers, a confirmed report for its readers too (RLS)."""
    return await _out(db, patient_id, report_id)


@router.patch(
    "/{report_id}", response_model=LabReportOut, responses=_ERRORS, dependencies=[_WRITE_LIMIT]
)
async def edit_report(
    patient_id: UUID, report_id: UUID, body: ReportPatch, db: PatientWriteDb
) -> LabReportOut:
    edit = review.ReportEdit(
        lab_name=body.lab_name,
        collected_at=body.collected_at,
        collected_precision=body.collected_precision,
        acknowledge=tuple(body.acknowledge),
    )
    await review.edit_report(db, patient_id, report_id, edit)
    return await _out(db, patient_id, report_id)


@router.patch(
    "/{report_id}/results/{result_id}",
    response_model=LabReportOut,
    responses=_ERRORS,
    dependencies=[_WRITE_LIMIT],
)
async def edit_result(
    patient_id: UUID, report_id: UUID, result_id: UUID, body: ResultPatch, db: PatientWriteDb
) -> LabReportOut:
    edit = review.RowEdit(
        raw_value=body.raw_value,
        raw_unit=body.raw_unit,
        ref_text=body.ref_text,
        critical_text=body.critical_text,
        test_code=body.test_code,
        acknowledge=tuple(body.acknowledge),
        clear=frozenset(body.clear),
    )
    await review.edit_result(db, patient_id, report_id, result_id, edit)
    return await _out(db, patient_id, report_id)


@router.post(
    "/{report_id}/results",
    response_model=LabReportOut,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    dependencies=[_WRITE_LIMIT],
)
async def add_result(
    patient_id: UUID, report_id: UUID, body: ResultNew, db: PatientWriteDb
) -> LabReportOut:
    edit = review.RowEdit(
        raw_value=body.raw_value,
        raw_unit=body.raw_unit,
        ref_text=body.ref_text,
        critical_text=body.critical_text,
        test_code=body.test_code,
    )
    await review.add_result(
        db, patient_id, report_id, new_id=uuid4(), raw_name=body.raw_name, edit=edit
    )
    return await _out(db, patient_id, report_id)


@router.delete(
    "/{report_id}/results/{result_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ERRORS,
    dependencies=[_WRITE_LIMIT],
)
async def delete_result(
    patient_id: UUID,
    report_id: UUID,
    result_id: UUID,
    db: PatientWriteDb,
    critical_seen: bool = False,
) -> Response:
    """A row that may be critical goes only with `critical_seen=true` (H5)."""
    await review.delete_result(db, patient_id, report_id, result_id, critical_seen=critical_seen)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{report_id}/confirm",
    response_model=LabReportOut,
    responses=_ERRORS,
    dependencies=[_WRITE_LIMIT],
)
async def confirm_report(patient_id: UUID, report_id: UUID, db: PatientWriteDb) -> LabReportOut:
    await review.confirm(db, patient_id, report_id)
    return await _out(db, patient_id, report_id)


@router.post(
    "/{report_id}/reject",
    response_model=LabReportOut,
    responses=_ERRORS,
    dependencies=[_WRITE_LIMIT],
)
async def reject_report(
    patient_id: UUID, report_id: UUID, db: PatientWriteDb, body: RejectBody | None = None
) -> LabReportOut:
    """A draft that may hold a critical value is rejected only with `critical_seen` (H5)."""
    seen = body.critical_seen if body else False
    await review.reject(db, patient_id, report_id, critical_seen=seen)
    return await _out(db, patient_id, report_id)
