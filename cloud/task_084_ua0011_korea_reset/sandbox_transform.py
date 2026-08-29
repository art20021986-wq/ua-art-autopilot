"""Pure, side-effect-free sandbox transform implementing the owner's target delta
for UA-0011, and a generic reusable transform for the same class of request.

No network, no filesystem writes, no CRM access. Operates only on in-memory
dict copies. Safe to unit test and to re-run any number of times (idempotent).
"""
from __future__ import annotations

import copy
from typing import Any, Dict

CANONICAL_STATUS_KOREA_BOUGHT = "kr_bought"

# The exact field names below MUST be confirmed against the live schema by the
# controller-side Gate A fetch (gate_a_fetch_ua0011.py) before this transform is
# ever applied to a real record. Defaults reflect the most likely canonical
# field names in the UA ART CRM schema and are overridable.
DEFAULT_STATUS_FIELD = "status"
DEFAULT_CONTAINER_FIELD = "container_number"
DEFAULT_ARRIVAL_DATE_FIELD = "arrival_date"


def apply_korea_bought_reset(
    card: Dict[str, Any],
    status_field: str = DEFAULT_STATUS_FIELD,
    container_field: str = DEFAULT_CONTAINER_FIELD,
    arrival_date_field: str = DEFAULT_ARRIVAL_DATE_FIELD,
) -> Dict[str, Any]:
    """Return a NEW dict: same as `card` except the three target fields.

    - status_field -> 'kr_bought'
    - container_field -> '' (canonical empty; caller's schema layer maps to NULL on write)
    - arrival_date_field -> '' (canonical empty; no ETA computed)

    All other keys, including nested media lists, are deep-copied unchanged.
    """
    result = copy.deepcopy(card)
    result[status_field] = CANONICAL_STATUS_KOREA_BOUGHT
    result[container_field] = ""
    result[arrival_date_field] = ""
    return result


def is_idempotent(card: Dict[str, Any], **field_names) -> bool:
    once = apply_korea_bought_reset(card, **field_names)
    twice = apply_korea_bought_reset(once, **field_names)
    return once == twice


def diff_fields(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Return {field: (before_value, after_value)} for every field that changed."""
    changed = {}
    keys = set(before.keys()) | set(after.keys())
    for key in sorted(keys):
        bv = before.get(key, "<absent>")
        av = after.get(key, "<absent>")
        if bv != av:
            changed[key] = (bv, av)
    return changed
