"""Which catalog test a printed row is (docs/05 "Тест таних"; rule 6).

Exact matches only, on the normalised name (`core.text.normalize_name`: case, spacing,
punctuation and Cyrillic/Latin look-alikes folded): the full printed name before any shortened
form, and for each the person's own learned synonyms before the catalog's. A near miss is not
a match - a wrong test puts a value on the wrong trend (e.g. NEUT% read as NEUT#) - so an
unknown name is left for the person to pick in review (where it becomes their synonym).
- An analyser's channel digit is dropped only from known analyser names ("RBC3", "RDW-CV1",
  "MONO#1"); elsewhere a digit means something ("IgG4", "25(OH)D3", cyclosporin "CyA2" - the
  2-hour level, not the trough).
- The specimen: the catalog's tests are blood tests except the urine ratios, so a urine
  panel's "Креатинин" never becomes the blood test, nor a blood row a urine ratio. With no
  specimen printed, or another fluid (ascites, drain, CSF), tests measured in more than one
  fluid are not matched at all (urine or drain creatinine on the blood creatinine trend would
  change eGFR; ascitic albumin, MELD) - the person picks.
"""

import re
import unicodedata
from collections.abc import Mapping
from typing import Final

from labtrack.core.text import normalize_name

URINE_TESTS: Final = frozenset({"UPCR", "UACR"})
# measured in both blood and urine: never matched without a printed specimen
BOTH_SPECIMENS: Final = frozenset(
    {"CREA", "ALB", "TP", "GLU", "RBC", "WBC", "TBIL", "UREA", "NA", "K", "UA", "CA", "PHOS"}
)
# analyser channel names that may carry a trailing channel digit
ANALYSER_NAMES: Final = frozenset(
    normalize_name(n)
    for n in (
        "RBC",
        "WBC",
        "HGB",
        "HCT",
        "PLT",
        "MCV",
        "MCH",
        "MCHC",
        "RDW-CV",
        "RDW-SD",
        "MPV",
        "PDW",
        "PCT",
        "P-LCR",
        *(f"{cell}{mark}" for cell in ("NEUT", "LYMPH", "MONO", "EO", "BASO", "NRBC", "IG")
          for mark in ("#", "%")),
    )
)  # fmt: skip
_URINE: Final = re.compile(r"шээс|urine|моч", re.IGNORECASE)
_BLOOD: Final = re.compile(
    r"цус|ийлдэс|сийвэн|serum|plasma|blood|кров|сыворот|плазм", re.IGNORECASE
)
_CHANNEL: Final = re.compile(r"\d$")


def is_urine(specimen: str | None) -> bool:
    return specimen is not None and bool(_URINE.search(unicodedata.normalize("NFKC", specimen)))


def name_keys(raw_name: str) -> tuple[str, ...]:
    """The printed name's key, then - for a known analyser name - the key without its digit."""
    full = normalize_name(raw_name)
    trimmed = normalize_name(_CHANNEL.sub("", raw_name.strip().rstrip(".")))
    keys = [full, trimmed] if trimmed != full and trimmed in ANALYSER_NAMES else [full]
    return tuple(k for k in keys if k)


def is_blood(specimen: str | None) -> bool:
    return specimen is not None and bool(_BLOOD.search(unicodedata.normalize("NFKC", specimen)))


def _fits(code: str, specimen: str | None) -> bool:
    if is_urine(specimen):
        return code in URINE_TESTS
    if is_blood(specimen):
        return code not in URINE_TESTS
    if specimen is None:
        return code not in BOTH_SPECIMENS
    # another fluid (ascites, drain, CSF): its albumin or creatinine is not the blood test
    return code not in BOTH_SPECIMENS and code not in URINE_TESTS


def match_test(
    raw_name: str,
    specimen: str | None,
    synonyms: Mapping[str, str],
    user_synonyms: Mapping[str, str] | None = None,
) -> str | None:
    """The catalog code for a printed name, or None (the person picks it in review).

    `synonyms` / `user_synonyms`: normalised name -> test code (test_synonyms).
    """
    for key in name_keys(raw_name):
        for table in (user_synonyms or {}, synonyms):
            code = table.get(key)
            if code is not None and _fits(code, specimen):
                return code
    return None
