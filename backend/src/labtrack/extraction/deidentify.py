"""The text sent to the AI, without who the person is (Q50, user decision 4.5).

Only the text layer of a PDF is ever sent - never the file, never a scan or photo (a name on
an image cannot be removed reliably). Before it leaves the server, word by word:
- an identity field's label and its value are replaced by "[хассан]": names (the value is
  also read here, on the server, for the name check - it is never sent or kept), register,
  card, passport, phone and sample numbers, birth dates; age and sex only as "label: value"
  (a range "Возраст 18-60" or "Пол М 62-115" stays). Labels are matched in Mongolian with
  their case endings ("Регистрийн", "Утасны"), Russian and English;
- an address line, a line of identity fields with nothing else, and the line of values under
  such a header (unless it reads as results) are dropped whole;
- what may still name the person is masked: register numbers (Cyrillic or Latin letters),
  e-mail, phone numbers written with "+", long digit runs that are not a measurement, and the
  profile's own name words - also in Latin letters - with Mongolian case endings.
A value, unit, range or test date is never masked: "1000-1500" or "12500000 copies/mL" stay.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Final, Literal

from labtrack.extraction.types import PrintedIdentity

Kind = Literal["family", "given", "full", "number", "birth", "age_sex", "address"]

# Cyrillic stems: matched as a word's start (case endings follow); Latin: whole words
_CYRILLIC: Final[tuple[tuple[str, Kind], ...]] = (
    ("овог", "family"),
    ("фамил", "family"),
    ("нэр", "given"),
    ("имя", "given"),
    ("отчеств", "given"),
    ("фио", "full"),
    ("ф.и.о", "full"),
    ("өвчтөн", "full"),
    ("үйлчлүүлэгч", "full"),
    ("эмчлүүлэгч", "full"),
    ("пациент", "full"),
    ("регистр", "number"),
    ("р/д", "number"),
    ("р.д", "number"),
    ("рд", "number"),
    ("иргэн", "number"),
    ("паспорт", "number"),
    ("дугаар", "number"),
    ("карт", "number"),
    ("утас", "number"),
    ("телефон", "number"),
    ("имэйл", "number"),
    ("и-мэйл", "number"),
    ("баркод", "number"),
    ("төрсөн", "birth"),
    ("рожд", "birth"),
    ("нас", "age_sex"),
    ("возраст", "age_sex"),
    ("хүйс", "age_sex"),
    ("пол", "age_sex"),
    ("хаяг", "address"),
    ("адрес", "address"),
)
_LATIN: Final[dict[str, Kind]] = {
    "surname": "family",
    "lastname": "family",
    "firstname": "given",
    "name": "full",
    "patient": "full",
    "client": "full",
    "mrn": "number",
    "id": "number",
    "passport": "number",
    "phone": "number",
    "tel": "number",
    "email": "number",
    "e-mail": "number",
    "barcode": "number",
    "№": "number",
    "dob": "birth",
    "birth": "birth",
    "birthdate": "birth",
    "age": "age_sex",
    "sex": "age_sex",
    "gender": "age_sex",
    "address": "address",
}
_HEADER_WORDS: Final = re.compile(
    r"үр\s*дүн|хариу|результат|result|лавлах|норма|reference|нэгж|unit|ед\.?\s*изм",
    re.IGNORECASE,
)
_RANGE: Final = re.compile(r"\d+(?:[.,]\d+)?\s*[-–—]\s*\d")
_UNIT_TOKEN: Final = re.compile(r"/|%|copies|копи|iu|ме\b|ед\b|г/л|g/l", re.IGNORECASE)
_REGISTER: Final = re.compile(r"(?<!\w)[A-ZА-ЯӨҮЁ]{2}\s?\d{8}(?!\w)", re.IGNORECASE)
_EMAIL: Final = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE: Final = re.compile(r"\+\d[\d\s-]{6,15}\d")
_LONG_NUMBER: Final = re.compile(
    r"(?<![\d.,])\d{8,}(?![\d.,])(?!\s*\S*(?:/|copies|копи|iu|ме))", re.I
)
_SUFFIXES: Final = r"(?:ын|ийн|ий|ы|д|т|аас|ээс|оос|өөс|тай|тэй|той|аар|ээр|оор|өөр)?"
_MAX_NAME_WORDS: Final = 3
_MAX_BIRTH_WORDS: Final = 7  # the label's own words ("огноо:", "он сар өдөр:") and the date
_PARENT: Final = ("эцэг", "эцгийн", "эх/", "эхийн", "father", "mother", "отец", "мать")
_STAFF: Final = (
    "эмч",
    "захиал",
    "баталгаажуул",
    "шинжил",
    "илгээ",
    "doctor",
    "physician",
    "ordered",
    "врач",
)
MIN_NAME_WORD: Final = 3
MASK: Final = "[хассан]"
_TRANSLIT: Final = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "ye", "ё": "yo", "ж": "j",
        "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
        "ө": "u", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ү": "u", "ф": "f",
        "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "y", "ь": "i",
        "э": "e", "ю": "yu", "я": "ya",
    }
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class Deidentified:
    text: str
    dropped_lines: int
    # the printed name, read here for the name check only - never sent, logged or kept
    identity: PrintedIdentity = field(default_factory=PrintedIdentity, repr=False)


def _kind(token: str) -> Kind | None:
    key = token.casefold().rstrip(":：")
    if not key:
        return None
    if key in _LATIN:
        return _LATIN[key]
    if re.match(r"[а-яөүё]", key):
        for stem, kind in _CYRILLIC:
            if key.startswith(stem):
                return kind
    return None


def _has_colon(tokens: list[str], i: int) -> bool:
    return tokens[i].endswith((":", "：")) or (i + 1 < len(tokens) and tokens[i + 1] in {":", "："})


def _reads_as_results(text: str) -> bool:
    tokens = text.split()
    numbers_with_units = any(
        re.search(r"\d", a) and _UNIT_TOKEN.search(b) for a, b in pairwise(tokens)
    )
    return bool(_RANGE.search(text)) or numbers_with_units


@dataclass(slots=True)
class _Found:
    family: str | None = None
    given: str | None = None
    full: list[str] = field(default_factory=list)

    def identity(self) -> PrintedIdentity:
        family, given = self.family, self.given
        if self.full and given is None:
            words = self.full
            if re.match(r"[а-яөүё]", words[0].casefold()):  # Cyrillic: family name first
                family = family or words[0]
                given = words[1] if len(words) > 1 else words[0]
            else:  # Latin: given name first
                given = words[0]
                family = family or (words[-1] if len(words) > 1 else None)
        return PrintedIdentity(family_name=family, given_name=given)


def _take_name(tokens: list[str], j: int, kind: Kind, found: _Found) -> int:
    """The name words after a name label (up to 3, no digits): noted, and skipped."""
    words: list[str] = []
    while (
        j < len(tokens)
        and len(words) < _MAX_NAME_WORDS
        and not re.search(r"\d", tokens[j])
        and _kind(tokens[j]) is None
    ):
        words.append(tokens[j].strip(",;"))
        j += 1
    if words:
        if kind == "family":
            found.family = found.family or words[0]
        elif kind == "given":
            found.given = found.given or words[0]
        elif not found.full:
            found.full = words
    return j


def _name_field(tokens: list[str], i: int, j: int, kind: Kind, found: _Found) -> int:
    """A name label at `i` (its value from `j`): whose name it is, then the words skipped."""
    prev = tokens[i - 1].casefold() if i > 0 else ""
    if kind == "family" and j < len(tokens) and _kind(tokens[j]) == "given":
        kind = "full"  # "Овог нэр: Дорж Батболд"
        j += 1
        if j < len(tokens) and tokens[j] in {":", "："}:
            j += 1
    if prev.startswith(_PARENT):
        kind = "family"  # a parent's name is the person's family name
    # a doctor's or sender's name is masked, never taken as the person's
    noted = _Found() if prev.startswith(_STAFF) else found
    return _take_name(tokens, j, kind, noted)


def _mask_line(text: str, found: _Found) -> tuple[str | None, bool]:
    """(the line with identity fields masked, or None to drop it; whether it had any)."""
    tokens = text.split()
    out: list[str] = []
    had = False
    i = 0
    while i < len(tokens):
        kind = _kind(tokens[i])
        if kind is None:
            out.append(tokens[i])
            i += 1
            continue
        if kind == "address":
            return None, True
        colon = _has_colon(tokens, i)
        if kind == "age_sex" and not colon:
            out.append(tokens[i])
            i += 1
            continue
        had = True
        j = i + 1
        if j < len(tokens) and tokens[j] in {":", "："}:
            j += 1
        if kind in {"family", "given", "full"}:
            j = _name_field(tokens, i, j, kind, found)
        elif kind == "birth":
            # "Төрсөн огноо: 1990/01/01", "Төрсөн он сар өдөр: 1990 оны 1 сарын 1"
            end = min(len(tokens), j + _MAX_BIRTH_WORDS)
            while j < end and _kind(tokens[j]) is None:
                j += 1
        elif j < len(tokens) and _kind(tokens[j]) is None:
            j += 1  # the one value: a number, a sex
        out.append(MASK)
        i = j
    line = " ".join(out)
    if had and not re.search(r"\d", line.replace(MASK, "")) and not _reads_as_results(line):
        return None, True  # a line of identity fields and nothing else
    return line, had


def _name_masks(profile_name: str) -> re.Pattern[str] | None:
    words = {
        w
        for w in re.split(r"[\s.,]+", unicodedata.normalize("NFKC", profile_name))
        if len(w) >= MIN_NAME_WORD
    }
    words |= {w.casefold().translate(_TRANSLIT) for w in words}
    words = {w for w in words if len(w) >= MIN_NAME_WORD}
    if not words:
        return None
    alternatives = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{alternatives}){_SUFFIXES}(?!\w)", re.IGNORECASE)


def deidentify(lines: Iterable[tuple[int, str]], profile_name: str) -> Deidentified:
    """`lines`: (page, text) as read from the text layer, in order."""
    names = _name_masks(profile_name)
    found = _Found()
    kept: list[str] = []
    dropped = 0
    page_now = 0
    after_identity_header = False
    for page, raw in lines:
        text = unicodedata.normalize("NFKC", raw).strip()
        if _HEADER_WORDS.search(text) and len(_HEADER_WORDS.findall(text)) >= 2:  # noqa: PLR2004
            masked: str | None = text  # a table header: "Шинжилгээний нэр Хариу Нэгж"
            had = False
        else:
            masked, had = _mask_line(text, found)
        if masked is None:
            dropped += 1
            after_identity_header = True
            continue
        if after_identity_header and not had and not _reads_as_results(masked):
            dropped += 1  # the values under a header of identity fields
            after_identity_header = False
            continue
        after_identity_header = False
        masked = _REGISTER.sub(MASK, masked)
        masked = _EMAIL.sub(MASK, masked)
        masked = _PHONE.sub(MASK, masked)
        masked = _LONG_NUMBER.sub(MASK, masked)
        if names is not None:
            masked = names.sub("[нэр]", masked)
        if page != page_now:
            kept.append(f"--- хуудас {page} ---")
            page_now = page
        kept.append(masked)
    return Deidentified(text="\n".join(kept), dropped_lines=dropped, identity=found.identity())
