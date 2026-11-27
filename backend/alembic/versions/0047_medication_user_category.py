"""The user says what an uncatalogued medicine is (Q34, physician 2026-11-18, ★ Б).

A medicine typed in without the catalogue had no category, so the emergency card showed it by
name without its dose - a hand-typed "Такролимус" lost its dose there. Now the user answers
"is this an immunosuppressant or a steroid?" when adding it: the answer (never a guess from the
name) puts it with its dose on the card. Only for a medicine without a catalogue entry: a
catalogue category is never overridden (CHECK).

Revision ID: 0047
Revises: 0046
Create Date: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0047"
down_revision: str | None = "0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        alter table medications add column user_category text
          check (user_category in ('immunosuppressant', 'corticosteroid', 'other'))
        """
    )
    op.execute(
        """
        alter table medications add constraint medications_user_category_uncatalogued
          check (user_category is null or catalog_code is null)
        """
    )
    op.execute(
        "grant insert (user_category), update (user_category) on medications to labtrack_app"
    )


def downgrade() -> None:
    op.execute("alter table medications drop column user_category")
