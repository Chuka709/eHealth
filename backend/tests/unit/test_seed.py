import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from labtrack.seed import SeedError, validate

_SEED = Path(__file__).resolve().parents[3] / "seed"


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (_SEED / name).read_text(encoding="utf-8"), parse_float=Decimal
    )
    return data


@pytest.fixture
def seeds() -> tuple[dict[str, Any], dict[str, Any]]:
    if not _SEED.exists():
        pytest.skip("seed/ not mounted")
    return _load("lab_tests.json"), _load("medications.json")


def test_repository_seed_files_are_valid(seeds: tuple[dict[str, Any], dict[str, Any]]) -> None:
    validate(*seeds)


def test_numbers_are_decimal_not_float(seeds: tuple[dict[str, Any], dict[str, Any]]) -> None:
    lab, _ = seeds
    factors = [c["factor"] for t in lab["tests"] for c in t["unit_conversions"]]
    assert factors
    assert all(isinstance(f, int | Decimal) for f in factors)


def test_reference_ranges_in_the_catalog_are_rejected(
    seeds: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    lab, meds = copy.deepcopy(seeds[0]), seeds[1]
    lab["tests"][0]["ref_ranges"] = [{"low": 4, "high": 10}]
    with pytest.raises(SeedError, match="must not contain"):
        validate(lab, meds)


def test_dosing_in_the_medication_catalog_is_rejected(
    seeds: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    lab, meds = seeds[0], copy.deepcopy(seeds[1])
    meds["medications"][0]["dose"] = "1 mg"
    with pytest.raises(SeedError, match="dosing"):
        validate(lab, meds)


def test_a_synonym_shared_by_two_tests_is_rejected(
    seeds: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    lab, meds = copy.deepcopy(seeds[0]), seeds[1]
    lab["tests"][1]["synonyms"].append(lab["tests"][0]["synonyms"][0].upper())
    with pytest.raises(SeedError, match="ambiguous"):
        validate(lab, meds)


def test_unknown_related_test_code_is_rejected(
    seeds: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    lab, meds = seeds[0], copy.deepcopy(seeds[1])
    meds["medications"][0]["related_test_code"] = "NOPE"
    with pytest.raises(SeedError, match="unknown related_test_code"):
        validate(lab, meds)
