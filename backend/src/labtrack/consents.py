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

Kind = Literal[
    "terms", "privacy", "sensitive_data", "ai_processing", "cross_border", "caregiver_sharing"
]

# Text version shown to the user; bump when the text changes (mn.json/en.json app.consent.*),
# then `just gen-client` so the app bundles the new version with the new text.
VERSIONS: Final[dict[Kind, str]] = {
    "terms": "draft-2026-10",
    "privacy": "draft-2026-10",
    "sensitive_data": "draft-2026-10",
    "ai_processing": "draft-2026-10",
    "cross_border": "draft-2026-10",
    # the user lets caregivers they invite see and keep their profiles (Phase 2.8d; Q42)
    "caregiver_sharing": "draft-2026-11",
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
            " where user_id = app_user_id() and patient_id is not distinct from :p"
            " order by kind, id desc"
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


async def missing(
    db: AsyncSession, needed: frozenset[Kind], patient_id: object = None
) -> set[Kind]:
    return {s.kind for s in await states(db, patient_id) if s.kind in needed and not s.granted}


def require(needed: frozenset[Kind]) -> Callable[[AsyncSession], Awaitable[None]]:
    """For PHI routes (Phase 2+): refuse until the user holds `needed` for the current text.

    The user's own consents only. Writing to a minor's profile (Phase 2) must check that
    profile's consents AND is_minor_patient() at that moment: at 18 the parent's consent
    stops counting.
    """
    from labtrack.api.errors import AppError  # noqa: PLC0415 - api depends on this module

    async def check(db: AsyncSession) -> None:
        if await missing(db, needed):
            raise AppError(403, "consent.required")

    return check


async def require_for_patient(db: AsyncSession, patient_id: object) -> None:
    """For a profile the user can already read (api.deps checks access first): a minor's
    profile also needs the consents its owner gave for it (Q9), checked now - at 18 (the
    Ulaanbaatar date) the parent's consent stops counting and the profile is no longer a
    minor's. The profile's consents are readable only by the user who gave them, so anyone else
    on a minor's profile it was shared with as a doctor or a viewer reads the owner's through
    `owner_profile_consents()` (0044, 7.6): open while the owner's consents are in force.
    """
    from labtrack.api.errors import AppError  # noqa: PLC0415 - api depends on this module

    minor = (
        await db.execute(bound_text("select is_minor_patient(:p)"), {"p": patient_id})
    ).scalar_one()
    if not minor:
        return
    owner = (await db.execute(bound_text("select is_owner(:p)"), {"p": patient_id})).scalar_one()
    if owner:
        if await missing(db, REQUIRED, patient_id):
            raise AppError(403, "consent.profile_required")
        return
    # a doctor or a viewer the owner shared it with (0040); a caregiver stays refused (0025: no
    # caregivers on a child's profile)
    level = (
        await db.execute(
            bound_text(
                "select level::text from patient_access where patient_id = :p"
                " and user_id = app_user_id() and revoked_at is null"
                " and (expires_at is null or expires_at > now())"
            ),
            {"p": patient_id},
        )
    ).scalar_one_or_none()
    if level not in ("doctor", "viewer"):
        raise AppError(403, "consent.profile_required")
    rows = await db.execute(
        bound_text("select * from owner_profile_consents(:p)"), {"p": patient_id}
    )
    given = {r.kind for r in rows if r.granted and r.version == VERSIONS.get(r.kind)}
    if not given >= REQUIRED:
        raise AppError(403, "consent.profile_required")
