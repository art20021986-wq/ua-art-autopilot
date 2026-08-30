"""TASK 096 — semantic deduplication for the Additional Specification block.

Prevents:
  1. Duplicate technical facts already present as an operator-entered primary
     CRM field (read-only reference, `primary_field_registry`).
  2. Duplicate technical facts already present in `additional_specification`
     under a different but semantically equivalent key.

This module performs no network or filesystem writes to the real CRM. It
operates purely on data passed to it (typically rows fetched from a sandbox
copy via read-only queries).
"""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from price_exclusion_guard import assert_not_price_field, PriceFieldRejected

# Canonical synonym map: maps loose vocabulary to one canonical field_key so that
# "мощность", "power_hp", "engine_power" etc. collapse to a single key.
SYNONYM_MAP = {
    "power_hp": {"мощность", "engine_power", "power_hp", "hp", "л.с."},
    "torque_nm": {"крутящий_момент", "torque", "torque_nm", "нм"},
    "drivetrain": {"привод", "drivetrain", "awd", "4matic"},
    "transmission": {"коробка_передач", "transmission", "gearbox", "9g-tronic"},
    "fuel_consumption_combined": {"расход_топлива", "fuel_consumption", "combined_consumption"},
    "co2_emissions": {"выбросы_co2", "co2", "co2_emissions"},
    "acceleration_0_100": {"разгон", "0-100", "acceleration_0_100"},
}


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def canonical_key(field_key: str) -> str:
    fk = normalize_text(field_key).replace(" ", "_")
    for canon, synonyms in SYNONYM_MAP.items():
        if fk == canon or fk in {normalize_text(s).replace(" ", "_") for s in synonyms}:
            return canon
    return fk


@dataclass
class DedupResult:
    allowed: bool
    reason: Optional[str] = None


def check_candidate(
    car_uid: str,
    field_key: str,
    field_value: str,
    primary_fields: dict[str, str],
    existing_additional: dict[str, str],
) -> DedupResult:
    """primary_fields: {canonical_key: normalized_value} for this car_uid, sourced
    read-only from primary_field_registry (operator-entered data).
    existing_additional: {canonical_key: normalized_value} already stored in
    additional_specification for this car_uid.
    """
    try:
        assert_not_price_field(field_key)
    except PriceFieldRejected as exc:
        return DedupResult(allowed=False, reason=f"PRICE_FIELD_FORBIDDEN:{exc}")

    ck = canonical_key(field_key)
    norm_val = normalize_text(field_value)

    if ck in primary_fields:
        # The operator has already recorded this fact manually. AI/indexation must
        # never overwrite or duplicate it, even if the new value differs in wording.
        return DedupResult(allowed=False, reason="MANUAL_FIELD_PROTECTED")

    if ck in existing_additional:
        if existing_additional[ck] == norm_val:
            return DedupResult(allowed=False, reason="DUPLICATE")
        # Same canonical fact, different value text -> still a semantic duplicate;
        # spec forbids semantic dupes regardless of exact wording match.
        return DedupResult(allowed=False, reason="DUPLICATE")

    return DedupResult(allowed=True)
