"""The "Эмчид үзүүлэх" summary as a PDF (Phase 7.5; docs/06 §8; H15, H38).

Read as the requesting user, under the row policies (nothing a reader could not see). The
patient's questions for the doctor come first, then the transplant, allergies, the medicines
taken now with their dose as entered, confirmed lab values of the period as printed (the lab's
range, the server's flag as text and glyph - never a judgement), the doctor's targets, recent
events and the latest vital signs. No computation beyond the server's own flags; no names of
anyone but the patient; nothing logged.

A4, Noto Sans (Mongolian Cyrillic). Rendered by WeasyPrint off the event loop.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from html import escape
from typing import Any, LiteralString
from zoneinfo import ZoneInfo

import anyio.to_thread
from PIL import ImageFile
from sqlalchemy.ext.asyncio import AsyncSession

from labtrack.api.numbers import num
from labtrack.db.sql import bound_text
from labtrack.summary_codes import _CODES

# their own loggers may print fragments of the page: errors only (rule 3)
for _name in ("weasyprint", "fontTools"):
    logging.getLogger(_name).setLevel(logging.ERROR)

_UB = ZoneInfo("Asia/Ulaanbaatar")

_LABELS: dict[str, dict[str, str]] = {
    "mn": {
        "title": "Эмчид үзүүлэх хураангуй",
        "made": "Бэлтгэсэн",
        "period": "Хугацаа",
        "born": "Төрсөн огноо",
        "questions": "Эмчээс асуух асуултууд",
        "no_questions": "Асуулт бичээгүй.",
        "transplant": "Шилжүүлэн суулгалт",
        "allergies": "Харшил",
        "no_allergies": "Харшил бүртгээгүй.",
        "nka": "Мэдэгдэж буй харшилгүй (өөрөө баталсан, {day}).",
        "meds": "Одоо уудаг эм",
        "no_meds": "Эм бүртгээгүй.",
        "labs": "Шинжилгээний хариу (батлагдсан)",
        "no_labs": "Энэ хугацаанд батлагдсан хариу алга.",
        "by_user": "* Огноо, цагийг хэрэглэгч оруулсан эсвэл зассан (апп уншаагүй).",
        "targets": "Эмчийн тогтоосон зорилт",
        "events": "Сүүлийн үйл явдал",
        "vitals": "Амин үзүүлэлт (сүүлийн хэмжилт)",
        "date": "Огноо",
        "test": "Шинжилгээ",
        "value": "Утга (хэвлэснээр)",
        "range": "Лабын лавлах",
        "flag": "Лабын лавлахтай харьцуулсан",
        "since": "-с хойш",
        "footer": (
            "Өвчтөн өөрөө оруулж, шинжилгээний хариуг өөрөө хянаж баталсан мэдээлэл. Тэмдэглэгээ"
            " нь тухайн лабын лавлахтай харьцуулсан тэмдэг — үнэлгээ биш. Эх баримттай тулгана уу."
        ),
    },
    "en": {
        "title": "Summary for the doctor",
        "made": "Prepared",
        "period": "Period",
        "born": "Date of birth",
        "questions": "Questions for the doctor",
        "no_questions": "No questions written.",
        "transplant": "Transplant",
        "allergies": "Allergies",
        "no_allergies": "No allergy recorded.",
        "nka": "No known allergies (self-reported, confirmed {day}).",
        "meds": "Medicines taken now",
        "no_meds": "No medicine recorded.",
        "labs": "Lab results (confirmed)",
        "no_labs": "No confirmed results in this period.",
        "by_user": "* Date/time entered or corrected by a person, not read from the report.",
        "targets": "Doctor's targets",
        "events": "Recent events",
        "vitals": "Vital signs (latest)",
        "date": "Date",
        "test": "Test",
        "value": "Value (as printed)",
        "range": "Lab's range",
        "flag": "Against the lab's range",
        "since": " onwards",
        "footer": (
            "Entered by the patient, who also checked and confirmed the lab results. Flags compare"
            " each value with that lab's own range - not an assessment. Check the source documents."
        ),
    },
}

_FLAGS: dict[str, dict[str, str]] = {
    "mn": {
        "normal": "● Лавлах хэмжээнд",
        "low": "↓ Лавлахаас бага",
        "high": "↑ Лавлахаас их",
        "critical_low": "⚠ Критик хязгаараас бага",
        "critical_high": "⚠ Критик хязгаараас их",
        "abnormal": "◆ Хэвийн бус гэж тэмдэглэсэн",
        "no_reference": "○ Лавлах байхгүй",
        "unknown": "○ Тулгах боломжгүй",
    },
    "en": {
        "normal": "● Within range",
        "low": "↓ Below range",
        "high": "↑ Above range",
        "critical_low": "⚠ Below critical limit",
        "critical_high": "⚠ Above critical limit",
        "abnormal": "◆ Marked abnormal",
        "no_reference": "○ No range",
        "unknown": "○ Cannot compare",
    },
}

_CSS = """
@page { size: A4; margin: 16mm 14mm 18mm 14mm;
        @bottom-center { content: counter(page) " / " counter(pages); font-size: 8pt; } }
