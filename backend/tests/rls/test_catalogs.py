"""Catalog seeding and access (docs/03; seed/*.json)."""

import os
from pathlib import Path

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.core.text import normalize_name
from labtrack.db.sql import bound_text
from labtrack.seed import run

from .conftest import as_user, make_user, scalar

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
async def seeded() -> None:
    seed_dir = Path(os.environ.get("SEED_DIR", "/seed"))
    stats = await run(os.environ["MIGRATION_DATABASE_URL"], seed_dir)
    assert stats.tests == 61
    assert stats.medications == 30
    again = await run(os.environ["MIGRATION_DATABASE_URL"], seed_dir)  # idempotent
    assert again == stats


async def test_catalog_is_readable_and_read_only_for_users(
    seeded: None, app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    me = await make_user(admin_engine)
    async with as_user(app_engine, me) as conn:
        assert await scalar(conn, bound_text("select count(*) from test_catalog")) == 61
        tac = await scalar(
            conn,
            bound_text(
                "select related_test_code from medication_catalog where code = 'TACROLIMUS'"
            ),
        )
        assert tac == "TAC"
    with pytest.raises(DBAPIError, match="permission denied"):
        async with as_user(app_engine, me) as conn:
            await conn.execute(bound_text("update test_catalog set physio_max = 1"))


async def test_catalog_has_no_reference_ranges(seeded: None, app_engine: AsyncEngine) -> None:
    async with app_engine.connect() as conn:
        cols = (
            await conn.execute(
                bound_text(
                    "select column_name from information_schema.columns"
                    " where table_name = 'test_catalog'"
                )
            )
        ).scalars()
        assert not {c for c in cols if c.startswith(("ref_", "critical_"))}


async def test_seeded_synonyms_resolve_printed_variants(
    seeded: None, app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    me = await make_user(admin_engine)
    async with as_user(app_engine, me) as conn:
        code = await scalar(
            conn,
            bound_text("select test_code from test_synonyms where synonym_norm = :k"),
            {"k": normalize_name(" Лейкоциты ")},
        )
    assert code == "WBC"


async def test_learned_synonyms_are_private(
    seeded: None, app_engine: AsyncEngine, admin_engine: AsyncEngine
) -> None:
    alice, bob = await make_user(admin_engine), await make_user(admin_engine)
    key = normalize_name("Сонгинохайрхан эмнэлэг WBC")
    insert = bound_text(
        "insert into test_synonyms (test_code, synonym, synonym_norm, user_id)"
        " values ('WBC', 'x', :k, :u)"
    )
    count = bound_text("select count(*) from test_synonyms where synonym_norm = :k")
    async with as_user(app_engine, alice) as conn:
        await conn.execute(insert, {"k": key, "u": alice})
    async with as_user(app_engine, alice) as conn:
        assert await scalar(conn, count, {"k": key}) == 1
    async with as_user(app_engine, bob) as conn:
        assert await scalar(conn, count, {"k": key}) == 0
    with pytest.raises(DBAPIError, match="row-level security"):
        async with as_user(app_engine, bob) as conn:
            await conn.execute(insert, {"k": normalize_name("other"), "u": alice})
