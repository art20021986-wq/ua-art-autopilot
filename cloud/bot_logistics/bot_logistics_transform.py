"""
BOT-LOGISTICS-001 Phase A — canonical hub logic + candidate transform primitives.

Everything here is UA-ID-agnostic (works for UA-0001..UA-XXXX). It operates
on generic anchor patterns and does not assume any specific real source file
contents (those are unknown to this worker — see README.md).

This module is intentionally split into:
  1. Pure business logic (container validation, ETA computation) — fully
     testable offline, and this is exactly what Gate B will use once real
     anchors are confirmed by discovery.
  2. Generic text-transform primitives that remove duplicate old menu
     entries and insert exactly one canonical hub entry point, driven by
     anchor line matches supplied by the discovery report — not hardcoded
     to any specific file.
  3. A deterministic multi-application guarantee: applying the same
     transform N times to the same input (after the first application it
     is a no-op) produces an identical output/hash every time.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

HUB_BUTTON_TEXT = "🚢 Этапы и доставка"

OLD_STAGE_MENU_LABELS = [
    "Срок доставки",
    "📦 Номер и дата контейнера",
    "Номер и дата контейнера",
]
OLD_CARD_EDITOR_LABELS = [
    "Дней до прибытия",
    "Номер контейнера",
]

CONTAINER_MIN_LEN = 7
CONTAINER_MAX_LEN = 32
DAYS_MIN = 0
DAYS_MAX = 365

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


class ValidationError(ValueError):
    pass


def normalize_container(raw: str) -> str:
    """Trim + uppercase; accept alphanumeric 7-32 chars; reject internal
    whitespace, control characters and unproven punctuation.

    Must accept 'ONEYSELGF1046602' (16 chars) and must NOT enforce a
    4-letter + 7-digit shape.
    """
    if raw is None:
        raise ValidationError("container is required")
    trimmed = raw.strip()
    if not trimmed:
        raise ValidationError("container is empty after trim")
    if _CONTROL_CHAR_RE.search(trimmed):
        raise ValidationError("container contains control characters")
    if any(ch.isspace() for ch in trimmed):
        raise ValidationError("container contains internal whitespace")
    upper = trimmed.upper()
    if not upper.isalnum():
        raise ValidationError("container must be alphanumeric only")
    if not (CONTAINER_MIN_LEN <= len(upper) <= CONTAINER_MAX_LEN):
        raise ValidationError(
            f"container length must be {CONTAINER_MIN_LEN}-{CONTAINER_MAX_LEN} chars"
        )
    return upper


def normalize_days(raw) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError("days must be an integer")
    if not (DAYS_MIN <= value <= DAYS_MAX):
        raise ValidationError(f"days must be within {DAYS_MIN}-{DAYS_MAX}")
    return value


def compute_eta(departure_date: Optional[date], days_to_arrival: Optional[int]) -> Optional[date]:
    """Single canonical ETA function. Returns None (=> render 'не указано')
    when either input is missing. Never fabricates a value.
    """
    if departure_date is None or days_to_arrival is None:
        return None
    if not isinstance(days_to_arrival, int):
        raise ValidationError("days_to_arrival must be int for ETA computation")
    return departure_date + timedelta(days=days_to_arrival)


def render_field(value) -> str:
    return "не указано" if value is None else str(value)


@dataclass
class LogisticsRecord:
    ua_id: str
    stage: Optional[str] = None
    container: Optional[str] = None
    departure_date: Optional[date] = None
    days_to_arrival: Optional[int] = None

    def eta(self) -> Optional[date]:
        return compute_eta(self.departure_date, self.days_to_arrival)

    def render_hub_text(self) -> str:
        lines = [
            f"{HUB_BUTTON_TEXT} — {self.ua_id}",
            f"Этап: {render_field(self.stage)}",
            f"Контейнер: {render_field(self.container)}",
            f"Дата отправления: {render_field(self.departure_date)}",
            f"Дней до прибытия: {render_field(self.days_to_arrival)}",
            f"ETA: {render_field(self.eta())}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Callback data scheme (Telegram inline buttons). Deterministic, bounded,
# unique per action+ua_id. Telegram hard limit is 64 bytes.
# ---------------------------------------------------------------------------

def cb_hub(ua_id: str) -> str:
    return f"logi:hub:{ua_id}"


def cb_stage(ua_id: str) -> str:
    return f"logi:stage:{ua_id}"


def cb_container_date(ua_id: str) -> str:
    return f"logi:cd:{ua_id}"


def cb_days(ua_id: str) -> str:
    return f"logi:days:{ua_id}"


def cb_back(context: str, ua_id: str) -> str:
    return f"logi:back:{context}:{ua_id}"


def assert_callback_valid(cb: str) -> None:
    encoded = cb.encode("utf-8")
    if len(encoded) > 64:
        raise ValidationError(f"callback_data exceeds 64 bytes: {cb!r}")
    if not cb:
        raise ValidationError("callback_data must not be empty")


# ---------------------------------------------------------------------------
# Generic menu construction used to prove: exactly one hub entry in main
# menu, exactly one hub entry in card editor, old duplicates removed.
# ---------------------------------------------------------------------------

@dataclass
class MenuButton:
    text: str
    callback_data: str


@dataclass
class Menu:
    name: str
    buttons: list = field(default_factory=list)

    def add(self, text: str, callback_data: str) -> "MenuButton":
        btn = MenuButton(text=text, callback_data=callback_data)
        self.buttons.append(btn)
        return btn

    def count_button_text(self, text: str) -> int:
        return sum(1 for b in self.buttons if b.text == text)

    def has_any(self, texts) -> bool:
        return any(self.count_button_text(t) > 0 for t in texts)


def build_main_menu(ua_ids) -> Menu:
    """Canonical candidate main-menu shape: exactly one hub entry point,
    then normal car selection (represented here as a nested selection step
    outside this function's responsibility), then the hub itself.
    """
    menu = Menu(name="main_menu")
    menu.add(HUB_BUTTON_TEXT, "logi:menu:select_car")
    return menu


def build_card_editor_menu(ua_id: str) -> Menu:
    """Canonical candidate card-editor shape: exactly one hub entry that
    goes straight into the hub for the already-selected ua_id, replacing
    the old 'Дней до прибытия' / 'Номер контейнера' controls.
    """
    menu = Menu(name=f"card_editor:{ua_id}")
    menu.add(HUB_BUTTON_TEXT, cb_hub(ua_id))
    return menu


def build_hub_menu(record: LogisticsRecord, back_context: str) -> Menu:
    menu = Menu(name=f"hub:{record.ua_id}")
    menu.add("Этап", cb_stage(record.ua_id))
    menu.add("Контейнер и дата", cb_container_date(record.ua_id))
    menu.add("Дней до прибытия", cb_days(record.ua_id))
    menu.add("Назад", cb_back(back_context, record.ua_id))
    return menu


# ---------------------------------------------------------------------------
# Deterministic text transform: remove old duplicate label lines, and
# ensure exactly one canonical hub button line is present in a given menu
# builder source block. Works on arbitrary source text using the anchor
# labels only (no hardcoded file/function names), so it is safe to apply
# repeatedly (idempotent) once real anchors are confirmed by discovery.
# ---------------------------------------------------------------------------

def remove_old_duplicate_lines(source_text: str, labels) -> str:
    lines = source_text.splitlines(keepends=True)
    kept = []
    for line in lines:
        if any(label in line for label in labels):
            continue
        kept.append(line)
    return "".join(kept)


def ensure_single_hub_button_line(source_text: str, insertion_after_marker: str) -> str:
    """Idempotent: if the hub button line already exists, source is
    returned unchanged. Otherwise it is inserted once, immediately after
    the given marker line.
    """
    if HUB_BUTTON_TEXT in source_text:
        return source_text
    lines = source_text.splitlines(keepends=True)
    out = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and insertion_after_marker in line:
            out.append(f'    add_button("{HUB_BUTTON_TEXT}", cb_hub(ua_id))\n')
            inserted = True
    if not inserted:
        # fail closed rather than silently appending at an unproven location
        raise ValidationError(
            "insertion marker not found; refusing to guess insertion point"
        )
    return "".join(out)


def apply_candidate_transform(source_text: str, remove_labels, insertion_after_marker: str) -> str:
    step1 = remove_old_duplicate_lines(source_text, remove_labels)
    step2 = ensure_single_hub_button_line(step1, insertion_after_marker)
    return step2


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply_n_times_stable(source_text: str, remove_labels, insertion_after_marker: str, n: int = 10):
    """Applies the transform n times, feeding each output back in as the
    next input. After the first application it must be a no-op, so all
    n candidate hashes (from application 1 onward) must be identical.
    Returns the list of hashes for test inspection.
    """
    hashes = []
    current = source_text
    for _ in range(n):
        current = apply_candidate_transform(current, remove_labels, insertion_after_marker)
        hashes.append(sha256_text(current))
    return hashes, current
