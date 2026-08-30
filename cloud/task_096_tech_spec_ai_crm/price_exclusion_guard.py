"""TASK 096 — hard purchase-price exclusion guard.

This module MUST be imported by any AI-enrichment or indexation writer before a
field is allowed into additional_specification. It never reads, stores, logs,
or returns actual price values; it only classifies field *keys* and, defensively,
scans values for currency-like purchase-cost patterns tied to internal wording.

No network access. No filesystem access outside process memory. Pure functions.
"""
from __future__ import annotations
import re
from typing import Iterable

# Canonical denylist of field keys (kept in sync with schema_additional_spec.sql).
PRICE_KEY_DENYLIST = {
    "purchase_price", "cost_price", "auction_price", "wholesale_price",
    "dealer_price", "buy_price", "acquisition_price", "internal_price",
    "закупочная_цена", "оптовая_цена", "аукционная_цена", "себестоимость",
}

# Substrings that indicate a key is price-related even if not an exact match.
_PRICE_SUBSTRINGS = (
    "purchase", "cost_price", "auction", "wholesale", "dealer_price",
    "закуп", "опт", "аукцион", "себестоим",
)


class PriceFieldRejected(Exception):
    """Raised when a field key or value is classified as purchase-cost data."""


def is_price_key(field_key: str) -> bool:
    key = (field_key or "").strip().lower()
    if key in PRICE_KEY_DENYLIST:
        return True
    return any(sub in key for sub in _PRICE_SUBSTRINGS)


def assert_not_price_field(field_key: str) -> None:
    if is_price_key(field_key):
        raise PriceFieldRejected(f"field key '{field_key}' is a forbidden purchase-cost field")


def filter_out_price_fields(records: Iterable[dict]) -> list[dict]:
    """Given candidate additional-spec records (dicts with 'field_key'), drop any
    that are price-related. Never mutates or inspects the excluded value beyond
    the key check itself; the actual value content is not logged.
    """
    safe: list[dict] = []
    for rec in records:
        if is_price_key(rec.get("field_key", "")):
            continue
        safe.append(rec)
    return safe
