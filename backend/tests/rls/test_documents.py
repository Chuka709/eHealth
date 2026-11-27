"""RLS and shape for uploaded documents (0029; phi-table)."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, LiteralString
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import as_user, grant, make_patient, make_user, scalar

pytestmark = pytest.mark.db

_INSERT = bound_text(
    "insert into documents (id, patient_id, client_id, storage_key, mime_type, size_bytes,"
    " sha256) values (:i, :p, :c, :k, 'application/pdf', 1024, :h) returning id"
)
_COUNT = bound_text("select count(*) from documents where patient_id = :p")


async def _add(
    app_engine: AsyncEngine, user: UUID, patient: UUID, *, client: UUID | None = None
) -> UUID:
    doc = uuid4()
    async with as_user(app_engine, user) as conn:
        return UUID(
            str(
                await scalar(
                    conn,
                    _INSERT,
                    {
                        "i": doc,
                        "p": patient,
                        "c": client or uuid4(),
                        "k": f"{patient}/{doc}/original",
                        "h": sha256(doc.bytes).hexdigest(),
                    },
                )
            )
        )


async def _count(app_engine: AsyncEngine, user: UUID | None, patient: UUID) -> int:
    async with as_user(app_engine, user) as conn:
        return int(await scalar(conn, _COUNT, {"p": patient}))


async def test_owner_uploads_reads_and_the_database_records_the_writer(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    doc = await _add(app_engine, owner, patient)
    assert await _count(app_engine, owner, patient) == 1
    async with as_user(app_engine, owner) as conn:
        await conn.execute(
            bound_text("update documents set status = 'queued' where id = :i"), {"i": doc}
        )
        row = (
            await conn.execute(
                bound_text("select status, recorded_by, updated_by from documents where id = :i"),
                {"i": doc},
            )
        ).one()
    assert (row.status, row.recorded_by, row.updated_by) == ("queued", owner, owner)


async def test_stored_identity_never_changes(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    doc = await _add(app_engine, owner, patient)
    statements: tuple[LiteralString, ...] = (
        "update documents set storage_key = 'x' where id = :i",
        "update documents set sha256 = repeat('0', 64) where id = :i",
        "update documents set patient_id = gen_random_uuid() where id = :i",
        "update documents set client_id = gen_random_uuid() where id = :i",
        "update documents set mime_type = 'image/png' where id = :i",
        "update documents set recorded_by = null where id = :i",
    )
    for sql in statements:
        with pytest.raises(DBAPIError, match="permission denied"):
            async with as_user(app_engine, owner) as conn:
                await conn.execute(bound_text(sql), {"i": doc})


async def test_a_retried_upload_and_the_same_file_are_one_row(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    client = uuid4()
    await _add(app_engine, owner, patient, client=client)
    with pytest.raises(IntegrityError):
        await _add(app_engine, owner, patient, client=client)
    doc = uuid4()
    async with as_user(app_engine, owner) as conn:
        first = await scalar(
            conn, bound_text("select sha256 from documents where patient_id = :p"), {"p": patient}
        )
    with pytest.raises(IntegrityError):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                _INSERT,
                {
                    "i": doc,
                    "p": patient,
                    "c": uuid4(),
                    "k": f"{patient}/{doc}/original",
                    "h": first,
                },
            )


@pytest.mark.parametrize(
    ("key", "mime", "size"),
    [
        ("../../etc/passwd", "application/pdf", 10),
        ("{p}/{d}/original", "text/html", 10),
        ("{p}/{d}/original", "application/pdf", 0),
        ("{p}/{d}/original", "application/pdf", 30 * 1024 * 1024),
    ],
)
async def test_the_database_refuses_odd_files(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, key: str, mime: str, size: int
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    doc = uuid4()
    with pytest.raises(IntegrityError):
        async with as_user(app_engine, owner) as conn:
            await conn.execute(
                bound_text(
                    "insert into documents (id, patient_id, client_id, storage_key, mime_type,"
                    " size_bytes, sha256) values (:i, :p, :c, :k, :m, :s, :h)"
                ),
                {
                    "i": doc,
                    "p": patient,
                    "c": uuid4(),
                    "k": key.format(p=patient, d=doc),
                    "m": mime,
                    "s": size,
                    "h": "a" * 64,
                },
            )


async def test_stranger_sees_and_changes_nothing(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, stranger = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    doc = await _add(app_engine, owner, patient)
    assert await _count(app_engine, stranger, patient) == 0
    async with as_user(app_engine, stranger) as conn:
        for sql in (
            "update documents set status = 'failed' where id = :i",
            "delete from documents where id = :i",
        ):
            assert (await conn.execute(bound_text(sql), {"i": doc})).rowcount == 0
    with pytest.raises(DBAPIError, match="row-level security"):
        await _add(app_engine, stranger, patient)


@pytest.mark.parametrize(
    ("expires", "revoked", "visible"),
    [(None, False, 1), (datetime.now(UTC) - timedelta(minutes=1), False, 0), (None, True, 0)],
)
async def test_shared_access_respects_expiry_and_revocation(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    expires: datetime | None,
    revoked: bool,
    visible: int,
) -> None:
    owner, doctor = await make_user(owner_engine), await make_user(owner_engine, "doctor")
    patient = await make_patient(app_engine, owner)
    await _add(app_engine, owner, patient)
    await grant(app_engine, owner, patient, doctor, "doctor", expires=expires, revoked=revoked)
    assert await _count(app_engine, doctor, patient) == visible


@pytest.mark.parametrize("level", ["doctor", "viewer"])
async def test_readers_cannot_upload_or_change(
    app_engine: AsyncEngine, owner_engine: AsyncEngine, level: str
) -> None:
    owner, reader = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    doc = await _add(app_engine, owner, patient)
    await grant(app_engine, owner, patient, reader, level)
    async with as_user(app_engine, reader) as conn:
        assert (
            await conn.execute(
                bound_text("update documents set status = 'failed' where id = :i"), {"i": doc}
            )
        ).rowcount == 0
        assert (
            await conn.execute(bound_text("delete from documents where id = :i"), {"i": doc})
        ).rowcount == 0
    with pytest.raises(DBAPIError, match="row-level security"):
        await _add(app_engine, reader, patient)


async def test_caregiver_uploads_but_never_deletes_the_owners_document(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner, carer = await make_user(owner_engine), await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await grant(app_engine, owner, patient, carer, "caregiver")
    mine = await _add(app_engine, carer, patient)
    owners = await _add(app_engine, owner, patient)
    async with as_user(app_engine, carer) as conn:
        assert (
            await conn.execute(bound_text("delete from documents where id = :i"), {"i": owners})
        ).rowcount == 0
        assert (
            await conn.execute(bound_text("delete from documents where id = :i"), {"i": mine})
        ).rowcount == 1


async def test_no_user_context_and_other_roles_see_nothing(
    app_engine: AsyncEngine,
    owner_engine: AsyncEngine,
    admin_engine: AsyncEngine,
    admin_login_engine: AsyncEngine,
    maint_engine: AsyncEngine,
    push_engine: AsyncEngine,
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await _add(app_engine, owner, patient)
    assert await _count(app_engine, None, patient) == 0
    engines: Any = (admin_engine, admin_login_engine, maint_engine, push_engine)
    for engine in engines:
        with pytest.raises(DBAPIError, match="permission denied"):
            async with engine.connect() as conn:
                await conn.execute(bound_text("select count(*) from documents"))


async def test_deleting_the_profile_deletes_its_documents(
    app_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    owner = await make_user(owner_engine)
    patient = await make_patient(app_engine, owner)
    await _add(app_engine, owner, patient)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(bound_text("delete from patients where id = :p"), {"p": patient})
        assert await scalar(conn, _COUNT, {"p": patient}) == 0
