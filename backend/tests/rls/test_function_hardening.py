"""Every SECURITY DEFINER function is pinned and closed to PUBLIC (CLAUDE.md rule 1, docs/03).

Generic, so a function added by a later migration is covered without a new test.
"""

from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

PINNED = "search_path=pg_catalog, public, pg_temp"


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
