from labtrack.admin.csv_import import PROBLEM_FIELDS, parse
from labtrack.error_codes import error_codes


def test_known_codes_are_collected() -> None:
    codes = set(error_codes())
    for code in (
        "auth.invalid_credentials",
        "admin.username_taken",
        "admin.reset_required",
        "consent.version_outdated",
        "password.too_weak",
        "internal",
        "validation",
    ):
        assert code in codes


def test_csv_problems_use_declared_fields_only() -> None:
    samples = [
        b"",
        b"username,display_name\n",
        b"username,display_name,phone,role\nBad Name,,123,x\nok_1,A,,\nok_1,B,,\nshort,C\n",
        "username,display_name\nbat,Б\n".encode("cp1251"),
    ]
    for data in samples:
        for problem in parse(data).problems:
            assert problem.field in PROBLEM_FIELDS
