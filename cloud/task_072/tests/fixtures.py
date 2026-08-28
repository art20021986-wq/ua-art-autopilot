"""
Synthetic reference fixture that mirrors the *confirmed* live schema facts from TASK 071
evidence (cars_count=11, UA-0001..UA-0011, single UA-0009 row, condition_text/description/
diag_text coexisting) WITHOUT containing any real production data. All values here are
synthetic placeholders created for offline testing only.

This fixture also includes a baseline ("buggy") reference module reproducing the two
confirmed root-cause defects, purely for regression comparison inside this test suite. It
is NOT the real db.py/cars_ui.py; those were never provided to this worker.
"""
from __future__ import annotations

import sqlite3


def make_synthetic_crm_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE cars (
            card_id TEXT PRIMARY KEY,
            vin TEXT,
            condition_text TEXT,
            description TEXT,
            diag_text TEXT,
            price TEXT
        );
        CREATE TABLE audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id TEXT,
            operation_id TEXT UNIQUE,
            field TEXT,
            action TEXT,
            actor TEXT,
            created_at TEXT,
            new_value TEXT
        );
        """
    )
    for i in range(1, 12):
        card_id = f"UA-{i:04d}"
        conn.execute(
            "INSERT INTO cars (card_id, vin, condition_text, description, diag_text, price) "
            "VALUES (?, ?, NULL, NULL, NULL, ?)",
            (card_id, f"SYNTHVIN{i:04d}0000000", "500 $"),
        )
    conn.commit()
    conn.close()


def quick_check(path: str) -> str:
    conn = sqlite3.connect(path)
    result = conn.execute("PRAGMA quick_check").fetchone()[0]
    conn.close()
    return result


def cars_count(path: str) -> int:
    conn = sqlite3.connect(path)
    n = conn.execute("SELECT COUNT(*) FROM cars").fetchone()[0]
    conn.close()
    return n


class BuggyReferenceWaitState:
    """Reproduces confirmed defect #1: car_wait popped before confirmed write,
    so a lock error loses the editing mode."""

    def __init__(self):
        self.user_data = {}

    def catch_message(self, card_id: str, text: str, simulate_lock: bool) -> str:
        wait = self.user_data.get("car_wait")
        if wait and text:
            self.user_data.pop("car_wait", None)  # BUG: popped before confirmed write
            if simulate_lock:
                raise sqlite3.OperationalError("database is locked")
            return "OK"
        return "NO_WAIT"
