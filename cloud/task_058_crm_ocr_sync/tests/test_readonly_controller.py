from __future__ import annotations

import datetime as dt
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest


PACKAGE_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

import task058_readonly_controller as ctrl  # noqa: E402


HEX = "a" * 64


def now_text() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def site_snapshot() -> dict:
    return {
        path: None
        if path in ctrl.OPTIONAL_SITE_PATHS
        else {"sha256": HEX, "size": 100, "mtime_ns": 1234567890123456789}
        for path in sorted(ctrl.ALLOWED_SITE_PATHS)
    }


def pass_receipt() -> dict:
    sources = [
        {
            "path": path,
            "sha256": HEX,
            "size": 100,
            "mtime_ns": 1234567890123456789,
            "syntax": "PASS",
            "anchors": [],
            "message_locations": [],
            "log_path_literals": [],
            "imports": [],
            "function_excerpts": [
                {
                    "name": name,
                    "line": index,
                    "end_line": index,
                    "calls": [],
                    "source": "def " + name + "(): pass",
                }
                for index, name in enumerate(
                    (
                        "detect_kind",
                        "intake",
                        "run_ai_draft",
                        "ai_save",
                    ),
                    1,
                )
            ]
            if path == "/home/Carix/team_bot.py"
            else [],
        }
        for path in sorted(ctrl.REQUIRED_SOURCE_PATHS)
    ]
    snapshot = site_snapshot()
    return {
        "task_id": "task_058",
        "mode": "READ_ONLY_LIVE_DISCOVERY",
        "status": "PASS",
        "generated_at_utc": now_text(),
        "started_at_utc": now_text(),
        "production_write": False,
        "crm_write": False,
        "db_write": False,
        "site_rebuilt": False,
        "service_reloaded": False,
        "ocr_fix_installed": False,
        "gate_b_executed": False,
        "ua0009_published": False,
        "ua0010_published": False,
        "sources": sources,
        "source_hashes_after": {item["path"]: item["sha256"] for item in sources},
        "source_identity_stable": True,
        "database": {
            "path": "/home/Carix/crm.db",
            "open_uri_mode": "ro",
            "query_only_requested": True,
            "query_only_value": 1,
            "quick_check": "ok",
            "sha256_before": HEX,
            "sha256_after": HEX,
            "sidecars_before": {"-wal": None, "-shm": None, "-journal": None},
            "sidecars_after": {"-wal": None, "-shm": None, "-journal": None},
            "identity_stable": True,
        },
        "site_before": snapshot,
        "site_after": json.loads(json.dumps(snapshot)),
        "site_identity_stable": True,
        "logs": {"paths_scanned": [], "counts": {}, "errors": []},
        "completeness": {
            "required_sources_found": True,
            "target_functions_found": True,
            "required_site_found": True,
            "database_readonly_verified": True,
            "logs_scanned": False,
            "ocr_failure_message_found": True,
            "rebuild_failure_message_found": True,
            "anchor_counts": {},
            "root_cause_confirmed": False,
        },
        "ua0009_status": "NOT_SAFE_TO_PUBLISH",
        "ua0009_evidence": {
            "db_row_count": 0,
            "db_published_count": 0,
            "video_page_present": False,
            "site_page_present": False,
        },
        "ua0010_status": "READY_FOR_DRAFT_CREATION_ONLY",
        "ua0010_evidence": {
            "db_row_count": 0,
            "db_published_count": 0,
            "video_page_present": False,
            "site_page_present": False,
            "owner_authorized": True,
            "publication_executed": False,
        },
        "errors": [],
    }


def manifest_for_current_files() -> dict:
    files = []
    for rel, path in ctrl.LOCAL_ARTIFACTS.items():
        files.append(
            {
                "source": rel,
                "remote": ctrl.REMOTE_ROOT + "/" + rel,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "http_status": 201,
            }
        )
    return {
        "status": "PASS",
        "remote_root": ctrl.REMOTE_ROOT,
        "generated_at_utc": now_text(),
        "production_touched": False,
        "crm_touched": False,
        "executed_remote_code": False,
        "webapp_reloaded": False,
        "files": files,
    }


class FakeAPI:
    def __init__(self, receipt: dict | None = None):
        self.receipt = receipt
        self.deleted_receipts = 0
        self.created_triggers = 0
        self.deleted_triggers = 0

    def read_file(self, path: str) -> str:
        if path == ctrl.REMOTE_MANIFEST_PATH:
            return json.dumps(manifest_for_current_files())
        if path == ctrl.REMOTE_SCRIPT:
            return (PACKAGE_DIR / "live_discovery.py").read_text(encoding="utf-8")
        if path == ctrl.REMOTE_ALLOWLIST:
            return (PACKAGE_DIR / "allowlist.json").read_text(encoding="utf-8")
        if path == ctrl.REMOTE_RECEIPT and self.receipt is not None:
            return json.dumps(self.receipt, ensure_ascii=False)
        raise FileNotFoundError(path)

    def delete_receipt(self) -> None:
        self.deleted_receipts += 1

    def create_trigger(self) -> tuple[str, int]:
        self.created_triggers += 1
        return "always_on", 123

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        self.deleted_triggers += 1
        if trigger != ("always_on", 123):
            raise AssertionError("unexpected trigger")


