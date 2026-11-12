"""Builds the synthetic eval cases in eval/cases/ (made up - no real person or result).

Each case is a printout as words placed on pages (`input.words.json`, read by
labtrack.extraction.evaluate) and the answer it should give (`expected.json`). Real documents
go in eval/local/<id>/{input.pdf, expected.json} and are never committed (PHI).

    python -I eval/make_synthetic.py
"""

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent / "cases"

# where the central-lab layout prints its columns (points from the left)
X_NAME, X_VALUE, X_REF, X_UNIT, X_FLAG = 40.0, 220.0, 268.0, 420.0, 500.0


def _words(x: float, text: str, step: float = 7.0) -> list[list[object]]:
    out: list[list[object]] = []
    for word in text.split():
        out.append([round(x, 1), word])
        x += step * (len(word) + 1)
    return out


class _Page:
    def __init__(self) -> None:
        self.lines: list[list[object]] = []
        self.top = 40.0

    def line(self, *parts: tuple[float, str]) -> None:
        words: list[list[object]] = []
        for x, text in parts:
            words += _words(x, text)
        self.lines.append([self.top, words])
        self.top += 14.0


def _central_lab(panels: list[dict[str, object]]) -> list[Any]:
    page = _Page()
    page.line((40, "Улсын Нэгдүгээр Төв Эмнэлгийн Төв лаборатори"))
    page.line((40, "ОВОГ: Зохиомол"), (220, "РЕГИСТР: ЖЖ00000000"))
    page.line((40, "НЭР: Туршилт"), (220, "ТӨРСӨН: 1980-01-01"))
    page.line((40, "НАС: 45"), (220, "ХҮЙС: Эр"))
    for panel in panels:
        page.line((40, f"ТӨРӨЛ: {panel['panel']}"), (300, "БАРКОД: 000001"))
        page.line((40, f"СОРЬЦ: {panel['specimen']}"), (300, "ТӨХӨӨРӨМЖ: Analyser"))
        page.line(
            (X_NAME, "ШИНЖЛЭГДЭХҮҮН"), (X_VALUE, "ХАРИУ"), (300, "ЛАВЛАХ"), (X_UNIT, "ХЭМЖЭЭ"),
            (X_FLAG, "АНХААРУУЛГА"),
        )  # fmt: skip
        for row in panel["rows"]:  # type: ignore[attr-defined]
            name, value, ref, unit, flag = row["printed"]
            parts = [(X_NAME, name), (X_VALUE, value)]
            parts += [(X_REF, ref)] if ref else []
            parts += [(X_UNIT, unit)] if unit else []
            parts += [(X_FLAG, flag)] if flag else []
            page.line(*parts)
        page.line((40, "H - лавлах хэмжээнээс их, L - лавлах хэмжээнээс бага"))
        day = panel["day"]
        page.line((40, f"Илгээсэн: Эмч {day} 00:00:00"))
        page.line((40, f"Шинжилсэн: Лаборант {day} 10:15:21"))
        page.line((40, f"Баталгаажуулсан: Эмч {day} 11:02:40"))
    return [page.lines]


def _foreign(rows: list[dict[str, object]], day: str) -> list[Any]:
    """A layout no local reader knows (as from a lab abroad): read by the AI only."""
    page = _Page()
    page.line((40, "Seoul Example Hospital - Laboratory Medicine"))
    page.line((40, "Patient: Test Person"), (300, "Sex/Age: M/45"))
    page.line((40, f"Collected: {day} 08:30"), (300, f"Reported: {day} 14:05"))
    page.line((40, "Test"), (220, "Result"), (300, "Unit"), (380, "Reference"), (480, "Flag"))
    for row in rows:
        name, value, ref, unit, flag = row["printed"]  # type: ignore[misc]
        parts = [(40, name), (220, value)]
        parts += [(300, unit)] if unit else []
        parts += [(380, ref)] if ref else []
        parts += [(480, flag)] if flag else []
        page.line(*parts)
    return [page.lines]


def row(
    name: str,
    value: str,
    ref: str | None,
    unit: str | None,
    flag: str | None = None,
    **answer: object,
) -> dict[str, object]:
    return {"printed": (name, value, ref, unit, flag), "answer": {"name": name, "value": value,
            "unit": unit, **answer}}  # fmt: skip


KIDNEY = [
    {
        "panel": "Биохими",
        "specimen": "Ийлдэс",
        "day": "2025-05-03",
        "rows": [
            row("Креатинин", "88", "62 - 115", "мкмоль/л", numeric="88", ref_low="62",
                ref_high="115", test_code="CREA"),
            row("Мочевин", "6,1", "2.5 - 7.5", "ммоль/л", numeric="6.1", ref_low="2.5",
                ref_high="7.5", test_code="UREA"),
            row("Кали", "5,4", "3.5 - 5.1", "ммоль/л", "H", numeric="5.4", ref_low="3.5",
                ref_high="5.1", test_code="K"),
            row("Натри", "139", "135 - 145", "ммоль/л", numeric="139", ref_low="135",
                ref_high="145", test_code="NA"),
            row("Глюкоз", "5.2", "3.9 - 6.1", "ммоль/л", numeric="5.2", ref_low="3.9",
                ref_high="6.1", test_code="GLU"),
        ],
    }
]  # fmt: skip

