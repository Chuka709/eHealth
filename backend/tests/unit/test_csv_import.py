import hashlib

import pytest
from hypothesis import given
from hypothesis import strategies as st

from labtrack.admin.csv_import import MAX_BYTES, MAX_ROWS, Problem, normalise_phone, parse


def _csv(*lines: str) -> bytes:
    return ("\n".join(lines) + "\n").encode()


def test_valid_file_with_bom_and_any_column_order() -> None:
    data = (
        "﻿" + "Display_Name,username,phone,role\nБат,bat.01,+976 9911-2233,\nДорж,dorj_2,,doctor\n"
    )
    parsed = parse(data.encode())
    assert parsed.problems == []
    assert [(r.line, r.username, r.phone, r.role) for r in parsed.rows] == [
        (2, "bat.01", "99112233", "user"),
        (3, "dorj_2", None, "doctor"),
    ]
    assert parsed.sha256 == hashlib.sha256(data.encode()).hexdigest()


def test_problems_name_the_row_and_field_never_the_value() -> None:
    parsed = parse(
        _csv(
            "username,display_name,phone,role",
            "ok_1,Бат,99112233,user",
            "Bad Name,Бат,,user",
            "ok_1,Дорж,,user",
            "ok_3,,12345,admin",
            "ok_4,Сараа",
        )
    )
    assert parsed.problems == [
        Problem(3, "username"),
        Problem(4, "username_duplicate"),
        Problem(5, "display_name"),
        Problem(5, "phone"),
        Problem(5, "role"),
        Problem(6, "columns"),
    ]
    rendered = repr(parsed.problems)
    for value in ("Bad Name", "12345", "admin", "Сараа"):
        assert value not in rendered


@pytest.mark.parametrize(
    ("data", "field"),
    [
        (b"", "columns"),
        (_csv("username,phone"), "columns"),
        (_csv("username,display_name,national_id"), "columns"),
        (_csv("username,display_name,username"), "columns"),
        (_csv("username,display_name"), "empty"),
        ("username,display_name\nbat,Бат\n".encode("cp1251"), "encoding"),
        (b"x" * (MAX_BYTES + 1), "too_large"),
    ],
)
def test_whole_file_problems(data: bytes, field: str) -> None:
    parsed = parse(data)
    assert parsed.rows == []
    assert parsed.problems == [Problem(0, field)]


def test_row_limit() -> None:
    lines = ["username,display_name"] + [f"user{i:05d},Н" for i in range(MAX_ROWS + 1)]
    assert parse(_csv(*lines)).problems == [Problem(0, "too_many_rows")]
    assert len(parse(_csv(*lines[:-1])).rows) == MAX_ROWS


def test_national_ids_are_never_imported() -> None:
    assert parse(_csv("username,display_name,national_id", "bat,Бат,УБ90010101")).problems == [
        Problem(0, "columns")
    ]


@given(st.binary(max_size=2000))
def test_arbitrary_bytes_never_crash(data: bytes) -> None:
    parsed = parse(data)
    assert parsed.rows or parsed.problems


@given(st.lists(st.text(max_size=20), max_size=6), st.integers(min_value=0, max_value=20))
def test_arbitrary_rows_never_crash(cells: list[str], blanks: int) -> None:
    body = "username,display_name,phone\n" + ",".join(cells) + "\n" * blanks
    parsed = parse(body.encode())
    for row in parsed.rows:
        assert 3 <= len(row.username) <= 32
        assert row.phone is None or len(row.phone) == 8


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("99112233", "99112233"),
        ("+976 8811 2233", "88112233"),
        ("976-6611-2233", "66112233"),
        ("12345678", None),
        ("9911223", None),
        ("+1 99112233", None),
    ],
)
def test_phone_normalisation(raw: str, expected: str | None) -> None:
    assert normalise_phone(raw) == expected
