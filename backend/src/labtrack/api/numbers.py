"""Numbers in API answers are strings (CLAUDE.md rule 7)."""

from decimal import Decimal


def num(value: Decimal | None) -> str | None:
    """Plain notation (never "1E-7"), and no "-0"."""
    if value is None:
        return None
    text = format(value, "f")
    return text.lstrip("-") if value.is_zero() else text
