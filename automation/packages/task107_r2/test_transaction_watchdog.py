#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "automation"))
import control_plane as CP  # noqa: E402
import transaction_watchdog as TW  # noqa: E402


class TransactionWatchdogTests(unittest.TestCase):
    def fixture(self, root: pathlib.Path) -> pathlib.Path:
        request_rel = "tasks/requests/TASK-ORPHAN.json"
        request = {
            "task_id": "TASK-ORPHAN",
            "production_required": True,
            "execution": {
                "backup_receipt_path": "state/receipts/TASK-ORPHAN-BACKUP.json"
            },
        }
        CP.atomic_json(root / request_rel, request)
        request_sha = CP.sha256_file(root / request_rel)
        transaction = {
            "autostart_ledger_path": "state/autostart_consumed/example.json",
            "backup_manifest_sha256": "a" * 64,
            "backup_receipt_path": "state/receipts/TASK-ORPHAN-BACKUP.json",
            "backup_receipt_sha256": "b" * 64,
            "expires_at": "2026-09-04T16:00:00Z",
            "mode_epoch": "auto-test-1234567890123456",
            "opened_at": "2026-09-04T14:00:00Z",
            "request_path": request_rel,
            "request_sha256": request_sha,
            "run_id": "run-123",
            "schema_version": CP.PRODUCTION_TRANSACTION_SCHEMA,
            "status": "OPEN",
            "task_id": "TASK-ORPHAN",
            "transaction_id": "tx-run-123-abcdef0123456789",
        }
        path = root / f"state/transactions/TASK-ORPHAN.{request_sha}.run-123.json"
        CP.atomic_json(path, transaction)
        return path

    def test_discovers_exact_open_transaction(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            path = self.fixture(root)
            result = TW.discover(root=root)
            self.assertTrue(result["has_pending"])
            self.assertEqual(result["transaction_path"], path.relative_to(root).as_posix())

    def test_rejects_request_sha_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.fixture(root)
            request = root / "tasks/requests/TASK-ORPHAN.json"
            request.write_text(request.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(TW.WatchdogError, "TRANSACTION_REQUEST_SHA"):
                TW.discover(root=root)


if __name__ == "__main__":
    unittest.main()