URINE = [
    {
        "panel": "Шээсний ерөнхий шинжилгээ",
        "specimen": "Шээс",
        "day": "2025-06-11",
        "rows": [
            # qualitative values and a range printed as text: kept as printed, never a number
            row("Уураг", "Сөрөг", "Сөрөг", None, qualitative="negative", ref_text="Сөрөг",
                test_code=None),
            row("Өнгө", "шар", None, None, test_code=None),
        ],
    }
]  # fmt: skip

TRANSPLANT_DRUGS = [
    {
        "panel": "Эмийн түвшин",
        "specimen": "Цус",
        "day": "2025-06-11",
        "rows": [
            row("Такролимус", "7.8", None, "нг/мл", numeric="7.8", test_code="TAC"),
            row("BK вирус", "<500", None, "copies/mL", numeric="500", comparator="<",
                test_code="BKV_DNA"),
            row("HBV ДНХ", "1.2E+06", None, "IU/mL", numeric="1.2E+06", test_code="HBV_DNA"),
        ],
    }
]  # fmt: skip

LIVER = [
    {
        "panel": "Элэгний сорил",
        "specimen": "Ийлдэс",
        "day": "2025-07-20",
        "rows": [
            row("АЛТ", "42", "0 - 40", "U/L", "H", numeric="42", ref_low="0", ref_high="40",
                test_code="ALT"),
            row("АСТ", "35", "0 - 40", "U/L", numeric="35", ref_low="0", ref_high="40",
                test_code="AST"),
            row("ГГТ", "60", "8 - 61", "U/L", numeric="60", ref_low="8", ref_high="61",
                test_code="GGT"),
            row("Нийт билирубин", "18,2", "3.4 - 20.5", "мкмоль/л", numeric="18.2",
                ref_low="3.4", ref_high="20.5", test_code="TBIL"),
            row("Альбумин", "41", "35 - 52", "г/л", numeric="41", ref_low="35", ref_high="52",
                test_code="ALB"),
            # a decimal comma in the range; a range by sex (none chosen: the profile's sex
            # is not the reader's to guess)
            row("Кали", "4,1", "3,5 - 5,1", "ммоль/л", numeric="4.1", ref_low="3.5",
                ref_high="5.1", test_code="K"),
            row("Креатинин", "70", "Эр: 62-115 / Эм: 44-97", "мкмоль/л", numeric="70",
                ref_text="Эр: 62-115 / Эм: 44-97", test_code="CREA"),
            # a test the catalog does not have: it must stay unknown, never guessed
            row("Зохиомол маркер", "1.2", "0 - 2", "ед", numeric="1.2", ref_low="0",
                ref_high="2", test_code=None),
        ],
    }
]  # fmt: skip

FOREIGN = [
    row("Creatinine", "1.02", "0.70 - 1.20", "mg/dL", numeric="1.02", ref_low="0.70",
        ref_high="1.20", test_code="CREA"),
    row("Tacrolimus", "6.4", None, "ng/mL", numeric="6.4", test_code="TAC"),
    row("ALT", "28", "0 - 41", "U/L", numeric="28", ref_low="0", ref_high="41",
        test_code="ALT"),
]  # fmt: skip


def _expected(panels: list[dict[str, object]], tags: list[str], note: str) -> dict[str, object]:
    return {
        "note": note,
        "tags": tags,
        "profile_name": "Зохиомол Туршилт",
        "reports": [
            {
                "collected": panel["day"],
                "results": [r["answer"] for r in panel["rows"]],  # type: ignore[attr-defined]
            }
            for panel in panels
        ],
    }


def main() -> None:
    cases = {
        "syn-kidney-biochem": (
            _central_lab(KIDNEY),
            _expected(KIDNEY, ["kidney", "mn", "local"], "Made up: central-lab layout"),
        ),
        "syn-transplant-drugs": (
            _central_lab(TRANSPLANT_DRUGS),
            _expected(TRANSPLANT_DRUGS, ["kidney", "liver", "mn", "local"], "Made up"),
        ),
        "syn-urine-general": (
            _central_lab(URINE),
            _expected(URINE, ["kidney", "mn", "local"], "Made up: qualitative values"),
        ),
        "syn-liver-panel": (
            _central_lab(LIVER),
            _expected(LIVER, ["liver", "mn", "local"], "Made up: with an unknown test"),
        ),
        "syn-foreign-layout": (
            _foreign(FOREIGN, "2025-08-02"),
            _expected(
                [{"day": "2025-08-02", "rows": FOREIGN}],
                ["kidney", "liver", "kr", "ai"],
                "Made up: a layout no local reader knows - read only with --ai",
            ),
        ),
    }
    for name, (pages, expected) in cases.items():
        folder = HERE / name
        folder.mkdir(parents=True, exist_ok=True)
        for file, data in (("input.words.json", {"pages": pages}), ("expected.json", expected)):
            (folder / file).write_text(
                json.dumps(data, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8",
                newline="\n",
            )
    print(f"{len(cases)} cases in {HERE}")


if __name__ == "__main__":
    main()
