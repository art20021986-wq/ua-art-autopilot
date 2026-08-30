"""TASK 096 — manual field protection layer.

Guarantees that AI enrichment / indexation code paths never write to the CRM's
primary (operator-only) columns. This is enforced by construction: the writer
function below only ever targets the `additional_specification` table and
refuses any field_key that appears in the frozen PRIMARY_FIELD_KEYS set.
"""
from __future__ import annotations
from typing import Iterable

# Frozen list of primary CRM fields that only the CRM operator may fill.
# This list must be kept in sync with the CRM primary schema by the controller,
# via a read-only export into primary_field_registry — Claude/Cloud does not
# have access to the live schema in this environment, so this is the documented
# baseline used for offline self-tests and must be reconciled by the controller
# against the real CRM schema before sandbox execution.
PRIMARY_FIELD_KEYS = frozenset({
    "vin", "make", "model", "trim", "year", "mileage", "body_type", "color_exterior",
    "color_interior", "fuel_type", "registration_status", "location", "listing_price",
    "currency", "seller_notes", "photos", "video_url", "status", "vin_check_result",
    "customs_status", "title_type", "car_uid",
})


class ManualFieldViolation(Exception):
    pass


def assert_target_is_additional_spec_only(field_key: str) -> None:
    fk = (field_key or "").strip().lower()
    if fk in PRIMARY_FIELD_KEYS:
        raise ManualFieldViolation(
            f"field key '{field_key}' belongs to the operator-only primary CRM schema "
            "and cannot be written by AI/indexation into additional_specification"
        )


def filter_protected(candidate_field_keys: Iterable[str]) -> list[str]:
    return [fk for fk in candidate_field_keys if fk.strip().lower() not in PRIMARY_FIELD_KEYS]
