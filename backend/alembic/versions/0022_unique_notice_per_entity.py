"""One notice per invitation and per dose alert, enforced by the database (commit review of 0021).

0021 checked "not yet announced" with `not exists`: two concurrent calls could both pass it and
insert twice. The index is now unique, so the second insert fails (unique_violation) however
the calls interleave; notify() keeps its check for the plain case.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WHERE = " where kind in ('share_invite', 'dose_overdue')"


def upgrade() -> None:
    op.execute("drop index notifications_entity")
    # an older duplicate (before 0021) would block the index: keep the first notice of each
    op.execute(
        "delete from notifications n using notifications m"
        " where n.kind in ('share_invite', 'dose_overdue') and m.kind = n.kind"
        " and m.entity_id = n.entity_id and m.id < n.id"
    )
    op.execute(
        f"create unique index notifications_entity on notifications (kind, entity_id){_WHERE}"
    )


def downgrade() -> None:
    op.execute("drop index notifications_entity")
    op.execute(f"create index notifications_entity on notifications (kind, entity_id){_WHERE}")
