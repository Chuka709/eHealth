"""Sessions ended by the user's own "Би хүсээгүй" or deletion request say so (Phase 1.11e-2 M1).

Both used to revoke with reason 'disabled', like an admin disabling the account. If the response
to the report or the deletion request was lost, the app only saw a plain sign-out on the next
refresh and the user never learned the account was locked or scheduled for deletion. With their
own reasons the refresh answers `auth.account_reported` / `auth.deletion_pending` - only to the
holder of that session's refresh token, so nothing is revealed to anyone else.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-03
"""

import importlib.util
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REASONS_0002 = (
    "'logout','user_revoke','admin_reset','disabled','reuse_detected','expired','rotated'"
)
_NEW_REASONS = ("user_report", "account_deletion")
_REVOKE = "perform public.revoke_user_sessions(uid, 'disabled');"


def _revision(filename: str) -> ModuleType:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report() -> str:
    sql: str = _revision("0007_me.py")._REPORT
    return sql.replace("create function", "create or replace function", 1)


def _deletion() -> str:
    statements: list[str] = _revision("0008_account_deletion.py")._UP
    (sql,) = [s for s in statements if "create function request_account_deletion(" in s]
    return sql.replace("create function", "create or replace function", 1)


def _with_reason(sql: str, reason: str) -> str:
    if sql.count(_REVOKE) != 1:
        raise RuntimeError("revoke_user_sessions call changed")
    return sql.replace(_REVOKE, f"perform public.revoke_user_sessions(uid, '{reason}');")


def _constraint(extra: Sequence[str]) -> list[str]:
    values = _REASONS_0002 + "".join(f",'{r}'" for r in extra)
    return [
        "alter table sessions drop constraint sessions_revoked_reason_check",
        f"alter table sessions add constraint sessions_revoked_reason_check"
        f" check (revoked_reason in ({values}))",
    ]


def upgrade() -> None:
    for sql in _constraint(_NEW_REASONS):
        op.execute(sql)
    op.execute(_with_reason(_report(), "user_report"))
    op.execute(_with_reason(_deletion(), "account_deletion"))


def downgrade() -> None:
    op.execute(_report())
    op.execute(_deletion())
    op.execute(
        "update sessions set revoked_reason = 'disabled'"
        " where revoked_reason in ('user_report', 'account_deletion')"
    )
    for sql in _constraint(()):
        op.execute(sql)
