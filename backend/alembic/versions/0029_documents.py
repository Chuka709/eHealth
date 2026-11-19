"""Uploaded documents: a lab result as a scan, photo or PDF (Phase 3.1; docs/03 "documents").

- One row per file, as stored (storage key `{patient_id}/{document_id}/original`); the file
  itself is in private object storage, never in the database.
- `client_id` (the app's upload id) + unique (patient_id, client_id): an upload retried from
  the offline queue finds the stored row (replaces docs/03's separate `pending_uploads`).
- unique (patient_id, sha256): the same file twice for one profile is one document.
- Written through the API (owner or writer of the profile); the processing worker moves
  `status` (uploaded -> queued -> ... -> failed) in the uploader's context. Only the profile's
  owner or the uploader deletes (as health records, 0018).
- Columns are granted one by one; id, patient_id, client_id, storage key and hash never change.
  No file name is kept (it often carries the person's name - security review).
- A deleted row - by the user, or by a profile or account purge (cascade) - leaves its storage
  key in `document_deletions` (a trigger, same transaction): the sealed object is still
  readable with the KEK, so the maintenance worker deletes it (Phase 3.3).

Revision ID: 0029
Revises: 0028
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INSERT = (
    "id, patient_id, client_id, storage_key, mime_type, size_bytes, page_count, sha256,"
    " has_text_layer"
)
_UPDATE = "status, error_code, page_count, has_text_layer, quality_score"


def upgrade() -> None:
    op.execute(
        """create type doc_status as enum
           ('uploaded', 'queued', 'processing', 'needs_review', 'confirmed', 'failed',
            'rejected')"""
    )
    op.execute(
        """
        create table documents (
          id uuid primary key default gen_random_uuid(),
          patient_id uuid not null references patients on delete cascade,
          client_id uuid not null,
          storage_key text not null check (storage_key ~ '^[0-9a-f-]{36}/[0-9a-f-]{36}/original$'),
          mime_type text not null check (mime_type in
            ('application/pdf', 'image/jpeg', 'image/png', 'image/heic', 'image/webp')),
          size_bytes int not null check (size_bytes > 0 and size_bytes <= 20971520),
          page_count int check (page_count between 1 and 50),
          sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
          has_text_layer boolean,
          quality_score numeric(3, 2) check (quality_score between 0 and 1),
          status doc_status not null default 'uploaded',
          error_code text check (error_code ~ '^[a-z_]{1,40}$'),
          recorded_by uuid references users on delete set null,
          updated_by uuid references users on delete set null,
          created_at timestamptz not null default now(),
          updated_at timestamptz,
          unique (patient_id, client_id),
          unique (patient_id, sha256),
          unique (id, patient_id)
        )
        """
    )
    op.execute("create index on documents (patient_id, created_at desc)")
    op.execute("alter table documents enable row level security")
    op.execute("alter table documents force row level security")
    op.execute(
        "create policy documents_owner on documents for all to labtrack_owner"
        " using (true) with check (true)"
    )
    op.execute(
        """create policy documents_select on documents for select to labtrack_app
           using (can_read_patient(patient_id))"""
    )
    op.execute(
        """create policy documents_insert on documents for insert to labtrack_app
           with check (can_write_patient(patient_id))"""
    )
    op.execute(
        """create policy documents_update on documents for update to labtrack_app
           using (can_write_patient(patient_id)) with check (can_write_patient(patient_id))"""
    )
    op.execute(
        """create policy documents_delete on documents for delete to labtrack_app
           using (can_write_patient(patient_id)
                  and (is_owner(patient_id) or recorded_by = app_user_id()))"""
    )
    op.execute("grant select, delete on documents to labtrack_app")
    op.execute(f"grant insert ({_INSERT}) on documents to labtrack_app")
    op.execute(f"grant update ({_UPDATE}) on documents to labtrack_app")
    op.execute("revoke truncate on documents from public")
    op.execute(
        """create trigger documents_writer before insert or update on documents
           for each row execute function set_row_writer()"""
    )
    op.execute(
        """create trigger documents_touch before update on documents
           for each row execute function touch_updated_at()"""
    )
    # objects to delete from storage: keys only (ids, no PHI); written by the trigger alone
    op.execute(
        """create table document_deletions (
             storage_key text primary key,
             created_at timestamptz not null default now()
           )"""
    )
    op.execute("alter table document_deletions enable row level security")
    op.execute("alter table document_deletions force row level security")
    op.execute(
        "create policy document_deletions_owner on document_deletions for all to labtrack_owner"
        " using (true) with check (true)"
    )
    op.execute("revoke all on document_deletions from public")
    op.execute(
        """create function documents_deleted() returns trigger language plpgsql
           security definer set search_path = pg_catalog, public, pg_temp as $$
           begin
             insert into public.document_deletions (storage_key) values (old.storage_key)
               on conflict do nothing;
             return old;
           end $$"""
    )
    op.execute("revoke execute on function documents_deleted() from public")
    op.execute(
        """create trigger documents_deleted after delete on documents
           for each row execute function documents_deleted()"""
    )


def downgrade() -> None:
    op.execute("drop table documents")
    op.execute("drop function documents_deleted()")
    op.execute("drop table document_deletions")
    op.execute("drop type doc_status")
