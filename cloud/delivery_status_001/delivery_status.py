"""Public delivery status projection for CRM and site boundaries."""

from collections import Counter
from enum import Enum
from typing import Iterable


class DeliveryStatus(str, Enum):
    KOREA = "korea"
    FERRY = "ferry"
    GEORGIA = "georgia"
    KYIV = "kyiv"


HIDDEN = "hidden"

CHOICES = (
    ("korea", "kr_bought", 1, "В Корее"),
    ("ferry", "sea_loaded", 2, "На пароме"),
    ("georgia", "ge_waiting", 3, "В Грузии"),
    ("kyiv", "ua_arrived", 4, "В Киеве"),
)
LABELS = {
    DeliveryStatus.KOREA.value: "В Корее",
    DeliveryStatus.FERRY.value: "На пароме",
    DeliveryStatus.GEORGIA.value: "В Грузии",
    DeliveryStatus.KYIV.value: "В Киеве",
}

# Existing CRM codes are translated at the boundary; the stored codes remain intact.
_INPUT = {
    "korea": "korea",
    "kr_bought": "korea",
    "ferry": "ferry",
    "sea_loaded": "ferry",
    "georgia": "georgia",
    "ge_waiting": "georgia",
    "kyiv": "kyiv",
    "ua_arrived": "kyiv",
}

_CANONICAL = frozenset(status.value for status in DeliveryStatus)
_CRM_CODES = {public: internal for public, internal, _, _ in CHOICES}
_STAGE_NUMBERS = {public: number for public, _, number, _ in CHOICES}


def normalize_status(value: object) -> str:
    """Accept only the public enum at an untrusted input boundary."""
    if not isinstance(value, str):
        return HIDDEN
    return value if value in _CANONICAL else HIDDEN


def crm_status_from_input(value: object) -> str:
    """Translate a new canonical CRM callback to its existing storage code."""
    return _CRM_CODES.get(normalize_status(value), HIDDEN)


def storage_status(value: object) -> str:
    """Normalize trusted existing writers and new canonical status codes."""
    if not isinstance(value, str):
        return HIDDEN
    if value in _CRM_CODES.values():
        return value
    return crm_status_from_input(value)


def stage_number(value: object) -> int:
    """Return zero for a card excluded from the public catalogue."""
    return _STAGE_NUMBERS.get(public_status(value), 0)


def public_status(value: object) -> str:
    """Map a known active CRM value; hide everything else."""
    return _INPUT.get(value, HIDDEN) if isinstance(value, str) else HIDDEN


def public_label(value: object) -> str | None:
    """Return no label for a hidden card."""
    return LABELS.get(public_status(value))


def catalog_counts(statuses: Iterable[object]) -> dict[str, int]:
    """Count only cars with a visible delivery status."""
    counts = Counter(map(public_status, statuses))
    return {code: counts[code] for code in LABELS}
