import typing

import pytest

from labtrack.api import admin_deps, deps


@pytest.mark.parametrize(
    "alias", [deps.AnonymousDb, deps.UserDb, admin_deps.AdminLoginDb, admin_deps.Admin]
)
def test_transactions_commit_before_the_response(alias: object) -> None:
    """A client must never receive a session or token whose row is not committed yet (the
    next request would not find it): every DB dependency ends with the endpoint function."""
    (depends,) = typing.get_args(alias)[1:]
    assert depends.scope == "function"
