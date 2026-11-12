"""Reading by AI: the sent text kept with the request (commit security review 4.5).

The default worker checks the AI's answer against the text it sent itself - never trusting
the checks the AI worker reports (it shares a broker with everyone until the Valkey ACL,
docs/BETA.md B10). `sent_text` is the de-identified text (no name, register number or birth
date), kept only while the request is open: removed with the request when the answer is
saved or the document fails, and with the document or profile (cascade). RLS as 0033.

Revision ID: 0034
Revises: 0033
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0034"
down_revision: str | None = "0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("delete from ai_requests")  # open requests from before: read again by the sweep
    op.execute(
        "alter table ai_requests add column sent_text text not null"
        " check (length(sent_text) between 1 and 70000)"
    )


def downgrade() -> None:
    op.execute("alter table ai_requests drop column sent_text")
