"""Sharing by link or QR with someone without an account (Phase 7.2; docs/04 §2 "Хуваалцах
хоёр арга" 2, §6.7; docs/03 "ХУВААЛЦАХ ЛИНК"; 11_TOOLING C; hazard H37; decision Q62).

- the owner makes a link: chosen sections, an optional date range, 24 hours / 7 / 30 days, an
  optional limit of opens. The server makes the token (256 bits, only its sha256 is kept) and a
  6-digit PIN (only its argon2id hash is kept); both are shown to the owner once. The token
  travels in the URL fragment, the PIN separately (said aloud);
- opening: the attempt is counted before the PIN is checked, atomically (04 §6.7); an open
  needs the token and a counted attempt. 5 wrong PINs in a row, or 10 in all, revoke the link
  and tell the owner. A right PIN opens a viewing session of 30 minutes (its own token, hash
  only) and counts one open;
- a link lives only while its maker still owns the profile with an active account, the same
  credentials (an admin reset or a password change ends it: token_version) and the required
  consents given;
- a viewing session reads nothing through the row policies (can_read_patient is not touched):
  every section is a definer function of its own that checks the session and applies the
  link's sections and dates in the database. 7.2 has whose record it is; the sections come
  with the web viewer (7.3);
- the owner sees each link (sections, until when, opens, last opened, why it ended) and every
  open.

Revision ID: 0041
Revises: 0040
Create Date: 2026-11-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0041"
down_revision: str | None = "0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFINER = "security definer set search_path = pg_catalog, public, pg_temp"
SCOPES = ("summary", "labs", "meds", "transplant", "events", "vitals")
_SCOPES_SQL = ", ".join(f"'{s}'" for s in SCOPES)

_KINDS_OLD = (
    "'review_ready','critical_pending','share_invite','admin_reset','reminder',"
    "'admin_action','dose_overdue'"
)
_KINDS_NEW = _KINDS_OLD + ",'share_link_locked'"

_TABLES = [
    f"""
    create table share_links (
      id uuid primary key default gen_random_uuid(),
      patient_id uuid not null references patients on delete cascade,
      token_hash text not null unique check (token_hash ~ '^[0-9a-f]{{64}}$'),
      pin_hash text not null check (pin_hash like '$argon2id$%'),
      scopes text[] not null
        check (cardinality(scopes) between 1 and 6 and scopes <@ array[{_SCOPES_SQL}]),
      date_from date,
      date_to date,
      expires_at timestamptz not null,
      max_views int check (max_views between 1 and 100),
      view_count int not null default 0 check (view_count >= 0),
      -- attempts counted and not yet answered by a right PIN (04 §6.7), and wrong PINs in all
      pin_failed_count int not null default 0 check (pin_failed_count between 0 and 5),
      pin_wrong_total int not null default 0 check (pin_wrong_total between 0 and 10),
      created_by uuid not null references users on delete cascade,
      owner_token_version int not null,
      revoked_at timestamptz,
      revoked_reason text check (revoked_reason in ('owner', 'pin_locked')),
      created_at timestamptz not null default now(),
      check (date_from is null or date_to is null or date_from <= date_to),
      check (expires_at <= created_at + interval '30 days 1 minute'),
      check ((revoked_at is null) = (revoked_reason is null))
    )
    """,
    "create index on share_links (patient_id, created_at desc)",
    """
    create table share_sessions (
      id bigserial primary key,
      link_id uuid not null references share_links on delete cascade,
      token_hash text not null unique check (token_hash ~ '^[0-9a-f]{64}$'),
      created_at timestamptz not null default now(),
      expires_at timestamptz not null default now() + interval '30 minutes'
    )
    """,
    "create index on share_sessions (link_id, created_at desc)",
]

# a link that can still be opened, whose maker still stands behind it (alias l)
_LIVE = """l.revoked_at is null and l.expires_at > now()
          and (l.max_views is null or l.view_count < l.max_views)
          and public.share_link_owner_ok(l.id)"""

_FUNCTIONS = [
    # the maker still owns the profile, with an active account, the same credentials and the
    # required consents (as 0026/0035 read them); the profile still exists
    f"""
    create function share_link_owner_ok(p_link uuid) returns boolean
    language sql stable {_DEFINER} as $$
      select exists (
        select 1 from public.share_links l
        join public.users u on u.id = l.created_by
        join public.patients x on x.id = l.patient_id
        where l.id = p_link and u.account_status = 'active' and u.deleted_at is null
          and u.token_version = l.owner_token_version and x.deleted_at is null
          and exists (select 1 from public.patient_access a
                      where a.patient_id = l.patient_id and a.user_id = u.id
                        and a.level = 'owner' and a.revoked_at is null)
          and not exists (
            select 1 from (
              select distinct on (c.kind) c.granted from public.consents c
              where c.user_id = u.id and c.patient_id is null
                and c.kind in ('terms', 'privacy', 'sensitive_data')
              order by c.kind, c.created_at desc, c.id desc) latest
            where not latest.granted)
          and (select count(distinct c.kind) from public.consents c
               where c.user_id = u.id and c.patient_id is null
                 and c.kind in ('terms', 'privacy', 'sensitive_data')) = 3)
    $$
    """,
    f"""
    create function create_share_link(p_patient uuid, p_token_hash text, p_pin_hash text,
                                      p_scopes text[], p_from date, p_to date, p_days int,
                                      p_max_views int)
    returns uuid language plpgsql volatile {_DEFINER} as $$
    declare
      me uuid := public.app_user_id();
      link uuid;
    begin
      if me is null or not public.is_owner(p_patient) then
        raise exception 'not the owner' using errcode = '42501';
      end if;
      if p_days not in (1, 7, 30) then
        raise exception 'invalid share link' using errcode = '22023';
      end if;
      if (select count(*) from public.share_links l
          where l.patient_id = p_patient and l.revoked_at is null
            and l.expires_at > now()) >= 20 then
        raise exception 'too many links' using errcode = '54000';
      end if;
      insert into public.share_links (patient_id, token_hash, pin_hash, scopes, date_from,
                                      date_to, expires_at, max_views, created_by,
                                      owner_token_version)
        select p_patient, p_token_hash, p_pin_hash, p_scopes, p_from, p_to,
               now() + make_interval(days => p_days), p_max_views, me, u.token_version
        from public.users u where u.id = me
        returning id into link;
      perform public.caregiver_audit('share_link.create', 'share_link', link::text, p_patient,
        jsonb_build_object('fields', jsonb_build_array('scopes', 'date_from', 'date_to',
                                                       'expires_at', 'max_views')));
      return link;
    end $$
    """,
    f"""
    create function revoke_share_link(p_link uuid) returns boolean
    language plpgsql volatile {_DEFINER} as $$
    declare
      pid uuid;
    begin
      update public.share_links set revoked_at = now(), revoked_reason = 'owner'
        where id = p_link and revoked_at is null and public.is_owner(patient_id)
        returning patient_id into pid;
      if pid is null then
        return false;
      end if;
      perform public.caregiver_audit('share_link.revoke', 'share_link', p_link::text, pid,
                                     null);
      return true;
    end $$
    """,
    f"""
    create function owner_share_links(p_patient uuid)
    returns table (id uuid, scopes text[], date_from date, date_to date, created_at timestamptz,
                   expires_at timestamptz, max_views int, view_count int,
                   revoked_at timestamptz, revoked_reason text, last_viewed_at timestamptz)
    language sql stable {_DEFINER} as $$
      select l.id, l.scopes, l.date_from, l.date_to, l.created_at, l.expires_at, l.max_views,
             l.view_count, l.revoked_at, l.revoked_reason,
             (select max(s.created_at) from public.share_sessions s where s.link_id = l.id)
      from public.share_links l
      where public.is_owner(p_patient) and l.patient_id = p_patient
        and l.created_at > now() - interval '90 days'
      order by l.created_at desc limit 100
    $$
    """,
    f"""
    create function owner_share_link_views(p_link uuid)
    returns table (opened_at timestamptz)
    language sql stable {_DEFINER} as $$
      select s.created_at from public.share_sessions s
      join public.share_links l on l.id = s.link_id
      where s.link_id = p_link and public.is_owner(l.patient_id)
      order by s.created_at desc limit 200
    $$
    """,
    # an opening attempt, counted before the PIN is checked (04 §6.7): the stored PIN hash of a
    # link that can still be opened, or nothing
    f"""
    create function share_link_attempt(p_token_hash text)
    returns table (link_id uuid, pin_hash text)
    language plpgsql volatile {_DEFINER} as $$
    declare
      l public.share_links;
    begin
      if public.app_user_id() is not null then
        raise exception 'anonymous only' using errcode = '42501';
      end if;
      update public.share_links x set pin_failed_count = x.pin_failed_count + 1
        where x.token_hash = p_token_hash and x.revoked_at is null and x.expires_at > now()
          and (x.max_views is null or x.view_count < x.max_views)
          and x.pin_failed_count < 5 and public.share_link_owner_ok(x.id)
        returning x.* into l;
      if l.id is null then
        return;
      end if;
      return query select l.id, l.pin_hash;
    end $$
    """,
    # a wrong PIN: 5 in a row or 10 in all revoke the link and tell the owner
    f"""
    create function share_link_failed(p_link uuid) returns void
    language plpgsql volatile {_DEFINER} as $$
    declare
      l public.share_links;
    begin
      if public.app_user_id() is not null then
        raise exception 'anonymous only' using errcode = '42501';
      end if;
      update public.share_links x set pin_wrong_total = least(x.pin_wrong_total + 1, 10)
        where x.id = p_link and x.revoked_at is null
        returning x.* into l;
      if l.id is null or (l.pin_failed_count < 5 and l.pin_wrong_total < 10) then
        return;
      end if;
      update public.share_links set revoked_at = now(), revoked_reason = 'pin_locked'
        where id = l.id;
      insert into public.notifications (user_id, kind, patient_id, entity_id, title_key)
        select o.user_id, 'share_link_locked', l.patient_id, l.id::text,
               'notification.share_link_locked'
        from public.patient_access o
        where o.patient_id = l.patient_id and o.level = 'owner' and o.revoked_at is null;
      insert into public.audit_logs (actor_id, actor_role, action, entity, entity_id,
                                     patient_id, diff)
        values (null, 'anonymous', 'share_link.locked', 'share_link', l.id::text,
                l.patient_id, null);
    end $$
    """,
    # a right PIN: needs the token and a counted attempt; the run of wrong ones ends (their
    # total stays), one open is counted, a session begins
    f"""
    create function share_link_open(p_token_hash text, p_session_hash text) returns boolean
    language plpgsql volatile {_DEFINER} as $$
    declare
      link uuid;
    begin
      if public.app_user_id() is not null then
        raise exception 'anonymous only' using errcode = '42501';
      end if;
      update public.share_links l
        set pin_failed_count = 0, view_count = l.view_count + 1
        where l.token_hash = p_token_hash and l.pin_failed_count > 0 and {_LIVE}
        returning l.id into link;
      if link is null then
        return false;
      end if;
      insert into public.share_sessions (link_id, token_hash) values (link, p_session_hash);
      return true;
    end $$
    """,
    # what a viewing session may see (the API's gate for every share route)
    f"""
    create function share_session_scope(p_session_hash text)
    returns table (link_id uuid, scopes text[], date_from date, date_to date,
                   expires_at timestamptz)
    language sql stable {_DEFINER} as $$
      select l.id, l.scopes, l.date_from, l.date_to, least(s.expires_at, l.expires_at)
      from public.share_sessions s
      join public.share_links l on l.id = s.link_id
      where public.app_user_id() is null and s.token_hash = p_session_hash
        and s.expires_at > now() and l.revoked_at is null and l.expires_at > now()
        and public.share_link_owner_ok(l.id)
    $$
    """,
    # whose record it is (the viewer must know), for a live session only
    f"""
    create function share_profile(p_session_hash text) returns text
    language sql stable {_DEFINER} as $$
      select x.full_name from public.share_sessions s
      join public.share_links l on l.id = s.link_id
      join public.patients x on x.id = l.patient_id
      where public.app_user_id() is null and s.token_hash = p_session_hash
        and s.expires_at > now() and l.revoked_at is null and l.expires_at > now()
        and public.share_link_owner_ok(l.id)
    $$
    """,
    # retention: links ended 400 days ago go, with their sessions (the maintenance worker)
    f"""
    create function maint_prune_share_links() returns int
    language sql volatile {_DEFINER} as $$
      with gone as (delete from public.share_links
                    where coalesce(revoked_at, expires_at) < now() - interval '400 days'
                    returning 1)
      select count(*)::int from gone
    $$
    """,
]

_APP_FUNCTIONS = [
    "create_share_link(uuid, text, text, text[], date, date, int, int)",
    "revoke_share_link(uuid)",
    "owner_share_links(uuid)",
    "owner_share_link_views(uuid)",
    "share_link_attempt(text)",
    "share_link_failed(uuid)",
    "share_link_open(text, text)",
    "share_session_scope(text)",
    "share_profile(text)",
]
_INTERNAL = ["share_link_owner_ok(uuid)"]


def upgrade() -> None:
    for sql in _TABLES:
        op.execute(sql)
    for table in ("share_links", "share_sessions"):
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")
        op.execute(
            f"create policy {table}_owner on {table} for all to labtrack_owner"
            " using (true) with check (true)"
        )
        op.execute(f"revoke truncate on {table} from public")
    op.execute("alter table notifications drop constraint notifications_kind_check")
    op.execute(
        "alter table notifications add constraint notifications_kind_check"
        f" check (kind in ({_KINDS_NEW}))"
    )
    for sql in _FUNCTIONS:
        op.execute(sql)
    for name in (*_APP_FUNCTIONS, *_INTERNAL, "maint_prune_share_links()"):
        op.execute(f"revoke execute on function {name} from public")
    op.execute(f"grant execute on function {', '.join(_APP_FUNCTIONS)} to labtrack_app")
    op.execute("grant execute on function maint_prune_share_links() to labtrack_maint")


def downgrade() -> None:
    for name in (*_APP_FUNCTIONS, "maint_prune_share_links()", *_INTERNAL):
        op.execute(f"drop function {name}")
    op.execute("delete from notifications where kind = 'share_link_locked'")
    op.execute("alter table notifications drop constraint notifications_kind_check")
    op.execute(
        "alter table notifications add constraint notifications_kind_check"
        f" check (kind in ({_KINDS_OLD}))"
    )
    op.execute("drop table share_sessions")
    op.execute("drop table share_links")
