"""Blood glucose readings up to 35 mmol/L (Q47, physician 2026-11-18).

Home meters (ISO 15197) read about 1.1-33.3 mmol/L and show "HI"/"LO" beyond. A number of
35-50 entered as mmol/L is most often a mg/dL reading (40 mg/dL = 2.2 mmol/L, a serious low),
so it is refused and the app asks the user to check the unit. Only the glucose bound changes;
the plausibility rule stays the same check as 0018 (never a normal range). NOT VALID: earlier
rows are kept as they were entered.

Revision ID: 0045
Revises: 0044
Create Date: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0045"
down_revision: str | None = "0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (kind, unit, low, high, max decimals) - plausibility only, never a normal range (0018); the
# numbers core/vitals.py checks (test_the_migration_checks_the_same_ranges reads this list)
VITALS = [
    ("bp_systolic", "mmHg", 40, 300, 0),
    ("bp_diastolic", "mmHg", 20, 200, 0),
    ("pulse", "bpm", 20, 300, 0),
    ("weight", "kg", 1, 400, 2),
    ("temperature", "C", 30, 45, 1),
    ("glucose", "mmol_L", "0.5", 35, 1),
    ("spo2", "percent", 50, 100, 0),
    ("urine_output", "ml", 0, 20000, 0),
    ("fluid_intake", "ml", 0, 20000, 0),
]


def _check(glucose_high: int) -> str:
    rows = [(k, u, lo, glucose_high if k == "glucose" else hi, d) for k, u, lo, hi, d in VITALS]
    return " or ".join(
        f"(kind = '{k}' and unit = '{u}' and value between {lo} and {hi} and scale(value) <= {d})"
        for k, u, lo, hi, d in rows
    )


def upgrade() -> None:
    op.execute("alter table vitals drop constraint vitals_check")
    op.execute(f"alter table vitals add constraint vitals_check check ({_check(35)}) not valid")


def downgrade() -> None:
    op.execute("alter table vitals drop constraint vitals_check")
    op.execute(f"alter table vitals add constraint vitals_check check ({_check(50)})")
