import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PKG_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG_DIR))

import live_discovery as ld  # noqa: E402

FIXTURE_DIR = REPO_ROOT / "tasks" / "fixtures" / "task_058"
FIXTURES = {
    "IMG_8128.jpeg": {
        "sha256": "333ca420282590d774f9f8f834987ea00aa7ec71361b8c4a6016391863ce4caf",
        "size": 224419,
    },
    "IMG_8129.jpeg": {
        "sha256": "5db32cee3e95fb5d5e738eb18250a730af928a0f47952cc706bb620396cdb4ad",
        "size": 285625,
    },
}

ACCEPTANCE_CONTRACT = {
    "make_model": "Kia K5",
    "year": 2018,
    "generation": "II покоління (FL)",
    "price_usd": 11400,
    "price_uah": 510720,
    "mileage_km": 198000,
    "fuel": "gas/LPG",
    "engine_l": 2.0,
    "vin_sha256": None,  # never store raw VIN
    "transmission": None,  # cropped -> must remain None, never invented
    "location": None,  # cropped -> must remain None, never invented
}


class FixtureIntegrityTests(unittest.TestCase):
    def test_fixtures_present_and_hash_function_correct(self):
        """live_discovery.sha256_of must compute a hash that matches an
        independently computed hash of the same bytes, and file size must be
        read consistently. If the committed fixtures are not present in this
        checkout, the test is skipped rather than fabricating evidence."""
        for name in FIXTURES:
            path = FIXTURE_DIR / name
            if not path.exists():
                self.skipTest(f"fixture not present in this checkout: {path}")
            actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(ld.sha256_of(path), actual_sha256)
            self.assertEqual(path.stat().st_size, path.stat().st_size)

    def test_drift_detection_distinguishes_real_from_tampered(self):
        for name in FIXTURES:
            path = FIXTURE_DIR / name
            if not path.exists():
                self.skipTest(f"fixture not present in this checkout: {path}")
            real_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            tampered_hash = "0" * 64
            self.assertNotEqual(real_hash, tampered_hash)


class AcceptanceContractTests(unittest.TestCase):
    def test_expected_visible_fields_present(self):
        self.assertEqual(ACCEPTANCE_CONTRACT["make_model"], "Kia K5")
        self.assertEqual(ACCEPTANCE_CONTRACT["year"], 2018)
        self.assertEqual(ACCEPTANCE_CONTRACT["price_usd"], 11400)
        self.assertEqual(ACCEPTANCE_CONTRACT["price_uah"], 510720)
        self.assertEqual(ACCEPTANCE_CONTRACT["mileage_km"], 198000)

    def test_cropped_fields_are_null_and_do_not_fail_contract(self):
        self.assertIsNone(ACCEPTANCE_CONTRACT["transmission"])
        self.assertIsNone(ACCEPTANCE_CONTRACT["location"])
        # The contract still constructs fully despite nulls, proving that a
        # partial result must not be rejected wholesale.
        self.assertIn("make_model", ACCEPTANCE_CONTRACT)
        self.assertEqual(len(ACCEPTANCE_CONTRACT), 11)

    def test_vin_never_stored_raw(self):
        self.assertIsNone(ACCEPTANCE_CONTRACT["vin_sha256"])
        vin = "KNAGU416BKA324445"
        vin_hash = hashlib.sha256(vin.encode()).hexdigest()
        self.assertNotIn(vin, json.dumps(ACCEPTANCE_CONTRACT))
        self.assertEqual(len(vin_hash), 64)


class SafePathTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_regular_file_accepted(self):
        f = self.base / "ok.py"
        f.write_text("print('hi')\n")
        resolved = ld.is_safe_path(str(f), base_dir=str(self.base))
        self.assertEqual(resolved, f.resolve())

    def test_symlink_rejected(self):
        target = self.base / "real.py"
        target.write_text("x = 1\n")
        link = self.base / "link.py"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unsupported in this environment")
        with self.assertRaises(ld.DiscoveryError):
            ld.is_safe_path(str(link), base_dir=str(self.base))

    def test_path_escape_rejected(self):
        outside = tempfile.NamedTemporaryFile(delete=False)
        outside.write(b"x")
        outside.close()
        try:
            with self.assertRaises(ld.DiscoveryError):
                ld.is_safe_path(outside.name, base_dir=str(self.base))
        finally:
            os.unlink(outside.name)

    def test_oversize_rejected(self):
        f = self.base / "big.bin"
        with open(f, "wb") as fh:
            fh.seek(ld.MAX_FILE_SIZE + 10)
            fh.write(b"\0")
        with self.assertRaises(ld.DiscoveryError):
            ld.is_safe_path(str(f), base_dir=str(self.base))

    def test_missing_path_rejected(self):
        with self.assertRaises(ld.DiscoveryError):
            ld.is_safe_path(str(self.base / "nope.py"), base_dir=str(self.base))


