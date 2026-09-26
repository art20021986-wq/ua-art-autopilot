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
    **{label.casefold(): code for code, label in LABELS.items()},
}


def public_status(value: object) -> str:
    """Map a known active CRM value; hide everything else."""
    return _INPUT.get(value.strip().casefold(), HIDDEN) if isinstance(value, str) else HIDDEN


def public_label(value: object) -> str | None:
    """Return no label for a hidden card."""
    return LABELS.get(public_status(value))


def catalog_counts(statuses: Iterable[object]) -> dict[str, int]:
    """Count only cars with a visible delivery status."""
    counts = Counter(map(public_status, statuses))
    return {code: counts[code] for code in LABELS}
