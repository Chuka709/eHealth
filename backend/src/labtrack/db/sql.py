"""The only allowed entry point for raw SQL.

`sqlalchemy.text` is banned project-wide (ruff TID251): raw SQL must be a literal string with
bind parameters. RLS does not protect against SQL injection - an injected
`set_config('app.user_id', ...)` would open every patient (docs/03_DATA_MODEL.md, RLS).
"""

from typing import LiteralString

from sqlalchemy import TextClause
from sqlalchemy import text as _text  # noqa: TID251 - the single sanctioned import


def bound_text(sql: LiteralString) -> TextClause:
    """Build a SQL clause from a literal string; values go in bind parameters (`:name`)."""
    return _text(sql)
