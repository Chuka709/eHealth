"""Index the moment of a dose record (Phase 6.10, DoD performance).

The intakes list filtered on `coalesce(scheduled_at, taken_at)` (an as-needed dose has no
scheduled time). A comparison on that expression is not leakproof, so under the row policy it
could not become an index condition: a day's records were found by checking all of the
profile's records through the policy - 0.4 s for five years of doses. The list now compares the
columns themselves (leakproof, index conditions): scheduled doses by `scheduled_at` (the
existing index), as-needed doses by `taken_at` through this partial index.

Revision ID: 0039
Revises: 0038
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0039"
down_revision: str | None = "0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "create index medication_intakes_unscheduled on medication_intakes"
        " (patient_id, taken_at desc) where scheduled_at is null"
    )


def downgrade() -> None:
    op.execute("drop index medication_intakes_unscheduled")
