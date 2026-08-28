import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

import task058_readonly_controller as ctl  # noqa: E402


def make_manifest(root: Path) -> ctl.SyncManifest:
    entries = []
    for rel in ["live_discovery.py", "task058_readonly_controller.py"]:
        full = root / rel
        sha = ctl.sha256_of_file(full)
        entries.append(ctl.ManifestEntry(relative_path=rel, expected_sha256=sha))
    return ctl.SyncManifest(entries=entries)


class TestManifestValidation(unittest.TestCase):
    def test_valid_manifest_passes(self):
        manifest = make_manifest(PACKAGE_ROOT)
        ctl.validate_manifest(PACKAGE_ROOT, manifest)  # should not raise

    def test_hash_mismatch_rejected(self):
        manifest = ctl.SyncManifest(
            entries=[ctl.ManifestEntry(relative_path="live_discovery.py", expected_sha256="0" * 64)]
        )
        with self.assertRaises(ctl.ManifestMismatchError):
            ctl.validate_manifest(PACKAGE_ROOT, manifest)

    def test_missing_file_rejected(self):
        manifest = ctl.SyncManifest(
            entries=[ctl.ManifestEntry(relative_path="does_not_exist.py", expected_sha256="0" * 64)]
        )
        with self.assertRaises(ctl.ManifestMismatchError):
            ctl.validate_manifest(PACKAGE_ROOT, manifest)

    def test_path_escape_rejected(self):
        manifest = ctl.SyncManifest(
            entries=[ctl.ManifestEntry(relative_path="../../etc/passwd", expected_sha256="0" * 64)]
        )
        with self.assertRaises(ctl.ManifestMismatchError):
            ctl.validate_manifest(PACKAGE_ROOT, manifest)

    def test_empty_manifest_rejected(self):
        with self.assertRaises(ctl.ManifestMismatchError):
            ctl.validate_manifest(PACKAGE_ROOT, ctl.SyncManifest(entries=[]))


class TestRemoteCommandBuild(unittest.TestCase):
    def test_exact_single_command_shape(self):
        cmd = ctl.build_remote_command(db_path="/home/Carix/crm.db", logs=["logs/app.log"])
        self.assertTrue(cmd.startswith("python3.10 "))
        self.assertIn("live_discovery.py", cmd)
        self.assertIn("--out", cmd)
        self.assertIn(ctl.SAFE_INBOX_ROOT, cmd)
        self.assertNotIn("sudo", cmd)
        self.assertNotIn("*", cmd)
        self.assertNotIn("find -exec", cmd)
        self.assertNotIn(">>", cmd)
        self.assertNotIn(";", cmd)


class TestReceiptValidation(unittest.TestCase):
    def test_valid_receipt_accepted(self):
        now = time.time()
        payload = json.dumps(
            {
                "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                "markers": {
                    "PRODUCTION_TOUCHED": "NO",
                    "CRM_TOUCHED": "NO",
                    "CRM_DB_WRITTEN": "NO",
                    "SITE_REBUILT": "NO",
                    "SERVICE_RELOADED": "NO",
                    "OCR_FIX_INSTALLED": "NO",
                    "GATE_B_EXECUTED": "NO",
                    "UA_0009_PUBLISHED": "NO",
                },
            }
        )
        data = ctl.validate_receipt(payload, now=now)
        self.assertEqual(data["markers"]["PRODUCTION_TOUCHED"], "NO")

    def test_malformed_json_rejected(self):
        with self.assertRaises(ctl.ReceiptValidationError):
            ctl.validate_receipt("{not valid json")

    def test_empty_receipt_rejected(self):
        with self.assertRaises(ctl.ReceiptValidationError):
            ctl.validate_receipt("")

    def test_sensitive_content_rejected(self):
        payload = json.dumps({"token": "abc123", "markers": {}})
        with self.assertRaises(ctl.ReceiptValidationError):
            ctl.validate_receipt(payload)

    def test_stale_receipt_rejected(self):
        old_time = time.time() - (ctl.MAX_RECEIPT_AGE_SECONDS + 3600)
        payload = json.dumps(
            {
                "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(old_time)),
                "markers": {},
            }
        )
        with self.assertRaises(ctl.ReceiptValidationError):
            ctl.validate_receipt(payload, now=time.time())

    def test_unsafe_marker_rejected(self):
        payload = json.dumps({"markers": {"PRODUCTION_TOUCHED": "YES"}})
        with self.assertRaises(ctl.ReceiptValidationError):
            ctl.validate_receipt(payload)


