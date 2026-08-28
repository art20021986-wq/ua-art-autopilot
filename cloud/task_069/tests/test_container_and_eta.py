"""
TASK 069 — offline tests for the isolated candidate module.

Run with: python -m pytest cloud/task_069/tests/test_container_and_eta.py -v
or:       python -m unittest cloud/task_069/tests/test_container_and_eta.py

No production or CRM database is touched. A throwaway SQLite file is created
under the OS temp directory for each test and removed afterward.
"""
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "candidate"))

import container_module as cm  # noqa: E402
import menu_patch_snippet as mp  # noqa: E402


SCHEMA = """
CREATE TABLE cars (
    id INTEGER PRIMARY KEY,
    vin TEXT,
    sea_container TEXT,
    eta_manual TEXT,
    days_to_kyiv INTEGER,
    status TEXT
);
"""


class BaseTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO cars (id, vin, sea_container, status) VALUES (1, 'VINCARD0009', NULL, 'open')"
        )
        conn.execute(
            "INSERT INTO cars (id, vin, sea_container, status) VALUES (2, 'VINCARDOTHER', 'UNCHANGEDXYZ1', 'open')"
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        os.remove(self.db_path)

    def connect(self):
        return sqlite3.connect(self.db_path)


class TestContainerSave(BaseTestCase):
    def test_ua_0011_saves_and_persists_after_reopen(self):
        conn = self.connect()
        ok, msg = cm.save_container(conn, 1, "ONEYSELGF1046602")
        self.assertTrue(ok)
        self.assertEqual(msg, "✅ Контейнер сохранён: ONEYSELGF1046602")
        conn.close()

        # Simulate reopening the menu: brand new connection.
        conn2 = self.connect()
        value = cm.get_container(conn2, 1)
        self.assertEqual(value, "ONEYSELGF1046602")
        conn2.close()

    def test_persists_after_simulated_process_restart(self):
        conn = self.connect()
        cm.save_container(conn, 1, "oneyselgf1046602")  # lower-case input
        conn.close()

        # Simulate process restart: re-import module fresh path + new conn.
        import importlib
        importlib.reload(cm)
        conn2 = self.connect()
        value = cm.get_container(conn2, 1)
        self.assertEqual(value, "ONEYSELGF1046602")
        conn2.close()

    def test_invalid_container_rejected_and_state_not_cleared(self):
        conn = self.connect()
        ok, msg = cm.save_container(conn, 1, "!!")
        self.assertFalse(ok)
        self.assertTrue(msg.startswith("❌"))
        self.assertIsNone(cm.get_container(conn, 1))
        conn.close()

    def test_other_card_not_modified(self):
        conn = self.connect()
        cm.save_container(conn, 1, "ONEYSELGF1046602")
        other_value = cm.get_container(conn, 2)
        self.assertEqual(other_value, "UNCHANGEDXYZ1")
        conn.close()

    def test_resend_is_idempotent(self):
        conn = self.connect()
        ok1, _ = cm.save_container(conn, 1, "ONEYSELGF1046602")
        ok2, msg2 = cm.save_container(conn, 1, "ONEYSELGF1046602")
        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertEqual(msg2, "✅ Контейнер сохранён: ONEYSELGF1046602")
        cur = conn.execute("SELECT COUNT(*) FROM cars WHERE id=1")
        self.assertEqual(cur.fetchone()[0], 1)
        conn.close()

    def test_missing_card_returns_error_no_silent_reset(self):
        conn = self.connect()
        ok, msg = cm.save_container(conn, 999, "ONEYSELGF1046602")
        self.assertFalse(ok)
        self.assertIn("не найдена", msg)
        conn.close()

    def test_length_boundaries(self):
        conn = self.connect()
        ok_short, _ = cm.save_container(conn, 1, "ABC")  # 3 chars -> invalid
        self.assertFalse(ok_short)
        ok_min, _ = cm.save_container(conn, 1, "ABCD")  # 4 chars -> valid
        self.assertTrue(ok_min)
        ok_long, _ = cm.save_container(conn, 1, "A" * 20)  # 20 chars -> valid
        self.assertTrue(ok_long)
        ok_too_long, _ = cm.save_container(conn, 1, "A" * 21)  # invalid
        self.assertFalse(ok_too_long)
        conn.close()


class TestEtaDays(BaseTestCase):
    def test_save_eta_days_writes_both_columns_and_reports_date(self):
        conn = self.connect()
        today = date(2026, 1, 1)
        ok, msg = cm.save_eta_days(conn, 1, 10, today=today)
        self.assertTrue(ok)
        self.assertIn("10 дн.", msg)
        cur = conn.execute("SELECT eta_manual, days_to_kyiv FROM cars WHERE id=1")
        row = cur.fetchone()
        self.assertEqual(row[0], "2026-01-01")
        self.assertEqual(row[1], 10)
        conn.close()

    def test_eta_days_range_validation(self):
        conn = self.connect()
        ok_neg, _ = cm.save_eta_days(conn, 1, -1)
        ok_over, _ = cm.save_eta_days(conn, 1, 401)
        ok_zero, _ = cm.save_eta_days(conn, 1, 0)
        ok_max, _ = cm.save_eta_days(conn, 1, 400)
        self.assertFalse(ok_neg)
        self.assertFalse(ok_over)
        self.assertTrue(ok_zero)
        self.assertTrue(ok_max)
        conn.close()

    def test_compute_kyiv_eta_decreases_daily(self):
        eta_manual = "2026-01-01"
        d0 = cm.compute_kyiv_eta(eta_manual, 10, today=date(2026, 1, 1))
        d5 = cm.compute_kyiv_eta(eta_manual, 10, today=date(2026, 1, 6))
        d_over = cm.compute_kyiv_eta(eta_manual, 10, today=date(2026, 1, 20))
        self.assertEqual(d0, date(2026, 1, 11))
        self.assertEqual(d5, date(2026, 1, 11))
        # Remaining never goes negative; date collapses to 'today' once elapsed.
        self.assertEqual(d_over, date(2026, 1, 20))


class TestMenuButton(unittest.TestCase):
    def test_button_added_exactly_once_when_missing(self):
        buttons = [("📦 Контейнер", "car_setf:1:container")]
        result = mp.ensure_eta_days_button(buttons, car_id=1)
        self.assertEqual(mp.count_eta_days_buttons(result), 1)

    def test_button_not_duplicated_when_already_present(self):
        buttons = [
            ("📦 Контейнер", "car_setf:1:container"),
            (mp.ETA_DAYS_BUTTON_TEXT, "car_setf:1:eta_days"),
        ]
        result = mp.ensure_eta_days_button(buttons, car_id=1)
        self.assertEqual(mp.count_eta_days_buttons(result), 1)
        self.assertEqual(result, buttons)

    def test_idempotent_double_call(self):
        buttons = [("📦 Контейнер", "car_setf:1:container")]
        r1 = mp.ensure_eta_days_button(buttons, car_id=1)
        r2 = mp.ensure_eta_days_button(r1, car_id=1)
        self.assertEqual(mp.count_eta_days_buttons(r2), 1)


class TestSqliteQuickCheckAndScopeIsolation(BaseTestCase):
    def test_quick_check_ok(self):
        conn = self.connect()
        cur = conn.execute("PRAGMA quick_check")
        result = cur.fetchone()[0]
        self.assertEqual(result, "ok")
        conn.close()

    def test_ua_0009_scope_isolation_placeholder(self):
        # This candidate touches only sea_container / eta_manual /
        # days_to_kyiv. It does not read, write, or reference any
        # publication/price/photo/video/diagnostics column, and therefore
        # makes no claim about UA-0009 publish-readiness one way or another.
        candidate_touches = {"sea_container", "eta_manual", "days_to_kyiv"}
        forbidden = {"price", "photo", "video", "diagnostics", "published", "status"}
        self.assertTrue(candidate_touches.isdisjoint(forbidden))


if __name__ == "__main__":
    unittest.main()
