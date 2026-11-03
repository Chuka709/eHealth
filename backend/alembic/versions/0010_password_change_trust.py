"""A password change ends the device trust of every other phone (Phase 1.11e review, M1).

Before, auth_change_password dropped trusted devices only with "sign out other devices", and
then all of them, this phone included: keeping the others signed in left whoever knew the old
password the soft lockout of a trusted device, and signing them out made the owner an unknown
device. Now every change drops the trust of all devices except the one the request came from
(identified by the hash of its device token, which the app sends along).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-03
"""

import importlib.util
from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_SIGNATURE = "auth_change_password(text, uuid, boolean)"
_NEW_SIGNATURE = "auth_change_password(text, uuid, boolean, text)"

_HEAD = """create function auth_change_password(p_new_hash text, p_keep_session uuid,
                                         p_revoke_others boolean) returns void"""
_HEAD_NEW = """create function auth_change_password(p_new_hash text, p_keep_session uuid,
                                         p_revoke_others boolean, p_keep_device_hash text)
    returns void"""
_TRUST = """\
      if p_revoke_others then
        update public.sessions set revoked_at = now(), revoked_reason = 'user_revoke'
          where user_id = uid and revoked_at is null and id is distinct from p_keep_session;
        delete from public.trusted_devices where user_id = uid;
      end if;"""
_TRUST_NEW = """\
      if p_revoke_others then
        update public.sessions set revoked_at = now(), revoked_reason = 'user_revoke'
          where user_id = uid and revoked_at is null and id is distinct from p_keep_session;
      end if;
      -- Whoever knew the old password loses a trusted device's softer lockout; this phone
      -- (the one changing the password) keeps its trust.
      delete from public.trusted_devices
        where user_id = uid and device_hash is distinct from p_keep_device_hash;"""


def _original() -> str:
    """auth_change_password as 0005 created it."""
    path = Path(__file__).with_name("0005_auth_functions.py")
    spec = importlib.util.spec_from_file_location("rev0005", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path.name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    statements: list[str] = module._UP
    (sql,) = [s for s in statements if "create function auth_change_password(" in s]
    return sql


def _patched() -> str:
    sql = _original()
    for old, new in ((_HEAD, _HEAD_NEW), (_TRUST, _TRUST_NEW)):
        if sql.count(old) != 1:
            raise RuntimeError("0005 auth_change_password changed")
        sql = sql.replace(old, new)
    return sql


def upgrade() -> None:
    op.execute(f"drop function {_OLD_SIGNATURE}")
    op.execute(_patched())
    op.execute("revoke execute on all functions in schema public from public")
    op.execute(f"grant execute on function {_NEW_SIGNATURE} to labtrack_app")


def downgrade() -> None:
    op.execute(f"drop function if exists {_NEW_SIGNATURE}")
    op.execute(_original())
    op.execute("revoke execute on all functions in schema public from public")
    op.execute(f"grant execute on function {_OLD_SIGNATURE} to labtrack_app")
