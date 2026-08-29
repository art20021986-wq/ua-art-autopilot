#!/usr/bin/env python3
"""Pure sandbox contract for CRM-CONTAINER-STAGE-SYNC-004 v1.0.

The module deliberately has no production filesystem access.  It proves the
row-level transaction and keyboard contract against a throwaway SQLite copy.
A production adapter must stage/validate its bounded publication bundle in
``publish_gate`` and may only return True after that gate passes.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Mapping, MutableSequence, Optional

CANONICAL_FERRY_STATUS = "sea_loaded"
LEGACY_FERRY_STATUS = "sea_transit"
FERRY_OWNER_LABEL = "На пароме"
DIAGNOSTIC_PLACEHOLDER_TEXT = "Материалы диагностики ожидаются."
MIN_DAYS = 0
MAX_DAYS = 400
LATER_PREFIXES = ("ge_", "ua_")
TERMINAL_STATUSES = {"sold_transit", "sold", "archive", "ua_handed"}


class StageSyncError(RuntimeError):
    """Fail-closed stage/ETA contract violation."""


@dataclass(frozen=True)
class TransitionResult:
    car_id: int
    status: str
    days_to_kyiv: int
    eta_manual: str
    changed: bool


def diagnostic_or_placeholder(card_id: str, diagnostic_html: Optional[str]) -> str:
    """Return real diagnostics or a deterministic canonical placeholder."""
    if diagnostic_html and diagnostic_html.strip():
        return diagnostic_html
    safe_id = str(card_id or "").strip().upper()
    if not safe_id.startswith("UA-"):
        raise StageSyncError("INVALID_CARD_ID")
    return (
        "<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\">"
        "<title>{0} — диагностика</title></head><body><h1>{0}</h1>"
        "<p>{1}</p></body></html>"
    ).format(safe_id, DIAGNOSTIC_PLACEHOLDER_TEXT)


def validate_days(days: int) -> int:
    if isinstance(days, bool) or not isinstance(days, int):
        raise StageSyncError("DAYS_MUST_BE_INTEGER")
    if not MIN_DAYS <= days <= MAX_DAYS:
        raise StageSyncError("DAYS_OUT_OF_RANGE")
    return days


def eta_date(today: date, days: int) -> str:
    validate_days(days)
    return (today + timedelta(days=days)).isoformat()


def status_after_container_eta(current_status: object) -> str:
    """Canonicalize ferry rows without ever moving a later/terminal row back."""
    status = str(current_status or "").strip()
    if status.startswith(LATER_PREFIXES) or status in TERMINAL_STATUSES:
        return status
    return CANONICAL_FERRY_STATUS


def owner_status_label(status: object, fallback: str = "—") -> str:
    if str(status or "").strip() in {CANONICAL_FERRY_STATUS, LEGACY_FERRY_STATUS}:
        return FERRY_OWNER_LABEL
    return str(status or fallback)


def _button_callback(button: Mapping) -> str:
    return str(button.get("callback_data") or button.get("callback") or "")


def remove_in_transit_button(rows: MutableSequence[MutableSequence[Mapping]]) -> list[list[Mapping]]:
    """Remove only the standalone sea_transit action; sold_transit is preserved."""
    result: list[list[Mapping]] = []
    for row in rows:
        kept = []
        for button in row:
            callback = _button_callback(button)
            action = str(button.get("action") or "")
            exact_text = str(button.get("text") or "").strip().casefold()
            standalone = (
                callback.endswith(":" + LEGACY_FERRY_STATUS)
                or action == "in_transit"
                or (exact_text == "в пути" and "sold_transit" not in callback)
            )
            if not standalone:
                kept.append(button)
        if kept:
            result.append(kept)
    return result


def audit_buttons(rows: MutableSequence[MutableSequence[Mapping]]) -> dict:
    callbacks = [_button_callback(button) for row in rows for button in row]
    return {
        "sea_transit": sum(value.endswith(":" + LEGACY_FERRY_STATUS) for value in callbacks),
        "sea_loaded": sum(value.endswith(":" + CANONICAL_FERRY_STATUS) for value in callbacks),
        "sold_transit": sum(value.endswith(":sold_transit") for value in callbacks),
    }


def _columns(conn: sqlite3.Connection) -> set[str]:
    return {str(row[1]) for row in conn.execute("PRAGMA table_info(cars)")}


def save_container_eta_atomic(
    conn: sqlite3.Connection,
    car_id: int,
    days: int,
    *,
    today: Optional[date] = None,
    publish_gate: Callable[[Mapping], bool],
    updated_at: Optional[str] = None,
) -> TransitionResult:
    """Save ETA + canonical ferry status in one verified SQLite transaction.

    ``publish_gate`` is a fail-closed staging/validation callback.  It must not
    claim success before the bounded candidate bundle is ready.  A False value
    rolls the database transaction back and no success result is returned.
    """
    validate_days(days)
    today = today or datetime.now(timezone.utc).date()
    eta = eta_date(today, days)
    columns = _columns(conn)
    required = {"id", "status", "days_to_kyiv", "eta_manual"}
    missing = sorted(required - columns)
    if missing:
        raise StageSyncError("SCHEMA_MISSING:" + ",".join(missing))
    if not callable(publish_gate):
        raise StageSyncError("PUBLISH_GATE_REQUIRED")

    owns_transaction = not conn.in_transaction
    try:
        if owns_transaction:
            conn.execute("BEGIN IMMEDIATE")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, status, days_to_kyiv, eta_manual"
            + (", updated_at" if "updated_at" in columns else "")
            + " FROM cars WHERE id=?",
            (car_id,),
        ).fetchone()
        if row is None:
            raise StageSyncError("CARD_NOT_FOUND")
        before = dict(row)
        status = status_after_container_eta(before.get("status"))
        stamp = updated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        assignments = ["status=?", "days_to_kyiv=?", "eta_manual=?"]
        values: list[object] = [status, days, eta]
        if "updated_at" in columns:
            assignments.append("updated_at=?")
            values.append(stamp)
        values.append(car_id)
        conn.execute("UPDATE cars SET " + ", ".join(assignments) + " WHERE id=?", values)
        verify = conn.execute(
            "SELECT id, status, days_to_kyiv, eta_manual"
            + (", updated_at" if "updated_at" in columns else "")
            + " FROM cars WHERE id=?",
            (car_id,),
        ).fetchone()
        after = dict(verify) if verify is not None else {}
        if (
            str(after.get("status") or "") != status
            or int(after.get("days_to_kyiv")) != days
            or str(after.get("eta_manual") or "") != eta
        ):
            raise StageSyncError("READ_BACK_MISMATCH")
        if publish_gate(after) is not True:
            raise StageSyncError("PUBLISH_GATE_FAILED")
        changed = any(
            str(before.get(key) or "") != str(after.get(key) or "")
            for key in ("status", "days_to_kyiv", "eta_manual")
        )
        if owns_transaction:
            conn.commit()
        return TransitionResult(car_id, status, days, eta, changed)
    except Exception:
        if owns_transaction and conn.in_transaction:
            conn.rollback()
        raise


def normalize_legacy_ferry_rows(conn: sqlite3.Connection) -> list[int]:
    """Sandbox migration: sea_transit -> sea_loaded, nothing else."""
    owns_transaction = not conn.in_transaction
    try:
        if owns_transaction:
            conn.execute("BEGIN IMMEDIATE")
        ids = [int(row[0]) for row in conn.execute(
            "SELECT id FROM cars WHERE status=? ORDER BY id", (LEGACY_FERRY_STATUS,)
        )]
        conn.execute(
            "UPDATE cars SET status=? WHERE status=?",
            (CANONICAL_FERRY_STATUS, LEGACY_FERRY_STATUS),
        )
        remains = conn.execute(
            "SELECT COUNT(*) FROM cars WHERE status=?", (LEGACY_FERRY_STATUS,)
        ).fetchone()[0]
        if remains:
            raise StageSyncError("LEGACY_STATUS_REMAINS")
        if owns_transaction:
            conn.commit()
        return ids
    except Exception:
        if owns_transaction and conn.in_transaction:
            conn.rollback()
        raise
