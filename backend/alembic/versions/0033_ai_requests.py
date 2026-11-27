"""Reading by AI: the request kept on our side, and the data owner's consent (Phase 4.5).

From the 4.5 security and medical reviews:
- `ai_requests`: one row per document handed to the AI worker - who asked (the uploader),
  a random nonce the answer must carry, and how well the printed name (read on the server,
  never sent) fits the profile. The answer is saved only as that user, only with that nonce;
  the AI worker's own messages are never trusted for who or what. RLS as the document's.
- `ai_consent_ok(patient, versions)`: the consent that counts is the data owner's - the
  profile owner's own `ai_processing` and `cross_border` for an adult's profile, the owner's
  consents for that profile on a child's - each the latest row, granted, for the current text.
  A caregiver's consent never sends someone else's results abroad. Security definer (the
  owner's consent rows are not readable by others); returns a yes/no only.

Revision ID: 0033
Revises: 0032
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        create table ai_requests (
          document_id uuid primary key,
          patient_id uuid not null references patients on delete cascade,
          requested_by uuid not null references users on delete cascade,
          nonce text not null check (nonce ~ '^[0-9a-f]{32}$'),
          name_match_score numeric(3, 2) check (name_match_score between 0 and 1),
          name_printed boolean not null,
          created_at timestamptz not null default now(),
          foreign key (document_id, patient_id) references documents (id, patient_id)
            on delete cascade
        )
        """
    )
    op.execute("alter table ai_requests enable row level security")
    op.execute("alter table ai_requests force row level security")
    op.execute(
        "create policy ai_requests_owner on ai_requests for all to labtrack_owner"
        " using (true) with check (true)"
    )
    # only the user who asked sees, writes or removes their request
    op.execute(
        """create policy ai_requests_select on ai_requests for select to labtrack_app
           using (requested_by = app_user_id() and can_write_patient(patient_id))"""
    )
    op.execute(
        """create policy ai_requests_insert on ai_requests for insert to labtrack_app
           with check (requested_by = app_user_id() and can_write_patient(patient_id))"""
    )
    op.execute(
        """create policy ai_requests_delete on ai_requests for delete to labtrack_app
           using (requested_by = app_user_id())"""
    )
    op.execute("grant select, insert, delete on ai_requests to labtrack_app")
    op.execute("revoke truncate on ai_requests from public")
    op.execute(
        """create function ai_consent_ok(p uuid, p_versions jsonb) returns boolean
           language sql stable security definer
           set search_path = pg_catalog, public, pg_temp as $$
             with owner as (
               select a.user_id from public.patient_access a
                where a.patient_id = p and a.level = 'owner' and a.revoked_at is null
                  and (a.expires_at is null or a.expires_at > now())
                limit 1
             ), minor as (
               select public.is_minor_patient(p) as is_minor
             ), latest as (
               select distinct on (c.kind) c.kind, c.version, c.granted
                 from public.consents c, owner o, minor m
                where c.user_id = o.user_id
                  and c.kind in ('ai_processing', 'cross_border')
                  and c.patient_id is not distinct from
                      (case when m.is_minor then p else null end)
                order by c.kind, c.id desc
             )
             select public.can_write_patient(p)
                and (select count(*) from latest l
                      where l.granted and l.version = p_versions ->> l.kind) = 2
           $$"""
    )
    op.execute("revoke execute on function ai_consent_ok(uuid, jsonb) from public")
    op.execute("grant execute on function ai_consent_ok(uuid, jsonb) to labtrack_app")


def downgrade() -> None:
    op.execute("drop function ai_consent_ok(uuid, jsonb)")
    op.execute("drop table ai_requests")
