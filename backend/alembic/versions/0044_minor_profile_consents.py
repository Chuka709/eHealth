"""A doctor or a viewer on a minor's shared profile (Phase 7.6; Q9, Q61).

A minor's profile is open only while its owner's consents for that profile are in force (the
API's profile gate). Those consents are readable only by the owner (row policies), so a doctor
or a viewer the owner shared the profile with was always refused (403). This function returns
the owner's latest required consent per kind (terms, privacy, sensitive_data) for a minor's
profile - kind, version, granted, nothing else - to a doctor or a viewer it is shared with
(in force), so the gate can check them; anyone else gets no rows.

Revision ID: 0044
Revises: 0043
Create Date: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"


def upgrade() -> None:
    op.execute(
        f"""
        create function owner_profile_consents(p uuid)
        returns table (kind text, version text, granted boolean)
        language sql stable {_DEFINER} as $$
          select distinct on (c.kind) c.kind, c.version, c.granted
          from public.consents c
          join public.patient_access a on a.patient_id = p and a.user_id = c.user_id
            and a.level = 'owner' and a.revoked_at is null
          where public.can_read_patient(p) and public.is_minor_patient(p) and c.patient_id = p
            and c.kind in ('terms', 'privacy', 'sensitive_data')
            and exists (
              select 1 from public.patient_access me
              where me.patient_id = p and me.user_id = public.app_user_id()
                and me.level in ('doctor', 'viewer') and me.revoked_at is null
                and (me.expires_at is null or me.expires_at > now()))
          order by c.kind, c.id desc
        $$
        """
    )
    op.execute("revoke execute on function owner_profile_consents(uuid) from public")
    op.execute("grant execute on function owner_profile_consents(uuid) to labtrack_app")


def downgrade() -> None:
    op.execute("drop function owner_profile_consents(uuid)")
