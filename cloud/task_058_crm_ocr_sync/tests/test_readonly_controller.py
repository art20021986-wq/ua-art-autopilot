import hashlib
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG_DIR))

import task058_readonly_controller as ctrl  # noqa: E402


def make_manifest(tmpdir):
    entries = []
    for name, content in (("live_discovery.py", "print('x')\n"), ("allowlist.json", "{}\n")):
        p = Path(tmpdir) / name
        p.write_text(content)
        entries.append({
            "local_path": str(p),
            "expected_sha256": hashlib.sha256(content.encode()).hexdigest(),
        })
    return entries


class ManifestValidationTests(unittest.TestCase):
    def test_valid_manifest_passes(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = make_manifest(d)
            cfg = ctrl.ControllerConfig(
                manifest=manifest,
                allowlist_file_remote=f"{ctrl.SAFE_INBOX_DIR}/allowlist.json",
                receipt_local_path=str(Path(d) / "out.json"),
            )
            c = ctrl.ReadOnlyController(cfg, lambda m: None, lambda cmd: None, lambda: None, lambda: None)
            c.validate_manifest()  # should not raise

    def test_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = make_manifest(d)
            manifest[0]["expected_sha256"] = "0" * 64
            cfg = ctrl.ControllerConfig(manifest=manifest, allowlist_file_remote="x", receipt_local_path=str(Path(d) / "o.json"))
            c = ctrl.ReadOnlyController(cfg, lambda m: None, lambda cmd: None, lambda: None, lambda: None)
            with self.assertRaises(ctrl.ControllerError):
                c.validate_manifest()

    def test_missing_file_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = [{"local_path": str(Path(d) / "nope.py"), "expected_sha256": "0" * 64}]
            cfg = ctrl.ControllerConfig(manifest=manifest, allowlist_file_remote="x", receipt_local_path=str(Path(d) / "o.json"))
            c = ctrl.ReadOnlyController(cfg, lambda m: None, lambda cmd: None, lambda: None, lambda: None)
            with self.assertRaises(ctrl.ControllerError):
                c.validate_manifest()


class RemoteCommandSafetyTests(unittest.TestCase):
    def _controller(self, d):
        manifest = make_manifest(d)
        cfg = ctrl.ControllerConfig(
            manifest=manifest,
            allowlist_file_remote=f"{ctrl.SAFE_INBOX_DIR}/allowlist.json",
            receipt_local_path=str(Path(d) / "out.json"),
        )
        return ctrl.ReadOnlyController(cfg, lambda m: None, lambda cmd: None, lambda: None, lambda: None)

    def test_command_has_no_forbidden_tokens(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._controller(d)
            cmd = c.build_remote_command()
            for tok in ctrl.FORBIDDEN_COMMAND_TOKENS:
                self.assertNotIn(tok, cmd)
            self.assertIn("python3.10", cmd)
            self.assertIn(ctrl.SAFE_INBOX_DIR, cmd)


class ReceiptValidationTests(unittest.TestCase):
    def _controller(self, d):
        manifest = make_manifest(d)
        cfg = ctrl.ControllerConfig(manifest=manifest, allowlist_file_remote="x", receipt_local_path=str(Path(d) / "out.json"))
        return ctrl.ReadOnlyController(cfg, lambda m: None, lambda cmd: None, lambda: None, lambda: None)

    def test_valid_receipt_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._controller(d)
            raw = json.dumps({"generated_at": time.time(), "status": "OK"})
            data = c.validate_receipt(raw)
            self.assertEqual(data["status"], "OK")

    def test_sensitive_content_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._controller(d)
            raw = json.dumps({"generated_at": time.time(), "token": "abc123"})
            with self.assertRaises(ctrl.ControllerError):
                c.validate_receipt(raw)

    def test_malformed_json_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._controller(d)
            with self.assertRaises(ctrl.ControllerError):
                c.validate_receipt("{not json")

    def test_stale_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._controller(d)
            raw = json.dumps({"generated_at": time.time() - 10000, "status": "OK"})
            with self.assertRaises(ctrl.ControllerError):
                c.validate_receipt(raw)

    def test_missing_timestamp_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._controller(d)
            raw = json.dumps({"status": "OK"})
            with self.assertRaises(ctrl.ControllerError):
                c.validate_receipt(raw)

    def test_oversized_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            c = self._controller(d)
            raw = json.dumps({"generated_at": time.time(), "blob": "x" * (ctrl.MAX_RECEIPT_BYTES + 10)})
            with self.assertRaises(ctrl.ControllerError):
                c.validate_receipt(raw)


class RunFlowTests(unittest.TestCase):
    def test_success_flow_cleans_up_and_relays(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = make_manifest(d)
            cfg = ctrl.ControllerConfig(
                manifest=manifest,
                allowlist_file_remote=f"{ctrl.SAFE_INBOX_DIR}/allowlist.json",
                receipt_local_path=str(Path(d) / "out.json"),
                poll_timeout_seconds=5,
                poll_interval_seconds=0.01,
            )
            calls = {"sync": 0, "run": 0, "poll": 0, "cleanup": 0}
            good_receipt = json.dumps({"generated_at": time.time(), "status": "OK"})

            def poll_fn():
                calls["poll"] += 1
                return good_receipt

            def sync_fn(m):
                calls["sync"] += 1

            def run_fn(cmd):
                calls["run"] += 1

            def cleanup_fn():
                calls["cleanup"] += 1

            c = ctrl.ReadOnlyController(cfg, sync_fn, run_fn, poll_fn, cleanup_fn)
            result = c.run()
            self.assertEqual(result["status"], "READY_FOR_LIVE_READONLY_CONTROLLER_TASK_058")
            self.assertEqual(calls["cleanup"], 1)
            self.assertEqual(calls["sync"], 1)
            self.assertEqual(calls["run"], 1)
            self.assertTrue(Path(cfg.receipt_local_path).exists())
            for key in (
                "PRODUCTION_TOUCHED", "CRM_TOUCHED", "CRM_DB_WRITTEN", "SITE_REBUILT",
                "SERVICE_RELOADED", "OCR_FIX_INSTALLED", "GATE_B_EXECUTED", "UA_0009_PUBLISHED",
            ):
                self.assertEqual(result[key], "NO")

    def test_timeout_still_cleans_up(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = make_manifest(d)
            cfg = ctrl.ControllerConfig(
                manifest=manifest,
                allowlist_file_remote="x",
                receipt_local_path=str(Path(d) / "out.json"),
                poll_timeout_seconds=0.05,
                poll_interval_seconds=0.01,
            )
            calls = {"cleanup": 0}

            def cleanup_fn():
                calls["cleanup"] += 1

            c = ctrl.ReadOnlyController(cfg, lambda m: None, lambda cmd: None, lambda: None, cleanup_fn)
            result = c.run()
            self.assertTrue(result["status"].startswith("BLOCKED_WITH_EXACT_REASON_TASK_058"))
            self.assertEqual(calls["cleanup"], 1)

    def test_exception_in_run_fn_still_cleans_up(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = make_manifest(d)
            cfg = ctrl.ControllerConfig(manifest=manifest, allowlist_file_remote="x", receipt_local_path=str(Path(d) / "out.json"))
            calls = {"cleanup": 0}

            def cleanup_fn():
                calls["cleanup"] += 1

            def run_fn(cmd):
                raise RuntimeError("simulated remote failure")

            c = ctrl.ReadOnlyController(cfg, lambda m: None, run_fn, lambda: None, cleanup_fn)
            with self.assertRaises(RuntimeError):
                c.run()
            self.assertEqual(calls["cleanup"], 1)

    def test_manifest_failure_still_cleans_up(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = [{"local_path": str(Path(d) / "missing.py"), "expected_sha256": "0" * 64}]
            cfg = ctrl.ControllerConfig(manifest=manifest, allowlist_file_remote="x", receipt_local_path=str(Path(d) / "out.json"))
            calls = {"cleanup": 0}

            def cleanup_fn():
                calls["cleanup"] += 1

            c = ctrl.ReadOnlyController(cfg, lambda m: None, lambda cmd: None, lambda: None, cleanup_fn)
            result = c.run()
            self.assertTrue(result["status"].startswith("BLOCKED_WITH_EXACT_REASON_TASK_058"))
            self.assertEqual(calls["cleanup"], 1)


class DeterminismTests(unittest.TestCase):
    def test_repeated_manifest_validation_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = make_manifest(d)
            cfg = ctrl.ControllerConfig(manifest=manifest, allowlist_file_remote="x", receipt_local_path=str(Path(d) / "o.json"))
            c = ctrl.ReadOnlyController(cfg, lambda m: None, lambda cmd: None, lambda: None, lambda: None)
            c.validate_manifest()
            c.validate_manifest()  # deterministic, no state mutation


if __name__ == "__main__":
    unittest.main()
