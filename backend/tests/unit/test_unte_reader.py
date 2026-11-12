"""The УНТЭ lab reader on synthetic page layouts (no real report in the repository).

Positions copy the real layout (points): name 25, result 220, range ~319, unit 408, flag 496;
the column header's words sit at 25/220/366/405/496. Names and values are made up.
"""

import dataclasses

from labtrack.extraction.readers import read_locally
from labtrack.extraction.readers.unte import READER
from labtrack.extraction.text_pdf import group_lines
from labtrack.extraction.types import Line, Page, Word

HEADER = (
    ("ШИНЖЛЭГДЭХҮҮН", 25),
    ("ХАРИУ", 220),
    ("ЛАВЛАХ", 366),
    ("ХЭМЖЭЭ", 405),
    ("АНХААРУУЛГА", 496),
)
IDENTITY = (
    (("Улсын", 24), ("Нэгдүгээр", 63), ("Төв", 127), ("Эмнэлэг", 150), ("ОВОГ:", 278),
     ("Тестийн", 314), ("РЕГИСТР:", 450), ("АА00000000", 505)),
    (("Лаборатори", 24), ("НЭР:", 278), ("Зохиомол", 314), ("ТӨРСӨН:", 450),
     ("2000/01/01", 505)),
    (("example.mn", 24), ("НАС:", 278), ("25", 314), ("ХҮЙС:", 450), ("эр", 505)),
)  # fmt: skip


def line(top: float, *words: tuple[str, float]) -> Line:
    return Line(tuple(Word(text=t, x0=x, x1=x + 6 * len(t), top=top) for t, x in words))


def row(top: float, name: str, value: str, ref: str, unit: str = "", flag: str = "") -> Line:
    words = [(w, 25 + 30 * i) for i, w in enumerate(name.split())]
    words += [(w, 220 + 40 * i) for i, w in enumerate(value.split())]
    words += [(w, 319 + 20 * i) for i, w in enumerate(ref.split())]
    words += [(unit, 408)] if unit else []
    words += [(flag, 496)] if flag else []
    return line(top, *words)


def panel_start(top: float, panel: str, specimen: str) -> list[Line]:
    return [
        line(top, ("ТӨРӨЛ:", 25), (panel, 60), ("БАРКОД:", 300), ("00000001", 340)),
        line(top + 13, ("СОРЬЦ:", 25), (specimen, 60), ("ТӨХӨӨРӨМЖ:", 300), ("X1", 360)),
        line(top + 26, ("ИЛГЭЭСЭН:", 25)),
        line(top + 39, *HEADER),
    ]


def panel_end(top: float) -> list[Line]:
    return [
        line(top, ("H", 25), ("-", 32), ("лавлах", 38), ("хэмжээнээс", 70), ("их", 120)),
        line(top + 13, ("Илгээсэн:", 25), ("А.Тест", 70), ("2025-08-18", 140), ("00:00:00", 190)),
        line(top + 26, ("Шинжилсэн:", 25), ("Б.Тест", 70), ("2025-08-18", 140), ("10:15:21", 190)),
        line(
            top + 39,
            ("Баталгаажуулсан:", 25),
            ("В.Тест", 100),
            ("2025-08-18", 140),
            ("12:05:52", 190),
        ),
    ]


def identity(top: float) -> list[Line]:
    return [line(top + 14 * i, *words) for i, words in enumerate(IDENTITY)]


def footer(top: float, page: int) -> list[Line]:
    return [
        line(top, ("Хуудас", 25), (str(page), 60), (".", 66), ("Хэвлэсэн:", 70)),
        line(top + 13, ("Байршил:", 25), ("Монгол", 70), ("улс,", 110), ("хот", 300)),
        line(
            top + 26,
            ("Улсын", 25),
            ("Нэгдүгээр", 60),
            ("Төв", 110),
            ("Эмнэлгийн", 130),
            ("Амбулатори", 230),
        ),
    ]


def report_pages() -> tuple[Page, ...]:
    page1 = [
        line(22, ("Эрүүл", 395), ("Мэндийн", 416)),
        line(54, ("ШИНЖИЛГЭЭНИЙ", 210), ("ХАРИУ", 337)),
        *identity(99),
        *panel_start(150, "Биохими", "цус"),
        row(215, "Глюкоз", "5.37", "4.11 - 6.38", "ммоль/л"),
        row(228, "Шүлтлэг фосфотаза", "134.4", "40.0 - 129.0", "нэгж/л", "H"),
        row(241, "CРБ", "0.53", "0 - 5.0", "мг/л", "LL"),
        *panel_end(260),
        *panel_start(330, "Клиник хими -Шээс", "шээс"),
        row(395, "Эпител", "1.6", "0 - 45", "/µL"),
        *footer(780, 1),
    ]
    page2 = [
        *identity(38),
        # the panel goes on over the page break, before any header
        row(96, "Креатинин", "200", "20.0 - 300.0", "мг/дл"),
        row(109, "Булингар", "-", "(-) Clear - *"),
        row(122, "Өнгө", "STRAW 02", "-"),
        row(135, "Уробилиноген", "normal", "<1.0 Normal -", "мг/дл"),
        *panel_end(160),
        line(
            300,
            ("Лабораторийн", 25),
            ("шинжилгээний", 90),
            ("хариу", 170),
            ("нь", 230),
            ("онош", 330),
        ),
        *footer(780, 2),
    ]
    return (Page(1, tuple(page1)), Page(2, tuple(page2)))


