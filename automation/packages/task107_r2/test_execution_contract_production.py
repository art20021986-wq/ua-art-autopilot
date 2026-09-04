#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import textwrap
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "automation/execution_contract.py"


def load_contract():
    fake_source = textwrap.dedent(
        """
        from enum import Enum

        class TaskClass(Enum):
            FAST = "FAST"
            STANDARD = "STANDARD"
            CRITICAL = "CRITICAL"

        class TaskRequest:
            def __init__(self, raw):
                self.raw = raw
                self.task_id = raw["task_id"]
                self.changed_paths = tuple(raw.get("changed_paths", ()))

            @classmethod
            def from_mapping(cls, raw):
                return cls(raw)

        class Plan:
            def __init__(self, task_class):
                self.task_class = task_class

            def to_dict(self):
                return {
                    "task_class": self.task_class,
                    "ai_route": "NONE",
                    "ai_call_budget": 0,
                }

        def build_plan(request):
            return Plan("CRITICAL" if request.raw.get("production_required") else "FAST")

        def validate_receipt(raw):
            return raw
        """
    )
    with tempfile.TemporaryDirectory() as folder:
        fake_path = pathlib.Path(folder) / "task_orchestrator.py"
        fake_path.write_text(fake_source, encoding="utf-8")
        original_spec = importlib.util.spec_from_file_location

        def redirected_spec(name, location, *args, **kwargs):
            if name == "uaart_execution_orchestrator":
                location = fake_path
            return original_spec(name, location, *args, **kwargs)

        spec = original_spec("task107_r2_execution_contract", CONTRACT_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError("EXECUTION_CONTRACT_SPEC")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        with mock.patch(
            "importlib.util.spec_from_file_location", side_effect=redirected_spec
        ):
            spec.loader.exec_module(module)
        return module


EC = load_contract()


BACKUP_CONTROLLER = """
import json
import os
import pathlib

assert os.environ["UAART_OPERATION"] == "backup"
assert os.environ["UAART_RECEIPT_PATH"] == os.environ["UAART_BACKUP_RECEIPT_PATH"]
value = {
    "schema_version": "UA-ART-PRODUCTION-BACKUP-RECEIPT-1",
    "operation": "backup",
    "task_id": os.environ["UAART_TASK_ID"],
    "request_sha256": os.environ["UAART_REQUEST_SHA256"],
    "run_id": os.environ["UAART_RUN_ID"],
    "transaction_id": os.environ["UAART_TRANSACTION_ID"],
    "manifest_sha256": os.environ["UAART_MANIFEST_SHA256"],
    "backup_manifest_sha256": "b" * 64,
    "status": "PASS",
    "backup": "PASS",
    "unexpected_changes": 0,
}
target = pathlib.Path(os.environ["UAART_RECEIPT_PATH"])
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(value, sort_keys=True) + "\\n", encoding="utf-8")
"""


ROLLBACK_CONTROLLER = """
import json
import os
import pathlib

assert os.environ["UAART_OPERATION"] == "rollback"
assert os.environ["UAART_RECEIPT_PATH"] == os.environ["UAART_ROLLBACK_RECEIPT_PATH"]
value = {
    "schema_version": "UA-ART-PRODUCTION-ROLLBACK-RECEIPT-1",
    "operation": "rollback",
    "task_id": os.environ["UAART_TASK_ID"],
    "request_sha256": os.environ["UAART_REQUEST_SHA256"],
    "run_id": os.environ["UAART_RUN_ID"],
    "transaction_id": os.environ["UAART_TRANSACTION_ID"],
    "manifest_sha256": os.environ["UAART_MANIFEST_SHA256"],
    "backup_manifest_sha256": os.environ["UAART_BACKUP_MANIFEST_SHA256"],
    "status": "ROLLED_BACK",
    "rollback": "PASS",
    "restored": True,
    "unexpected_changes": 0,
    "protected_files_unchanged": True,
    "crm_unchanged": True,
    "live_verify": "PASS",
}
target = pathlib.Path(os.environ["UAART_RECEIPT_PATH"])
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(value, sort_keys=True) + "\\n", encoding="utf-8")
"""


MAIN_CONTROLLER = """
import json
import os
import pathlib

assert os.environ["UAART_OPERATION"] == "execute"
assert os.environ["UAART_BACKUP_MANIFEST_SHA256"] == "b" * 64
target = pathlib.Path(os.environ["UAART_RECEIPT_PATH"])
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps({"environment": "production"}) + "\\n", encoding="utf-8")
"""


class ProductionExecutionContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temporary.name)
        self.original_globals = (
            EC.ROOT,
            EC.ALLOWED_CONTROLLER_ROOTS,
            EC.ALLOWED_EVIDENCE_ROOTS,
            EC.SPECIAL_EVIDENCE,
        )
        EC.ROOT = self.root
        EC.ALLOWED_CONTROLLER_ROOTS = (
            self.root / "cloud",
            self.root / "automation/packages",
        )
        EC.ALLOWED_EVIDENCE_ROOTS = (
            self.root / "cloud",
            self.root / "state/receipts",
        )
        EC.SPECIAL_EVIDENCE = set()
        self.environment = {
            "UAART_RUN_ID": "run-991",
            "UAART_TRANSACTION_ID": "transaction-991",
        }

    def tearDown(self):
        (
            EC.ROOT,
            EC.ALLOWED_CONTROLLER_ROOTS,
            EC.ALLOWED_EVIDENCE_ROOTS,
            EC.SPECIAL_EVIDENCE,
        ) = self.original_globals
        self.temporary.cleanup()

    @staticmethod
    def sha(path: pathlib.Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def write(self, relative: str, content: str) -> pathlib.Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
        return path

    def create_request(self, *, include_backup: bool = True):
        package = "automation/packages/production_fixture"
        main_rel = package + "/controller.py"
        backup_rel = package + "/backup.py"
        rollback_rel = package + "/rollback.py"
        test_rel = package + "/test_controller.py"
        main = self.write(main_rel, MAIN_CONTROLLER)
        backup = self.write(backup_rel, BACKUP_CONTROLLER) if include_backup else None
        rollback = self.write(rollback_rel, ROLLBACK_CONTROLLER)
        test = self.write(test_rel, "assert True\n")
        task_id = "TASK-PRODUCTION-CONTRACT"
        receipt_rel = "state/receipts/%s.json" % task_id
        backup_receipt_rel = "state/receipts/%s-BACKUP.json" % task_id
        rollback_receipt_rel = "state/receipts/%s-ROLLBACK.json" % task_id
        execution = {
            "controller_path": main_rel,
            "controller_sha256": self.sha(main),
            "test_paths": [test_rel],
            "file_sha256": {test_rel: self.sha(test)},
            "receipt_path": receipt_rel,
            "evidence_paths": [receipt_rel, rollback_receipt_rel],
            "production_required": True,
            "rollback_controller_path": rollback_rel,
            "rollback_controller_sha256": self.sha(rollback),
            "rollback_receipt_path": rollback_receipt_rel,
            "timeout_seconds": 30,
        }
        if include_backup:
            execution.update(
                {
                    "backup_controller_path": backup_rel,
                    "backup_controller_sha256": self.sha(backup),
                    "backup_receipt_path": backup_receipt_rel,
                }
            )
            execution["evidence_paths"].append(backup_receipt_rel)
        request = {
            "task_id": task_id,
            "title": "Production execution contract fixture",
            "changed_paths": ["cloud/production-fixture.json"],
            "production_required": True,
            "requested_min_class": "CRITICAL",
            "execution": execution,
            "critical": {"manifest_sha256": "a" * 64},
        }
        request_rel = "tasks/requests/%s.json" % task_id
        request_path = self.write(
            request_rel, json.dumps(request, indent=2, sort_keys=True) + "\n"
        )
        return request_rel, request_path, request

    def test_production_requires_complete_pinned_backup_contract(self):
        request_rel, _, _ = self.create_request(include_backup=False)
        with self.assertRaisesRegex(
            EC.ExecutionContractError, "PRODUCTION_BACKUP_CONTRACT_REQUIRED"
        ):
            EC.validate_execution(request_rel, "CRITICAL")

    def test_tampered_backup_controller_hash_is_rejected(self):
        request_rel, request_path, request = self.create_request()
        request["execution"]["backup_controller_sha256"] = "f" * 64
        request_path.write_text(
            json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(
            EC.ExecutionContractError, "BACKUP_CONTROLLER_SHA_MISMATCH"
        ):
            EC.validate_execution(request_rel, "CRITICAL")

    def test_undeclared_package_python_dependency_is_rejected(self):
        request_rel, _, _ = self.create_request()
        self.write(
            "automation/packages/production_fixture/helper.py",
            "VALUE = 'trusted'\n",
        )
        with self.assertRaisesRegex(
            EC.ExecutionContractError, "PACKAGE_PYTHON_CLOSURE_MISMATCH"
        ):
            EC.validate_execution(request_rel, "CRITICAL")

    def test_symlinked_package_directory_is_rejected(self):
        request_rel, _, _ = self.create_request()
        outside = self.root / "outside-package"
        outside.mkdir()
        (outside / "injected.py").write_text("VALUE = 'outside'\n", encoding="utf-8")
        package = self.root / "automation/packages/production_fixture"
        (package / "linked-package").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(
            EC.ExecutionContractError, "PACKAGE_SYMLINK_ENTRY"
        ):
            EC.validate_execution(request_rel, "CRITICAL")

    def test_sourceless_or_native_package_module_is_rejected(self):
        request_rel, _, _ = self.create_request()
        package = self.root / "automation/packages/production_fixture"
        for filename in ("injected.pyc", "injected.so"):
            with self.subTest(filename=filename):
                (package / filename).write_bytes(b"untrusted-import-artifact")
                with self.assertRaisesRegex(
                    EC.ExecutionContractError, "PACKAGE_IMPORT_ARTIFACT_FORBIDDEN"
                ):
                    EC.validate_execution(request_rel, "CRITICAL")
                (package / filename).unlink()

    def test_dependency_closure_is_exact_hashed_and_canonical(self):
        request_rel, request_path, request = self.create_request()
        dependency_rel = "automation/packages/production_fixture/helper.py"
        dependency = self.write(dependency_rel, "VALUE = 'trusted'\n")
        request["execution"]["dependency_paths"] = [dependency_rel]
        request["execution"]["file_sha256"][dependency_rel] = self.sha(dependency)
        request_path.write_text(
            json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        spec = EC.validate_execution(request_rel, "CRITICAL")
        self.assertEqual(spec.dependency_paths, (dependency_rel,))
        self.assertEqual(
            spec.dependency_sha256,
            EC.dependency_digest(spec.file_sha256),
        )
        dependency.write_text("VALUE = 'tampered'\n", encoding="utf-8")
        with self.assertRaisesRegex(
            EC.ExecutionContractError, "DEPENDENCY_SHA_MISMATCH"
        ):
            EC.validate_execution(request_rel, "CRITICAL")

    def test_file_hash_map_cannot_smuggle_undeclared_dependency(self):
        request_rel, request_path, request = self.create_request()
        dependency_rel = "automation/packages/production_fixture/helper.py"
        dependency = self.write(dependency_rel, "VALUE = 'trusted'\n")
        request["execution"]["file_sha256"][dependency_rel] = self.sha(dependency)
        request_path.write_text(
            json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(
            EC.ExecutionContractError, "FILE_SHA256_KEY_SET_MISMATCH"
        ):
            EC.validate_execution(request_rel, "CRITICAL")

    def test_isolated_launcher_blocks_sitecustomize_and_keeps_sibling_imports(self):
        request_rel, request_path, request = self.create_request()
        package = "automation/packages/production_fixture"
        helper_rel = package + "/helper.py"
        hook_rel = package + "/sitecustomize.py"
        helper = self.write(helper_rel, "VALUE = 'trusted'\n")
        hook = self.write(
            hook_rel,
            "import os, pathlib\n"
            "pathlib.Path(os.environ['HOOK_MARKER']).write_text('executed')\n",
        )
        controller_rel = request["execution"]["controller_path"]
        controller = self.root / controller_rel
        controller.write_text("import helper\n" + MAIN_CONTROLLER, encoding="utf-8")
        request["execution"]["controller_sha256"] = self.sha(controller)
        request["execution"]["dependency_paths"] = [helper_rel, hook_rel]
        request["execution"]["file_sha256"].update(
            {helper_rel: self.sha(helper), hook_rel: self.sha(hook)}
        )
        request_path.write_text(
            json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        spec = EC.validate_execution(request_rel, "CRITICAL")
        marker = self.root / "hook-ran.txt"
        environment = dict(self.environment)
        environment["HOOK_MARKER"] = str(marker)
        with mock.patch.dict(os.environ, environment, clear=True):
            EC.run_backup(spec)
            EC.run_controller(spec)
        self.assertFalse(marker.exists())
        self.assertFalse((self.root / package / "__pycache__").exists())
        self.assertTrue((self.root / spec.receipt_path).is_file())

    def test_backup_execute_and_rollback_are_bound_to_one_transaction(self):
        request_rel, _, _ = self.create_request()
        spec = EC.validate_execution(request_rel, "CRITICAL")
        with mock.patch.dict(os.environ, self.environment, clear=True):
            EC.run_backup(spec)
            backup = EC.validate_backup_receipt(spec)
            self.assertEqual(backup["request_sha256"], spec.request_sha256)
            self.assertEqual(backup["manifest_sha256"], "a" * 64)
            self.assertEqual(backup["backup_manifest_sha256"], "b" * 64)
            EC.run_controller(spec)
            self.assertTrue((self.root / spec.receipt_path).is_file())
            os.environ["UAART_BACKUP_MANIFEST_SHA256"] = "b" * 64
            EC.run_rollback(spec)
            rollback = EC.validate_rollback_receipt(spec)
            self.assertEqual(
                rollback["backup_manifest_sha256"],
                backup["backup_manifest_sha256"],
            )
            refreshed = EC.validate_execution(request_rel, "CRITICAL")
            completed = mock.Mock(returncode=0)
            with mock.patch.object(EC.subprocess, "run", return_value=completed):
                staged = EC.stage_evidence(refreshed)
            self.assertEqual(
                set(staged),
                {
                    refreshed.receipt_path,
                    refreshed.backup_receipt_path,
                    refreshed.rollback_receipt_path,
                },
            )

    def test_preexisting_backup_receipt_blocks_controller_execution(self):
        request_rel, _, _ = self.create_request()
        spec = EC.validate_execution(request_rel, "CRITICAL")
        self.write(str(spec.backup_receipt_path), "stale\n")
        with mock.patch.dict(os.environ, self.environment, clear=True):
            with self.assertRaisesRegex(
                EC.ExecutionContractError, "BACKUP_RECEIPT_PREEXISTING"
            ):
                EC.run_backup(spec)

    def test_preexisting_final_and_rollback_receipts_are_never_overwritten(self):
        request_rel, _, _ = self.create_request()
        spec = EC.validate_execution(request_rel, "CRITICAL")
        environment = dict(self.environment)
        environment["UAART_BACKUP_MANIFEST_SHA256"] = "b" * 64
        with mock.patch.dict(os.environ, environment, clear=True):
            EC.run_backup(spec)
            self.write(spec.receipt_path, "stale-final\n")
            with self.assertRaisesRegex(
                EC.ExecutionContractError, "CONTROLLER_RECEIPT_PREEXISTING"
            ):
                EC.run_controller(spec)
            self.write(str(spec.rollback_receipt_path), "stale-rollback\n")
            with self.assertRaisesRegex(
                EC.ExecutionContractError, "ROLLBACK_RECEIPT_PREEXISTING"
            ):
                EC.run_rollback(spec)

    def test_backup_receipt_rejects_extra_keys_and_wrong_request_binding(self):
        request_rel, _, _ = self.create_request()
        spec = EC.validate_execution(request_rel, "CRITICAL")
        with mock.patch.dict(os.environ, self.environment, clear=True):
            EC.run_backup(spec)
            receipt_path = self.root / str(spec.backup_receipt_path)
            value = json.loads(receipt_path.read_text(encoding="utf-8"))
            value["extra"] = True
            receipt_path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(
                EC.ExecutionContractError, "BACKUP_RECEIPT_SCHEMA_KEYS"
            ):
                EC.validate_backup_receipt(spec)
            value.pop("extra")
            value["request_sha256"] = "c" * 64
            receipt_path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(
                EC.ExecutionContractError,
                "BACKUP_RECEIPT_BINDING_REQUEST_SHA256",
            ):
                EC.validate_backup_receipt(spec)

    def test_rollback_receipt_must_match_runtime_backup_manifest(self):
        request_rel, _, _ = self.create_request()
        spec = EC.validate_execution(request_rel, "CRITICAL")
        environment = dict(self.environment)
        environment["UAART_BACKUP_MANIFEST_SHA256"] = "b" * 64
        with mock.patch.dict(os.environ, environment, clear=True):
            EC.run_backup(spec)
            EC.run_rollback(spec)
            receipt_path = self.root / str(spec.rollback_receipt_path)
            value = json.loads(receipt_path.read_text(encoding="utf-8"))
            value["backup_manifest_sha256"] = "c" * 64
            receipt_path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(
                EC.ExecutionContractError,
                "ROLLBACK_RECEIPT_BACKUP_MANIFEST_SHA256_MISMATCH",
            ):
                EC.validate_rollback_receipt(spec)

    def test_backup_receipt_rejects_every_changed_runtime_binding(self):
        request_rel, _, _ = self.create_request()
        spec = EC.validate_execution(request_rel, "CRITICAL")
        with mock.patch.dict(os.environ, self.environment, clear=True):
            EC.run_backup(spec)
            receipt_path = self.root / str(spec.backup_receipt_path)
            original = json.loads(receipt_path.read_text(encoding="utf-8"))
            changed_values = {
                "task_id": "TASK-OTHER",
                "request_sha256": "c" * 64,
                "run_id": "run-other",
                "transaction_id": "transaction-other",
                "manifest_sha256": "d" * 64,
            }
            for key, changed in changed_values.items():
                with self.subTest(key=key):
                    value = dict(original)
                    value[key] = changed
                    receipt_path.write_text(json.dumps(value), encoding="utf-8")
                    with self.assertRaisesRegex(
                        EC.ExecutionContractError,
                        "BACKUP_RECEIPT_BINDING_" + key.upper(),
                    ):
                        EC.validate_backup_receipt(spec)

    def test_request_schema_declares_backup_fields_mandatory_for_production(self):
        schema = json.loads(
            (ROOT / "state/schemas/task_request.schema.json").read_text(
                encoding="utf-8"
            )
        )
        execution_properties = schema["properties"]["execution"]["properties"]
        for key in (
            "backup_controller_path",
            "backup_controller_sha256",
            "backup_receipt_path",
            "dependency_paths",
        ):
            self.assertIn(key, execution_properties)
        production_required = set(
            schema["allOf"][0]["then"]["properties"]["execution"]["required"]
        )
        self.assertTrue(
            {
                "backup_controller_path",
                "backup_controller_sha256",
                "backup_receipt_path",
            }.issubset(production_required)
        )

    def test_runtime_run_and_transaction_bindings_are_required(self):
        request_rel, _, _ = self.create_request()
        spec = EC.validate_execution(request_rel, "CRITICAL")
        with mock.patch.dict(os.environ, {"UAART_RUN_ID": "run-only"}, clear=True):
            with self.assertRaisesRegex(
                EC.ExecutionContractError,
                "RUNTIME_BINDING_INVALID:UAART_TRANSACTION_ID",
            ):
                EC.run_backup(spec)


if __name__ == "__main__":
    unittest.main(verbosity=2)
