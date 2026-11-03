import unicodedata

from hypothesis import given
from hypothesis import strategies as st

from labtrack.core.text import clean_device_label, normalize_name, normalize_unit

# Cyrillic letters that print identically to Latin ones.
_HOMOGLYPHS = {
    "A": "А",
    "B": "В",
    "E": "Е",
    "K": "К",
    "M": "М",
    "H": "Н",
    "O": "О",
    "P": "Р",
    "C": "С",
    "T": "Т",
    "Y": "У",
    "X": "Х",
    "a": "а",
    "e": "е",
    "o": "о",
    "p": "р",
    "c": "с",
    "y": "у",
    "x": "х",
}


def test_printed_variants_of_the_same_name_share_one_key() -> None:
    variants = ["HGB", "Hgb", " H G B ", "HGB:", "Н" + "GB", "(HGB)", "h-g-b"]
    assert {normalize_name(v) for v in variants} == {"hgb"}


def test_mongolian_names_ignore_case_spacing_and_latin_lookalikes() -> None:
    assert normalize_name("Креатинин") == normalize_name("КРЕАТИНИН ")
    assert normalize_name("Креатинин") == normalize_name("Kpeатинин")  # Latin K, p, e


@given(st.text(alphabet=st.sampled_from(sorted(_HOMOGLYPHS)), min_size=1, max_size=20))
def test_swapping_any_lookalike_letter_never_changes_the_key(latin: str) -> None:
    cyrillic = "".join(_HOMOGLYPHS[ch] for ch in latin)
    assert normalize_name(cyrillic) == normalize_name(latin)


@given(st.text(max_size=40))
def test_normalisation_is_idempotent(text: str) -> None:
    once = normalize_name(text)
    assert normalize_name(once) == once


def test_unit_keys_unify_micro_signs_case_and_spaces() -> None:
    assert normalize_unit("μmol/L") == normalize_unit("µmol/l") == normalize_unit(" µmol / L")
    assert normalize_unit("ммоль/л") == "ммоль/л"


@given(st.text(max_size=300))
def test_device_labels_never_carry_invisible_characters(label: str) -> None:
    cleaned = clean_device_label(label)
    if cleaned is None:
        return
    assert len(cleaned) <= 100
    assert cleaned == cleaned.strip()
    assert not any(unicodedata.category(ch) in {"Cc", "Cf"} for ch in cleaned)


def test_device_label_examples() -> None:
    assert clean_device_label("Pixel 8") == "Pixel 8"
    rtl, pop = chr(0x202E), chr(0x202C)  # bidi override + pop
    assert clean_device_label(f"{rtl}Энэ төхөөрөмж{pop}") == "Энэ төхөөрөмж"
    assert clean_device_label("a\u200b\u200bb  \n c") == "ab c"
    assert clean_device_label("\u200b \t") is None
    assert clean_device_label(None) is None