class TestRunReadonlyDiscoveryOrchestration(unittest.TestCase):
    def _good_receipt(self) -> str:
        return json.dumps(
            {
                "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "markers": {
                    "PRODUCTION_TOUCHED": "NO",
                    "CRM_TOUCHED": "NO",
                    "CRM_DB_WRITTEN": "NO",
                    "SITE_REBUILT": "NO",
                    "SERVICE_RELOADED": "NO",
                    "OCR_FIX_INSTALLED": "NO",
                    "GATE_B_EXECUTED": "NO",
                    "UA_0009_PUBLISHED": "NO",
                },
            }
        )

    def test_success_path_calls_cleanup(self):
        manifest = make_manifest(PACKAGE_ROOT)
        calls = {"executed": [], "cleaned": 0}

        def executor(cmd):
            calls["executed"].append(cmd)

        def receipt_reader():
            return self._good_receipt()

        def cleanup():
            calls["cleaned"] += 1

        result = ctl.run_readonly_discovery(
            PACKAGE_ROOT, manifest, executor, receipt_reader, cleanup,
            db_path="/home/Carix/crm.db",
        )
        self.assertEqual(result.status, "OK")
        self.assertEqual(len(calls["executed"]), 1)
        self.assertEqual(calls["cleaned"], 1)

    def test_manifest_failure_never_executes_and_still_no_cleanup_needed(self):
        bad_manifest = ctl.SyncManifest(
            entries=[ctl.ManifestEntry(relative_path="missing.py", expected_sha256="0" * 64)]
        )
        calls = {"executed": 0, "cleaned": 0}

        def executor(cmd):
            calls["executed"] += 1

        def receipt_reader():
            return None

        def cleanup():
            calls["cleaned"] += 1

        result = ctl.run_readonly_discovery(PACKAGE_ROOT, bad_manifest, executor, receipt_reader, cleanup)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("MANIFEST_VALIDATION_FAILED", result.error)
        self.assertEqual(calls["executed"], 0)

    def test_timeout_path_still_calls_cleanup(self):
        manifest = make_manifest(PACKAGE_ROOT)
        calls = {"cleaned": 0, "slept": 0}

        def executor(cmd):
            pass

        def receipt_reader():
            return None  # never arrives

        def cleanup():
            calls["cleaned"] += 1

        fake_clock = {"t": 0.0}

        def clock_fn():
            return fake_clock["t"]

        def sleep_fn(seconds):
            calls["slept"] += 1
            fake_clock["t"] += seconds

        result = ctl.run_readonly_discovery(
            PACKAGE_ROOT, manifest, executor, receipt_reader, cleanup,
            poll_interval_seconds=1, timeout_seconds=3,
            sleep_fn=sleep_fn, clock_fn=clock_fn,
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.error, "RECEIPT_TIMEOUT")
        self.assertEqual(calls["cleaned"], 1)

    def test_executor_exception_still_calls_cleanup(self):
        manifest = make_manifest(PACKAGE_ROOT)
        calls = {"cleaned": 0}

        def executor(cmd):
            raise RuntimeError("simulated ssh failure")

        def receipt_reader():
            return None

        def cleanup():
            calls["cleaned"] += 1

        result = ctl.run_readonly_discovery(PACKAGE_ROOT, manifest, executor, receipt_reader, cleanup)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("UNEXPECTED_ERROR", result.error)
        self.assertEqual(calls["cleaned"], 1)

    def test_malformed_receipt_still_calls_cleanup(self):
        manifest = make_manifest(PACKAGE_ROOT)
        calls = {"cleaned": 0}

        def executor(cmd):
            pass

        def receipt_reader():
            return "{not valid json"

        def cleanup():
            calls["cleaned"] += 1

        result = ctl.run_readonly_discovery(PACKAGE_ROOT, manifest, executor, receipt_reader, cleanup)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("RECEIPT_VALIDATION_FAILED", result.error)
        self.assertEqual(calls["cleaned"], 1)

    def test_no_production_markers_can_become_true(self):
        manifest = make_manifest(PACKAGE_ROOT)

        def executor(cmd):
            pass

        def receipt_reader():
            return json.dumps(
                {
                    "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "markers": {"SITE_REBUILT": "YES"},
                }
            )

        def cleanup():
            pass

        result = ctl.run_readonly_discovery(PACKAGE_ROOT, manifest, executor, receipt_reader, cleanup)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("UNSAFE_MARKER", result.error)


if __name__ == "__main__":
    unittest.main()
