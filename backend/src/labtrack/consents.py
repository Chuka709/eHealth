"""Consents (docs/04 §5; Q9): which ones exist, their current text version, which are needed.

Rows are append-only (consents table, RLS): giving, re-giving after a new version and
withdrawing all add a row; the latest row per kind is the state. A consent counts only for the
version currently shown - a new text version asks everyone again.

Texts await legal review (OPEN_QUESTIONS Q12): versions are marked `draft-`, and a production
service refuses to start while any version is still a draft.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.db.sql import bound_text

Kind = Literal["terms", "privacy", "sensitive_data", "ai_processing", "cross_border"]

# Text version shown to the user; bump when the text changes (mn.json/en.json keys follow it).
VERSIONS: Final[dict[Kind, str]] = {
    "terms": "draft-2026-10",
    "privacy": "draft-2026-10",
    "sensitive_data": "draft-2026-10",
    "ai_processing": "draft-2026-10",
    "cross_border": "draft-2026-10",
}
# Without these the app cannot be used (health data cannot be processed at all).
REQUIRED: Final[frozenset[Kind]] = frozenset({"terms", "privacy", "sensitive_data"})
# AI extraction sends documents to the Claude API abroad: both, or results are entered by hand.
AI_EXTRACTION: Final[frozenset[Kind]] = frozenset({"ai_processing", "cross_border"})


def assert_releasable(environment: str) -> None:
    if environment == "production" and any(v.startswith("draft-") for v in VERSIONS.values()):
        raise RuntimeError("consent texts are drafts (OPEN_QUESTIONS Q12): not for production")


@dataclass(frozen=True)
class ConsentState:
    kind: Kind
    current_version: str
    granted: bool  # granted for the current version
    granted_version: str | None  # version of the latest row, if any
    at: datetime | None
    required: bool


async def states(db: AsyncSession, patient_id: object = None) -> list[ConsentState]:
    """Latest row per kind for the user (or for a minor's profile they own)."""
    rows = await db.execute(
        bound_text(
            "select distinct on (kind) kind, version, granted, created_at from consents"
            " where patient_id is not distinct from :p order by kind, created_at desc, id desc"
        ),
        {"p": patient_id},
    )
    latest = {r.kind: r for r in rows}
    result = []
    for kind, version in VERSIONS.items():
        row = latest.get(kind)
        result.append(
            ConsentState(
                kind=kind,
                current_version=version,
                granted=bool(row and row.granted and row.version == version),
                granted_version=row.version if row else None,
                at=row.created_at if row else None,
                required=kind in REQUIRED,
            )
        )
    return result


async def missing(db: AsyncSession, needed: frozenset[Kind]) -> set[Kind]:
    return {s.kind for s in await states(db) if s.kind in needed and not s.granted}


def require(needed: frozenset[Kind]) -> Callable[[AsyncSession], Awaitable[None]]:
    """For PHI routes (Phase 2+): refuse until the user holds `needed` for the current text."""
    from labtrack.api.errors import AppError  # noqa: PLC0415 - api depends on this module

    async def check(db: AsyncSession) -> None:
        if await missing(db, needed):
            raise AppError(403, "consent.required")

    return check
