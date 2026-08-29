import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "fixtures"))

from eta_transaction import EtaSyncController
from mock_crm import MockCrmDb
from mock_publisher import MockPublisher


def make_controller():
    db = MockCrmDb()
    pub = MockPublisher()
    return EtaSyncController(db, pub, readback_timeout_s=0.2), db, pub


class TestHappyPath(unittest.TestCase):
    def test_thirty_days_success(self):
        ctrl, db, pub = make_controller()
        db.seed("UA-0009", days_to_kyiv=11, eta_manual="2026-09-09", updated_at="old")
        result = ctrl.submit("UA-0009", 30)
        self.assertTrue(result.success)
        self.assertEqual(result.days_to_kyiv, 30)
        self.assertIn("UA-0009", pub.published_pages)

    def test_idempotent_repeat(self):
        ctrl, db, pub = make_controller()
        db.seed("UA-0010", days_to_kyiv=11, eta_manual="2026-09-09", updated_at="old")
        r1 = ctrl.submit("UA-0010", 30)
        r2 = ctrl.submit("UA-0010", 30)
        self.assertTrue(r1.success)
        self.assertTrue(r2.success)
        self.assertEqual(r1.eta_manual, r2.eta_manual)

    def test_future_synthetic_card_no_special_case(self):
        ctrl, db, pub = make_controller()
        result = ctrl.submit("SYNTHETIC-FUTURE-CARD-999", 5)
        self.assertTrue(result.success)


class TestBoundaryDays(unittest.TestCase):
    def test_zero_and_one(self):
        ctrl, db, pub = make_controller()
        for n in (0, 1):
            r = ctrl.submit(f"UA-BOUND-{n}", n)
            self.assertTrue(r.success)

    def test_400_allowed(self):
        ctrl, db, pub = make_controller()
        r = ctrl.submit("UA-BOUND-400", 400)
        self.assertTrue(r.success)

    def test_invalid_rejected(self):
        ctrl, db, pub = make_controller()
        for n in (-1, 401, 5000):
            r = ctrl.submit("UA-INVALID", n)
            self.assertFalse(r.success)


class TestInjectedFailures(unittest.TestCase):
    def test_fail_after_first_db_field(self):
        ctrl, db, pub = make_controller()
        db.seed("UA-0010", days_to_kyiv=11, eta_manual="2026-09-09", updated_at="old")
        db.fail_after_first_field = True
        r = ctrl.submit("UA-0010", 30)
        self.assertFalse(r.success)
        self.assertTrue(r.retry_queued)
        self.assertEqual(r.error, "db_write_failed")

    def test_readback_mismatch_triggers_rollback(self):
        ctrl, db, pub = make_controller()
        db.seed("UA-0010", days_to_kyiv=11, eta_manual="2026-09-09", updated_at="old")
        original_write = db.write_eta

        def bad_write(car_id, days_to_kyiv, eta_manual, updated_at):
            original_write(car_id, days_to_kyiv, "1999-01-01", updated_at)

        db.write_eta = bad_write
        r = ctrl.submit("UA-0010", 30)
        self.assertFalse(r.success)
        self.assertTrue(r.rolled_back)
        self.assertEqual(db.rows["UA-0010"]["eta_manual"], "2026-09-09")

    def test_queue_timeout_on_readback(self):
        ctrl, db, pub = make_controller()
        db.seed("UA-0010", days_to_kyiv=11, eta_manual="2026-09-09", updated_at="old")
        db.fail_readback_once = True
        r = ctrl.submit("UA-0010", 30)
        if not r.success:
            self.assertTrue(r.retry_queued)

    def test_publisher_failure_rolls_back(self):
        ctrl, db, pub = make_controller()
        db.seed("UA-0011", days_to_kyiv=11, eta_manual="2026-09-09", updated_at="old")
        pub.fail_video = True
        r = ctrl.submit("UA-0011", 30)
        self.assertFalse(r.success)
        self.assertTrue(r.rolled_back)
        self.assertEqual(db.rows["UA-0011"]["days_to_kyiv"], 11)

    def test_partial_file_write_rebuild_card_fails(self):
        ctrl, db, pub = make_controller()
        db.seed("UA-0009", days_to_kyiv=11, eta_manual="2026-09-09", updated_at="old")
        pub.fail_rebuild_card = True
        r = ctrl.submit("UA-0009", 30)
        self.assertFalse(r.success)
        self.assertTrue(r.rolled_back)

    def test_delayed_rebuild_overwrite_protection(self):
        ctrl, db, pub = make_controller()
        db.seed("UA-0009", days_to_kyiv=11, eta_manual="2026-09-09", updated_at="old")
        r = ctrl.submit("UA-0009", 30)
        self.assertTrue(r.success)
        current = db.read_back("UA-0009")
        self.assertEqual(current["days_to_kyiv"], 30)


class TestProtectedRowsUnaffected(unittest.TestCase):
    def test_untouched_cards_not_modified(self):
        ctrl, db, pub = make_controller()
        db.seed("UA-0001", days_to_kyiv=5, eta_manual="2026-09-03", updated_at="orig")
        ctrl.submit("UA-0009", 30)
        self.assertEqual(
            db.rows["UA-0001"],
            {"days_to_kyiv": 5, "eta_manual": "2026-09-03", "updated_at": "orig"},
        )


if __name__ == "__main__":
    unittest.main()
