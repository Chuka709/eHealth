"""Load seed/lab_tests.json and seed/medications.json into the catalogs (idempotent).

Runs as labtrack_owner (`just seed`): catalogs are read-only for every runtime role.
Numbers are parsed as Decimal - never float (CLAUDE.md rule 7).
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from labtrack.core.text import normalize_name, normalize_unit
from labtrack.db.sql import bound_text


class SeedError(ValueError):
    """The seed files are inconsistent; nothing was written."""


@dataclass(frozen=True)
class SeedStats:
    tests: int
    synonyms: int
    conversions: int
    unit_aliases: int
    medications: int


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    return data


def _synonyms(tests: list[dict[str, Any]]) -> dict[str, tuple[str, str]]:
    """normalised name -> (code, original text); a name shared by two tests is a seed error."""
    out: dict[str, tuple[str, str]] = {}
    clashes: list[str] = []
    for t in tests:
        names = [t["code"], t["name_mn"], t["name_en"], t.get("name_ru"), *t.get("synonyms", [])]
        for name in filter(None, names):
            key = normalize_name(name)
            if not key:
                continue
            seen = out.get(key)
            if seen and seen[0] != t["code"]:
                clashes.append(f"{name!r}: {seen[0]} / {t['code']}")
            out.setdefault(key, (t["code"], name))
    if clashes:
        raise SeedError("ambiguous synonyms: " + "; ".join(sorted(clashes)))
    return out


def validate(lab: dict[str, Any], meds: dict[str, Any]) -> None:
    codes = {t["code"] for t in lab["tests"]}
    if len(codes) != len(lab["tests"]):
        raise SeedError("duplicate test codes")
    for t in lab["tests"]:
        # Reference/critical ranges must never come from the catalog (CLAUDE.md rule 5).
        forbidden = {
            "ref_low",
            "ref_high",
            "ref_ranges",
            "critical_low",
            "critical_high",
        } & t.keys()
        if forbidden:
            raise SeedError(f"{t['code']}: catalog must not contain {sorted(forbidden)}")
        for c in t.get("unit_conversions", []):
            if Decimal(c["factor"]) <= 0:
                raise SeedError(f"{t['code']}: non-positive conversion factor")
    for m in meds["medications"]:
        rel = m.get("related_test_code")
        if rel and rel not in codes:
            raise SeedError(f"{m['code']}: unknown related_test_code {rel}")
        if {"dose", "doses", "dosage", "indication"} & m.keys():
            raise SeedError(f"{m['code']}: medication catalog must not contain dosing")
    _synonyms(lab["tests"])


async def _write(conn: AsyncConnection, lab: dict[str, Any], meds: dict[str, Any]) -> SeedStats:
    tests = lab["tests"]
    for t in tests:
        await conn.execute(
            bound_text(
                "insert into test_catalog (code, loinc, name_mn, name_en, name_ru, category, kind,"
                " canonical_unit, decimals, physio_min, physio_max, delta_check_pct)"
                " values (:code, :loinc, :name_mn, :name_en, :name_ru, :category,"
                " cast(:kind as value_kind), :canonical_unit, :decimals, :physio_min, :physio_max,"
                " :delta_check_pct)"
                " on conflict (code) do update set loinc = excluded.loinc,"
                " name_mn = excluded.name_mn, name_en = excluded.name_en,"
                " name_ru = excluded.name_ru, category = excluded.category, kind = excluded.kind,"
                " canonical_unit = excluded.canonical_unit, decimals = excluded.decimals,"
                " physio_min = excluded.physio_min, physio_max = excluded.physio_max,"
                " delta_check_pct = excluded.delta_check_pct, is_active = true"
            ),
            {
                "code": t["code"],
                "loinc": t.get("loinc"),
                "name_mn": t["name_mn"],
                "name_en": t["name_en"],
                "name_ru": t.get("name_ru"),
                "category": t["category"],
                "kind": t.get("kind", "numeric"),
                "canonical_unit": t.get("canonical_unit"),
                "decimals": t.get("decimals", 2),
                "physio_min": t.get("physio_min"),
                "physio_max": t.get("physio_max"),
                "delta_check_pct": t.get("delta_check_pct"),
            },
        )
    await conn.execute(bound_text("delete from unit_conversions"))
    conversions = 0
    for t in tests:
        for c in t.get("unit_conversions", []):
            await conn.execute(
                bound_text(
                    "insert into unit_conversions (test_code, from_unit, to_unit, factor)"
                    " values (:code, :f, :t, :factor)"
                ),
                {"code": t["code"], "f": c["from_unit"], "t": c["to_unit"], "factor": c["factor"]},
            )
            conversions += 1
    # Global synonyms are owned by the seed; users' learned synonyms are left untouched.
    await conn.execute(bound_text("delete from test_synonyms where user_id is null"))
    synonyms = _synonyms(tests)
    for key, (code, name) in synonyms.items():
        await conn.execute(
            bound_text(
                "insert into test_synonyms (test_code, synonym, synonym_norm) values (:c, :s, :k)"
            ),
            {"c": code, "s": name, "k": key},
        )
    aliases = {normalize_unit(a): u for a, u in lab.get("unit_aliases", {}).items()}
    for alias, unit in aliases.items():
        await conn.execute(
            bound_text(
                "insert into unit_aliases (alias_norm, unit) values (:a, :u)"
                " on conflict (alias_norm) do update set unit = excluded.unit"
            ),
            {"a": alias, "u": unit},
        )
    for m in meds["medications"]:
        await conn.execute(
            bound_text(
                "insert into medication_catalog (code, generic_mn, generic_en, brands, category,"
                " forms, related_test_code) values (:code, :mn, :en, :brands, :cat, :forms, :rel)"
                " on conflict (code) do update set generic_mn = excluded.generic_mn,"
                " generic_en = excluded.generic_en, brands = excluded.brands,"
                " category = excluded.category, forms = excluded.forms,"
                " related_test_code = excluded.related_test_code, is_active = true"
            ),
            {
                "code": m["code"],
                "mn": m["generic_mn"],
                "en": m["generic_en"],
                "brands": m.get("brands", []),
                "cat": m["category"],
                "forms": m.get("forms", []),
                "rel": m.get("related_test_code"),
            },
        )
    return SeedStats(len(tests), len(synonyms), conversions, len(aliases), len(meds["medications"]))


async def run(database_url: str, seed_dir: Path) -> SeedStats:
    lab = _load(seed_dir / "lab_tests.json")
    meds = _load(seed_dir / "medications.json")
    validate(lab, meds)  # fail before touching the database
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as conn:
            return await _write(conn, lab, meds)
    finally:
        await engine.dispose()
