"""ETA normalization engine for UA ART CRM cards.

Single source of truth for a car's estimated arrival to Kyiv used by every
generator and the publisher. Priority order (mandatory per TASK 076):
  confirmed manual eta (days+date, written together) > stage rule > neutral.

Zero runtime LLM tokens: this module is pure deterministic Python.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import re
from typing import Optional

MIN_DAYS = 0
MAX_DAYS = 400
STAGE3_DAYS = 15  # TASK 075 rule: 15 days from actual stage transition, not payment
NEUTRAL_TEXT = "\u0443\u0442\u043e\u0447\u043d\u044f\u0435\u0442\u0441\u044f"  # "уточняется"


class InvalidDaysError(ValueError):
    pass


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def validate_days(n) -> int:
    """Reject non-integers, negatives, and anything above MAX_DAYS."""
    if isinstance(n, bool):
        raise InvalidDaysError(f"days_to_kyiv must be an integer, got bool {n!r}")
    if isinstance(n, float) and not n.is_integer():
        raise InvalidDaysError(f"days_to_kyiv must be a whole number, got {n!r}")
    try:
        n_int = int(n)
    except (TypeError, ValueError):
        raise InvalidDaysError(f"days_to_kyiv must be an integer, got {n!r}")
    if n_int < MIN_DAYS or n_int > MAX_DAYS:
        raise InvalidDaysError(
            f"days_to_kyiv={n_int} out of allowed range [{MIN_DAYS}, {MAX_DAYS}]"
        )
    return n_int


@dataclass(frozen=True)
class EtaObject:
    days_to_kyiv: int
    eta_manual: date
    source: str  # "manual" | "stage_rule" | "neutral"

    def display_date(self) -> str:
        return self.eta_manual.strftime("%d.%m.%Y")


def compute_manual_eta(days: int, base_date: Optional[date] = None) -> EtaObject:
    """Compute an eta object for a single logical write transaction.

    Both days_to_kyiv and eta_manual are derived from the same base_date, so
    they are mutually consistent by construction (the task's contract
    requires this: 'days_to_kyiv=N, eta_manual=UTC_today+N days' as one
    logical transaction).
    """
    validated = validate_days(days)
    base = base_date if base_date is not None else utc_today()
    eta_date = base + timedelta(days=validated)
    return EtaObject(days_to_kyiv=validated, eta_manual=eta_date, source="manual")


def compute_stage_eta(stage: int, stage_entered_at: date,
                       base_date: Optional[date] = None) -> "EtaObject":
    """Fallback stage-rule ETA, used only when there is no confirmed manual eta.

    TASK 075 rule preserved: stage 3 is 15 days from the actual date the car
    entered stage 3, never from the payment date.
    """
    base = base_date if base_date is not None else utc_today()
    if stage != 3:
        return neutral_eta(base)
    eta_date = stage_entered_at + timedelta(days=STAGE3_DAYS)
    days = max((eta_date - base).days, 0)
    return EtaObject(days_to_kyiv=days, eta_manual=eta_date, source="stage_rule")


def neutral_eta(base_date: Optional[date] = None) -> EtaObject:
    return EtaObject(days_to_kyiv=-1, eta_manual=(base_date or utc_today()), source="neutral")


def resolve_eta(manual: Optional[EtaObject], stage_fallback: Optional[EtaObject]) -> EtaObject:
    """Priority resolver used by every generator and the publisher.

    manual (confirmed) > stage rule > neutral 'уточняется'.
    """
    if manual is not None:
        return manual
    if stage_fallback is not None:
        return stage_fallback
    return neutral_eta()


def eta_is_consistent(days_to_kyiv, eta_manual_iso: str, base_date: Optional[date] = None) -> bool:
    """Cross-check that days_to_kyiv and eta_manual agree with each other.

    A mismatch must block publication per the task contract.
    """
    try:
        base = base_date if base_date is not None else utc_today()
        parsed = date.fromisoformat(eta_manual_iso)
        expected_days = (parsed - base).days
        return int(days_to_kyiv) == expected_days
    except Exception:
        return False


# --- description sanitation -------------------------------------------------

_MONTHS = (
    "\u044f\u043d\u0432\u0430\u0440\u044f", "\u0444\u0435\u0432\u0440\u0430\u043b\u044f",
    "\u043c\u0430\u0440\u0442\u0430", "\u0430\u043f\u0440\u0435\u043b\u044f",
    "\u043c\u0430\u044f", "\u0438\u044e\u043d\u044f", "\u0438\u044e\u043b\u044f",
    "\u0430\u0432\u0433\u0443\u0441\u0442\u0430", "\u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f",
    "\u043e\u043a\u0442\u044f\u0431\u0440\u044f", "\u043d\u043e\u044f\u0431\u0440\u044f",
    "\u0434\u0435\u043a\u0430\u0431\u0440\u044f",
)  # ru month genitive forms: января..декабря

_RU_DATE_RE = re.compile(
    r"\b\d{1,2}\s+(?:%s)(?:\s+\d{4})?(?:\s*\u0433\.?)?\b" % "|".join(_MONTHS),
    re.IGNORECASE,
)
_NUM_DATE_RE = re.compile(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b")


def strip_stale_dates(description: str) -> str:
    """Remove independent absolute delivery dates from free-text description.

    The ETA component is the single public source of the date; the
    description must never contradict it with an old hardcoded date. This
    function is generic (regex-based), so it applies to any current or
    future card without a hardcoded ID list.
    """
    if not description:
        return description
    cleaned = _RU_DATE_RE.sub("", description)
    cleaned = _NUM_DATE_RE.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = cleaned.strip(" ,.-")
    return cleaned
