"""
TASK 069 — defensive menu-patch snippet (isolated candidate, NOT applied to
production cars_ui.py).

Shows how to add exactly one '⏱ Количество дней до Киева' button to the
existing '📦 Контейнер, даты и сроки' menu, without duplicating it if it is
already present, and without touching any other button, stage, price, photo,
video, diagnostics, or publication logic.

The real integration point is wherever the production code currently builds
the inline keyboard for that menu (in cars_ui.py / konteyner.py). This
snippet is intentionally framework-agnostic pseudocode using a generic
(text, callback_data) button tuple representation so it can be adapted to
whatever keyboard library production actually uses (aiogram / pyTelegramBotAPI
/ python-telegram-bot), without guessing an API that may not match reality.
"""
from __future__ import annotations

from typing import Iterable, List, Tuple

ETA_DAYS_BUTTON_TEXT = "⏱ Количество дней до Киева"


def ensure_eta_days_button(
    buttons: List[Tuple[str, str]],
    car_id: int,
) -> List[Tuple[str, str]]:
    """Return `buttons` with exactly one ETA-days button present.

    `buttons` is a list of (text, callback_data) tuples representing the
    current '📦 Контейнер, даты и сроки' menu. If a button with the exact
    text ETA_DAYS_BUTTON_TEXT already exists (regardless of its
    callback_data), the list is returned unchanged (no duplicate added).
    Otherwise, one button is appended routing to the existing, unchanged
    `car_setf:<id>:eta_days` callback route.
    """
    for text, _cb in buttons:
        if text == ETA_DAYS_BUTTON_TEXT:
            return buttons

    new_buttons = list(buttons)
    new_buttons.append((ETA_DAYS_BUTTON_TEXT, f"car_setf:{car_id}:eta_days"))
    return new_buttons


def count_eta_days_buttons(buttons: Iterable[Tuple[str, str]]) -> int:
    return sum(1 for text, _cb in buttons if text == ETA_DAYS_BUTTON_TEXT)
