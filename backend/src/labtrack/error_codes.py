"""Every error `code` the API can return (clients show `error.<code>` from messages/*.json).

`just gen-client` writes the list to packages/shared/error-codes.json; a shared test then
requires a Mongolian and an English text for each, so no code reaches a user untranslated.
"""

import re
from pathlib import Path

from labtrack.admin.csv_import import PROBLEM_FIELDS
from labtrack.admin.users import _CONSTRAINTS, _DB_ERRORS
from labtrack.auth.service import INVALID_CREDENTIALS

_SRC = Path(__file__).resolve().parent
_LITERALS = (
    re.compile(r'AppError\(\s*\d{3},\s*"([a-z0-9_.]+)"'),
    re.compile(r'"code":\s*"([a-z0-9_.]+)"'),
)
_PASSWORD = re.compile(r'"(password\.[a-z_]+)"')


def error_codes() -> list[str]:
    codes = {INVALID_CREDENTIALS}
    codes |= {code for _, _, code in _DB_ERRORS}
    codes |= {code for _, code in _CONSTRAINTS.values()}
    for path in _SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for pattern in _LITERALS:
            codes |= set(pattern.findall(text))
    # password policy problems are returned as the code of a 422 (auth/service.py)
    codes |= set(_PASSWORD.findall((_SRC / "core" / "security.py").read_text(encoding="utf-8")))
    return sorted(codes)


def import_problem_fields() -> list[str]:
    return sorted(PROBLEM_FIELDS)
