"""Every table is under RLS and every SECURITY DEFINER function is pinned, closed to PUBLIC and
granted to exactly the roles that need it (CLAUDE.md rule 1, docs/03).

Generic, so a table or function added by a later migration is covered without a new test.
"""

from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

PINNED = "search_path=pg_catalog, public, pg_temp"

# Shared reference data (no user data): readable by everyone, written only by migrations/seed.
NO_RLS = {
    "alembic_version",
    "medication_catalog",
    "test_catalog",
    "unit_aliases",
    "unit_conversions",
}

# Exact set of SECURITY DEFINER functions each runtime role may execute. A new grant, a role
# reaching a function it should not, or a stale overload left by an older migration fails here;
# update this snapshot deliberately when a migration adds a function.
EXECUTE_MATRIX: dict[str, set[str]] = {
    "labtrack_app": {
        "activation_consume(text,text,inet,boolean)",
        "activation_token_user(text)",
        "activation_username_mismatch(text,inet)",
        "admin_token_is_live(text)",
        "audit_write(text,text,text,uuid,jsonb)",
        "auth_change_password(text,uuid,boolean,text)",
        "auth_failure_counts(text,text,inet,text,interval)",
        "auth_login_lookup(text)",
        "auth_own_password_hash()",
        "auth_record_failure(text,text,inet,text,boolean)",
        "can_read_patient(uuid)",
        "can_write_patient(uuid)",
        "caregiver_alerts_on(uuid)",
        "create_patient(text,text,date,sex)",
        "device_is_trusted(text,text)",
        "extra_recorder_role(uuid)",
        "intake_recorder_role(uuid)",
        "invite_caregiver(uuid,text)",
        "is_minor_patient(uuid)",
        "is_owner(uuid)",
        "is_shareable_user(uuid)",
        "leave_patient(uuid)",
        "lookup_user_for_share(text)",
        "my_admin_actions()",
        "my_caregiver_invitations()",
        "notify(uuid,text,uuid,text,text)",
        "owner_caregiver_invitations(uuid)",
        "owner_caregivers(uuid)",
        "pause_caregiver_alerts(uuid,uuid,boolean)",
        "report_unwanted_admin_action()",
        "request_account_deletion()",
        "respond_caregiver_invitation(uuid,boolean)",
        "revoke_caregiver(uuid,uuid)",
        "revoke_caregiver_invitation(uuid)",
        "revoke_my_session(uuid,text)",
        "session_check(uuid,uuid,integer)",
        "session_create(uuid,text,text,text,text,boolean,inet,interval)",
        "session_revoke_by_token(text)",
        "session_rotate(text,text,interval)",
        "set_caregiver_alerts(uuid,integer,boolean)",
        "set_session_push_token(uuid,text)",
    },
    "labtrack_admin": {
        "admin_cancel_deletion(uuid,text)",
        "admin_clear_lockout(uuid)",
        "admin_create_user(uuid,text,text,user_role,bytea,text,text,text)",
        "admin_identity_check(uuid,text,text)",
        "admin_issue_token(uuid,text,text,text,bigint,text,inet)",
        "admin_log_import(text,integer)",
        "admin_reveal_phone(uuid)",
        "admin_security_events(integer)",
        "admin_session_begin(text)",
        "admin_session_end(text)",
        "admin_set_identity(uuid,text,text)",
        "admin_set_status(uuid,text,text)",
        "admin_sms_target(uuid)",
        "user_key_get(uuid)",
        "user_key_put(uuid,bytea)",
    },
    "labtrack_admin_login": {
        "admin_login_failure(text,inet)",
        "admin_login_lookup(text)",
        "admin_session_create(uuid,text,inet,bigint)",
        "auth_failure_counts(text,text,inet,text,interval)",
    },
    "labtrack_maint": {
        "maint_caregiver_alert_targets()",
        "maint_live_document_keys(text[])",
        "maint_sweep_extractions()",
        "maint_purge_deleted_users(integer)",
    },
    # 0028: the push worker's own role
    "labtrack_push": {
        "maint_forget_push_token(text)",
        "maint_forget_receipt_token(bigint)",
        "maint_mark_pushed(bigint[])",
        "maint_push_queue(integer)",
    },
}


