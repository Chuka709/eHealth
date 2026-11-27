"""Which catalog test a printed row is (core/matching.py), against the real seed synonyms."""

import json
from pathlib import Path

import pytest

from labtrack.core.matching import is_urine, match_test, name_keys
from labtrack.core.text import normalize_name

SEED = Path(__file__).resolve().parents[3] / "seed" / "lab_tests.json"


@pytest.fixture(scope="module")
def synonyms() -> dict[str, str]:
    tests = json.loads(SEED.read_text(encoding="utf-8"))["tests"]
    out: dict[str, str] = {}
    for t in tests:
        for name in filter(None, [t["code"], t["name_mn"], t["name_en"], t.get("name_ru"),
                                  *t["synonyms"]]):  # fmt: skip
            out.setdefault(normalize_name(name), t["code"])
    return out


@pytest.mark.parametrize(
    ("raw", "specimen", "code"),
    [
        # names as the УНТЭ lab prints them
        ("Глюкоз", "цус", "GLU"),
        ("Нийт билирубин", "цус", "TBIL"),
        ("Асат", "цус", "AST"),
        ("Алат", "цус", "ALT"),
        ("Шүлтлэг фосфотаза", "цус", "ALP"),
        ("ГГТ", "цус", "GGT"),
        ("CРБ", "цус", "CRP"),  # Latin C, Cyrillic РБ
        ("Креатинин", "цус", "CREA"),
        ("Мочевин", "цус", "UREA"),
        ("HbA1c", "цус", "HBA1C"),
        ("RBC3", "цус", "RBC"),  # analyser channel digit
        ("RDW-CV1", "цус", "RDW"),
        ("NEUT#", "цус", "NEUT_ABS"),
        ("LYMPH#", "цус", "LYMPH_ABS"),
        ("APTT", "цус", "APTT"),
        ("INR", "цус", "INR"),
        ("Такролимус.", "цус", "TAC"),
        ("Альбумин/креатинин харьцаа", "шээс", "UACR"),
        ("Уураг/креатинин харьцаа", "шээс", "UPCR"),
        ("Такролимус", None, "TAC"),  # no specimen printed: a blood-only test is fine
        ("ГГТ", None, "GGT"),
        ("Альбумин", "Ийлдэс", "ALB"),  # serum is blood
        ("Creatinine", "Plasma", "CREA"),
    ],
)
def test_printed_names_find_their_test(
    synonyms: dict[str, str], raw: str, specimen: str | None, code: str
) -> None:
    assert match_test(raw, specimen, synonyms) == code


@pytest.mark.parametrize(
    ("raw", "specimen"),
    [
        ("Креатинин", "шээс"),  # urine creatinine is not the blood test
        ("Альбумин", "шээс"),
        ("Глюкоз", "шээс"),
        ("Эритроцит", "шээс"),  # dipstick blood, not the red cell count
        ("Уураг/креатинин харьцаа", "цус"),  # a urine ratio never in a blood panel
        ("NEUT%", "цус"),  # a percentage is not the absolute count
        ("RDW-SD1", "цус"),  # RDW-SD (fL) is not RDW-CV (%)
        ("NRBC#1", "цус"),
        ("Альфа амилаза", "цус"),  # not in the catalog
        ("ЛДГ IFFC", "цус"),
        ("Креатинин", None),  # both blood and urine: never without a specimen
        ("Глюкоз", None),
        ("Альбумин", None),
        ("WBC", None),
        ("PCR", None),  # a viral PCR, not the protein/creatinine ratio
        ("микроальбумин", "шээс"),  # a concentration, not the ratio
        ("CyA2", "цус"),  # the 2-hour cyclosporin level is not the trough
        ("Циклоспорин2", "цус"),
        ("Альбумин", "асцитын шингэн"),  # another fluid is not blood
        ("Креатинин", "дренаж"),
        ("Уураг/креатинин харьцаа", "плеврийн шингэн"),
    ],
)
def test_near_misses_and_other_specimens_are_left_to_the_person(
    synonyms: dict[str, str], raw: str, specimen: str
) -> None:
    assert match_test(raw, specimen, synonyms) is None


def test_the_persons_own_synonym_comes_first(synonyms: dict[str, str]) -> None:
    mine = {normalize_name("Альфа амилаза"): "GLU"}  # whatever they chose in review
    assert match_test("Альфа амилаза", "цус", synonyms, mine) == "GLU"
    assert match_test("Глюкоз", "цус", synonyms, mine) == "GLU"


def test_name_keys_strip_only_a_channel_digit() -> None:
    assert name_keys("RBC3") == (normalize_name("RBC3"), normalize_name("RBC"))
    assert name_keys("25-OH D") == (normalize_name("25-OH D"),)
    assert name_keys("T4") == (normalize_name("T4"),)
    assert name_keys("IgG4") == (normalize_name("IgG4"),)
    assert name_keys("25(OH)D3") == (normalize_name("25(OH)D3"),)
    assert name_keys("EO#1") == (normalize_name("EO#1"), normalize_name("EO#"))


def test_urine_is_told_by_the_printed_specimen() -> None:
    assert is_urine("шээс")
    assert is_urine("Urine (spot)")
    assert is_urine("моча")
    assert not is_urine("цус")
    assert not is_urine(None)


def test_the_full_printed_name_comes_before_a_shortened_one() -> None:
    catalog = {normalize_name("RBC3"): "RBC"}
    mine = {normalize_name("RBC"): "WBC"}
    assert match_test("RBC3", "цус", catalog, mine) == "RBC"
