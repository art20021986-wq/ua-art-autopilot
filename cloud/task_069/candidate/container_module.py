"""
TASK 069 — isolated candidate module (NOT wired into production).

Implements:
  - strict container-number normalization/validation (4-20 latin letters/digits)
  - transactional save into an explicitly-identified open card, with
    mandatory read-back verification before clearing any "awaiting input"
    state
  - manual ETA-to-Kyiv-days save (0-400) into eta_manual + days_to_kyiv,
    manual value taking priority over any auto/default value, decreasing
    daily by calendar date

This module has no side effects on import and does not touch any real
production or CRM database. It is designed to be schema-compatible with a
`cars` table containing at least:
    id INTEGER PRIMARY KEY
    sea_container TEXT
    eta_manual TEXT   -- ISO date the manual value was set
    days_to_kyiv INTEGER
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

CONTAINER_RE = re.compile(r"^[A-Z0-9]{4,20}$")

MIN_DAYS = 0
MAX_DAYS = 400


class ContainerSaveError(Exception):
    """Raised when a container number cannot be validated or saved.

    Handlers must NOT clear their 'awaiting container' state when this is
    raised — they must show the message to the user and keep waiting.
    """


class EtaDaysError(Exception):
    """Raised when an ETA-days value cannot be validated or saved."""


def normalize_container(raw_text: str) -> str:
    """Normalize a raw user message into a candidate container code.

    Trims whitespace, uppercases, and strips internal spaces/dashes that
    users sometimes type (e.g. 'ONEY SELG F1046602' or 'ONEY-SELGF1046602').
    Does NOT validate the shape; call is_valid_container() separately.
    """
    if raw_text is None:
        return ""
    text = raw_text.strip().upper()
    text = re.sub(r"[\s\-_]+", "", text)
    return text


def is_valid_container(normalized: str) -> bool:
    return bool(CONTAINER_RE.match(normalized))


def save_container(
    conn: sqlite3.Connection,
    car_id: int,
    raw_text: str,
) -> Tuple[bool, str]:
    """Save a container number into the explicitly-opened card `car_id`.

    Returns (ok, message). On ok=False, the caller MUST NOT clear its
    awaiting-input state and MUST show `message` to the user verbatim (or
    wrapped), so the failure is never silent.

    On ok=True the write has already been verified via read-back and
    committed; the caller may safely clear the awaiting-input state and
    reply with the returned message.

    Idempotent: sending the same already-normalized value again for the same
    card is a no-op success (read-back already matches).
    """
    if car_id is None:
        return False, "❌ Ошибка: карточка не открыта явно. Повторите ввод после открытия карточки."

    normalized = normalize_container(raw_text)
    if not is_valid_container(normalized):
        return (
            False,
            "❌ Неверный номер контейнера. Нужно 4–20 латинских букв/цифр, например ONEYSELGF1046602.",
        )

    cur = conn.cursor()
    cur.execute("SELECT id, sea_container FROM cars WHERE id = ?", (car_id,))
    row = cur.fetchone()
    if row is None:
        return False, f"❌ Ошибка: карточка id={car_id} не найдена. Ничего не сохранено."

    current_value = row[1]
    if current_value == normalized:
        # Idempotent resend: already correct, nothing to change.
        return True, f"✅ Контейнер сохранён: {normalized}"

    try:
        cur.execute(
            "UPDATE cars SET sea_container = ? WHERE id = ?",
            (normalized, car_id),
        )
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        return False, f"❌ Ошибка записи в базу: {exc}. Повторите ввод."

    # Mandatory read-back verification before declaring success.
    cur.execute("SELECT sea_container FROM cars WHERE id = ?", (car_id,))
    verify_row = cur.fetchone()
    if verify_row is None or verify_row[0] != normalized:
        return (
            False,
            "❌ Не удалось подтвердить сохранение контейнера (read-back не совпал). Повторите ввод.",
        )

    return True, f"✅ Контейнер сохранён: {normalized}"


def get_container(conn: sqlite3.Connection, car_id: int) -> Optional[str]:
    cur = conn.cursor()
    cur.execute("SELECT sea_container FROM cars WHERE id = ?", (car_id,))
    row = cur.fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# ETA to Kyiv (days) — manual value takes priority, decreases daily.
# ---------------------------------------------------------------------------


def save_eta_days(
    conn: sqlite3.Connection,
    car_id: int,
    days: int,
    today: Optional[date] = None,
) -> Tuple[bool, str]:
    """Save a manual ETA-to-Kyiv value.

    Writes eta_manual = today's ISO date, days_to_kyiv = days.
    Range 0..400 inclusive. Manual value overrides any automatic default
    (e.g. the old fixed '15 days') and is meant to be reduced daily by the
    calendar via compute_kyiv_eta(), not by mutating days_to_kyiv itself.
    """
    if car_id is None:
        return False, "❌ Ошибка: карточка не открыта явно."

    if not isinstance(days, int) or isinstance(days, bool):
        return False, "❌ Введите целое число дней (0–400)."

    if days < MIN_DAYS or days > MAX_DAYS:
        return False, f"❌ Число дней должно быть в диапазоне {MIN_DAYS}–{MAX_DAYS}."

    today = today or date.today()
    cur = conn.cursor()
    cur.execute("SELECT id FROM cars WHERE id = ?", (car_id,))
    if cur.fetchone() is None:
        return False, f"❌ Ошибка: карточка id={car_id} не найдена."

    try:
        cur.execute(
            "UPDATE cars SET eta_manual = ?, days_to_kyiv = ? WHERE id = ?",
            (today.isoformat(), days, car_id),
        )
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        return False, f"❌ Ошибка записи в базу: {exc}. Повторите ввод."

    cur.execute("SELECT eta_manual, days_to_kyiv FROM cars WHERE id = ?", (car_id,))
    verify = cur.fetchone()
    if verify is None or verify[0] != today.isoformat() or verify[1] != days:
        return False, "❌ Не удалось подтвердить сохранение срока (read-back не совпал)."

    kyiv_date = compute_kyiv_eta(today.isoformat(), days, today=today)
    kyiv_str = kyiv_date.isoformat() if kyiv_date else "—"
    return True, f"✅ Срок сохранён: {days} дн. до Киева (дата: {kyiv_str})"


def compute_kyiv_eta(
    eta_manual: Optional[str],
    days_to_kyiv: Optional[int],
    today: Optional[date] = None,
) -> Optional[date]:
    """Compute the effective Kyiv-arrival date.

    The stored days_to_kyiv is the value as of eta_manual's date. The
    effective remaining days decreases by calendar days elapsed since then,
    per the task's requirement that the manual value 'ежедневно уменьшается
    по календарю' (decreases daily by the calendar), never going below 0.
    """
    if eta_manual is None or days_to_kyiv is None:
        return None
    try:
        manual_date = datetime.strptime(eta_manual, "%Y-%m-%d").date()
    except ValueError:
        return None

    today = today or date.today()
    elapsed = (today - manual_date).days
    remaining = max(0, days_to_kyiv - max(0, elapsed))
    return today + timedelta(days=remaining)