async def test_definer_functions_pin_search_path(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as conn:
        loose = (
            (
                await conn.execute(
                    bound_text(
                        "select p.oid::regprocedure::text from pg_proc p"
                        " where p.pronamespace = 'public'::regnamespace and p.prosecdef"
                        " and not coalesce(p.proconfig @> array[:pin], false)"
                    ),
                    {"pin": PINNED},
                )
            )
            .scalars()
            .all()
        )
    assert loose == []


async def test_no_definer_function_is_executable_by_public(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as conn:
        open_to_all = (
            (
                await conn.execute(
                    bound_text(
                        "select p.oid::regprocedure::text from pg_proc p"
                        " where p.pronamespace = 'public'::regnamespace and p.prosecdef"
                        " and has_function_privilege('public', p.oid, 'execute')"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert open_to_all == []


async def test_activation_username_mismatch_is_for_the_app_role_only(
    owner_engine: AsyncEngine,
) -> None:
    fn = "public.activation_username_mismatch(text, inet)"
    async with owner_engine.connect() as conn:
        allowed = {
            role: (
                await conn.execute(
                    bound_text("select has_function_privilege(:r, :f, 'execute')"),
                    {"r": role, "f": fn},
                )
            ).scalar_one()
            for role in ("labtrack_app", "labtrack_admin", "labtrack_admin_login", "labtrack_maint")
        }
    assert allowed == {
        "labtrack_app": True,
        "labtrack_admin": False,
        "labtrack_admin_login": False,
        "labtrack_maint": False,
    }


async def test_every_table_forces_rls(owner_engine: AsyncEngine) -> None:
    """A new table must be ENABLE + FORCE row level security, or be listed in NO_RLS on purpose."""
    async with owner_engine.connect() as conn:
        loose = (
            await conn.execute(
                bound_text(
                    "select c.relname from pg_class c"
                    " where c.relnamespace = 'public'::regnamespace and c.relkind in ('r', 'p')"
                    " and not (c.relrowsecurity and c.relforcerowsecurity)"
                )
            )
        ).scalars()
        assert set(loose) == NO_RLS


async def test_no_view_bypasses_rls(owner_engine: AsyncEngine) -> None:
    """A view runs with its owner's rights unless security_invoker is set, and a materialized
    view has no RLS at all: either would read the tables above without the policies."""
    async with owner_engine.connect() as conn:
        bypass = (
            await conn.execute(
                bound_text(
                    "select relname from pg_class where relnamespace = 'public'::regnamespace"
                    " and (relkind = 'm' or (relkind = 'v' and not coalesce("
                    "'security_invoker=true' = any(reloptions), false)))"
                )
            )
        ).scalars()
        assert list(bypass) == []


async def test_definer_functions_have_one_signature(owner_engine: AsyncEngine) -> None:
    """`create or replace` with a new argument list adds an overload instead of replacing."""
    async with owner_engine.connect() as conn:
        duplicated = (
            await conn.execute(
                bound_text(
                    "select proname from pg_proc where pronamespace = 'public'::regnamespace"
                    " and prosecdef group by proname having count(*) > 1"
                )
            )
        ).scalars()
        assert list(duplicated) == []


async def test_definer_execute_matrix(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as conn:
        rows = (
            await conn.execute(
                bound_text(
                    "select r, p.oid::regprocedure::text from pg_proc p"
                    " cross join unnest(array['labtrack_app', 'labtrack_admin',"
                    " 'labtrack_admin_login', 'labtrack_maint', 'labtrack_push']) r"
                    " where p.pronamespace = 'public'::regnamespace and p.prosecdef"
                    " and has_function_privilege(r, p.oid, 'execute')"
                )
            )
        ).all()
    granted: dict[str, set[str]] = {role: set() for role in EXECUTE_MATRIX}
    for role, fn in rows:
        granted[role].add(fn)
    assert granted == EXECUTE_MATRIX
