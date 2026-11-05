"""The emergency card (Phase 2.7; docs/08 "Яаралтай тусламжийн карт", hazards H17, H27).

The card shows what the user recorded. It picks facts and puts them in order. It never judges
a value, fills a gap or suggests a dose (CLAUDE.md rules 5, 10):

- blood type: the recipient's type is shown only when every transplant that records one
  agrees. If two records disagree, none is shown and the card says the records conflict.
  After a stem-cell transplant (HSCT) from a donor of another type, or of an unknown type, the
  blood type itself changes, so the recorded type is withheld too. The card never picks one;
- transplants: grafts still working come first, then unknown, then failed or removed. Within
  each group the newest comes first (by date, then by transplant number, because a month- or
  year-only date ties);
- allergies: the most severe first (severe, moderate, mild, then unknown or not given),
  otherwise in the order they were recorded;
- medicines shown with their recorded dose: immunosuppressants, then corticosteroids (a long
  steroid course matters to an emergency team). Every other current medicine is shown by name.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

BLOOD_TYPES = frozenset({"O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"})
DosedCategory = Literal["immunosuppressant", "corticosteroid"]
_DOSED_ORDER: dict[DosedCategory, int] = {"immunosuppressant": 0, "corticosteroid": 1}
_GRAFT_ORDER = {"functioning": 0, "unknown": 1, "failed": 2, "removed": 2}
_SEVERITY_ORDER = {"severe": 0, "moderate": 1, "mild": 2}

Withheld = Literal["conflict", "hsct"]


@dataclass(frozen=True)
class BloodRecord:
    organ: str
    recipient: str | None
    donor: str | None


@dataclass(frozen=True)
class CardBloodType:
    value: str | None
    withheld: Withheld | None  # why no type is shown although one is recorded


def card_blood_type(records: Iterable[BloodRecord]) -> CardBloodType:
    """The recipient's blood type across their transplants. Missing values and "unknown" are
    skipped. One distinct value is shown. It is withheld after an HSCT whose donor's type
    differs or is unknown, and when two records disagree."""
    rows = list(records)
    known = {r.recipient for r in rows if r.recipient in BLOOD_TYPES}
    if not known:
        return CardBloodType(None, withheld=None)
    if any(
        r.organ == "hsct" and (r.donor not in BLOOD_TYPES or r.donor != r.recipient) for r in rows
    ):
        return CardBloodType(None, withheld="hsct")
    if len(known) > 1:
        return CardBloodType(None, withheld="conflict")
    return CardBloodType(next(iter(known)), withheld=None)


def dosed_category(category: str | None) -> DosedCategory | None:
    """The category of a medicine shown with its recorded dose. None means it is shown by
    name only."""
    if category == "immunosuppressant":
        return "immunosuppressant"
    if category == "corticosteroid":
        return "corticosteroid"
    return None


def order_dosed[T](rows: Sequence[T], category: Callable[[T], DosedCategory]) -> list[T]:
    """Immunosuppressants, then corticosteroids; otherwise the given order (stable)."""
    return sorted(rows, key=lambda r: _DOSED_ORDER[category(r)])


def order_transplants[T](
    rows: Sequence[T],
    graft_status: Callable[[T], str],
    transplant_date: Callable[[T], date],
    transplant_number: Callable[[T], int],
) -> list[T]:
    """Working grafts first, then the newest. Stable: rows that tie keep their order."""
    return sorted(
        rows,
        key=lambda r: (
            _GRAFT_ORDER.get(graft_status(r), 1),
            -transplant_date(r).toordinal(),
            -transplant_number(r),
        ),
    )


def order_allergies[T](rows: Sequence[T], severity: Callable[[T], str | None]) -> list[T]:
    """The most severe first; otherwise the recorded order (stable)."""
    return sorted(rows, key=lambda r: _SEVERITY_ORDER.get(severity(r) or "", 3))
