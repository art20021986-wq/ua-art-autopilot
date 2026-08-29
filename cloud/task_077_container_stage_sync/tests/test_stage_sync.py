#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sqlite3
import sys
import unittest
from datetime import date

BASE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import stage_sync as s  # noqa: E402

SCHEMA = """
CREATE TABLE cars (
  id INTEGER PRIMARY KEY,
  auto_number TEXT,
  status TEXT,
  days_to_kyiv INTEGER,
  eta_manual TEXT,
  updated_at TEXT,
  photos TEXT,
  videos TEXT
);
"""


def connection():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT INTO cars VALUES (?,?,?,?,?,?,?,?)",
        [
            (12, "UA-0012", "sea_transit", 11, "2026-09-09", "old", '["p"]', '["v"]'),
            (13, "UA-0013", "kr_bought", None, None, None, '["future"]', "[]"),
            (14, "UA-0014", "ge_waiting", 15, "2026-09-13", None, "[]", "[]"),
            (15, "UA-0015", "sold_transit", 30, "2026-09-28", None, "[]", "[]"),
        ],
    )
    conn.commit()
    return conn


class AtomicTransitionTests(unittest.TestCase):
    def test_ua0012_30_days_becomes_canonical_ferry(self):
        conn = connection()
        result = s.save_container_eta_atomic(
            conn, 12, 30, today=date(2026, 8, 29), publish_gate=lambda row: True,
            updated_at="2026-08-29T06:30:00+00:00",
        )
        self.assertEqual(result.status, "sea_loaded")
        self.assertEqual(result.eta_manual, "2026-09-28")
        row = conn.execute(
            "SELECT status,days_to_kyiv,eta_manual,photos,videos FROM cars WHERE id=12"
        ).fetchone()
        self.assertEqual(row[:3], ("sea_loaded", 30, "2026-09-28"))
        self.assertEqual(row[3:], ('["p"]', '["v"]'))
        self.assertEqual(s.owner_status_label(row[0]), "На пароме")

    def test_future_card_uses_same_rule(self):
        conn = connection()
        result = s.save_container_eta_atomic(
            conn, 13, 30, today=date(2026, 8, 29), publish_gate=lambda row: True
        )
        self.assertEqual((result.status, result.eta_manual), ("sea_loaded", "2026-09-28"))

    def test_later_and_terminal_stages_never_regress(self):
        conn = connection()
        ge = s.save_container_eta_atomic(
            conn, 14, 30, today=date(2026, 8, 29), publish_gate=lambda row: True
        )
        sold = s.save_container_eta_atomic(
            conn, 15, 30, today=date(2026, 8, 29), publish_gate=lambda row: True
        )
        self.assertEqual(ge.status, "ge_waiting")
        self.assertEqual(sold.status, "sold_transit")

    def test_boundaries_and_invalid_values(self):
        for value in (0, 1, 30, 400):
            conn = connection()
            result = s.save_container_eta_atomic(
                conn, 13, value, today=date(2026, 8, 29), publish_gate=lambda row: True
            )
            self.assertEqual(result.days_to_kyiv, value)
        for value in (-1, 401, True, "30"):
            conn = connection()
            with self.assertRaises(s.StageSyncError):
                s.save_container_eta_atomic(
                    conn, 13, value, today=date(2026, 8, 29), publish_gate=lambda row: True
                )

    def test_publisher_failure_rolls_back_every_field(self):
        conn = connection()
        before = conn.execute(
            "SELECT status,days_to_kyiv,eta_manual,updated_at FROM cars WHERE id=12"
        ).fetchone()
        with self.assertRaisesRegex(s.StageSyncError, "PUBLISH_GATE_FAILED"):
            s.save_container_eta_atomic(
                conn, 12, 30, today=date(2026, 8, 29), publish_gate=lambda row: False
            )
        after = conn.execute(
            "SELECT status,days_to_kyiv,eta_manual,updated_at FROM cars WHERE id=12"
        ).fetchone()
        self.assertEqual(tuple(after), tuple(before))

    def test_idempotent_repeat(self):
        conn = connection()
        first = s.save_container_eta_atomic(
            conn, 12, 30, today=date(2026, 8, 29), publish_gate=lambda row: True,
            updated_at="2026-08-29T06:30:00+00:00",
        )
        second = s.save_container_eta_atomic(
            conn, 12, 30, today=date(2026, 8, 29), publish_gate=lambda row: True,
            updated_at="2026-08-29T06:30:00+00:00",
        )
        self.assertTrue(first.changed)
        self.assertFalse(second.changed)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM cars WHERE id=12").fetchone()[0], 1)


class KeyboardAndMigrationTests(unittest.TestCase):
    def test_only_standalone_in_transit_button_is_removed(self):
        rows = [[
            {"text": "Загружено в контейнер", "callback_data": "car_setstage:12:sea_loaded"},
            {"text": "В пути", "callback_data": "car_setstage:12:sea_transit"},
        ], [
            {"text": "Продано · в пути", "callback_data": "car_setstage:12:sold_transit"},
        ]]
        candidate = s.remove_in_transit_button(rows)
        audit = s.audit_buttons(candidate)
        self.assertEqual(audit, {"sea_transit": 0, "sea_loaded": 1, "sold_transit": 1})

    def test_legacy_rows_are_normalized_without_touching_other_stages(self):
        conn = connection()
        changed = s.normalize_legacy_ferry_rows(conn)
        self.assertEqual(changed, [12])
        statuses = dict(conn.execute("SELECT id,status FROM cars"))
        self.assertEqual(statuses[12], "sea_loaded")
        self.assertEqual(statuses[14], "ge_waiting")
        self.assertEqual(statuses[15], "sold_transit")

    def test_missing_diagnostics_gets_placeholder_instead_of_blocking(self):
        page = s.diagnostic_or_placeholder("UA-0012", None)
        self.assertIn("UA-0012", page)
        self.assertIn("Материалы диагностики ожидаются", page)
        self.assertNotIn("SEO068_DIAGNOSTIC_TARGET_MISSING", page)


if __name__ == "__main__":
    unittest.main()