class TransportTests(unittest.TestCase):
    def test_real_transport_and_main_exist(self):
        self.assertTrue(callable(ctrl.main))
        self.assertTrue(hasattr(ctrl.PythonAnywhereAPI, "create_trigger"))
        self.assertTrue(hasattr(ctrl.PythonAnywhereAPI, "delete_trigger"))
        self.assertEqual(
            ctrl.EXACT_COMMAND,
            "python3.10 /home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync/live_discovery.py "
            "--allowlist-file /home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync/allowlist.json "
            "--output /home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync/task_058_live_discovery_receipt.json",
        )
        for forbidden in ("/home/Carix/team_bot.py", "systemctl", "reload", "sqlite3"):
            self.assertNotIn(forbidden, ctrl.EXACT_COMMAND)

    def test_api_rejects_wrong_account_host_and_remote_path(self):
        with self.assertRaisesRegex(ctrl.ControllerError, "USERNAME_INVALID"):
            ctrl.PythonAnywhereAPI(username="Other", host=ctrl.ALLOWED_HOSTS[0], token="x")
        with self.assertRaisesRegex(ctrl.ControllerError, "HOST_INVALID"):
            ctrl.PythonAnywhereAPI(username="Carix", host="evil.example", token="x")
        api = ctrl.PythonAnywhereAPI(username="Carix", host=ctrl.ALLOWED_HOSTS[0], token="x")
        with self.assertRaisesRegex(ctrl.ControllerError, "REMOTE_FILE_PATH_NOT_ALLOWED"):
            api._file_url("/home/Carix/team_bot.py")


class LocalAndManifestTests(unittest.TestCase):
    def test_local_artifacts_compile_and_allowlist_is_exact(self):
        controller = ctrl.ReadOnlyController(FakeAPI())
        hashes = controller.verify_local_artifacts()
        self.assertEqual(set(hashes), set(ctrl.LOCAL_ARTIFACTS))
        self.assertEqual(json.loads((PACKAGE_DIR / "allowlist.json").read_text()), ctrl.expected_allowlist())

    def test_valid_manifest_and_remote_hashes_pass(self):
        controller = ctrl.ReadOnlyController(FakeAPI())
        hashes = controller.verify_local_artifacts()
        controller.verify_sync_manifest(hashes)

    def test_manifest_safety_flag_or_hash_mismatch_is_blocked(self):
        class UnsafeAPI(FakeAPI):
            def read_file(self, path: str) -> str:
                if path == ctrl.REMOTE_MANIFEST_PATH:
                    manifest = manifest_for_current_files()
                    manifest["production_touched"] = True
                    manifest["files"][0]["sha256"] = "0" * 64
                    return json.dumps(manifest)
                return super().read_file(path)

        controller = ctrl.ReadOnlyController(UnsafeAPI())
        with self.assertRaises(ctrl.ControllerError):
            controller.verify_sync_manifest(controller.verify_local_artifacts())


