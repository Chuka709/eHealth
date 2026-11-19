"""History and emergency-card rows are edited only by the owner or whoever wrote them
(commit security review of 0018).

0018 let only the owner or the writer delete clinical events, allergies and emergency
contacts, but any writer (a caregiver) could still edit them - and rewriting an allergy's
substance or a contact's phone erases it as surely as deleting it (H27). Updates now follow
the same rule as deletes. Vitals are never edited; appointments and questions stay editable
by every writer (planning together).

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("clinical_events", "allergies", "emergency_contacts")
_WRITER = "can_write_patient(patient_id) and (is_owner(patient_id) or recorded_by = app_user_id())"


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"drop policy {table}_update on {table}")
        op.execute(
            f"create policy {table}_update on {table} for update to labtrack_app"
            f" using ({_WRITER}) with check ({_WRITER})"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"drop policy {table}_update on {table}")
        op.execute(
            f"create policy {table}_update on {table} for update to labtrack_app"
            " using (can_write_patient(patient_id)) with check (can_write_patient(patient_id))"
        )
