import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eta_engine import (
    compute_manual_eta, validate_days, InvalidDaysError,
    strip_stale_dates, compute_stage_eta, resolve_eta, eta_is_consistent,
)


class TestValidateDays(unittest.TestCase):
    def test_valid_values(self):
        for n in (0, 1, 30, 400):
            self.assertEqual(validate_days(n), n)

    def test_rejects_negative(self):
        with self.assertRaises(InvalidDaysError):
            validate_days(-1)

    def test_rejects_over_max(self):
        with self.assertRaises(InvalidDaysError):
            validate_days(401)

    def test_rejects_non_integer(self):
        with self.assertRaises(InvalidDaysError):
            validate_days(30.5)

    def test_rejects_non_numeric(self):
        with self.assertRaises(InvalidDaysError):
            validate_days("thirty")


class TestComputeManualEta(unittest.TestCase):
    def test_consistency(self):
        base = date(2026, 8, 29)
        eta = compute_manual_eta(30, base_date=base)
        self.assertEqual(eta.days_to_kyiv, 30)
        self.assertEqual(eta.eta_manual, base + timedelta(days=30))

    def test_ua0009_ua0011_thirty_days_same_date(self):
        base = date(2026, 8, 29)
        e1 = compute_manual_eta(30, base_date=base)
        e2 = compute_manual_eta(30, base_date=base)
        self.assertEqual(e1.eta_manual, e2.eta_manual)
        self.assertEqual(e1.eta_manual, date(2026, 9, 28))


class TestStageRule(unittest.TestCase):
    def test_stage3_fifteen_days_from_transition_not_payment(self):
        transition = date(2026, 8, 1)
        eta = compute_stage_eta(3, stage_entered_at=transition, base_date=date(2026, 8, 5))
        self.assertEqual(eta.eta_manual, date(2026, 8, 16))


class TestResolvePriority(unittest.TestCase):
    def test_manual_wins_over_stage(self):
        manual = compute_manual_eta(30, base_date=date(2026, 8, 29))
        stage = compute_stage_eta(3, date(2026, 8, 1), base_date=date(2026, 8, 29))
        resolved = resolve_eta(manual, stage)
        self.assertEqual(resolved.source, "manual")

    def test_neutral_when_nothing_available(self):
        resolved = resolve_eta(None, None)
        self.assertEqual(resolved.source, "neutral")


class TestConsistencyCheck(unittest.TestCase):
    def test_consistent_pair(self):
        base = date(2026, 8, 29)
        self.assertTrue(eta_is_consistent(30, "2026-09-28", base_date=base))

    def test_inconsistent_pair_blocks(self):
        base = date(2026, 8, 29)
        self.assertFalse(eta_is_consistent(11, "2026-09-28", base_date=base))


class TestStripStaleDates(unittest.TestCase):
    def test_removes_ru_worded_date(self):
        text = "\u041e\u0436\u0438\u0434\u0430\u0435\u043c\u043e\u0435 \u043f\u0440\u0438\u0431\u044b\u0442\u0438\u0435 9 \u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f 2026 \u0433\u043e\u0434\u0430, \u043c\u0430\u0448\u0438\u043d\u0430 \u0432 \u043e\u0442\u043b\u0438\u0447\u043d\u043e\u043c \u0441\u043e\u0441\u0442\u043e\u044f\u043d\u0438\u0438."
        cleaned = strip_stale_dates(text)
        self.assertNotIn("\u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f", cleaned)

    def test_removes_numeric_date(self):
        text = "\u041f\u0440\u0438\u0431\u044b\u0442\u0438\u0435: 09.09.2026, \u043a\u043e\u043c\u043f\u043b\u0435\u043a\u0442\u0430\u0446\u0438\u044f \u043f\u043e\u043b\u043d\u0430\u044f."
        cleaned = strip_stale_dates(text)
        self.assertNotIn("09.09.2026", cleaned)

    def test_no_stale_date_left_untouched(self):
        text = "\u041c\u0430\u0448\u0438\u043d\u0430 \u0432 \u043e\u0442\u043b\u0438\u0447\u043d\u043e\u043c \u0441\u043e\u0441\u0442\u043e\u044f\u043d\u0438\u0438, \u043a\u043e\u043c\u043f\u043b\u0435\u043a\u0442\u0430\u0446\u0438\u044f \u043f\u043e\u043b\u043d\u0430\u044f."
        self.assertEqual(strip_stale_dates(text), text)


if __name__ == "__main__":
    unittest.main()
