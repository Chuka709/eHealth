"""A cancelled deletion no longer tells old devices that deletion is pending (Phase 1.13 L2).

The deletion request revokes the sessions with reason 'account_deletion' (0011), so a refresh
answers `auth.deletion_pending`. When a super admin cancels the deletion the account comes back
locked (identity check + new password), but those sessions kept their reason and an old device
still showed "your account will be deleted". The cancellation now relabels them 'disabled': the
next refresh is a plain sign-out, and signing in explains the lock.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-04
"""

import importlib.util
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AUDIT = "perform public.admin_audit(actor, 'admin.deletion_cancel', p_user_id,"
_RELABEL = (
    "update public.sessions set revoked_reason = 'disabled'"
    " where user_id = p_user_id and revoked_reason = 'account_deletion';\n      "
)


def _revision(filename: str) -> ModuleType:
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cancel() -> str:
    statements: list[str] = _revision("0008_account_deletion.py")._UP
    (sql,) = [s for s in statements if "create function admin_cancel_deletion(" in s]
    if sql.count(_AUDIT) != 1:
        raise RuntimeError("admin_cancel_deletion changed")
    return sql.replace("create function", "create or replace function", 1)


def upgrade() -> None:
    op.execute(_cancel().replace(_AUDIT, _RELABEL + _AUDIT))


def downgrade() -> None:
    op.execute(_cancel())
