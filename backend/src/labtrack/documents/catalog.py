"""The test catalog and a profile's earlier values, as `core` needs them (worker and review).

Read in the caller's own context: RLS gives the global synonyms and the caller's own learned
ones, and the profile's results as far as the caller may see them.
"""

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from labtrack.core.lab_drafts import Catalog, CatalogTest, DraftReport, Prior
from labtrack.core.ranges import Sex
from labtrack.db.sql import bound_text

Db = AsyncConnection | AsyncSession

_TESTS = bound_text(
    "select code, canonical_unit, physio_min, physio_max, delta_check_pct from test_catalog"
    " where is_active"
)
_FACTORS = bound_text(
    "select c.test_code, c.from_unit, c.factor from unit_conversions c"
    " join test_catalog t on t.code = c.test_code and t.canonical_unit = c.to_unit"
)
_SYNONYMS = bound_text("select synonym_norm, test_code, user_id from test_synonyms")
_UNITS = bound_text("select alias_norm, unit from unit_aliases")
# the profile's values of these tests in the catalog unit, confirmed or another draft still
# waiting (duplicate, delta checks); a value with a comparator is never compared; never the
# rows of this document or report themselves (a reading of it again, a review edit)
_PRIOR = bound_text(
    "select x.test_code, x.collected_at, x.value_canonical, r.status = 'confirmed' as confirmed"
    " from lab_results x"
    " join lab_reports r on r.id = x.report_id and r.status in ('confirmed', 'needs_review')"
    " where x.patient_id = :p and x.value_canonical is not null and x.collected_at is not null"
    " and x.comparator is null and x.test_code = any(cast(:codes as text[]))"
    " and r.document_id is distinct from :d and r.id is distinct from :r"
)
_SEX = bound_text("select sex::text from patients where id = :p")


async def load_catalog(db: Db) -> tuple[Catalog, dict[str, str]]:
    """(catalog, the caller's own learned synonyms)."""
    factors: dict[str, dict[str, Decimal]] = {}
    for r in (await db.execute(_FACTORS)).all():
        factors.setdefault(r.test_code, {})[r.from_unit] = r.factor
    tests = {
        r.code: CatalogTest(
            r.code,
            r.canonical_unit,
            r.physio_min,
            r.physio_max,
            factors=factors.get(r.code, {}),
            delta_check_pct=r.delta_check_pct,
        )
        for r in (await db.execute(_TESTS)).all()
    }
    synonyms: dict[str, str] = {}
    mine: dict[str, str] = {}
    for r in (await db.execute(_SYNONYMS)).all():
        (mine if r.user_id is not None else synonyms)[r.synonym_norm] = r.test_code
    units = {r.alias_norm: r.unit for r in (await db.execute(_UNITS)).all()}
    return Catalog(tests=tests, synonyms=synonyms, unit_aliases=units), mine


async def load_prior(
    db: Db,
    patient_id: UUID,
    reports: Sequence[DraftReport],
    *,
    document_id: UUID | None = None,
    report_id: UUID | None = None,
) -> list[Prior]:
    codes = sorted({x.test_code for r in reports for x in r.results if x.test_code})
    if not codes:
        return []
    params = {"p": patient_id, "d": document_id, "r": report_id, "codes": codes}
    rows = (await db.execute(_PRIOR, params)).all()
    return [Prior(r.test_code, r.collected_at, r.value_canonical, r.confirmed) for r in rows]


def as_sex(value: str | None) -> Sex:
    return "male" if value == "male" else "female" if value == "female" else "unknown"


async def patient_sex(db: Db, patient_id: UUID) -> Sex:
    return as_sex((await db.execute(_SEX, {"p": patient_id})).scalar_one_or_none())
