"""Name normalisation for matching lab test names and units (docs/05, "Нормчлол").

Lab printouts mix Cyrillic and Latin letters that look identical (HGB typed with a Cyrillic
Н, "Креатинин" with a Latin e), use different case, spacing and punctuation. The normalised key
folds all of that so the same printed name always maps to the same catalog row. It is a lookup
key only - never shown to users.
"""

import re
import unicodedata

# Cyrillic letters that look like Latin ones in upper OR lower case, folded to Latin after
# casefolding (so "КРЕАТИНИН", "Креатинин" and "Kpeатинин" share one key).
_FOLD = str.maketrans("авекмнорстухіјѕ", "abekmhopctyxijs")
_STRIP = re.compile(r"[\s\-_.,:;()\[\]{}/\\'\"`*·]+")


def normalize_name(text: str) -> str:
    """Case-, spacing-, punctuation- and homoglyph-insensitive key."""
    s = unicodedata.normalize("NFKC", text).casefold().translate(_FOLD)
    # Folding and stripping can leave a letter next to a loose combining mark; recompose last so
    # the key is stable when normalised again.
    return unicodedata.normalize("NFKC", _STRIP.sub("", s))


def normalize_unit(text: str) -> str:
    """Key for unit aliases: case-insensitive, no spaces, µ/μ unified; '/' and '^' kept."""
    s = unicodedata.normalize("NFKC", text).strip().replace("μ", "µ")
    return re.sub(r"\s+", "", s).casefold()
