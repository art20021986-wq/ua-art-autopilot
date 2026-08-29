import os
import sys
import unittest
from datetime import timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "fixtures"))

from eta_transaction import EtaSyncController
from eta_engine import strip_stale_dates, compute_manual_eta
from mock_crm import MockCrmDb
from mock_publisher import MockPublisher


DESCRIPTIONS = {
    "UA-0009": "\u0410\u0432\u0442\u043e\u043c\u043e\u0431\u0438\u043b\u044c \u0432 \u043f\u0443\u0442\u0438, \u043f\u0440\u0438\u0431\u044b\u0442\u0438\u0435 \u043e\u0436\u0438\u0434\u0430\u0435\u0442\u0441\u044f 9 \u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f 2026 \u0433\u043e\u0434\u0430.",
    "UA-0010": "\u041a\u043e\u043c\u043f\u043b\u0435\u043a\u0442\u0430\u0446\u0438\u044f \u043f\u043e\u043b\u043d\u0430\u044f, \u043f\u0440\u0438\u0431\u044b\u0442\u0438\u0435 09.09.2026.",
    "UA-0011": "\u0412\u0441\u0435 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u044b \u0433\u043e\u0442\u043e\u0432\u044f\u0442\u0441\u044f, \u043e\u0436\u0438\u0434\u0430\u0435\u0442\u0441\u044f \u043f\u0440\u0438\u0431\u044b\u0442\u0438\u0435 28 \u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f 2026.",
}


class TestThreeCardBugFix(unittest.TestCase):
    def setUp(self):
        self.db = MockCrmDb()
        self.pub = MockPublisher()
        self.ctrl = EtaSyncController(self.db, self.pub)
        self.db.seed("UA-0009", days_to_kyiv=11, eta_manual="2026-09-09", updated_at="2026-08-29T06:12:00Z")
        self.db.seed("UA-0010", days_to_kyiv=11, eta_manual="2026-09-09", updated_at="2026-08-29T02:01:00Z")
        self.db.seed("UA-0011", days_to_kyiv=11, eta_manual="2026-09-09", updated_at="2026-08-29T06:12:00Z")

    def test_all_three_become_thirty_days_same_date(self):
        results = {}
        for car_id in ("UA-0009", "UA-0010", "UA-0011"):
            results[car_id] = self.ctrl.submit(car_id, 30)
        for car_id, r in results.items():
            self.assertTrue(r.success, f"{car_id} failed: {r.error}")
            self.assertEqual(r.days_to_kyiv, 30)
        dates = {r.eta_manual for r in results.values()}
        self.assertEqual(len(dates), 1, "all three cards must share one consistent computed date")

    def test_ua0010_simulated_original_defect_and_fix(self):
        self.db.fail_readback_once = True
        r = self.ctrl.submit("UA-0010", 30)
        if not r.success:
            self.assertTrue(r.retry_queued)
            retry_results = self.ctrl.process_retries()
            self.assertTrue(any(rr.success for rr in retry_results))
        else:
            self.assertEqual(r.days_to_kyiv, 30)

    def test_description_no_longer_contains_stale_date(self):
        for car_id, desc in DESCRIPTIONS.items():
            cleaned = strip_stale_dates(desc)
            self.assertNotRegex(
                cleaned,
                r"\d{1,2}\s+(\u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f|\u0430\u0432\u0433\u0443\u0441\u0442\u0430)",
            )
            self.assertNotRegex(cleaned, r"\d{2}\.\d{2}\.\d{4}")

    def test_two_consecutive_deterministic_canary_runs_match(self):
        run1 = compute_manual_eta(30, base_date=None)
        run2 = compute_manual_eta(30, base_date=run1.eta_manual - timedelta(days=30))
        self.assertEqual(run1.eta_manual, run2.eta_manual)


if __name__ == "__main__":
    unittest.main()