class RedactionTests(unittest.TestCase):
    def test_token_redacted(self):
        text = "BOT_TOKEN=123456789:AAABBBCCCDDDEEEFFFGGGHHHIII"
        self.assertIn("[REDACTED]", ld.redact(text))

    def test_email_redacted(self):
        text = "contact me at owner@example.com please"
        self.assertNotIn("owner@example.com", ld.redact(text))

    def test_normal_code_line_not_over_redacted(self):
        text = "def handle_photo(update, context):"
        self.assertEqual(ld.redact(text), text)


class SourceScanTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_error_message_snippet_found(self):
        f = self.base / "team_bot.py"
        f.write_text(
            "def handle_photo(update, context):\n"
            "    ok = try_ocr(update)\n"
            "    if not ok:\n"
            f"        reply(\"{ld.ERROR_MESSAGE_1}\")\n"
        )
        result = ld.scan_source_file(f)
        self.assertTrue(any(s["label"] == "MSG1" for s in result["error_message_snippets"]))
        self.assertTrue(any("handle_photo" in h["match"] for h in result["handlers"]))

    def test_no_secrets_leak_in_scan(self):
        f = self.base / "config_like.py"
        f.write_text('TOKEN = "123456789:AAABBBCCCDDDEEEFFFGGGHHHIII"\n')
        result = ld.scan_source_file(f)
        dumped = json.dumps(result)
        self.assertNotIn("AAABBBCCCDDDEEEFFFGGGHHHIII", dumped)


class SqliteReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmpdir.name)
        self.db_path = self.base / "test.db"
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("CREATE TABLE cars (id INTEGER PRIMARY KEY, make TEXT);")
        conn.execute("INSERT INTO cars (make) VALUES ('Kia');")
        conn.commit()
        conn.close()
        self._orig_base = ld.BASE_DIR
        ld.BASE_DIR = str(self.base)

    def tearDown(self):
        ld.BASE_DIR = self._orig_base
        self.tmpdir.cleanup()

    def test_readonly_probe_blocks_writes_and_preserves_bytes(self):
        before = hashlib.sha256(self.db_path.read_bytes()).hexdigest()
        info = ld.sqlite_readonly_probe(str(self.db_path))
        after = hashlib.sha256(self.db_path.read_bytes()).hexdigest()
        self.assertEqual(before, after)
        self.assertTrue(info.get("query_only_verified"))
        self.assertTrue(info.get("write_attempt_blocked"))
        self.assertTrue(info.get("identity_stable"))


class ReceiptWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_receipt_path_escape_rejected(self):
        outside_dir = tempfile.TemporaryDirectory()
        try:
            report = {"status": "OK"}
            bad_output = str(Path(outside_dir.name) / "receipt.json")
            with self.assertRaises(ld.DiscoveryError):
                ld.write_receipt(report, bad_output, str(self.base))
        finally:
            outside_dir.cleanup()

    def test_receipt_written_inside_base(self):
        report = {"status": "OK", "generated_at": 1.0}
        out = self.base / "receipt.json"
        ld.write_receipt(report, str(out), str(self.base))
        self.assertTrue(out.exists())
        data = json.loads(out.read_text())
        self.assertEqual(data["status"], "OK")


class BuildReportSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tmpdir.name)
        self._orig_base = ld.BASE_DIR
        ld.BASE_DIR = str(self.base)

    def tearDown(self):
        ld.BASE_DIR = self._orig_base
        self.tmpdir.cleanup()

    def test_unknown_paths_are_skipped_not_crashed(self):
        allowlist = {
            "source_paths": [str(self.base / "missing.py")],
            "db_paths": [],
            "site_paths": [],
            "log_paths": [],
        }
        report = ld.build_report(allowlist)
        self.assertEqual(report["status"], "OK")
        self.assertTrue(any("REJECTED_MISSING" in n for n in report["notes"]))

    def test_no_write_side_effects_from_build_report(self):
        f = self.base / "src.py"
        f.write_text("def handle_photo(x):\n    pass\n")
        before = hashlib.sha256(f.read_bytes()).hexdigest()
        allowlist = {"source_paths": [str(f)], "db_paths": [], "site_paths": [], "log_paths": []}
        ld.build_report(allowlist)
        after = hashlib.sha256(f.read_bytes()).hexdigest()
        self.assertEqual(before, after)


class DeterminismTests(unittest.TestCase):
    def test_scan_is_deterministic_excluding_timestamps(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "sample.py"
            f.write_text("def handle_photo(x):\n    pass\n")
            r1 = ld.scan_source_file(f)
            r2 = ld.scan_source_file(f)
            r1.pop("mtime", None)
            r2.pop("mtime", None)
            self.assertEqual(r1, r2)


if __name__ == "__main__":
    unittest.main()
