"""CSV bulk registration (docs/04 §1 "CSV бөөн бүртгэл").

The file is itself sensitive (a transplant centre's patient list): it is parsed in memory only,
never stored, logged or sent to Sentry. Problems are reported as row number + field name, never
with the value. Pure functions here; the API previews, then commits all rows in one transaction.

Columns (header row required, any order, UTF-8 with or without BOM):
    username, display_name, phone (optional), role (optional: user | doctor, default user)
National ids are not imported: they are enrolled in person from the ID card (docs/04 §1).
"""

import csv
import hashlib
import io
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final, Literal

from labtrack.core.text import valid_display_name

MAX_BYTES: Final = 1_000_000
MAX_ROWS: Final = 1000
REQUIRED: Final = ("username", "display_name")
KNOWN: Final = frozenset({"username", "display_name", "phone", "role"})
_USERNAME = re.compile(r"^[a-z0-9._]{3,32}$")
_NON_DIGITS = re.compile(r"[^0-9]")  # ASCII: "\D" keeps Arabic or full-width digits


@dataclass(frozen=True)
class Row:
    line: int  # 1-based data row number as the admin sees it in a spreadsheet (header = 1)
    username: str
    display_name: str
    phone: str | None
    role: Literal["user", "doctor"]


@dataclass(frozen=True)
class Problem:
    line: int  # 0 = the file as a whole
    field: str


@dataclass(frozen=True)
class Parsed:
    sha256: str
    rows: list[Row]
    problems: list[Problem]


def normalise_phone(raw: str) -> str | None:
    """Mongolian mobile: 8 digits starting 6-9; +976 and separators are dropped."""
    digits = _NON_DIGITS.sub("", raw)
    if not digits.isascii():
        return None
    if len(digits) == 11 and digits.startswith("976"):  # noqa: PLR2004
        digits = digits[3:]
    if len(digits) != 8 or digits[0] not in "6789":  # noqa: PLR2004
        return None
    return digits


def _row(line: int, record: dict[str, str], seen: set[str]) -> Row | list[str]:
    """One data row: the Row, or the names of the fields that are wrong."""
    problems = []
    username = record["username"].lower()
    if not _USERNAME.match(username):
        problems.append("username")
    elif username in seen:
        problems.append("username_duplicate")
    display_name = record["display_name"]
    if not valid_display_name(display_name):
        problems.append("display_name")
    phone_raw = record.get("phone", "")
    phone = normalise_phone(phone_raw) if phone_raw else None
    if phone_raw and phone is None:
        problems.append("phone")
    role = (record.get("role") or "user").lower()
    if role not in {"user", "doctor"}:
        problems.append("role")
    if problems:
        return problems
    return Row(line, username, display_name, phone, "doctor" if role == "doctor" else "user")


def _header(reader: Iterator[list[str]]) -> list[str] | None:
    try:
        header = [h.strip().lower() for h in next(reader)]
    except (StopIteration, csv.Error):
        return None
    if (
        any(c not in header for c in REQUIRED)
        or any(h not in KNOWN for h in header)
        or len(set(header)) != len(header)
    ):
        return None
    return header


def parse(data: bytes) -> Parsed:
    digest = hashlib.sha256(data).hexdigest()
    if len(data) > MAX_BYTES:
        return Parsed(digest, [], [Problem(0, "too_large")])
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return Parsed(digest, [], [Problem(0, "encoding")])
    reader = csv.reader(io.StringIO(text, newline=""))
    header = _header(reader)
    if header is None:
        return Parsed(digest, [], [Problem(0, "columns")])

    rows: list[Row] = []
    problems: list[Problem] = []
    seen: set[str] = set()
    counted = 0
    try:
        for values in reader:
            line = reader.line_num  # physical line, also for quoted multi-line fields
            if not any(v.strip() for v in values):
                continue  # blank lines
            counted += 1
            if counted > MAX_ROWS:
                return Parsed(digest, [], [Problem(0, "too_many_rows")])
            if len(values) != len(header):
                problems.append(Problem(line, "columns"))
                continue
            result = _row(line, dict(zip(header, (v.strip() for v in values), strict=True)), seen)
            if isinstance(result, Row):
                seen.add(result.username)
                rows.append(result)
            else:
                problems.extend(Problem(line, f) for f in result)
    except csv.Error:
        return Parsed(digest, [], [Problem(0, "format")])
    if not rows and not problems:
        problems.append(Problem(0, "empty"))
    return Parsed(digest, rows, problems)
