from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


remote = load("task105_remote_test", "production_canary_remote.py")
controller = load("task105_controller_test", "production_canary_controller.py")


class RemoteCanaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        (root / "video").mkdir(parents=True)
        (root / "autopilot_inbox/cloud/task_105_fast_pipeline_phase3").mkdir(parents=True)
        (root / "backups").mkdir(parents=True)
        (root / "crm.db").write_bytes(b"crm-stable")
        (root / "video/index.html").write_bytes(b"<html>home stable</html>")
        (root / "video/katalog.html").write_bytes(b"<html>catalog stable</html>")

        remote.ROOT = root
        remote.REMOTE = root / "autopilot_inbox/cloud/task_105_fast_pipeline_phase3"
        remote.PAYLOAD = remote.REMOTE / "task105_fast_canary_payload.txt"
        remote.TARGET = root / "video/task105-fast-canary.txt"
        remote.LOCK = root / ".ua_art_production_writer.lock"
        remote.BACKUPS = root / "backups/task_105_fast_canary"
        remote.LAST_SUCCESS = remote.REMOTE / "task105_fast_canary_last_success.json"
        remote.RECEIPTS = {
            "install": remote.REMOTE / "task105_fast_canary_install_receipt.json",
            "rollback": remote.REMOTE / "task105_fast_canary_rollback_receipt.json",
        }
        remote.PROTECTED = (
            root / "crm.db",
            root / "video/index.html",
            root / "video/katalog.html",
        )
        self.payload = controller.build_payload("12345", "a" * 40)
        remote.PAYLOAD.write_bytes(self.payload)

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_new_marker_and_rollback_to_absence(self):
        result = remote.run_install()
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["before"]["existed"])
        self.assertEqual(remote.TARGET.read_bytes(), self.payload)
        self.assertEqual(result["protected_before"], result["protected_after"])
        rollback = remote.run_rollback()
        self.assertEqual(rollback["status"], "PASS")
        self.assertFalse(remote.TARGET.exists())

    def test_existing_preimage_is_restored(self):
        original = b"older harmless marker\n"
        remote.TARGET.write_bytes(original)
        result = remote.run_install()
        self.assertTrue(result["before"]["existed"])
        self.assertNotEqual(remote.TARGET.read_bytes(), original)
        remote.run_rollback()
        self.assertEqual(remote.TARGET.read_bytes(), original)

    def test_backup_manifest_is_durable_and_scoped(self):
        result = remote.run_install()
        backup_root = pathlib.Path(result["backup_root"])
        self.assertTrue((backup_root / "manifest.json").is_file())
        self.assertTrue(backup_root.resolve().is_relative_to(remote.BACKUPS.resolve()))

    def test_symlink_target_is_rejected(self):
        destination = remote.ROOT / "video/other.txt"
        destination.write_text("x", encoding="utf-8")
        remote.TARGET.symlink_to(destination)
        with self.assertRaises(remote.CanaryError):
            remote.run_install()

    def test_invalid_payload_is_rejected_without_target_write(self):
        remote.PAYLOAD.write_text("bad\n", encoding="utf-8")
        with self.assertRaises(remote.CanaryError):
            remote.run_install()
        self.assertFalse(remote.TARGET.exists())

    def test_protected_drift_triggers_local_target_rollback(self):
        original_atomic = remote.atomic_write

        def injecting_atomic(path, value, mode=0o644):
            original_atomic(path, value, mode)
            if path == remote.TARGET:
                remote.PROTECTED[0].write_bytes(b"external-drift")

        with mock.patch.object(remote, "atomic_write", side_effect=injecting_atomic):
            with self.assertRaises(remote.CanaryError):
                remote.run_install()
        self.assertFalse(remote.TARGET.exists())


class ControllerContractTests(unittest.TestCase):
    def test_payload_contract_is_exact_and_unique(self):
        first = controller.build_payload("11", "a" * 40)
        second = controller.build_payload("12", "a" * 40)
        self.assertEqual(len(first.decode().splitlines()), 7)
        self.assertNotEqual(first, second)
        self.assertIn(controller.CONTRACT_ID.encode(), first)

    def test_validate_install_accepts_only_bounded_scope(self):
        payload = controller.build_payload("11", "a" * 40)
        sample = {
            "contract_id": controller.CONTRACT_ID,
            "status": "PASS",
            "mode": "INSTALL",
            "production_write": True,
            "crm_write": False,
            "existing_site_file_write": False,
            "cloudflare_write": False,
            "dns_write": False,
            "before": {"existed": False},
            "changed_files": ["/home/Carix/video/task105-fast-canary.txt"],
            "expected_sha256": controller.sha(payload),
            "backup_root": "/home/Carix/backups/task_105_fast_canary/x",
            "backup_manifest": "/home/Carix/backups/task_105_fast_canary/x/manifest.json",
            "rollback_ready": True,
            "protected_before": {"a": 1},
            "protected_after": {"a": 1},
            "unexpected_changes": 0,
        }
        controller.validate_install(sample, payload)

    def test_validate_install_rejects_crm_write(self):
        payload = controller.build_payload("11", "a" * 40)
        sample = {
            "contract_id": controller.CONTRACT_ID,
            "status": "PASS",
            "mode": "INSTALL",
            "production_write": True,
            "crm_write": True,
            "existing_site_file_write": False,
            "cloudflare_write": False,
            "dns_write": False,
            "before": {"existed": False},
            "changed_files": ["/home/Carix/video/task105-fast-canary.txt"],
            "expected_sha256": controller.sha(payload),
            "backup_root": "x",
            "backup_manifest": "x",
            "rollback_ready": True,
            "protected_before": {},
            "protected_after": {},
            "unexpected_changes": 0,
        }
        with self.assertRaises(controller.ControllerError):
            controller.validate_install(sample, payload)

    def test_validate_rollback_rejects_protected_drift(self):
        sample = {
            "contract_id": controller.CONTRACT_ID,
            "status": "PASS",
            "mode": "ROLLBACK",
            "production_write": True,
            "crm_write": False,
            "protected_before": {"a": 1},
            "protected_after": {"a": 2},
            "unexpected_changes": 0,
        }
        with self.assertRaises(controller.ControllerError):
            controller.validate_rollback(sample)


if __name__ == "__main__":
    unittest.main()
