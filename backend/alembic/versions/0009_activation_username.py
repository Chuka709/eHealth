"""Activation needs the username as well as the token (Phase 1.11b security review, M2).

An SMS activation/reset link uses the `labtrack://` scheme, which any Android app can also
claim; a token caught that way must not be enough to take over the account. The app now sends
the username (printed on the user's sign-in card) with the token. A wrong username counts
against the token; the third one revokes it and is reported to admins. Usernames are never
stored in the event, only the fact and the count.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"

MAX_USERNAME_FAILURES = 3

_UP = [
    """alter table activation_tokens
       add column username_failures smallint not null default 0
       check (username_failures between 0 and 100)""",
    # Called by the API when the username sent with a live token does not match its account.
    # Returns true when this failure revoked the token.
    f"""
    create function activation_username_mismatch(p_token_hash text, p_ip inet)
    returns boolean
    language plpgsql volatile {_DEFINER} as $$
    declare
      tok record;
    begin
      insert into public.auth_attempts (kind, ip, success)
        values ('activation', public.ip_net(p_ip), false);
      update public.activation_tokens
        set username_failures = username_failures + 1,
            revoked_at = case when username_failures + 1 >= {MAX_USERNAME_FAILURES}
                              then now() else revoked_at end
        where token_hash = p_token_hash and used_at is null and revoked_at is null
          and expires_at > now()
        returning * into tok;
      if not found then
        return false;
      end if;
      if tok.revoked_at is not null then
        insert into public.audit_logs (actor_role, action, target_user_id, diff)
          values ('anonymous', 'security.activation_username_mismatch', tok.user_id,
                  jsonb_build_object('purpose', tok.purpose, 'channel', tok.channel,
                                     'failures', tok.username_failures, 'revoked', true));
        return true;
      end if;
      return false;
    end $$
    """,
    "revoke execute on all functions in schema public from public",
    "grant execute on function activation_username_mismatch(text, inet) to labtrack_app",
]


def upgrade() -> None:
    for sql in _UP:
        op.execute(sql)


def downgrade() -> None:
    op.execute("drop function if exists activation_username_mismatch(text, inet)")
    op.execute("alter table activation_tokens drop column if exists username_failures")