def test_recognises_the_layout_and_reads_panels_with_dates_and_specimen() -> None:
    pages = report_pages()
    assert READER.recognises(pages)
    document = read_locally(pages)
    assert document is not None
    assert document.reader == "unte.v1"
    blood, urine = document.reports
    assert (blood.lab_name, blood.panel_name, blood.specimen) == (
        "Улсын Нэгдүгээр Төв Эмнэлэг",
        "Биохими",
        "цус",
    )
    assert (blood.collected_raw, blood.reported_raw) == (
        "2025-08-18 00:00:00",
        "2025-08-18 12:05:52",
    )
    assert [
        (r.raw_name, r.raw_value, r.ref_text, r.raw_unit, r.lab_flag) for r in blood.results
    ] == [
        ("Глюкоз", "5.37", "4.11 - 6.38", "ммоль/л", None),
        ("Шүлтлэг фосфотаза", "134.4", "40.0 - 129.0", "нэгж/л", "H"),
        ("CРБ", "0.53", "0 - 5.0", "мг/л", "LL"),  # kept as printed; flags come from core
    ]
    assert (urine.panel_name, urine.specimen) == ("Клиник хими -Шээс", "шээс")


def test_a_panel_goes_on_over_the_page_break_past_the_identity_block() -> None:
    document = read_locally(report_pages())
    assert document is not None
    urine = document.reports[1]
    assert [(r.raw_name, r.page) for r in urine.results] == [
        ("Эпител", 1),
        ("Креатинин", 2),
        ("Булингар", 2),
        ("Өнгө", 2),
        ("Уробилиноген", 2),
    ]


def test_qualitative_values_and_text_ranges_stay_as_printed() -> None:
    document = read_locally(report_pages())
    assert document is not None
    rows = {r.raw_name: r for r in document.reports[1].results}
    assert (rows["Булингар"].raw_value, rows["Булингар"].ref_text) == ("-", "(-) Clear - *")
    assert (rows["Өнгө"].raw_value, rows["Өнгө"].ref_text) == ("STRAW 02", "-")
    assert (rows["Уробилиноген"].raw_value, rows["Уробилиноген"].ref_text) == (
        "normal",
        "<1.0 Normal -",
    )


def test_footers_legends_signatures_and_the_disclaimer_are_never_rows() -> None:
    document = read_locally(report_pages())
    assert document is not None
    names = {r.raw_name for report in document.reports for r in report.results}
    assert not names & {"Хуудас", "Байршил:", "Илгээсэн:", "H", "Лабораторийн", "Улсын"}
    assert sum(len(r.results) for r in document.reports) == 8


def test_the_printed_identity_is_read_for_the_name_check_but_never_kept_or_shown() -> None:
    document = read_locally(report_pages())
    assert document is not None
    assert (document.identity.family_name, document.identity.given_name) == ("Тестийн", "Зохиомол")
    kept = repr(document.to_raw_output()) + repr(document) + repr(document.identity)
    snippets = " ".join(r.snippet for report in document.reports for r in report.results)
    for printed in ("Тестийн", "Зохиомол", "АА00000000", "2000/01/01"):
        assert printed not in kept
        assert printed not in snippets


def test_columns_follow_the_header_not_fixed_positions() -> None:
    shift = 15.0

    def moved(page: Page) -> Page:
        return Page(
            page.number,
            tuple(
                Line(tuple(dataclasses.replace(w, x0=w.x0 + shift) for w in ln.words))
                for ln in page.lines
            ),
        )

    document = read_locally(tuple(moved(p) for p in report_pages()))
    assert document is not None
    first = document.reports[0].results[1]
    assert (first.raw_name, first.raw_value, first.raw_unit, first.lab_flag) == (
        "Шүлтлэг фосфотаза",
        "134.4",
        "нэгж/л",
        "H",
    )


def test_other_documents_are_not_read_here() -> None:
    other = (
        Page(1, (line(20, ("Laboratory", 25), ("report", 90)), row(40, "Na", "140", "135 - 145"))),
    )
    assert not READER.recognises(other)
    assert read_locally(other) is None
    # the layout with no result row at all is not a reading either (AI or by hand)
    empty = (Page(1, tuple(panel_start(150, "Биохими", "цус") + footer(780, 1))),)
    assert read_locally(empty) is None


def test_words_close_in_height_make_one_line_left_to_right() -> None:
    words = [
        Word("b", 50, 56, 100.8),
        Word("a", 25, 31, 100.0),
        Word("c", 25, 31, 113.0),
    ]
    assert [ln.text for ln in group_lines(words)] == ["a b", "c"]
