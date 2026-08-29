"""Stdlib-only Gate A tests for CRM-CONTAINER-STAGE-SYNC-004 v1.0."""

from __future__ import annotations

import hashlib
import os
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve()
PATCHER = HERE.parents[1] / "patcher"
TASK076 = HERE.parents[2] / "task_076_eta_sync"
sys.path.insert(0, str(PATCHER))
sys.path.insert(0, str(TASK076))

import eta_release_candidate as erc  # noqa: E402
import live_patcher as lp  # noqa: E402

FIXED_NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)


class EtaReleaseCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="task077-gate-a-")
        root = pathlib.Path(self.temp.name)
        self.db_path = str(root / "crm.db")
        self.stage = str(root / "staging")
        self.video = str(root / "live-video")
        self.site = str(root / "live-site")
        setup = sqlite3.connect(self.db_path)
        erc.init_sandbox_db(setup)
        setup.close()
        self.write = self._conn()
        self.read = self._conn()

    def tearDown(self):
        self.read.close()
        self.write.close()
        self.temp.cleanup()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.isolation_level = None
        return conn

    def _insert(self, car_id=1, code="UA-TEST", status="sea_loaded",
                days=None, eta=None, published=0, description="desc",
                price_uah=1000, vin="VIN", condition_text=""):
        self.write.execute(
            "INSERT INTO cars (id,auto_number,vin,status,days_to_kyiv,"
            "eta_manual,published,condition_text,description,price_uah,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (car_id, code, vin, status, days, eta, published, condition_text, description,
             price_uah, "2026-01-01T00:00:00+00:00"),
        )

    def _apply(self, car_id=1, days=30, **kwargs):
        return erc.apply_eta_change(
            self.write, self.read, self.stage, self.video, self.site,
            car_id, days, "tester", now_utc=FIXED_NOW, **kwargs)

    def _targets(self, code="UA-TEST"):
        return [
            os.path.join(self.video, code + ".html"),
            os.path.join(self.site, code + ".html"),
            os.path.join(self.video, code + "-diag.html"),
            os.path.join(self.site, code + "-diag.html"),
            os.path.join(self.video, "katalog.html"),
            os.path.join(self.site, "katalog.html"),
        ]

    def test_n_boundaries_and_exact_utc_date(self):
        for index, n in enumerate((0, 1, 30, 400), 1):
            self._insert(index, "UA-%04d" % index)
            result = erc.write_eta_transaction(
                self.write, index, n, "tester", now_utc=FIXED_NOW)
            self.assertEqual(result.n_days, n)
            expected = erc.compute_eta(n, FIXED_NOW.date())
            self.assertEqual(result.eta, expected)
        self.assertEqual(erc.compute_eta(30, FIXED_NOW.date()), "2026-09-28")

    def test_invalid_days_fail_closed(self):
        self._insert()
        for invalid in (-1, 401, 3.5, "30", True, None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(erc.ValidationError):
                    erc.write_eta_transaction(
                        self.write, 1, invalid, "tester", now_utc=FIXED_NOW)

    def test_integer_id_required(self):
        self._insert()
        for invalid in ("1", 1.0, True, 0, -1):
            with self.subTest(invalid=invalid):
                with self.assertRaises(erc.ValidationError):
                    erc.write_eta_transaction(
                        self.write, invalid, 30, "tester", now_utc=FIXED_NOW)

    def test_idempotence_and_audit_count(self):
        self._insert()
        first = erc.write_eta_transaction(
            self.write, 1, 30, "tester", now_utc=FIXED_NOW)
        second = erc.write_eta_transaction(
            self.write, 1, 30, "tester", now_utc=FIXED_NOW)
        self.assertEqual(first.eta, second.eta)
        self.assertEqual(len(first.audit_ids), 2)
        self.assertEqual(second.audit_ids, ())
        self.assertEqual(self.write.execute(
            "SELECT COUNT(*) FROM audit").fetchone()[0], 2)

    def test_only_evidenced_ferry_statuses_normalize(self):
        for index, status in enumerate(
                ("kr_bought", "sea_transit", "sea_loaded"), 1):
            self._insert(index, "UA-%04d" % index, status=status)
            result = erc.write_eta_transaction(
                self.write, index, 30, "tester", True, FIXED_NOW)
            self.assertEqual(result.status_after, "sea_loaded")
        self.assertEqual(
            erc.ALLOWED_FERRY_NORMALIZATION_SOURCES,
            {"kr_bought", "sea_transit", "sea_loaded"})

    def test_real_protected_and_terminal_statuses_stay_unchanged(self):
        statuses = (
            "ge_waiting", "ge_to_kyiv", "ua_arrived",
            "sold_transit", "sold_done", "archive", "archive_old",
        )
        for index, status in enumerate(statuses, 1):
            self._insert(index, "UA-%04d" % index, status=status)
            result = erc.write_eta_transaction(
                self.write, index, 30, "tester", True, FIXED_NOW)
            self.assertEqual(result.status_after, status)

    def test_concurrent_preimage_change_is_rejected(self):
        self._insert()
        preimage = erc.read_car_row(self.write, 1)
        self.write.execute("UPDATE cars SET description='changed' WHERE id=1")
        with self.assertRaises(erc.ValidationError):
            erc.write_eta_transaction(
                self.write, 1, 30, "tester", False, FIXED_NOW, preimage)

    def test_commit_precedes_publisher(self):
        self._insert()
        seen = {}

        def publisher(files):
            row = erc.read_car_row(self.read, 1)
            seen["pair"] = (row.days_to_kyiv, row.eta_manual)
            return erc.default_publisher(files)

        result = self._apply(publisher=publisher)
        self.assertTrue(result.success, result.message)
        self.assertEqual(seen["pair"], (30, "2026-09-28"))

    def test_published_preimage_preserved_on_success(self):
        for published in (0, 1):
            with self.subTest(published=published):
                car_id = published + 1
                self._insert(car_id, "UA-%04d" % car_id,
                             published=published)
                result = self._apply(car_id)
                self.assertTrue(result.success, result.message)
                self.assertEqual(
                    erc.read_car_row(self.write, car_id).published, published)

    def test_exact_six_live_targets_and_distinct_staging(self):
        self._insert()
        result = self._apply()
        self.assertTrue(result.success, result.message)
        targets = self._targets()
        self.assertEqual(len(targets), 6)
        self.assertEqual(len(set(targets)), 6)
        for target in targets:
            self.assertTrue(os.path.isfile(target), target)
            self.assertFalse(os.path.abspath(target).startswith(
                os.path.abspath(self.stage) + os.sep))
        staged = [p for p in pathlib.Path(self.stage).iterdir() if p.is_file()]
        self.assertEqual(len(staged), 6)

    def test_publisher_failure_restores_db_files_and_audits(self):
        self._insert(days=5, eta="2026-01-06", published=1)
        for index, target in enumerate(self._targets()):
            os.makedirs(os.path.dirname(target), exist_ok=True)
            pathlib.Path(target).write_bytes(("ORIGINAL-%d" % index).encode())
        before = {p: pathlib.Path(p).read_bytes() for p in self._targets()}

        def fail_with_unrelated_audit(files):
            other = self._conn()
            other.execute(
                "INSERT INTO audit(actor_id,action,entity_type,entity_id,field,"
                "old_value,new_value,created_at) VALUES(?,?,?,?,?,?,?,?)",
                ("other", "other", "cars", 999, "x", None, "y", "now"))
            other.close()
            return False

        result = self._apply(publisher=fail_with_unrelated_audit)
        self.assertFalse(result.success)
        self.assertTrue(result.rolled_back)
        row = erc.read_car_row(self.write, 1)
        self.assertEqual((row.days_to_kyiv, row.eta_manual, row.published),
                         (5, "2026-01-06", 1))
        self.assertEqual(
            self.write.execute(
                "SELECT actor_id,entity_id FROM audit").fetchall(),
            [("other", 999)])
        self.assertEqual(
            {p: pathlib.Path(p).read_bytes() for p in self._targets()}, before)

    def test_readback_failure_rolls_back(self):
        self._insert(days=5, eta="2026-01-06")
        result = self._apply(inject_readback_failure=True)
        self.assertFalse(result.success)
        self.assertTrue(result.rolled_back)
        self.assertEqual(erc.read_car_row(self.write, 1).days_to_kyiv, 5)
        self.assertEqual(
            self.write.execute("SELECT COUNT(*) FROM audit").fetchone()[0], 0)

    def test_partial_install_rolls_back(self):
        self._insert(days=5, eta="2026-01-06")
        result = self._apply(inject_install_partial_failure=True)
        self.assertFalse(result.success)
        self.assertTrue(result.rolled_back)
        self.assertTrue(all(not os.path.exists(p) for p in self._targets()))

    def test_delayed_overwrite_is_detected_and_rolled_back(self):
        self._insert(days=5, eta="2026-01-06")
        card = self._targets()[0]

        def overwrite():
            pathlib.Path(card).write_bytes(b"CORRUPTED")

        result = self._apply(inject_delayed_overwrite=overwrite)
        self.assertFalse(result.success)
        self.assertTrue(result.rolled_back)
        self.assertFalse(os.path.exists(card))

    def test_target_cards_9_10_11_exact(self):
        self._insert(
            9, "UA-0009", days=13, eta="2026-09-28",
            condition_text=(
                "Перша частина. Орієнтовне прибуття — 9 вересня 2026 року. "
                "Сервіс був 15 січня 2026."))
        self._insert(10, "UA-0010", days=None, eta="2026-09-28")
        self._insert(11, "UA-0011", days=None, eta="2026-09-28")
        for car_id in (9, 10, 11):
            result = self._apply(car_id)
            self.assertTrue(result.success, result.message)
            row = erc.read_car_row(self.write, car_id)
            self.assertEqual(
                (row.days_to_kyiv, row.eta_manual, row.status),
                (30, "2026-09-28", "sea_loaded"))
        ua9 = erc.read_car_row(self.write, 9)
        self.assertNotIn("9 вересня 2026", ua9.condition_text)
        self.assertIn("15 січня 2026", ua9.condition_text)

    def test_ua0012_legacy_status_and_diag_placeholder(self):
        self._insert(12, "UA-0012", status="sea_transit")
        result = self._apply(
            12, allow_ferry_normalization=True, include_diagnostic=False)
        self.assertTrue(result.success, result.message)
        row = erc.read_car_row(self.write, 12)
        self.assertEqual(
            (row.status, row.days_to_kyiv, row.eta_manual),
            ("sea_loaded", 30, "2026-09-28"))
        for target in self._targets("UA-0012")[2:4]:
            self.assertIn(
                "Материалы диагностики ожидаются",
                pathlib.Path(target).read_text(encoding="utf-8"))

    def test_unrelated_db_fields_unchanged(self):
        self._insert(description="KEEP  EXACT\nTEXT", price_uah=11400,
                     vin="VIN-KEEP")
        result = self._apply()
        self.assertTrue(result.success, result.message)
        row = erc.read_car_row(self.write, 1)
        self.assertEqual(
            (row.description, row.price_uah, row.vin),
            ("KEEP  EXACT\nTEXT", 11400, "VIN-KEEP"))

    def test_toggle_publish_failure_restores_preimage_without_success(self):
        self._insert(published=0)
        result = erc.toggle_publish(
            self.write, 1, 1, "tester", lambda files: False, [])
        self.assertFalse(result.success)
        self.assertNotIn("Машина видна", result.message)
        self.assertEqual(erc.read_car_row(self.write, 1).published, 0)

    def test_toggle_publish_success_text_only_after_pass(self):
        self._insert(published=0)
        result = erc.toggle_publish(
            self.write, 1, 1, "tester", lambda files: True, [])
        self.assertTrue(result.success)
        self.assertIn("Машина видна", result.message)

    def test_stale_sentence_removal_preserves_exact_other_bytes(self):
        prefix = "Префикс  с  двумя пробелами. "
        stale = "Орієнтовне прибуття — 9 вересня 2026 року."
        suffix = "\n• Сервіс був 15 січня 2026.  Хвіст."
        result = erc.sanitize_stale_arrival_sentence(prefix + stale + suffix)
        self.assertEqual(result, prefix + suffix)

    def test_unrelated_dates_are_byte_identical(self):
        text = (
            "Авто куплено 3 січня 2026.\n"
            "  Реєстрацію планують 12 грудня 2026. "
            "Сервіс: 15.01.2026; аукціон 01.02.2026.")
        self.assertEqual(erc.sanitize_stale_arrival_sentence(text), text)

    def test_numeric_arrival_date_is_narrowly_removed(self):
        text = "До. Доставка запланована 09.09.2026. Після."
        self.assertEqual(
            erc.sanitize_stale_arrival_sentence(text), "До. Після.")

    def test_full_file_anchor_refuses_mismatch(self):
        path = pathlib.Path(self.temp.name) / "db.py"
        path.write_text("# wrong", encoding="utf-8")
        with self.assertRaises(erc.AnchorMismatchError):
            erc.verify_full_file_anchor(str(path), "db.py")

    def test_function_hash_selects_one_definition_among_duplicates(self):
        path = pathlib.Path(self.temp.name) / "many.py"
        source = "def f():\n    return 1\n\ndef f():\n    return 2\n"
        path.write_text(source, encoding="utf-8")
        matches = lp._find_function_definitions(source, "f")
        selected = lp.verify_function_anchor(
            str(path), "f", matches[1].source_sha256)
        self.assertIn("return 2", selected.source)

    def test_zero_and_two_exact_function_matches_refuse(self):
        path = pathlib.Path(self.temp.name) / "many.py"
        one = "def f():\n    return 1\n"
        source = one + "\n" + one
        path.write_text(source, encoding="utf-8")
        digest = hashlib.sha256(one.encode()).hexdigest()
        with self.assertRaises(lp.PatchAbortedError):
            lp.verify_function_anchor(str(path), "f", digest)
        with self.assertRaises(lp.PatchAbortedError):
            lp.verify_function_anchor(str(path), "f", "0" * 64)

    def test_patch_specs_cover_all_live_anchors_with_concrete_transforms(self):
        expected = {
            ("db.py", "update_card_field"),
            ("cars_ui.py", "apply_value"),
            ("cars_ui.py", "stage_menu"),
            ("cars_ui.py", "toggle_publish"),
            ("konteyner.py", "prinyat"),
            ("konteyner.py", "_peresobrat"),
            ("stranica.py", "sobrat_kartochku"),
            ("publikaciya.py", "opublikovat"),
        }
        self.assertEqual(
            {(s.anchor_key, s.function_name) for s in lp.PATCH_SPECS}, expected)
        self.assertEqual(len({s.function_sha256 for s in lp.PATCH_SPECS}), 8)
        self.assertTrue(all(s.transform for s in lp.PATCH_SPECS))

    def test_gate_b_writer_has_three_independent_gates(self):
        with self.assertRaises(lp.PatchAbortedError):
            lp.apply_patch_bundle(
                self.temp.name, self.temp.name + "-backup", "wrong", True)
        with self.assertRaises(lp.PatchAbortedError):
            lp.apply_patch_bundle(
                self.temp.name, self.temp.name + "-backup",
                lp.OWNER_TOKEN, False)

    def test_validation_failure_returns_one_failure_message(self):
        result = self._apply(days=401)
        self.assertFalse(result.success)
        self.assertTrue(result.message.startswith("FAIL:"))
        self.assertNotIn("OK:", result.message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