class ReceiptValidationTests(unittest.TestCase):
    def test_complete_pass_receipt_is_accepted(self):
        receipt = pass_receipt()
        accepted = ctrl.ReadOnlyController.validate_receipt(json.dumps(receipt))
        self.assertEqual(accepted["status"], "PASS")
        self.assertEqual(accepted["ua0010_status"], "READY_FOR_DRAFT_CREATION_ONLY")
        self.assertIn("/home/Carix/video/UA-0010.html", accepted["site_before"])

    def test_long_numeric_metadata_is_not_misclassified_as_phone(self):
        receipt = pass_receipt()
        self.assertFalse(ctrl._sensitive_value(receipt["site_before"]))

    def test_secret_email_phone_and_vin_are_rejected(self):
        values = (
            "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456",
            "owner@example.com",
            "+380 67 123 45 67",
            "KNAGU416BKA324445",
            "API_KEY='this-is-a-hardcoded-provider-secret'",
        )
        for value in values:
            receipt = pass_receipt()
            receipt["errors"] = [value]
            with self.assertRaisesRegex(ctrl.ControllerError, "SENSITIVE_CONTENT"):
                ctrl.ReadOnlyController.validate_receipt(json.dumps(receipt))

    def test_missing_required_source_cannot_be_green(self):
        receipt = pass_receipt()
        removed = receipt["sources"].pop()
        receipt["source_hashes_after"].pop(removed["path"])
        with self.assertRaisesRegex(ctrl.ControllerError, "REQUIRED_SOURCE_PATH_MISSING"):
            ctrl.ReadOnlyController.validate_receipt(json.dumps(receipt))

    def test_missing_required_site_cannot_be_green(self):
        receipt = pass_receipt()
        missing = sorted(ctrl.REQUIRED_SITE_PATHS)[0]
        receipt["site_before"].pop(missing)
        receipt["site_after"].pop(missing)
        with self.assertRaisesRegex(ctrl.ControllerError, "SITE_SCOPE_INCOMPLETE"):
            ctrl.ReadOnlyController.validate_receipt(json.dumps(receipt))

    def test_database_or_site_change_cannot_be_green(self):
        receipt = pass_receipt()
        receipt["database"]["sha256_after"] = "b" * 64
        with self.assertRaisesRegex(ctrl.ControllerError, "DATABASE_IDENTITY_MISMATCH"):
            ctrl.ReadOnlyController.validate_receipt(json.dumps(receipt))
        receipt = pass_receipt()
        path = sorted(ctrl.REQUIRED_SITE_PATHS)[0]
        receipt["site_after"][path]["sha256"] = "b" * 64
        with self.assertRaisesRegex(ctrl.ControllerError, "SITE_IDENTITY_MISMATCH"):
            ctrl.ReadOnlyController.validate_receipt(json.dumps(receipt))

    def test_minimal_blocked_receipt_is_relayable_but_not_green(self):
        receipt = {
            "task_id": "task_058",
            "mode": "READ_ONLY_LIVE_DISCOVERY",
            "status": "BLOCKED",
            "generated_at_utc": now_text(),
            "production_write": False,
            "crm_write": False,
            "db_write": False,
            "site_rebuilt": False,
            "service_reloaded": False,
            "ocr_fix_installed": False,
            "gate_b_executed": False,
            "ua0009_published": False,
            "ua0010_published": False,
            "errors": ["REQUIRED_PATH_MISSING"],
        }
        accepted = ctrl.ReadOnlyController.validate_receipt(json.dumps(receipt))
        self.assertEqual(accepted["status"], "BLOCKED")
        self.assertNotEqual(accepted["status"], "PASS")

    def test_duplicate_json_key_and_stale_receipt_are_rejected(self):
        with self.assertRaisesRegex(ctrl.ControllerError, "DUPLICATE_JSON_KEY"):
            ctrl.ReadOnlyController.validate_receipt('{"task_id":"task_058","task_id":"task_058"}')
        receipt = pass_receipt()
        receipt["generated_at_utc"] = "2020-01-01T00:00:00Z"
        with self.assertRaisesRegex(ctrl.ControllerError, "RECEIPT_STALE"):
            ctrl.ReadOnlyController.validate_receipt(json.dumps(receipt))


class RunFlowTests(unittest.TestCase):
    def test_success_flow_verifies_runs_relays_and_always_cleans_up(self):
        api = FakeAPI(pass_receipt())
        with tempfile.TemporaryDirectory() as directory:
            old = (ctrl.EVIDENCE_PATH, ctrl.REPORT_PATH)
            ctrl.EVIDENCE_PATH = pathlib.Path(directory) / "evidence.json"
            ctrl.REPORT_PATH = pathlib.Path(directory) / "report.md"
            try:
                controller = ctrl.ReadOnlyController(
                    api,
                    sleep=lambda _: None,
                    monotonic=lambda: 0,
                    poll_interval=0,
                    poll_timeout=1,
                )
                result = controller.run()
                self.assertEqual(result["status"], "PASS")
                self.assertTrue(ctrl.EVIDENCE_PATH.is_file())
                self.assertTrue(ctrl.REPORT_PATH.is_file())
                self.assertIn("PRODUCTION_TOUCHED: NO", ctrl.REPORT_PATH.read_text())
            finally:
                ctrl.EVIDENCE_PATH, ctrl.REPORT_PATH = old
        self.assertEqual(api.created_triggers, 1)
        self.assertEqual(api.deleted_triggers, 1)
        self.assertEqual(api.deleted_receipts, 2)

    def test_malformed_receipt_still_cleans_trigger_and_receipt(self):
        class MalformedAPI(FakeAPI):
            def read_file(self, path: str) -> str:
                if path == ctrl.REMOTE_RECEIPT:
                    return "{not-json"
                return super().read_file(path)

        api = MalformedAPI()
        ticks = iter([0, 0, 0, 0])
        controller = ctrl.ReadOnlyController(
            api,
            sleep=lambda _: None,
            monotonic=lambda: next(ticks),
            poll_interval=0,
            poll_timeout=1,
        )
        with self.assertRaises(ctrl.ControllerError):
            controller.run()
        self.assertEqual(api.deleted_triggers, 1)
        self.assertEqual(api.deleted_receipts, 2)


if __name__ == "__main__":
    unittest.main()
