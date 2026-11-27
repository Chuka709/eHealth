"""Dose alerts stop when a required consent is withdrawn (Phase 2.8e).

maint_caregiver_alert_targets() leaves out a (profile, caregiver) pair when the profile's owner
or the caregiver has withdrawn one of the consents the app cannot be used without (terms,
privacy, sensitive_data): their latest row for it says granted = false. A newer text version
that has not been accepted yet does not stop alerts (decision 2, user 2026-11-11): a text update
must never silence a caregiver's safety alert without anyone choosing it.

Also (security review): only a person ('user'/'doctor') is a target, never an admin role; and
nothing is read for a profile whose owner asked to delete the account (Q46). A locked or
disabled owner keeps their caregivers' alerts - the patient's safety does not depend on the
account's state.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"

# one user's own consents (patient_id is null), the latest row per required kind
_WITHDRAWN = """exists (
        select 1 from (
          select distinct on (c.kind) c.granted from public.consents c
          where c.user_id = {u} and c.patient_id is null
            and c.kind in ('terms', 'privacy', 'sensitive_data')
          order by c.kind, c.created_at desc, c.id desc) latest
        where not latest.granted)"""


def _targets(consent_filter: bool) -> str:
    extra = (
        f"""
        and not {_WITHDRAWN.format(u="s.caregiver_user_id")}
        -- a caregiver is a person, never an admin role (rule 2a; security review L1)
        and u.role in ('user', 'doctor')
        -- an owner who asked to delete the account: nothing more is read for it (Q46)
        and not exists (select 1 from public.patient_access o
                        join public.users ou on ou.id = o.user_id
                        where o.patient_id = s.patient_id and o.level = 'owner'
                          and o.revoked_at is null and ou.deleted_at is not null)
        and not exists (select 1 from public.patient_access o
                        where o.patient_id = s.patient_id and o.level = 'owner'
                          and o.revoked_at is null
                          and {_WITHDRAWN.format(u="o.user_id")})"""
        if consent_filter
        else ""
    )
    return f"""
    create or replace function maint_caregiver_alert_targets()
    returns table (patient_id uuid, caregiver_user_id uuid, after_min int)
    language sql stable {_DEFINER} as $$
      select s.patient_id, s.caregiver_user_id, s.missed_dose_after_min
      from public.caregiver_alert_settings s
      join public.patient_access a on a.patient_id = s.patient_id
        and a.user_id = s.caregiver_user_id and a.level = 'caregiver'
        and a.revoked_at is null and (a.expires_at is null or a.expires_at > now())
      join public.patients p on p.id = s.patient_id and p.deleted_at is null
      join public.users u on u.id = s.caregiver_user_id and u.account_status = 'active'
        and u.deleted_at is null
      where s.missed_dose_after_min is not null and not s.owner_paused{extra}
    $$
    """


def upgrade() -> None:
    op.execute(_targets(consent_filter=True))


def downgrade() -> None:
    op.execute(_targets(consent_filter=False))