body { font-family: "Noto Sans", sans-serif; font-size: 9.5pt; color: #111; }
h1 { font-size: 15pt; margin: 0 0 2mm; }
h2 { font-size: 11pt; margin: 5mm 0 1.5mm; border-bottom: 0.4pt solid #888; }
p, li { margin: 0.6mm 0; }
.meta { color: #333; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; vertical-align: top; padding: 0.8mm 1.2mm;
         border-bottom: 0.3pt solid #ccc; }
th { font-weight: 600; }
.q { font-size: 10.5pt; }
.foot { margin-top: 6mm; font-size: 8pt; color: #333; }
"""


@dataclass(frozen=True, slots=True)
class SummaryInput:
    patient_id: Any
    months: int
    lang: str


def _day(value: date | datetime | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.astimezone(_UB).strftime("%Y.%m.%d")
    return value.strftime("%Y.%m.%d")


def _partial(value: date | None, precision: str) -> str:
    if value is None:
        return "—"
    if precision == "year":
        return str(value.year)
    if precision == "month":
        return value.strftime("%Y.%m")
    return _day(value)


def _code(kind: str, value: object, lang: str) -> str:
    """A stored code in words (the app's own label), or the code itself."""
    return _CODES[kind][lang].get(str(value), str(value)) if value else ""


def _e(value: object) -> str:
    return escape("" if value is None else str(value))


def _dose(regimen: dict[str, Any] | None, lang: str = "en") -> str:
    """The dose as entered: "08:00 · 2 mg, 20:00 · 1.5 mg" (no computation)."""
    if not regimen:
        return "—"
    unit = regimen.get("dose_unit_text") or _code("unit", regimen.get("dose_unit"), lang)
    schedule = regimen.get("schedule") or {}
    if schedule.get("type") == "prn":
        raw = regimen.get("dose_amount")
        amount = num(Decimal(str(raw))) if raw is not None else None
        return f"PRN {amount} {unit}".strip() if amount else "PRN"
    times = schedule.get("times") or []
    parts = [f"{t.get('at', '')} · {t.get('amount', '')} {unit}".strip() for t in times]
    days = schedule.get("days")
    text = ", ".join(parts) or "—"
    return f"[{', '.join(str(d) for d in days)}] {text}" if days else text


async def _rows(db: AsyncSession, sql: LiteralString, **params: object) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in await db.execute(bound_text(sql), params)]


async def gather(db: AsyncSession, patient_id: object, months: int) -> dict[str, Any]:
    """What the summary shows, read as the caller (row policies apply)."""
    today = datetime.now(_UB).date()
    since = today - timedelta(days=round(months * 30.44))
    since_at = datetime.combine(since, time(), _UB)
    p = {"p": patient_id}
    profile = await _rows(
        db, "select full_name, birth_date, sex::text as sex from patients where id = :p", **p
    )
    return {
        "today": today,
        "since": since,
        "profile": profile[0] if profile else None,
        "questions": await _rows(
            db,
            "select text from doctor_questions where patient_id = :p and status = 'open'"
            " order by created_at",
            **p,
        ),
        "transplants": await _rows(
            db,
            "select organ::text as organ, transplant_date, date_precision, hospital,"
            " graft_status::text as graft_status from transplants where patient_id = :p"
            " order by transplant_date desc nulls last",
            **p,
        ),
        "allergies": await _rows(
            db,
            "select substance, reaction, severity from allergies where patient_id = :p"
            " order by substance",
            **p,
        ),
        "nka": await _rows(
            db, "select confirmed_on from no_known_allergies where patient_id = :p", **p
        ),
        "meds": await _rows(
            db,
            "select m.name, m.strength, m.form, m.started_on,"
            " (select jsonb_build_object('dose_amount', g.dose_amount::text,"
            " 'dose_unit', g.dose_unit,"
            " 'dose_unit_text', g.dose_unit_text, 'schedule', g.schedule)"
            " from medication_regimens g where g.medication_id = m.id and g.voided_at is null"
            " and g.effective_from <= :today order by g.effective_from desc, g.seq desc limit 1)"
            " as regimen"
            " from medications m where m.patient_id = :p"
            " and (m.stopped_on is null or m.stopped_on > :today)"
            " and (m.planned_end_on is null or m.planned_end_on >= :today)"
            " order by m.name",
            today=today,
            **p,
        ),
        "labs": await _rows(
            db,
            "select r.collected_at, r.collected_precision,"
            " (r.source = 'typed' or r.collected_edited) as collected_by_user,"
            " coalesce(t.name_mn, v.raw_name)"
            " as name_mn, coalesce(t.name_en, v.raw_name) as name_en, v.raw_value, v.raw_unit,"
            " v.ref_text, v.flag::text as flag"
            " from lab_reports r join lab_results v on v.report_id = r.id"
            " and v.patient_id = r.patient_id left join test_catalog t on t.code = v.test_code"
            " where r.patient_id = :p and r.status = 'confirmed' and r.collected_at >= :since"
            " order by r.collected_at desc, r.id, v.position limit 400",
            since=since_at,
            **p,
        ),
        "targets": await _rows(
            db,
            "select test_code, low, high, unit, valid_from from patient_targets"
            " where patient_id = :p and (valid_to is null or valid_to >= :today)"
            " and valid_from <= :today order by test_code",
            today=today,
            **p,
        ),
        "events": await _rows(
            db,
            "select kind::text as kind, title, started_on, ended_on from clinical_events"
            " where patient_id = :p and coalesce(ended_on, started_on) >= :since"
            " order by started_on desc limit 30",
            since=since,
            **p,
        ),
        "vitals": await _rows(
            db,
            "select distinct on (kind) kind::text as kind, value, unit, measured_at from vitals"
            " where patient_id = :p order by kind, measured_at desc",
            **p,
        ),
    }


def render_html(data: dict[str, Any], lang: str) -> str:  # noqa: PLR0912, PLR0915 - one page, in order
    t = _LABELS[lang]
    flags = _FLAGS[lang]
    person = data["profile"] or {}
    out = [
        f"<html lang='{lang}'><head><meta charset='utf-8'><style>{_CSS}</style></head><body>",
        f"<h1>{_e(t['title'])}</h1>",
        f"<p><b>{_e(person.get('full_name'))}</b> · {_e(t['born'])}: "
        f"{_day(person.get('birth_date'))}</p>",
        f"<p class='meta'>{_e(t['made'])}: {_day(data['today'])} · {_e(t['period'])}: "
        f"{_day(data['since'])}{_e(t['since'])}</p>",
        f"<h2>{_e(t['questions'])}</h2>",
    ]
    if data["questions"]:
        out.append(
            "<ol>"
            + "".join(f"<li class='q'>{_e(q['text'])}</li>" for q in data["questions"])
            + "</ol>"
        )
    else:
        out.append(f"<p>{_e(t['no_questions'])}</p>")
    if data["transplants"]:
        out.append(f"<h2>{_e(t['transplant'])}</h2><ul>")
        for x in data["transplants"]:
            out.append(
                f"<li>{_e(_code('organ', x['organ'], lang))}"
                f" · {_partial(x['transplant_date'], x['date_precision'])}"
                f" · {_e(x['hospital'])} · {_e(_code('graft', x['graft_status'], lang))}</li>"
            )
        out.append("</ul>")
    out.append(f"<h2>{_e(t['allergies'])}</h2>")
    if data["allergies"]:
        out.append(
            "<ul>"
            + "".join(
                "<li>"
                + _e(
                    " — ".join(
                        str(v)
                        for v in (
                            a["substance"],
                            a["reaction"],
                            _code("severity", a["severity"], lang),
                        )
                        if v
                    )
                )
                + "</li>"
                for a in data["allergies"]
            )
            + "</ul>"
        )
    elif data["nka"]:  # a dated statement (Q39) - never said for "none recorded" (H17)
        out.append(f"<p>{_e(t['nka'].format(day=_day(data['nka'][0]['confirmed_on'])))}</p>")
    else:
        out.append(f"<p>{_e(t['no_allergies'])}</p>")
    out.append(f"<h2>{_e(t['meds'])}</h2>")
    if data["meds"]:
        out.append("<table>")
        for m in data["meds"]:
            name = " · ".join(str(v) for v in (m["name"], m["strength"], m["form"]) if v)
            out.append(f"<tr><td>{_e(name)}</td><td>{_e(_dose(m['regimen'], lang))}</td></tr>")
        out.append("</table>")
    else:
        out.append(f"<p>{_e(t['no_meds'])}</p>")
    if data["targets"]:
        out.append(f"<h2>{_e(t['targets'])}</h2><ul>")
        for g in data["targets"]:
            bounds = " – ".join(v for v in (num(g["low"]), num(g["high"])) if v)
            out.append(
                f"<li>{_e(g['test_code'])}: {_e(bounds)} {_e(g['unit'])}"
                f" ({_day(g['valid_from'])})</li>"
            )
        out.append("</ul>")
    out.append(f"<h2>{_e(t['labs'])}</h2>")
    if data["labs"]:
        out.append(
            f"<table><thead><tr><th>{_e(t['date'])}</th><th>{_e(t['test'])}</th>"
            f"<th>{_e(t['value'])}</th><th>{_e(t['range'])}</th><th>{_e(t['flag'])}</th>"
            "</tr></thead><tbody>"
        )
        for r in data["labs"]:
            name = r["name_mn"] if lang == "mn" else r["name_en"]
            value = " ".join(v for v in (r["raw_value"], r["raw_unit"]) if v)
            flag = flags.get(r["flag"] or "unknown", flags["unknown"])
            out.append(
                # a date the person typed in or changed is marked, never shown as the lab's (Q65)
                f"<tr><td>{_day(r['collected_at'])}{'*' if r['collected_by_user'] else ''}</td>"
                f"<td>{_e(name)}</td><td>{_e(value)}</td>"
                f"<td>{_e(r['ref_text'] or '—')}</td><td>{_e(flag)}</td></tr>"
            )
        out.append("</tbody></table>")
        if any(r["collected_by_user"] for r in data["labs"]):
            out.append(f"<p>{_e(t['by_user'])}</p>")
    else:
        out.append(f"<p>{_e(t['no_labs'])}</p>")
    if data["events"]:
        out.append(f"<h2>{_e(t['events'])}</h2><ul>")
        for ev in data["events"]:
            span = _day(ev["started_on"]) + (f" – {_day(ev['ended_on'])}" if ev["ended_on"] else "")
            title = f" — {_e(ev['title'])}" if ev["title"] else ""
            out.append(f"<li>{span} · {_e(_code('event', ev['kind'], lang))}{title}</li>")
        out.append("</ul>")
    if data["vitals"]:
        out.append(f"<h2>{_e(t['vitals'])}</h2><ul>")
        for v in data["vitals"]:
            out.append(
                f"<li>{_e(_code('vital', v['kind'], lang))}: {_e(num(v['value']))}"
                f" {_e(v['unit'] or '')} ({_day(v['measured_at'])})</li>"
            )
        out.append("</ul>")
    out.append(f"<p class='foot'>{_e(t['footer'])}</p></body></html>")
    return "".join(out)


def _pdf(html: str) -> bytes:
    # Importing WeasyPrint turns on Pillow's LOAD_TRUNCATED_IMAGES for the whole process, which
    # would let a truncated upload through the document checks (3.2): off again at once (the
    # checks also refuse truncated images themselves). The summary has no images of its own.
    from weasyprint import HTML  # type: ignore[import-untyped]  # noqa: PLC0415 - heavy, only here

    ImageFile.LOAD_TRUNCATED_IMAGES = False
    # refuse every resource fetch: the page is self-contained (no images, links or font URLs)
    pdf: bytes = HTML(string=html, url_fetcher=_no_fetch).write_pdf()
    return pdf


def _no_fetch(url: str, *args: object, **kwargs: object) -> dict[str, object]:
    raise ValueError("no external resources in the summary")


# at most two renders at a time, apart from the app's other threads (each may take seconds)
_RENDERS = anyio.CapacityLimiter(2)


async def summary_pdf(db: AsyncSession, patient_id: object, months: int, lang: str) -> bytes:
    data = await gather(db, patient_id, months)
    html = render_html(data, lang if lang in _LABELS else "mn")
    # a render cannot be cut off midway: its bounds are this limiter and the page's size
    # (400 lab rows, 30 events, current medicines only)
    return await anyio.to_thread.run_sync(_pdf, html, limiter=_RENDERS)
