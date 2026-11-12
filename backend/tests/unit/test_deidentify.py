"""Text for the AI without who the person is (extraction/deidentify.py; Q50, 4.5 reviews)."""

import pytest

from labtrack.extraction.deidentify import deidentify

PROFILE = "Дорж Батболд"


def _run(*lines: str, profile: str = PROFILE):  # type: ignore[no-untyped-def]
    return deidentify([(1, line) for line in lines], profile)


def _text(*lines: str, profile: str = PROFILE) -> str:
    return str(_run(*lines, profile=profile).text)


SECRETS = (
    "Дорж",
    "Батболд",
    "Иванов",
    "Smith",
    "УБ90010112",
    "AA12345678",
    "1990/01/01",
    "01.01.1990",
    "1990 оны",
    "Сүхбаатар",
    "bat@example.mn",
    "+976 9911 2233",
    "99112233",
)


@pytest.mark.parametrize(
    "line",
    [
        "ОВОГ: Дорж РЕГИСТР: УБ90010112",
        "НЭР: Батболд ТӨРСӨН: 1990/01/01",
        "Регистрийн дугаар: AA12345678",
        "Утасны дугаар 99112233",
        "Хаягийн мэдээлэл: Сүхбаатар дүүрэг",
        "ФИО: Иванов Иван Иванович",
        "Дата рождения: 01.01.1990",
        "Patient name: John Smith",
        "DOB 1990/01/01 Sex: M",
        "Phone: +976 9911 2233",
        "Өвчтөн: Дорж Батболд",
        "Р/Д: УБ90010112",
        "E-mail: bat@example.mn",
        "Төрсөн огноо: 1990/01/01",
        "Төрсөн он сар өдөр: 1990 оны 01 сарын 01",
        "Овог нэр: Дорж Батболд",
    ],
)
def test_identity_fields_never_leave(line: str) -> None:
    text = _text(line, "Glucose 5.4 mmol/L 3.9 - 6.1")
    for secret in SECRETS:
        assert secret not in text
    assert "Glucose 5.4 mmol/L 3.9 - 6.1" in text


def test_what_may_still_name_the_person_is_masked() -> None:
    text = _text(
        "Захиалсан: Батболдын эмч, баталгаажуулсан Д.Батболд",
        "Код УБ90010112, bat@example.mn, +976 9911 2233",
        "Signed for Batbold",  # the profile's name in Latin letters
    )
    for secret in ("Батболд", "УБ90010112", "bat@example.mn", "9911", "Batbold"):
        assert secret not in text
    assert "[нэр]" in text


@pytest.mark.parametrize(
    "line",
    [
        "Креатинин 0.70 мг/дл 0.7 - 1.2",
        "Такролимус 4.19 нг/мл 3 - 15 L",
        "Циклоспорин C2 1250 нг/мл 1000-1500",  # four-digit ranges are not phones
        "Фибриноген 1250 мг/л 2000 - 4000",
        "HBV DNA <20 IU/mL",
        "CMV PCR 1.2x10^3 copies/mL",
        "BK virus 12500000 copies/mL",  # a long number with its unit is a measurement
        "Collected: 2025-08-18 07:30",
        "Нийт уураг 72.9 г/л 66.0 - 87.0",
        "Average glucose 6.1",
        "eGFR (age-adjusted) 85 mL/min/1.73m2",
        "Возраст 18-60: 62-115 мкмоль/л",  # an age-dependent range is not an age field
        "Пол М 62-115",
        "Натрий 140 ммоль/л 136-145",  # a short name never cuts into a test name
    ],
)
def test_results_ranges_units_and_dates_stay(line: str) -> None:
    assert line in _text(line, profile="Нат Ан")


def test_an_identity_cell_on_a_result_line_is_masked_and_the_rest_stays() -> None:
    text = _text("Нэр: Батболд Дээж авсан: 2025-08-18")
    assert "Батболд" not in text
    assert "2025-08-18" in text


def test_a_table_header_with_name_stays() -> None:
    line = "Шинжилгээний нэр Хариу Нэгж Лавлах хэмжээ"
    assert line in _text(line)


def test_values_under_an_identity_header_are_dropped() -> None:
    result = _run(
        "Нэр Нас Хүйс Төрсөн огноо", "Бат Дорж 35 Эр 1989.03.12", "Na 140 ммоль/л 136-145"
    )
    assert "1989.03.12" not in result.text
    assert "Na 140 ммоль/л 136-145" in result.text
    assert result.dropped_lines == 2


def test_the_printed_name_is_read_for_the_check_but_not_sent() -> None:
    result = _run("ОВОГ: Сүх НЭР: Тэмүүлэн", "Na 140 ммоль/л 136-145")
    assert (result.identity.family_name, result.identity.given_name) == ("Сүх", "Тэмүүлэн")
    assert "Тэмүүлэн" not in result.text
    russian = _run("ФИО: Иванов Иван Иванович").identity
    assert (russian.family_name, russian.given_name) == ("Иванов", "Иван")
    english = _run("Patient name: John Smith").identity
    assert (english.family_name, english.given_name) == ("Smith", "John")


def test_pages_are_marked() -> None:
    result = deidentify([(1, "Na 140"), (2, "K 4.1")], "Бо Ан")
    assert result.text == "--- хуудас 1 ---\nNa 140\n--- хуудас 2 ---\nK 4.1"


@pytest.mark.parametrize(
    ("line", "family", "given"),
    [
        ("Овог нэр: Дорж Батболд", "Дорж", "Батболд"),
        ("Эцэг/эхийн нэр: Дорж Нэр: Батболд", "Дорж", "Батболд"),
        ("Эмчийн нэр: Сүх Нэр: Батболд", None, "Батболд"),  # the doctor is not the person
    ],
)
def test_the_persons_name_not_a_parents_or_doctors(
    line: str, family: str | None, given: str
) -> None:
    identity = _run(line, "Na 140 ммоль/л 136-145").identity
    assert (identity.family_name, identity.given_name) == (family, given)


@pytest.mark.parametrize(
    ("profile", "printed"),
    [
        ("Мөнх-Очир", "Munkh-Ochir"),
        ("Мөнх-Очир", "Monkh-Ochir"),
        ("Мөнх-Очир", "Mönh-Ochir"),
        ("Түмэн", "Tümen"),
        ("Batbold", "Батболд"),  # a profile in Latin letters, a report in Cyrillic
    ],
)
def test_other_spellings_of_the_name_are_masked(profile: str, printed: str) -> None:
    assert printed not in _text(f"Signed for {printed}", profile=profile)


@pytest.mark.parametrize(
    "line",
    ["Contact 88112233 /night/", "Утас 99112233 2025/01/02", "Sample 12345678 a/b"],
)
def test_a_long_number_without_a_real_unit_is_masked(line: str) -> None:
    assert not any(n in _text(line) for n in ("88112233", "99112233", "12345678"))
