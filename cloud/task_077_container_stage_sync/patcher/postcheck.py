#!/usr/bin/env python3
"""
Postcheck / read-back verification tool for TASK 077.

GET-only for any remote resource; local sqlite reads use read-only mode.
Used by both the sandbox harness and (later, separately) any real Gate B run.
"""
from __future__ import annotations

import sqlite3


def readback_car(conn: sqlite3.Connection, car_id: str) -> dict:
    cur = conn.execute(
        "SELECT status, days_to_kyiv, eta_manual, updated_at, published FROM cars WHERE id=?",
        (car_id,),
    )
    row = cur.fetchone()
    if row is None:
        return {}
    return {
        "status": row[0],
        "days_to_kyiv": row[1],
        "eta_manual": row[2],
        "updated_at": row[3],
        "published": row[4],
    }


def verify_badge_and_category(status: str, badge: str, category: str) -> bool:
    from stage_sync_patch import site_badge_and_category  # local import for standalone use

    expected = site_badge_and_category(status)
    return expected["badge"] == badge and expected["category"] == category


def verify_no_standalone_transit_button(active_buttons) -> bool:
    for label, callback in active_buttons:
        if callback.endswith(":sea_transit") and "sold_transit" not in callback:
            return False
    return True


def verify_exactly_one_sea_loaded(active_buttons) -> bool:
    count = sum(1 for _, cb in active_buttons if cb.endswith(":sea_loaded"))
    return count == 1
