"""Push delivery under its own role, labtrack_push (Phase 2.11b; beta blocker from 2.8b).

The push worker has internet (Expo). It ran as labtrack_maint, which may also purge accounts
and read every maintenance function. Now it gets only what delivery needs:

- execute on the four delivery functions (security definer, fixed search_path):
  maint_push_queue, maint_mark_pushed, maint_forget_push_token, maint_forget_receipt_token;
  labtrack_maint loses them (the maintenance worker never sends pushes).
- push_receipts: select, insert and update of the delivery columns, never delete (the daily
  purge stays with labtrack_maint, which keeps only select and delete); its sequence.
- nothing else: no PHI table, no other function (RLS tests prove it).

The role itself is cluster-wide: infra/postgres/init/02-push-role.sh on a new data directory,
`just db-roles` on an existing one (before `just migrate`).

Revision ID: 0028
Revises: 0027
"""

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

_FUNCTIONS = (
    "maint_push_queue(int), maint_mark_pushed(bigint[]), maint_forget_push_token(text),"
    " maint_forget_receipt_token(bigint)"
)


def upgrade() -> None:
    op.execute(f"revoke execute on function {_FUNCTIONS} from public, labtrack_maint")
    op.execute(f"grant execute on function {_FUNCTIONS} to labtrack_push")
    # one policy per granted command: no delete even if a grant were added by mistake
    op.execute(
        "create policy push_receipts_push_select on push_receipts for select to labtrack_push"
        " using (true)"
    )
    op.execute(
        "create policy push_receipts_push_insert on push_receipts for insert to labtrack_push"
        " with check (true)"
    )
    op.execute(
        "create policy push_receipts_push_update on push_receipts for update to labtrack_push"
        " using (true) with check (true)"
    )
    # the maintenance worker only purges old receipts now
    op.execute("revoke insert, update on push_receipts from labtrack_maint")
    op.execute("grant select (id, ticket_id, status, created_at) on push_receipts to labtrack_push")
    op.execute(
        """grant insert (notification_id, session_id, ticket_id, status, error, token_sha256)
           on push_receipts to labtrack_push"""
    )
    op.execute("grant update (status, error, checked_at) on push_receipts to labtrack_push")
    op.execute("grant usage on sequence push_receipts_id_seq to labtrack_push")


def downgrade() -> None:
    op.execute("revoke usage on sequence push_receipts_id_seq from labtrack_push")
    op.execute("revoke all on push_receipts from labtrack_push")
    for command in ("select", "insert", "update"):
        op.execute(f"drop policy push_receipts_push_{command} on push_receipts")
    op.execute("grant insert, update on push_receipts to labtrack_maint")
    op.execute(f"revoke execute on function {_FUNCTIONS} from labtrack_push")
    op.execute(f"grant execute on function {_FUNCTIONS} to labtrack_maint")
