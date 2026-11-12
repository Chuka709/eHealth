"""Results typed in by hand and documents moved to the right profile (Phase 5.4; 0037)."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import ClientFactory
from .test_documents import _scanned
from .test_lab_reports import _report, _uploaded
from .test_lab_review import code  # noqa: F401 - fixture
from .test_patients import REQUIRED, _child_birth, _create, _signed_in
from .test_records import _grant, _profile

pytestmark = pytest.mark.db


@pytest.fixture
async def client(client_from: ClientFactory) -> AsyncIterator[AsyncClient]:
    async with client_from() as c:
        yield c


def _typed(test: str, **extra: Any) -> dict[str, Any]:
    return {
        "collected_at": "2025-06-01T08:10:00+08:00",
        "collected_precision": "minute",
        "results": [
            {"raw_name": "Креатинин", "raw_value": "1,2", "raw_unit": "г/дл",
             "ref_text": "0.7 - 1.3", "test_code": test},
            {"raw_name": "Өнгө", "raw_value": "шар"},
        ],
        **extra,
    }  # fmt: skip


async def test_a_typed_in_result_is_a_draft_checked_like_a_read_one(
    client: AsyncClient,
    owner_engine: AsyncEngine,
    code: str,  # noqa: F811
) -> None:
    _, h, base = await _profile(client, owner_engine)
    document_id = await _uploaded(client, base, h)
    await _scanned(owner_engine, document_id, "failed")  # a photo: not read (Q50)
    r = await client.post(f"{base}/reports", headers=h, json=_typed(code, document_id=document_id))
    assert r.status_code == 201, r.text
    report = r.json()
    assert (report["status"], report["method"], report["document_id"], report["source"]) == (
        "needs_review",
        None,
        document_id,
        "typed",
    )
    first, _second = sorted(report["results"], key=lambda x: x["position"])
    assert (first["flag"], first["value_canonical"]) == ("normal", "12.0")
    # typed from a photo: whose name is on it is the person's to confirm (H2)
    assert "name_missing" in first["issues"]
    r = await client.patch(
        f"{base}/reports/{report['id']}", headers=h, json={"acknowledge": ["name_missing"]}
    )
    assert r.status_code == 200, r.text
    for row in sorted(r.json()["results"], key=lambda x: x["position"]):
        for issue in [i for i in row["issues"] if i not in row["acknowledged"]]:
            r2 = await client.patch(
                f"{base}/reports/{report['id']}/results/{row['id']}",
                headers=h,
                json={"acknowledge": [issue]},
            )
            assert r2.status_code == 200, r2.text
    r = await client.post(f"{base}/reports/{report['id']}/confirm", headers=h)
    assert r.status_code == 200, r.text
    doc = await client.get(f"{base}/documents/{document_id}", headers=h)
    assert doc.json()["status"] == "confirmed"


@pytest.mark.parametrize(
    "body",
    [
        {"collected_at": "2025-06-01T08:10:00", "collected_precision": "minute"},  # no zone
        {"collected_at": "2025-06-01T08:10:00+08:00"},  # day or minute?
        {"collected_at": "2025-06-01T08:10:00+08:00", "collected_precision": "day",
         "results": []},
    ],
)  # fmt: skip
async def test_a_typed_in_result_says_its_date(
    client: AsyncClient,
    owner_engine: AsyncEngine,
    code: str,  # noqa: F811
    body: dict[str, Any],
) -> None:
    _, h, base = await _profile(client, owner_engine)
    r = await client.post(f"{base}/reports", headers=h, json={**_typed(code), **body})
    if "collected_precision" not in body:
        payload = _typed(code)
        payload.pop("collected_precision")
        r = await client.post(f"{base}/reports", headers=h, json=payload)
    assert r.status_code == 422


async def _two_profiles(
    client: AsyncClient, owner_engine: AsyncEngine, sex: str = "unknown"
) -> tuple[dict[str, str], str, str]:
    _, h, base = await _profile(client, owner_engine)
    status, other = await _create(
        client, h, full_name="Сараа", relation="child", birth_date=_child_birth(), sex=sex
    )
    assert status == 201, other
    target = f"/api/v1/patients/{other['id']}"
    r = await client.post(f"{base}/documents/{await _uploaded(client, base, h)}/move",
                          headers=h, json={"patient_id": other["id"]})  # fmt: skip
    assert (r.status_code, r.json()["code"]) == (403, "consent.profile_required")
    body = {"items": REQUIRED, "patient_id": other["id"]}
    assert (await client.post("/api/v1/me/consents", json=body, headers=h)).status_code == 204
    return h, base, target


async def test_a_document_moves_with_its_drafts_and_is_checked_again(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    h, base, other = await _two_profiles(client, owner_engine)
    document_id = await _uploaded(client, base, h)
    await _scanned(owner_engine, document_id, "needs_review")
    report = await _report(owner_engine, base, document_id)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text("update lab_results set acknowledged = issues where report_id = :r"),
            {"r": report},
        )
        # as a reading leaves it: a run of the document
        await conn.execute(
            bound_text(
                "with run as (insert into extraction_runs (patient_id, document_id, method,"
                " reader, pipeline_version) select patient_id, document_id, 'local', 'unte.v1',"
                " 'v1' from lab_reports where id = :r returning id)"
                " update lab_reports set extraction_run_id = (select id from run) where id = :r"
            ),
            {"r": report},
        )
    target = other.rsplit("/", 1)[1]
    r = await client.post(
        f"{base}/documents/{document_id}/move", headers=h, json={"patient_id": target}
    )
    assert r.status_code == 204, r.text
    assert (await client.get(f"{base}/documents/{document_id}", headers=h)).status_code == 404
    moved = await client.get(f"{other}/documents/{document_id}/reports", headers=h)
    assert moved.status_code == 200, moved.text
    [draft] = moved.json()
    rows = draft["results"]
    assert len(rows) == 2
    # nothing accepted moves along; the printed name was never checked for this profile
    assert all(x["acknowledged"] == [] for x in rows)
    assert all("name_missing" in x["issues"] for x in rows)
    assert draft["name_match_score"] is None


async def test_a_confirmed_or_foreign_move_is_refused(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    h, base, other = await _two_profiles(client, owner_engine)
    document_id = await _uploaded(client, base, h)
    await _scanned(owner_engine, document_id, "needs_review")
    await _report(owner_engine, base, document_id, status="confirmed")
    target = other.rsplit("/", 1)[1]
    r = await client.post(
        f"{base}/documents/{document_id}/move", headers=h, json={"patient_id": target}
    )
    assert (r.status_code, r.json()["code"]) == (409, "review.move_confirmed")
    # to a profile the user cannot write
    _, hs = await _signed_in(client, owner_engine)
    _, foreign = await _create(client, hs, full_name="Бусад", relation="self")
    other_doc = await _uploaded(client, base, h)
    r = await client.post(
        f"{base}/documents/{other_doc}/move", headers=h, json={"patient_id": foreign["id"]}
    )
    assert (r.status_code, r.json()["code"]) == (403, "review.move_target")
    # a reader of the source profile moves nothing
    doctor, hd = await _signed_in(client, owner_engine)
    await _grant(owner_engine, base, doctor, "doctor")
    r = await client.post(
        f"{base}/documents/{other_doc}/move", headers=hd, json={"patient_id": target}
    )
    assert r.status_code == 403


async def test_a_paper_result_has_no_name_to_check_and_a_critical_one_is_told(
    client: AsyncClient,
    owner_engine: AsyncEngine,
    code: str,  # noqa: F811
) -> None:
    owner, h, base = await _profile(client, owner_engine)
    carer, hc = await _signed_in(client, owner_engine)
    await _grant(owner_engine, base, carer, "caregiver")
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into caregiver_alert_settings (patient_id, caregiver_user_id,"
                " critical_result) values (cast(:p as uuid), :c, true)"
            ),
            {"p": base.rsplit("/", 1)[1], "c": carer},
        )
    body = _typed(code)
    body["results"] = [
        {"raw_name": "Кали", "raw_value": "2,0", "raw_unit": "г/л", "ref_text": "3.5 - 5.1",
         "critical_text": "< 2.5", "test_code": code},
    ]  # fmt: skip
    r = await client.post(f"{base}/reports", headers=h, json=body)
    assert r.status_code == 201, r.text
    [row] = r.json()["results"]
    assert not {"name_missing", "name_mismatch"} & set(row["issues"])
    assert r.json()["has_unconfirmed_critical"]

    async def notices(headers: dict[str, str]) -> list[str]:
        async with owner_engine.connect() as conn:
            user = carer if headers is hc else owner
            rows = await conn.execute(
                bound_text("select kind from notifications where user_id = :u"), {"u": user}
            )
            return [x.kind for x in rows]

    assert await notices(hc) == ["critical_pending"]  # an alerting caregiver
    assert await notices(h) == []  # not the person who typed it


async def test_a_moved_document_is_told_on_the_new_profile_and_still_opens(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    h, base, other = await _two_profiles(client, owner_engine)
    document_id = await _uploaded(client, base, h)
    await _scanned(owner_engine, document_id, "needs_review")
    report = await _report(owner_engine, base, document_id)
    patient = base.rsplit("/", 1)[1]
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "with run as (insert into extraction_runs (patient_id, document_id, method,"
                " reader, pipeline_version) select patient_id, document_id, 'local', 'unte.v1',"
                " 'v1' from lab_reports where id = :r returning id)"
                " update lab_reports set extraction_run_id = (select id from run) where id = :r"
            ),
            {"r": report},
        )
        await conn.execute(
            bound_text(
                "insert into notifications (user_id, kind, patient_id, entity_id, title_key)"
                " select user_id, 'review_ready', patient_id, :d, 'notification.review_ready'"
                " from patient_access where patient_id = cast(:p as uuid) and level = 'owner'"
            ),
            {"d": document_id, "p": patient},
        )
    target = other.rsplit("/", 1)[1]
    r = await client.post(
        f"{base}/documents/{document_id}/move", headers=h, json={"patient_id": target}
    )
    assert r.status_code == 204, r.text
    async with owner_engine.connect() as conn:
        notices = (
            await conn.execute(
                bound_text(
                    "select patient_id::text as p, kind from notifications where entity_id = :d"
                ),
                {"d": document_id},
            )
        ).all()
    assert [(n.p, n.kind) for n in notices] == [(target, "review_ready")]
    # the file still opens on the new profile (its stored key is kept)
    f = await client.get(f"{other}/documents/{document_id}/file", headers=h)
    assert f.status_code == 200, f.text


async def test_a_moved_row_is_flagged_by_the_new_profiles_sex(
    client: AsyncClient, owner_engine: AsyncEngine
) -> None:
    h, base, other = await _two_profiles(client, owner_engine, sex="female")
    document_id = await _uploaded(client, base, h)
    await _scanned(owner_engine, document_id, "needs_review")
    report = await _report(owner_engine, base, document_id)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "update lab_results set raw_value = '100', value_numeric = 100,"
                " ref_text = 'Эр: 62-115 / Эм: 44-97', ref_low = null, ref_high = null"
                " where report_id = :r and position = 0"
            ),
            {"r": report},
        )
    target = other.rsplit("/", 1)[1]
    r = await client.post(
        f"{base}/documents/{document_id}/move", headers=h, json={"patient_id": target}
    )
    assert r.status_code == 204, r.text
    [draft] = (await client.get(f"{other}/documents/{document_id}/reports", headers=h)).json()
    row = next(x for x in draft["results"] if x["position"] == 0)
    # the range printed for women, for the profile it now belongs to
    assert (row["ref_low"], row["ref_high"], row["flag"]) == ("44", "97", "high")


async def test_a_failed_document_moves_too(client: AsyncClient, owner_engine: AsyncEngine) -> None:
    h, base, other = await _two_profiles(client, owner_engine)
    document_id = await _uploaded(client, base, h)
    await _scanned(owner_engine, document_id, "failed")
    target = other.rsplit("/", 1)[1]
    r = await client.post(
        f"{base}/documents/{document_id}/move", headers=h, json={"patient_id": target}
    )
    assert r.status_code == 204, r.text
    r = await client.get(f"{other}/documents/{document_id}", headers=h)
    assert r.json()["status"] == "failed"


async def test_a_typed_critical_draft_leaves_no_notice_on_the_old_profile(
    client: AsyncClient,
    owner_engine: AsyncEngine,
    code: str,  # noqa: F811
) -> None:
    h, base, other = await _two_profiles(client, owner_engine)
    carer, _ = await _signed_in(client, owner_engine)
    await _grant(owner_engine, base, carer, "caregiver")
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into caregiver_alert_settings (patient_id, caregiver_user_id,"
                " critical_result) values (cast(:p as uuid), :c, true)"
            ),
            {"p": base.rsplit("/", 1)[1], "c": carer},
        )
    document_id = await _uploaded(client, base, h)
    await _scanned(owner_engine, document_id, "failed")  # a photo, typed in by hand
    body = _typed(code, document_id=document_id)
    body["results"] = [
        {"raw_name": "Кали", "raw_value": "2,0", "raw_unit": "г/л", "ref_text": "3.5 - 5.1",
         "critical_text": "< 2.5", "test_code": code},
    ]  # fmt: skip
    r = await client.post(f"{base}/reports", headers=h, json=body)
    assert r.status_code == 201, r.text

    async def carer_notices() -> int:
        async with owner_engine.connect() as conn:
            return int(
                (
                    await conn.execute(
                        bound_text("select count(*) from notifications where user_id = :u"),
                        {"u": carer},
                    )
                ).scalar_one()
            )

    assert await carer_notices() == 1
    r = await client.post(
        f"{base}/documents/{document_id}/move",
        headers=h,
        json={"patient_id": other.rsplit("/", 1)[1]},
    )
    assert r.status_code == 204, r.text
    assert await carer_notices() == 0  # someone else's result: no longer told here
