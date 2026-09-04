#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "automation"))
import control_plane as CP  # noqa: E402
import transaction_watchdog as TW  # noqa: E402


class TransactionWatchdogTests(unittest.TestCase):
    MODE_EPOCH = "auto-20260904T135101Z-watchdogfixture01"
    SOURCE_COMMIT = "d" * 40
    MANIFEST_SHA = "c" * 64
    BACKUP_MANIFEST_SHA = "a" * 64

    def fixture(self, root: pathlib.Path, *, status: str = "OPEN") -> dict:
        task_id = "TASK-ORPHAN"
        run_id = "run-123"
        transaction_id = "tx-run-123-abcdef0123456789"
        request_rel = "tasks/requests/TASK-ORPHAN.json"
        backup_rel = "state/receipts/TASK-ORPHAN-BACKUP.json"
        request = {
            "changed_paths": ["automation/packages/task-orphan/controller.py"],
            "complexity": 5,
            "critical": {
                "gate_b_authorized": True,
                "manifest_sha256": self.MANIFEST_SHA,
            },
            "description": "Bounded critical Production recovery fixture",
            "execution": {"backup_receipt_path": backup_rel},
            "production_required": True,
            "requested_min_class": "CRITICAL",
            "task_id": task_id,
            "title": "Production recovery fixture",
        }
        CP.atomic_json(root / request_rel, request)
        request_sha = CP.sha256_file(root / request_rel)
        identity = CP._identity(request, request_sha, run_id)
        ledger_rel = f"state/autostart_consumed/{task_id}.{request_sha}.json"
        CP.atomic_json(
            root / ledger_rel,
            {
                "expires_at": "2026-09-04T16:00:00Z",
                "fixture": "ledger",
                "mode_epoch": self.MODE_EPOCH,
            },
        )
        ledger_sha = CP.sha256_file(root / ledger_rel)
        transaction_rel = CP.transaction_relative_path(identity)

        if status in {"OPEN", "ROLLING_BACK"}:
            receipt = {
                "backup": "PASS",
                "backup_manifest_sha256": self.BACKUP_MANIFEST_SHA,
                "manifest_sha256": self.MANIFEST_SHA,
                "operation": "backup",
                "request_sha256": request_sha,
                "run_id": run_id,
                "schema_version": "UA-ART-PRODUCTION-BACKUP-RECEIPT-1",
                "status": "PASS",
                "task_id": task_id,
                "transaction_id": transaction_id,
                "unexpected_changes": 0,
            }
            CP.atomic_json(root / backup_rel, receipt)
            backup_receipt_sha = CP.sha256_file(root / backup_rel)
            backup_manifest_sha = self.BACKUP_MANIFEST_SHA
            opened_at = "2026-09-04T14:01:00Z"
        elif status == "PREPARING":
            receipt = None
            backup_receipt_sha = None
            backup_manifest_sha = None
            opened_at = None
        else:
            raise AssertionError("unsupported fixture status")

        transaction = {
            "autostart_ledger_path": ledger_rel,
            "backup_manifest_sha256": backup_manifest_sha,
            "backup_receipt_path": backup_rel,
            "backup_receipt_sha256": backup_receipt_sha,
            "expires_at": "2026-09-04T16:00:00Z",
            "mode_epoch": self.MODE_EPOCH,
            "opened_at": opened_at,
            "prepared_at": "2026-09-04T14:00:00Z",
            "request_path": request_rel,
            "request_sha256": request_sha,
            "run_id": run_id,
            "schema_version": CP.PRODUCTION_TRANSACTION_SCHEMA,
            "status": status,
            "task_id": task_id,
            "transaction_id": transaction_id,
        }
        transaction_path = root / transaction_rel
        CP.atomic_json(transaction_path, transaction)
        claim_rel = CP.claim_relative_path(identity)
        claim = {
            "autostart_ledger_path": ledger_rel,
            "autostart_ledger_sha256": ledger_sha,
            "autostart_source_commit": self.SOURCE_COMMIT,
            "critical_gate_evidence_sha256": "f" * 64,
            "critical_gate_status": "PASS_PRODUCTION",
            "execution_mode": "AUTOMATIC",
            "identity": identity,
            "mode_epoch": self.MODE_EPOCH,
            "package_compile_status": "PASS",
            "pre_health_status": "PASS",
            "production_required": True,
            "production_transaction_id": transaction_id,
            "production_transaction_path": transaction_rel,
            "production_transaction_status": status,
            "request_path": request_rel,
            "request_sha256": request_sha,
            "schema_version": CP.SCHEMA_VERSION,
            "storage_preflight": {
                "allowed": True,
                "status": "WARN_70",
            },
            "storage_preflight_status": "WARN_70",
            "task_class": "CRITICAL",
        }
        CP.atomic_json(root / claim_rel, claim)
        return {
            "backup_rel": backup_rel,
            "claim": claim,
            "claim_rel": claim_rel,
            "identity": identity,
            "ledger_rel": ledger_rel,
            "ledger_sha": ledger_sha,
            "path": transaction_path,
            "receipt": receipt,
            "request": request,
            "request_rel": request_rel,
            "request_sha": request_sha,
            "transaction": transaction,
            "transaction_rel": transaction_rel,
        }

    @contextlib.contextmanager
    def trusted_verifiers(self, root: pathlib.Path):
        def verify_ledger(
            ledger_path,
            request_path,
            raw,
            request_sha256,
            run_id,
            **kwargs,
        ):
            self.assertEqual(ledger_path, kwargs.pop("expected_ledger", ledger_path))
            self.assertEqual(request_path, f"tasks/requests/{raw['task_id']}.json")
            self.assertEqual(request_sha256, CP.sha256_file(root / request_path))
            self.assertEqual(run_id, "run-123")
            self.assertEqual(kwargs["expected_source_commit"], self.SOURCE_COMMIT)
            self.assertEqual(kwargs["root"], root.resolve(strict=False))
            self.assertIs(kwargs["allow_expired_for_recovery"], True)
            self.assertIs(kwargs["allow_halt_for_recovery"], True)
            return {
                "ledger_path": ledger_path,
                "ledger_sha256": CP.sha256_file(root / ledger_path),
                "source_commit": self.SOURCE_COMMIT,
            }

        with mock.patch.object(
            TW.cp,
            "verify_execution_mode",
            return_value={"mode": "AUTOMATIC", "mode_epoch": self.MODE_EPOCH},
        ) as mode_mock, mock.patch.object(
            TW.cp, "verify_autostart_ledger", side_effect=verify_ledger
        ) as ledger_mock:
            yield mode_mock, ledger_mock

    def rewrite(self, path: pathlib.Path, value: dict) -> None:
        CP.atomic_json(path, value)

    def test_discovers_exact_open_transaction_and_recovery_bindings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            fixture = self.fixture(root)
            with self.trusted_verifiers(root) as (mode_mock, ledger_mock):
                result = TW.discover(root=root)
            self.assertTrue(result["has_pending"])
            self.assertEqual(result["pending_count"], 1)
            self.assertEqual(result["transaction_status"], "OPEN")
            self.assertEqual(result["transaction_path"], fixture["transaction_rel"])
            self.assertEqual(result["claim_path"], fixture["claim_rel"])
            self.assertEqual(result["source_commit"], self.SOURCE_COMMIT)
            outputs = TW._github_outputs(result)
            self.assertEqual(outputs["claim_path"], fixture["claim_rel"])
            self.assertEqual(outputs["source_commit"], self.SOURCE_COMMIT)
            mode_mock.assert_called_once_with(
                root=root.resolve(strict=False),
                required_mode="AUTOMATIC",
                allow_halt_for_recovery=True,
            )
            self.assertEqual(ledger_mock.call_count, 1)

    def test_discovers_preparing_without_backup_credential_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.fixture(root, status="PREPARING")
            with self.trusted_verifiers(root):
                result = TW.discover(root=root)
            self.assertTrue(result["has_pending"])
            self.assertEqual(result["transaction_status"], "PREPARING")
            self.assertNotIn("backup_manifest_sha256", TW._github_outputs(result))

    def test_discovers_rolling_back_without_making_it_clear(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            fixture = self.fixture(root, status="ROLLING_BACK")
            with self.trusted_verifiers(root):
                result = TW.discover(root=root)
            self.assertTrue(result["has_pending"])
            self.assertEqual(result["transaction_status"], "ROLLING_BACK")
            self.assertEqual(
                TW._github_outputs(result)["backup_manifest_sha256"],
                self.BACKUP_MANIFEST_SHA,
            )
            with self.trusted_verifiers(root), self.assertRaisesRegex(
                TW.WatchdogError,
                "PENDING_PRODUCTION_TRANSACTION:ROLLING_BACK",
            ):
                TW.assert_clear(root=root)
            self.assertEqual(result["transaction_path"], fixture["transaction_rel"])

    def test_rejects_rolling_back_without_open_backup_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            fixture = self.fixture(root, status="ROLLING_BACK")
            transaction = dict(fixture["transaction"])
            transaction["opened_at"] = None
            self.rewrite(fixture["path"], transaction)
            with self.trusted_verifiers(root), self.assertRaisesRegex(
                TW.WatchdogError, "TRANSACTION_OPEN_TIME_INVALID"
            ):
                TW.discover(root=root)

    def test_rejects_request_sha_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            fixture = self.fixture(root)
            request = root / fixture["request_rel"]
            request.write_text(request.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(TW.WatchdogError, "TRANSACTION_REQUEST_SHA"):
                TW.discover(root=root)

    def test_rejects_forged_noncanonical_transaction_alias(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            fixture = self.fixture(root)
            forged = root / "state/transactions/forged-alias.json"
            fixture["path"].replace(forged)
            with self.trusted_verifiers(root), self.assertRaisesRegex(
                TW.WatchdogError, "TRANSACTION_CANONICAL_PATH"
            ):
                TW.discover(root=root)

    def test_rejects_missing_exact_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            fixture = self.fixture(root)
            (root / fixture["claim_rel"]).unlink()
            with self.trusted_verifiers(root), self.assertRaisesRegex(
                TW.WatchdogError, "TRANSACTION_CLAIM_MISSING"
            ):
                TW.discover(root=root)

    def test_rejects_claim_without_gate_b(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            fixture = self.fixture(root)
            claim = dict(fixture["claim"])
            claim["critical_gate_status"] = "PENDING"
            self.rewrite(root / fixture["claim_rel"], claim)
            with self.trusted_verifiers(root), self.assertRaisesRegex(
                TW.WatchdogError, "TRANSACTION_CLAIM_GATE_B"
            ):
                TW.discover(root=root)

    def test_rejects_claim_ledger_sha_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            fixture = self.fixture(root)
            claim = dict(fixture["claim"])
            claim["autostart_ledger_sha256"] = "e" * 64
            self.rewrite(root / fixture["claim_rel"], claim)
            with self.trusted_verifiers(root), self.assertRaisesRegex(
                TW.WatchdogError, "TRANSACTION_CLAIM_LEDGER_SHA"
            ):
                TW.discover(root=root)

    def test_rejects_backup_receipt_sha_drift(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            fixture = self.fixture(root)
            backup = root / fixture["backup_rel"]
            backup.write_text(backup.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.trusted_verifiers(root), self.assertRaisesRegex(
                TW.WatchdogError, "TRANSACTION_BACKUP_RECEIPT_SHA"
            ):
                TW.discover(root=root)

    def test_rejects_backup_receipt_identity_forgery(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            fixture = self.fixture(root)
            receipt = dict(fixture["receipt"])
            receipt["transaction_id"] = "tx-forged-abcdef0123456789"
            backup = root / fixture["backup_rel"]
            self.rewrite(backup, receipt)
            transaction = dict(fixture["transaction"])
            transaction["backup_receipt_sha256"] = CP.sha256_file(backup)
            self.rewrite(fixture["path"], transaction)
            with self.trusted_verifiers(root), self.assertRaisesRegex(
                TW.WatchdogError, "TRANSACTION_BACKUP_RECEIPT_BINDING"
            ):
                TW.discover(root=root)

    def test_rejects_preparing_record_with_open_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            fixture = self.fixture(root, status="PREPARING")
            transaction = dict(fixture["transaction"])
            transaction["backup_manifest_sha256"] = self.BACKUP_MANIFEST_SHA
            self.rewrite(fixture["path"], transaction)
            with self.trusted_verifiers(root), self.assertRaisesRegex(
                TW.WatchdogError, "TRANSACTION_PREPARING_HAS_BACKUP_STATE"
            ):
                TW.discover(root=root)

    def test_multiple_preparing_or_open_transactions_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            fixture = self.fixture(root, status="PREPARING")
            second = root / "state/transactions/second.json"
            self.rewrite(second, fixture["transaction"] | {"status": "OPEN"})
            with self.assertRaisesRegex(
                TW.WatchdogError, "MULTIPLE_PENDING_PRODUCTION_TRANSACTIONS"
            ):
                TW.discover(root=root)

    def test_assert_clear_passes_empty_and_blocks_pending(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            result = TW.assert_clear(root=root)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["transaction_status"], "NONE")
            self.fixture(root, status="PREPARING")
            with self.trusted_verifiers(root), self.assertRaisesRegex(
                TW.WatchdogError, "PENDING_PRODUCTION_TRANSACTION:PREPARING"
            ):
                TW.assert_clear(root=root)

    def test_rejects_mode_epoch_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.fixture(root)
            with mock.patch.object(
                TW.cp,
                "verify_execution_mode",
                return_value={"mode": "AUTOMATIC", "mode_epoch": "auto-other-1234567890123456"},
            ), self.assertRaisesRegex(TW.WatchdogError, "TRANSACTION_MODE_EPOCH"):
                TW.discover(root=root)


if __name__ == "__main__":
    unittest.main()
