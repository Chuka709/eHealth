"""The doctor's summary PDF and the owner's export (Phase 7.5)."""

import io
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pdfplumber
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack.db.sql import bound_text

from .conftest import ClientFactory
from .test_caregivers import _username
from .test_dashboard import seeded  # noqa: F401 - fixture (the catalog)
from .test_patients import _create, _signed_in

pytestmark = pytest.mark.db


async def _profile(c: AsyncClient, owner_engine: AsyncEngine) -> tuple[dict[str, str], str, UUID]:
    _, owner = await _signed_in(c, owner_engine)
    _, profile = await _create(c, owner, full_name="Батболд", relation="self")
    pid = UUID(profile["id"])
    now = datetime.now(UTC)
    async with owner_engine.connect() as conn, conn.begin():
        await conn.execute(
            bound_text(
                "insert into doctor_questions (patient_id, client_id, text, status)"
                " values (:p, :c, 'Тунгаа хэзээ шалгуулах вэ?', 'open')"
            ),
            {"p": pid, "c": uuid4()},
        )
        report = uuid4()
        await conn.execute(
            bound_text(
                "insert into lab_reports (id, patient_id, lab_name, collected_at, status,"
                " confirmed_at) values (:r, :p, 'Лаб', :at, 'confirmed', now())"
            ),
            {"r": report, "p": pid, "at": now - timedelta(days=10)},
        )
        await conn.execute(
            bound_text(
                "insert into lab_results (report_id, patient_id, position, test_code, raw_name,"
                " raw_value, raw_unit, value_numeric, value_canonical, unit_canonical, ref_text,"
                " flag, collected_at) values (:r, :p, 0, 'TAC', 'Tacrolimus', '10.50', 'ng/mL',"
                " 10.50, 10.50, 'ng/mL', '5-10', 'high', :at)"
            ),
            {"r": report, "p": pid, "at": now - timedelta(days=10)},
        )
    return owner, f"/api/v1/patients/{pid}", pid


async def test_the_summary_pdf_puts_the_questions_first_and_values_as_printed(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, _ = await _profile(c, owner_engine)
        r = await c.get(f"{base}/summary.pdf", headers=owner)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.headers["cache-control"] == "no-store"
        assert "Батболд" not in r.headers["content-disposition"]
        assert r.content.startswith(b"%PDF")
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        assert "Батболд" in text
        assert text.index("Тунгаа хэзээ шалгуулах вэ?") < text.index("10.50")
        assert "Лавлахаас их" in text  # the server's flag, as text


async def test_the_export_is_the_owners_and_the_fhir_numbers_are_exact(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, _ = await _profile(c, owner_engine)
        r = await c.get(f"{base}/export.json", headers=owner)
        assert r.status_code == 200
        data = json.loads(r.content)
        assert data["profile"]["full_name"] == "Батболд"
        assert data["lab_results"][0]["raw_value"] == "10.50"
        r = await c.get(f"{base}/export.fhir.json", headers=owner)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/fhir+json")
        assert b'"value":10.50' in r.content  # exact, never through a float
        bundle = json.loads(r.content)
        kinds = [e["resource"]["resourceType"] for e in bundle["entry"]]
        assert kinds[0] == "Patient"
        assert "Observation" in kinds
        # a doctor with access may print the summary, but the export is the owner's
        doc_id, doc = await _signed_in(c, owner_engine)
        await c.post(
            f"{base}/share-invitations",
            json={"username": await _username(owner_engine, doc_id), "level": "doctor", "days": 7},
            headers=owner,
        )
        [inv] = (await c.get("/api/v1/me/share-invitations", headers=doc)).json()
        await c.post(
            "/api/v1/me/share-invitations/respond",
            json={"invitation_id": inv["id"], "accept": True},
            headers=doc,
        )
        assert (await c.get(f"{base}/summary.pdf", headers=doc)).status_code == 200
        for path in ("export.json", "export.fhir.json"):
            assert (await c.get(f"{base}/{path}", headers=doc)).status_code == 403
        _, stranger = await _signed_in(c, owner_engine)
        assert (await c.get(f"{base}/summary.pdf", headers=stranger)).status_code == 404


def test_making_pdfs_leaves_truncated_images_refused() -> None:
    """WeasyPrint turns Pillow's LOAD_TRUNCATED_IMAGES on when imported (3.2 needs it off)."""
    from PIL import ImageFile  # noqa: PLC0415

    from labtrack import summary  # noqa: PLC0415

    summary._pdf("<p>x</p>")
    assert ImageFile.LOAD_TRUNCATED_IMAGES is False


def test_only_plain_decimals_become_fhir_numbers() -> None:
    from labtrack.export import _number  # noqa: PLC0415

    assert _number("10.50") == "10.50"
    assert _number("-0.5") == "-0.5"
    for bad in ("NaN", "Infinity", "1_000", "+1", ".5", "1e5", None):
        assert _number(bad) is None


def test_the_summary_escapes_what_people_typed() -> None:
    from datetime import date  # noqa: PLC0415

    from labtrack.summary import render_html  # noqa: PLC0415

    html = render_html(
        {
            "today": date(2026, 1, 1), "since": date(2025, 7, 1),
            "profile": {"full_name": "<b>X</b>", "birth_date": None},
            "questions": [{"text": '<img src="file:///etc/passwd">'}],
            "transplants": [], "allergies": [], "meds": [], "targets": [], "labs": [],
            "events": [], "vitals": [],
        },
        "mn",
    )  # fmt: skip
    assert "<img" not in html
    assert "&lt;img" in html
    assert "<b>X</b>" not in html
