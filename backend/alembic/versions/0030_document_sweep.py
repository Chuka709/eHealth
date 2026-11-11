"""The maintenance worker removes objects of deleted documents and orphans (Phase 3.3).

- labtrack_maint reads and deletes `document_deletions` (storage keys only, no PHI); one policy
  per granted command.
- maint_live_document_keys(keys): which of the given storage keys still belong to a document -
  for the daily sweep of objects a failed upload left behind. Keys in, keys out: nothing else
  of documents reaches the maintenance role.

Revision ID: 0030
Revises: 0029
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "create policy document_deletions_maint_select on document_deletions for select"
        " to labtrack_maint using (true)"
    )
    op.execute(
        "create policy document_deletions_maint_delete on document_deletions for delete"
        " to labtrack_maint using (true)"
    )
    op.execute("grant select, delete on document_deletions to labtrack_maint")
    op.execute(
        """create function maint_live_document_keys(p_keys text[]) returns setof text
           language sql stable security definer set search_path = pg_catalog, public, pg_temp
           as $$
             select d.storage_key from public.documents d where d.storage_key = any(p_keys)
           $$"""
    )
    op.execute("revoke execute on function maint_live_document_keys(text[]) from public")
    op.execute("grant execute on function maint_live_document_keys(text[]) to labtrack_maint")


def downgrade() -> None:
    op.execute("drop function maint_live_document_keys(text[])")
    op.execute("revoke all on document_deletions from labtrack_maint")
    op.execute("drop policy document_deletions_maint_delete on document_deletions")
    op.execute("drop policy document_deletions_maint_select on document_deletions")
