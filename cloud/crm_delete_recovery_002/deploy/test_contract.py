"""Local synthetic contract tests. No fixture is production evidence."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import contract as c


class ContractFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.execution = {"production_required": True, "test_paths": [c.PACKAGE_REL + "/test_controller.py"],
            "dependency_paths": [c.PACKAGE_REL + "/remote_worker.py"],
            "file_sha256": {}, "receipt_path": c.RECEIPT_REL,
            "backup_receipt_path": c.BACKUP_RECEIPT_REL, "rollback_receipt_path": c.ROLLBACK_RECEIPT_REL,
            "evidence_paths": [c.RECEIPT_REL, c.BACKUP_RECEIPT_REL, c.ROLLBACK_RECEIPT_REL]}
        for prefix, name in (("", "controller.py"), ("backup_", "backup_controller.py"),
                             ("rollback_", "rollback_controller.py")):
            relative = c.PACKAGE_REL + "/" + name
            raw = ("IDENTITY = " + repr(name) + "\n").encode()
            self.write(relative, raw)
            self.execution[prefix + "controller_path"] = relative
            self.execution[prefix + "controller_sha256"] = c.sha(raw)
        for relative in self.execution["test_paths"] + self.execution["dependency_paths"]:
            raw = b"LOCAL_FIXTURE_ONLY = True\n"
            self.write(relative, raw)
            self.execution["file_sha256"][relative] = c.sha(raw)
        self.policy = c.sha(b"synthetic-policy-only")
        self.package = c.sha(b"synthetic-package-only")
        self.deletion_schema = {name: "CREATE TABLE " + name + " (id TEXT PRIMARY KEY)"
                                for name in sorted(c.DELETION_TABLES)}
        self.schema_source_text = "SCHEMA = " + repr(self.deletion_schema) + "\n"
        self.manifest = {"task_id": c.TASK_ID, "parent_task_id": c.PARENT_TASK_ID,
            "task_class": "CRITICAL", "contract_id": c.CRITICAL_CONTRACT,
            "production_write": True, "backup_required": True, "rollback_required": True,
            "live_verify_required": True, "acceptance_scope": c.RECEIPT_SCOPE,
            "package_manifest_sha256": self.package, "installation_policy_sha256": self.policy,
            "operations": [{"path": "production/cars_ui.py", "action": "replace",
                "expected_before_sha256": c.sha(b"before"), "expected_after_sha256": c.sha(b"after")},
                {"path": c.SCHEMA_OPERATION_PATH, "action": "replace", "digest_scope": "sqlite_schema",
                 "expected_before_sha256": c.sha(c.canonical_json(dict.fromkeys(sorted(c.DELETION_TABLES)))),
                 "expected_after_sha256": c.sha(c.canonical_json(self.deletion_schema)),
                 "before_projection": dict.fromkeys(sorted(c.DELETION_TABLES)), "after_projection": self.deletion_schema,
                 "migration_payload_sha256": c.sha(self.schema_source_text.encode()),
                 "database_file_hash_claimed": False, "fresh_projection_verification_required": True}],
            "protected_paths": ["production/protected.py"]}
        self.approval = {"schema_version": "UA-ART-PRODUCTION-AUTHORIZATION-1", "task_id": c.TASK_ID,
            "authorized_environment": "production",
            "owner_authorized": True, "production_allowed": True, "request_path": c.REQUEST_REL,
            "approved_at": "2026-01-01T00:00:00Z", "expires_at": "2026-01-01T01:00:00Z",
            "authorization_id": "prod-auth-fixture-only-no-authority", "launch_nonce": "fixture-local-only",
            "mode_epoch": "fixture-mode", "owner": "fixture-owner-no-authority"}
        self.request = {"task_id": c.TASK_ID, "parent_task_id": c.PARENT_TASK_ID,
            "production_required": True, "requested_min_class": "CRITICAL",
            "acceptance_scope": c.RECEIPT_SCOPE, "package_manifest_sha256": self.package,
            "installation_policy_sha256": self.policy, "changed_paths": ["production/cars_ui.py", c.SCHEMA_OPERATION_PATH],
            "execution": self.execution, "critical": {"manifest_path": c.MANIFEST_REL,
                "owner_approval_path": c.APPROVAL_REL, "gate_b_authorized": True}}
        self.gate = {"contract_id": c.CRITICAL_CONTRACT, "task_id": c.TASK_ID, "status": "PASS",
            "production_write": False, "tests": "PASS", "unexpected_changes": 0,
            "backup_plan_ready": True, "rollback_plan_ready": True,
            "protected_snapshot": {"production/protected.py": c.sha(b"protected")},
            "test_evidence": {"passed": 1, "failed": 0, "skipped": 0}}
        self.env = {"UAART_OPERATION": "backup", "UAART_REQUEST_PATH": c.REQUEST_REL,
            "UAART_TASK_ID": c.TASK_ID, "UAART_TASK_CLASS": "CRITICAL", "UAART_RUN_ID": "fixture-run",
            "UAART_TRANSACTION_ID": "fixture-transaction", "UAART_RECEIPT_PATH": c.BACKUP_RECEIPT_REL,
            "UAART_BACKUP_RECEIPT_PATH": c.BACKUP_RECEIPT_REL}
        self.sync()

    def write(self, relative, raw):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    def sync(self):
        manifest_raw = c.canonical_json(self.manifest)
        self.write(c.MANIFEST_REL, manifest_raw)
        self.request["critical"]["manifest_sha256"] = c.sha(manifest_raw)
        self.approval["manifest_sha256"] = c.sha(manifest_raw)
        self.gate["manifest_sha256"] = c.sha(manifest_raw)
        files = dict(self.execution["file_sha256"])
        for prefix in ("", "backup_", "rollback_"):
            files[self.execution[prefix + "controller_path"]] = self.execution[prefix + "controller_sha256"]
        self.gate["test_evidence"]["dependency_sha256"] = c.sha(c.canonical_json(files))
        gate_raw = c.canonical_json(self.gate)
        self.write(c.GATE_A_REL, gate_raw)
        self.request["critical"].update(gate_a_path=c.GATE_A_REL, gate_a_sha256=c.sha(gate_raw))
        self.approval["gate_a_sha256"] = c.sha(gate_raw)
        self.request["critical"]["owner_approval_sha256"] = "0" * 64
        self.approval["request_subject_sha256"] = c.request_authorization_sha256(self.request)
        approval_raw = c.canonical_json(self.approval)
        self.write(c.APPROVAL_REL, approval_raw)
        self.request["critical"]["owner_approval_sha256"] = c.sha(approval_raw)
        request_raw = c.canonical_json(self.request)
        self.write(c.REQUEST_REL, request_raw)
        self.env["UAART_REQUEST_SHA256"] = c.sha(request_raw)
        self.env["UAART_MANIFEST_SHA256"] = c.sha(manifest_raw)

    def load(self, operation="backup"):
        return c.load_envelope(self.root, self.env, operation)

    def set_operation(self, operation):
        previous = self.load()
        backup_sha = c.sha(b"synthetic-backup")
        receipt = dict(previous.bindings, backup_manifest_sha256=backup_sha,
            schema_version=c.BACKUP_RECEIPT_SCHEMA, operation="backup", status="PASS", backup="PASS",
            unexpected_changes=0)
        self.write(c.BACKUP_RECEIPT_REL, c.canonical_json(receipt))
        self.env.update(UAART_OPERATION=operation, UAART_BACKUP_MANIFEST_SHA256=backup_sha,
            UAART_RECEIPT_PATH=c.RECEIPT_REL if operation == "execute" else c.ROLLBACK_RECEIPT_REL)
        if operation == "rollback":
            self.env["UAART_ROLLBACK_RECEIPT_PATH"] = c.ROLLBACK_RECEIPT_REL


class EnvelopeTests(ContractFixture):
    def test_complete_fixture_envelope_is_read_only_and_contains_no_token(self):
        self.env["PYTHONANYWHERE_API_TOKEN"] = "fixture-token-never-returned"
        before = {str(path.relative_to(self.root)): path.read_bytes()
                  for path in self.root.rglob("*") if path.is_file()}
        envelope = self.load()
        self.assertEqual(c.TASK_ID, envelope.task_id)
        self.assertNotIn("PYTHONANYWHERE_API_TOKEN", envelope.values)
        self.assertFalse(envelope.receipt_path.exists())
        self.assertEqual(before, {str(path.relative_to(self.root)): path.read_bytes()
                                for path in self.root.rglob("*") if path.is_file()})

    def test_parent_task_cannot_be_finished_through_install_identity(self):
        self.env["UAART_TASK_ID"] = c.PARENT_TASK_ID
        with self.assertRaisesRegex(c.ContractError, "TASK_IDENTITY"):
            self.load()

    def test_required_envelope_values_reject_missing_injected_or_wrong_values(self):
        for key, value in (("UAART_RUN_ID", ""), ("UAART_TRANSACTION_ID", "a\nb"),
                           ("UAART_REQUEST_SHA256", "0" * 64), ("UAART_OPERATION", "execute"),
                           ("UAART_RECEIPT_PATH", "state/receipts/other.json"),
                           ("UAART_BACKUP_RECEIPT_PATH", c.RECEIPT_REL)):
            with self.subTest(key=key):
                previous = self.env[key]
                self.env[key] = value
                with self.assertRaises(c.ContractError):
                    self.load()
                self.env[key] = previous

    def test_noncanonical_sha_not_normalized(self):
        self.env["UAART_MANIFEST_SHA256"] = self.env["UAART_MANIFEST_SHA256"].upper()
        with self.assertRaisesRegex(c.ContractError, "SHA256_INVALID"):
            self.load()

    def test_exact_manifest_canonical_hash_is_independent_of_formatting(self):
        import json
        self.write(c.MANIFEST_REL, json.dumps(self.manifest, indent=4).encode())
        self.assertEqual(self.env["UAART_MANIFEST_SHA256"], self.load().manifest_sha256)

    def test_changed_manifest_requires_new_authority_binding(self):
        self.manifest["operations"][0]["expected_after_sha256"] = "e" * 64
        self.write(c.MANIFEST_REL, c.canonical_json(self.manifest))
        with self.assertRaisesRegex(c.ContractError, "MANIFEST_HASH_MISMATCH"):
            self.load()

    def test_plain_tz_approval_is_not_production_authority(self):
        raw = "Утверждаю ТЗ UA-ART-CRM-DELETE-RECOVERY-002 v1.0".encode()
        self.write(c.APPROVAL_REL, raw)
        self.request["critical"]["owner_approval_sha256"] = c.sha(raw)
        raw_request = c.canonical_json(self.request)
        self.write(c.REQUEST_REL, raw_request)
        self.env["UAART_REQUEST_SHA256"] = c.sha(raw_request)
        with self.assertRaisesRegex(c.ContractError, "JSON_INVALID:owner_approval"):
            self.load()

    def test_each_authority_boolean_and_identity_is_strict(self):
        for key, value in (("owner_authorized", 1), ("production_allowed", "true"),
                           ("authorized_environment", "test"), ("task_id", c.PARENT_TASK_ID),
                           ("request_path", "tasks/requests/other.json")):
            with self.subTest(key=key):
                old = self.approval[key]
                self.approval[key] = value
                self.sync()
                with self.assertRaisesRegex(c.ContractError, "STRUCTURED_INSTALLATION_AUTHORITY"):
                    self.load()
                self.approval[key] = old
        self.sync()

    def test_gate_b_boolean_cannot_be_inferred_from_approval(self):
        self.request["critical"]["gate_b_authorized"] = False
        self.sync()
        with self.assertRaisesRegex(c.ContractError, "STRUCTURED_INSTALLATION_AUTHORITY"):
            self.load()

    def test_owner_approval_subject_binds_fields_beyond_manifest(self):
        self.request["http_checks"] = {"installed": [{"url": "https://www.uaart.com.ua/", "status": 500}]}
        changed = c.canonical_json(self.request)
        self.write(c.REQUEST_REL, changed)
        self.env["UAART_REQUEST_SHA256"] = c.sha(changed)
        with self.assertRaisesRegex(c.ContractError, "OWNER_APPROVAL_REQUEST_SUBJECT_BINDING"):
            self.load()

    def test_custom_approval_fields_cannot_violate_existing_control_plane_schema(self):
        self.approval["installation_policy_sha256"] = self.policy
        self.sync()
        with self.assertRaisesRegex(c.ContractError, "STRUCTURED_INSTALLATION_AUTHORITY"):
            self.load()

    def test_policy_release_and_scope_are_bound_in_all_documents(self):
        for document in (self.manifest,):
            for field in ("package_manifest_sha256", "installation_policy_sha256", "acceptance_scope"):
                with self.subTest(document=document is self.manifest, field=field):
                    old = document[field]
                    document[field] = "f" * 64
                    self.sync()
                    with self.assertRaisesRegex(c.ContractError, "INSTALLATION_POLICY_BINDING"):
                        self.load()
                    document[field] = old
        self.sync()

    def test_source_hash_drift_and_undeclared_python_fail_before_result(self):
        path = self.root / self.execution["dependency_paths"][0]
        original = path.read_bytes()
        path.write_bytes(original + b"CHANGED = True\n")
        with self.assertRaisesRegex(c.ContractError, "EXECUTABLE_HASH_MISMATCH"):
            self.load()
        path.write_bytes(original)
        self.write(c.PACKAGE_REL + "/hidden.py", b"EXTRA = True\n")
        with self.assertRaisesRegex(c.ContractError, "PACKAGE_PYTHON_CLOSURE"):
            self.load()

    def test_bytecode_and_symlinks_are_not_hidden_dependencies(self):
        path = self.write(c.PACKAGE_REL + "/module.pyc", b"not-code")
        with self.assertRaisesRegex(c.ContractError, "PACKAGE_IMPORT_ARTIFACT"):
            self.load()
        path.unlink()
        path.symlink_to(self.root / c.REQUEST_REL)
        with self.assertRaisesRegex(c.ContractError, "PACKAGE_IMPORT_ARTIFACT"):
            self.load()

    def test_preexisting_or_symlink_receipt_never_overwritten(self):
        path = self.write(c.BACKUP_RECEIPT_REL, b"existing")
        with self.assertRaisesRegex(c.ContractError, "RECEIPT_PREEXISTING"):
            self.load()
        path.unlink()
        path.symlink_to(self.root / "missing")
        with self.assertRaisesRegex(c.ContractError, "REPO_PATH_SYMLINK"):
            self.load()

    def test_parent_directory_symlink_cannot_escape_evidence_scope(self):
        directory = self.root / "state"
        directory.symlink_to(self.root / "tasks", target_is_directory=True)
        with self.assertRaisesRegex(c.ContractError, "REPO_PATH_SYMLINK"):
            self.load()

    def test_duplicate_json_keys_are_rejected_even_with_matching_sha(self):
        raw = b'{"task_id":"ignored","task_id":"' + c.TASK_ID.encode() + b'"}'
        self.write(c.REQUEST_REL, raw)
        self.env["UAART_REQUEST_SHA256"] = c.sha(raw)
        with self.assertRaisesRegex(c.ContractError, "JSON_DUPLICATE_KEY"):
            self.load()

    def test_execute_and_rollback_require_exact_prior_backup_receipt(self):
        self.set_operation("execute")
        self.assertEqual("execute", self.load("execute").operation)
        self.env["UAART_BACKUP_MANIFEST_SHA256"] = "f" * 64
        with self.assertRaisesRegex(c.ContractError, "BACKUP_RECEIPT_BINDING"):
            self.load("execute")

    def test_backup_receipt_boolean_zero_and_extra_keys_refuse(self):
        self.set_operation("rollback")
        path = self.root / c.BACKUP_RECEIPT_REL
        receipt = c.decode_object(path.read_bytes(), "test")
        receipt["unexpected_changes"] = False
        path.write_bytes(c.canonical_json(receipt))
        with self.assertRaisesRegex(c.ContractError, "BACKUP_RECEIPT_UNEXPECTED_CHANGES"):
            self.load("rollback")
        receipt["unexpected_changes"] = 0
        receipt["unrecognized"] = True
        path.write_bytes(c.canonical_json(receipt))
        with self.assertRaisesRegex(c.ContractError, "BACKUP_RECEIPT_SCHEMA"):
            self.load("rollback")

    def test_inspection_matches_prohibited_calls_without_running_them(self):
        path = self.execution["dependency_paths"][0]
        raw = b"eval('untrusted')\n"
        self.write(path, raw)
        self.execution["file_sha256"][path] = c.sha(raw)
        self.sync()
        with self.assertRaisesRegex(c.ContractError, "PYTHON_DENIED_CALL"):
            self.load()

    def test_gate_a_skips_failures_or_empty_pass_cannot_become_tests_pass(self):
        for key, value in (("passed", 0), ("failed", 1), ("skipped", 1), ("passed", True)):
            with self.subTest(key=key, value=value):
                previous = self.gate["test_evidence"][key]
                self.gate["test_evidence"][key] = value
                self.sync()
                with self.assertRaisesRegex(c.ContractError, "GATE_A_TEST_CLOSURE"):
                    self.load()
                self.gate["test_evidence"][key] = previous
        self.sync()

    def test_gate_a_test_source_closure_is_exact(self):
        gate = copy.deepcopy(self.gate)
        gate["test_evidence"]["dependency_sha256"] = "0" * 64
        raw = c.canonical_json(gate)
        self.write(c.GATE_A_REL, raw)
        self.request["critical"]["gate_a_sha256"] = c.sha(raw)
        self.approval["gate_a_sha256"] = c.sha(raw)
        self.approval["request_subject_sha256"] = c.request_authorization_sha256(self.request)
        approved = c.canonical_json(self.approval)
        self.write(c.APPROVAL_REL, approved)
        self.request["critical"]["owner_approval_sha256"] = c.sha(approved)
        requested = c.canonical_json(self.request)
        self.write(c.REQUEST_REL, requested)
        self.env["UAART_REQUEST_SHA256"] = c.sha(requested)
        with self.assertRaisesRegex(c.ContractError, "GATE_A_TEST_CLOSURE"):
            self.load()


class ReceiptTests(ContractFixture):
    def make_result(self, operation):
        digest = lambda name: c.sha(("synthetic-" + name).encode())
        release = {"format": 1, "task": c.PARENT_TASK_ID + "-v1.0", "root": "/home/Carix",
            "supervisor": {"id": 266084, "command": "python3.10 /home/Carix/start_safe.py"},
            "application_schema_sha256": digest("schema"),
            "deletion_schema": {"payload": "schema.py", "sha256": c.sha(self.schema_source_text.encode())},
            "files": [{"destination": "cars_ui.py", "before_sha256": digest("cars-before"),
                       "payload_sha256": digest("cars-after")},
                      {"destination": "ua_delete_runtime.py", "before_sha256": None,
                       "payload_sha256": digest("helper")}],
            "source_guards": {name: digest(name) for name in
                              ("db.py", "run_all.py", "start_safe.py", "publication_fence.py")},
            "route_patch": {"destination": "/var/www/www_uaart_com_ua_wsgi.py",
                            "before_sha256": digest("wsgi-before"), "payload_sha256": digest("wsgi-after")},
            "runtime_config": {"destination": "ua_crm_deletion_state/runtime.json",
                               "before_sha256": None, "payload_sha256": digest("runtime-config")}}
        package_raw = c.canonical_json(release)
        self.package = c.sha(package_raw)
        for document in (self.request, self.manifest):
            document["package_manifest_sha256"] = self.package
        checks = {"installed": [{"url": "https://www.uaart.com.ua/video/UA-0002.html", "status": 410}],
                  "baseline": [{"url": "https://www.uaart.com.ua/video/katalog.html", "status": 200,
                                "body_sha256": digest("catalog")} ]}
        self.request["http_checks"] = checks
        self.sync()
        code_files = {item["destination"]: item["before_sha256"] for item in release["files"]}
        code_files.update(release["source_guards"])
        code_files[release["runtime_config"]["destination"]] = None
        code_manifest = {"package_sha256": self.package, "database_file": "crm.snapshot.db",
            "database_sha256": digest("database-snapshot"), "database_logical_sha256": digest("database-logical"),
            "database_integrity": "ok", "files": {
                name: {"sha256": value, "stored": str(index) + ".before" if value is not None else None,
                       "mode": 0o644 if value is not None else None}
                for index, (name, value) in enumerate(code_files.items())}}
        code_sha = c.sha(c._package_json(code_manifest))
        composite = {"format": 1, "package_manifest_sha256": self.package,
            "transaction_id": self.env["UAART_TRANSACTION_ID"], "code_backup_manifest_sha256": code_sha,
            "wsgi_before_sha256": release["route_patch"]["before_sha256"],
            "wsgi_destination": release["route_patch"]["destination"], "wsgi_backup_mode": 0o644}
        backup_sha = c.sha(c._package_json(composite))
        envelope = self.load()
        if operation != "backup":
            receipt = dict(envelope.bindings, backup_manifest_sha256=backup_sha,
                schema_version=c.BACKUP_RECEIPT_SCHEMA, operation="backup", status="PASS", backup="PASS", unexpected_changes=0)
            self.write(c.BACKUP_RECEIPT_REL, c.canonical_json(receipt))
            self.env.update(UAART_OPERATION=operation, UAART_BACKUP_MANIFEST_SHA256=backup_sha,
                            UAART_RECEIPT_PATH=c.RECEIPT_REL if operation == "execute" else c.ROLLBACK_RECEIPT_REL)
            if operation == "rollback":
                self.env["UAART_ROLLBACK_RECEIPT_PATH"] = c.ROLLBACK_RECEIPT_REL
            envelope = self.load(operation)
        field = "payload_sha256" if operation == "execute" else "before_sha256"
        files = {item["destination"]: item[field] for item in release["files"]}
        files[release["route_patch"]["destination"]] = release["route_patch"][field]
        if operation == "execute":
            files[release["runtime_config"]["destination"]] = release["runtime_config"]["payload_sha256"]
        http = [dict(item, body_sha256=item.get("body_sha256", digest("http-body")), observed_epoch=100)
                for item in checks["installed" if operation == "execute" else "baseline"]]
        result = {"schema_version": c.REMOTE_RESULT_SCHEMA, "status": "PASS",
            "execution_origin": "LIVE_REMOTE_READBACK", "safe_to_stop": True,
            "operation": operation, "task_id": c.TASK_ID, "parent_task_id": c.PARENT_TASK_ID,
            "scope": c.RECEIPT_SCOPE, "live_telegram_action_verified": False,
            "phase_status": {"backup": "BACKUP_VERIFIED", "execute": "COMPLETE", "rollback": "ROLLED_BACK"}[operation],
            "workflow_run_id": envelope.run_id, "transaction_id": envelope.transaction_id,
            "request_sha256": envelope.request_sha256, "manifest_sha256": envelope.manifest_sha256,
            "package_manifest_sha256": self.package, "installation_policy_sha256": self.policy,
            "context_sha256": digest("context"), "unexpected_changes": 0, "backup_manifest_sha256": backup_sha,
            "proofs": {"package_manifest_text": package_raw.decode(), "schema_source_text": self.schema_source_text,
                "backup": {"manifest": composite, "manifest_sha256": backup_sha,
                    "code_manifest": code_manifest, "code_manifest_sha256": code_sha,
                    "database": {"snapshot_sha256": code_manifest["database_sha256"],
                        "logical_sha256": code_manifest["database_logical_sha256"], "integrity": "ok", "wal_coherent": True},
                    "durable": True, "files_verified": True},
                "files": {"expected_sha256": dict(files), "observed_sha256": dict(files),
                    "guarded_expected_sha256": dict(release["source_guards"]),
                    "guarded_observed_sha256": dict(release["source_guards"])},
                "preservation": {"crm_logical_before": code_manifest["database_logical_sha256"],
                    "crm_logical_after": code_manifest["database_logical_sha256"], "public_or_media_writes": 0,
                    "database_restored": False, "code_only": True,
                    "application_schema_sha256": release["application_schema_sha256"], "database_integrity": "ok",
                    "deletion_schema_projection": self.deletion_schema if operation != "backup" else dict.fromkeys(sorted(c.DELETION_TABLES)),
                    "deletion_schema_sha256": c.sha(c.canonical_json(self.deletion_schema if operation != "backup" else dict.fromkeys(sorted(c.DELETION_TABLES))))},
                "runtime": {"status": "RUNTIME_RUNNING" if operation == "execute" else "BASELINE_PROCESS_RUNNING",
                    "pid": 120, "start_ticks": "300", "live_telegram_action_verified": False,
                    "config_sha256": release["runtime_config"]["payload_sha256"]},
                "http": http, "crm_resume": {"id": 266084, "enabled": True, "state": "Running"}}}
        if operation == "execute":
            result["proofs"]["rollback_readiness"] = {"status": "PASS",
                "scope": "BACKUP_AND_CODE_RESTORE_READINESS_VERIFIED", "backup_manifest_sha256": backup_sha,
                "code_backup_manifest_sha256": code_sha, "deletion_state_counts": dict.fromkeys(sorted(c.DELETION_TABLES), 0),
                "code_restore_performed": False, "database_restored": False, "checked_epoch": 100}
        return envelope, result

    def test_backup_maps_to_exact_existing_receipt_keys_and_writes_nothing(self):
        envelope, result = self.make_result("backup")
        receipt = c.receipt_from_result(envelope, result)
        self.assertEqual(c.BACKUP_RECEIPT_KEYS, set(receipt))
        self.assertEqual("PASS", receipt["backup"])
        self.assertFalse(envelope.receipt_path.exists())

    def test_rollback_maps_to_exact_existing_receipt_keys(self):
        envelope, result = self.make_result("rollback")
        receipt = c.receipt_from_result(envelope, result)
        self.assertEqual(c.ROLLBACK_RECEIPT_KEYS, set(receipt))
        self.assertEqual("ROLLED_BACK", receipt["status"])
        self.assertTrue(receipt["crm_unchanged"])

    def test_execute_finishes_only_child_and_explicitly_leaves_parent_pending(self):
        envelope, result = self.make_result("execute")
        receipt = c.receipt_from_result(envelope, result)
        self.assertEqual(c.TASK_ID, receipt["task_id"])
        self.assertEqual("FINISHED", receipt["status"])
        self.assertEqual(c.RECEIPT_SCOPE, receipt["receipt_scope"])
        self.assertEqual(c.PARENT_PENDING, receipt["parent_status"])
        self.assertFalse(receipt["live_telegram_action_verified"])

    def test_pass_word_mock_origin_or_partial_state_never_produces_receipt(self):
        envelope, result = self.make_result("backup")
        with self.assertRaises(c.ContractError):
            c.receipt_from_result(envelope, {"status": "PASS"})
        for key, value in (("execution_origin", "FIXTURE"), ("status", "FAIL"),
                           ("safe_to_stop", 1), ("phase_status", "PREPARED"),
                           ("unexpected_changes", False), ("live_telegram_action_verified", True)):
            with self.subTest(key=key):
                changed = dict(result, **{key: value})
                with self.assertRaises(c.ContractError):
                    c.receipt_from_result(envelope, changed)

    def test_independent_workflow_and_release_identities_are_required(self):
        envelope, result = self.make_result("execute")
        for key in ("workflow_run_id", "transaction_id", "request_sha256", "manifest_sha256",
                    "package_manifest_sha256", "installation_policy_sha256", "backup_manifest_sha256"):
            with self.subTest(key=key):
                changed = dict(result, **{key: "0" * 64})
                with self.assertRaises(c.ContractError):
                    c.receipt_from_result(envelope, changed)

    def test_each_backup_readback_proof_is_required(self):
        envelope, result = self.make_result("backup")
        mutations = [(("durable",), False), (("files_verified",), False),
                     (("database", "wal_coherent"), False), (("database", "integrity"), "corrupt"),
                     (("database", "snapshot_sha256"), "0" * 64), (("manifest", "transaction_id"), "wrong"),
                     (("code_manifest", "database_logical_sha256"), "0" * 64)]
        for keys, value in mutations:
            with self.subTest(keys=keys):
                changed = copy.deepcopy(result)
                target = changed["proofs"]["backup"]
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = value
                with self.assertRaises(c.ContractError):
                    c.receipt_from_result(envelope, changed)

    def test_changing_both_claimed_expected_and_observed_code_still_fails_pinned_release(self):
        envelope, result = self.make_result("execute")
        for kind in ("expected_sha256", "observed_sha256"):
            result["proofs"]["files"][kind]["cars_ui.py"] = "f" * 64
        with self.assertRaisesRegex(c.ContractError, "EXACT_CODE_READBACK"):
            c.receipt_from_result(envelope, result)

    def test_protected_source_drift_is_not_hidden_by_successful_install(self):
        envelope, result = self.make_result("execute")
        result["proofs"]["files"]["guarded_observed_sha256"]["db.py"] = "0" * 64
        with self.assertRaisesRegex(c.ContractError, "EXACT_PROTECTED_READBACK"):
            c.receipt_from_result(envelope, result)

    def test_database_restore_or_media_write_or_lost_crm_edit_forbids_rollback_pass(self):
        envelope, result = self.make_result("rollback")
        for key, value in (("database_restored", True), ("public_or_media_writes", 1),
                           ("code_only", False), ("crm_logical_after", "0" * 64)):
            with self.subTest(key=key):
                changed = copy.deepcopy(result)
                changed["proofs"]["preservation"][key] = value
                with self.assertRaisesRegex(c.ContractError, "PRESERVATION_NOT_PROVEN"):
                    c.receipt_from_result(envelope, changed)

    def test_code_rollback_can_preserve_legitimate_newer_crm_edits(self):
        envelope, result = self.make_result("rollback")
        result["proofs"]["preservation"].update(crm_logical_before="a" * 64, crm_logical_after="a" * 64)
        self.assertEqual("ROLLED_BACK", c.receipt_from_result(envelope, result)["status"])

    def test_http_redirects_wrong_body_or_missing_runtime_resume_refuse(self):
        envelope, result = self.make_result("backup")
        changes = [("http", [{"url": "https://www.uaart.com.ua/video/katalog.html", "status": 302,
                              "body_sha256": "a" * 64, "observed_epoch": 100}]),
                   ("crm_resume", {"id": 266084, "enabled": False, "state": "Stopped"}),
                   ("runtime", {"status": "BASELINE_PROCESS_RUNNING", "pid": True, "start_ticks": 20,
                                "live_telegram_action_verified": False})]
        for key, value in changes:
            with self.subTest(key=key):
                changed = copy.deepcopy(result)
                changed["proofs"][key] = value
                with self.assertRaises(c.ContractError):
                    c.receipt_from_result(envelope, changed)

    def test_receipt_created_after_load_is_never_reused(self):
        envelope, result = self.make_result("backup")
        self.write(c.BACKUP_RECEIPT_REL, b"already-created")
        with self.assertRaisesRegex(c.ContractError, "RECEIPT_PREEXISTING"):
            c.receipt_from_result(envelope, result)

    def test_database_digest_scope_cannot_be_a_whole_file_claim(self):
        self.manifest["operations"][1]["digest_scope"] = "file_bytes"
        self.sync()
        with self.assertRaisesRegex(c.ContractError, "EXACT_SQLITE_SCHEMA_OPERATION"):
            self.load()

    def test_partial_wrong_or_mislabelled_schema_cannot_be_install_success(self):
        envelope, result = self.make_result("execute")
        for projection in ({}, dict.fromkeys(sorted(c.DELETION_TABLES)),
                           dict(self.deletion_schema, ua_delete_jobs=None),
                           dict(self.deletion_schema, ua_delete_jobs="CREATE TABLE ua_delete_jobs (changed TEXT)")):
            with self.subTest(projection=projection):
                changed = copy.deepcopy(result)
                changed["proofs"]["preservation"]["deletion_schema_projection"] = projection
                changed["proofs"]["preservation"]["deletion_schema_sha256"] = c.sha(c.canonical_json(projection))
                with self.assertRaises(c.ContractError):
                    c.receipt_from_result(envelope, changed)

    def test_schema_source_must_match_pinned_release_without_import(self):
        envelope, result = self.make_result("execute")
        result["proofs"]["schema_source_text"] += "SIDE_EFFECT = True\n"
        with self.assertRaisesRegex(c.ContractError, "SCHEMA_SOURCE_PROOF_HASH"):
            c.receipt_from_result(envelope, result)

    def test_durable_intent_or_missing_readiness_forbids_generic_rollback_pass(self):
        envelope, result = self.make_result("execute")
        changed = copy.deepcopy(result)
        del changed["proofs"]["rollback_readiness"]
        with self.assertRaisesRegex(c.ContractError, "rollback_readiness"):
            c.receipt_from_result(envelope, changed)
        result["proofs"]["rollback_readiness"]["deletion_state_counts"]["ua_delete_intents"] = 1
        with self.assertRaisesRegex(c.ContractError, "INTENT_AWARE_ROLLBACK_READINESS"):
            c.receipt_from_result(envelope, result)


class RealProducerInteropTests(ContractFixture):
    """Actual worker/phase proofs over SQLite WAL, files and flock.

    Authority, provider, process startup and HTTP are explicitly local fakes.
    These tests establish producer/consumer interoperability, not production
    acceptance. Runtime implementation imports remain inside the declared package.
    """

    def setUp(self):
        super().setUp()
        self.env["UAART_TRANSACTION_ID"] = "tx-fixture01234567890123456789"
        import package_install
        import lifecycle_worker
        import remote_worker
        self.install, self.worker_module, self.phase_module = package_install, lifecycle_worker, remote_worker
        self.live_root, self.stage = self.root / "fixture-production", self.root / "fixture-package"
        self.live_root.mkdir(mode=0o700)
        self.stage.mkdir(mode=0o700)
        originals = {name: ("ORIGINAL = " + repr(name) + "\n").encode() for name in
                     ("cars_ui.py", "publikaciya.py", "db.py", "run_all.py", "start_safe.py", "publication_fence.py")}
        for name, raw in originals.items():
            (self.live_root / name).write_bytes(raw)
        for name in (".start_safe.singleton.lock", ".ua_art_publish_transaction.lock"):
            (self.live_root / name).touch(mode=0o600)
        self.database = sqlite3.connect(self.live_root / "crm.db")
        self.addCleanup(self.database.close)
        self.database.execute("PRAGMA journal_mode=WAL")
        self.database.execute("PRAGMA wal_autocheckpoint=0")
        self.database.execute("CREATE TABLE cars(id INTEGER PRIMARY KEY, price INTEGER)")
        self.database.execute("INSERT INTO cars VALUES(8, 12000)")
        self.database.commit()
        (self.stage / "schema.py").write_text(self.schema_source_text)
        release = {"format": 1, "task": c.PARENT_TASK_ID + "-v1.0", "root": "/home/Carix",
            "supervisor": {"id": 266084, "command": "python3.10 /home/Carix/start_safe.py"},
            "application_schema_sha256": package_install.application_schema(self.database),
            "deletion_schema": {"payload": "schema.py", "sha256": c.sha(self.schema_source_text.encode())},
            "source_guards": {name: c.sha(originals[name]) for name in
                              ("db.py", "run_all.py", "start_safe.py", "publication_fence.py")}, "files": []}
        for name, role in (("cars_ui.py", "entrypoint"), ("publikaciya.py", "writer"), ("ua_delete_runtime.py", "helper")):
            raw = ("INSTALLED = " + repr(name) + "\n").encode()
            payload = "payload-" + name
            (self.stage / payload).write_bytes(raw)
            release["files"].append({"destination": name, "before_sha256": c.sha(originals[name]) if name in originals else None,
                "payload": payload, "payload_sha256": c.sha(raw), "role": role})
        config = package_install.encoded({"version": 1, "application_schema_sha256": release["application_schema_sha256"],
            "source_sha256": release["source_guards"], "shared": {}, "shared_routes": {},
            "direct_route_prefixes": {"video": [], "site": []}, "writers_receipt_sha256": "c" * 64})
        (self.stage / "runtime.json").write_bytes(config)
        release["runtime_config"] = {"destination": "ua_crm_deletion_state/runtime.json", "payload": "runtime.json",
                                     "payload_sha256": c.sha(config), "before_sha256": None}
        self.wsgi_path = self.live_root / "fixture_wsgi.py"
        self.wsgi_path.write_bytes(b"BASELINE_WSGI = True\n")
        (self.stage / "wsgi.py").write_bytes(b"INSTALLED_WSGI = True\n")
        release["route_patch"] = {"destination": "/var/www/www_uaart_com_ua_wsgi.py",
            "before_sha256": c.sha(self.wsgi_path.read_bytes()), "payload": "wsgi.py",
            "payload_sha256": c.sha((self.stage / "wsgi.py").read_bytes()), "role": "route"}
        package_raw = package_install.encoded(release)
        (self.stage / "manifest.json").write_bytes(package_raw)
        for entry in self.stage.iterdir():
            entry.chmod(0o600)
        self.package = c.sha(package_raw)
        self.real_package = package_install.Package(self.stage, self.package)
        self.worker = lifecycle_worker.InstallWorker(self.real_package, allowed_python_sha256=(),
            root=self.live_root, wsgi_path=self.wsgi_path, inventory=lambda: [],
            transaction_id=self.env["UAART_TRANSACTION_ID"])
        self.worker.pre_pause_namespace = mock.Mock(return_value={"status": "CRM_NAMESPACE_VERIFIED", "pid": 9001})
        self.worker.startup = mock.Mock(side_effect=lambda **kw: {
            "status": "RUNTIME_RUNNING" if kw["installed"] else "BASELINE_PROCESS_RUNNING",
            "pid": 9001, "start_ticks": 1001, "config_sha256": release["runtime_config"]["payload_sha256"],
            "live_telegram_action_verified": False})
        for document in (self.request, self.manifest):
            document["package_manifest_sha256"] = self.package
        checks = [{"url": "https://www.uaart.com.ua/video/katalog.html", "status": 200, "body_sha256": "d" * 64}]
        self.request["http_checks"] = {"installed": copy.deepcopy(checks), "baseline": copy.deepcopy(checks)}
        self.request["title"] = "Local fixture installation child"
        self.sync()

    def runner(self, operation, backup_sha=None):
        self.env["UAART_OPERATION"] = operation
        paths = {"backup": c.BACKUP_RECEIPT_REL, "execute": c.RECEIPT_REL, "rollback": c.ROLLBACK_RECEIPT_REL}
        self.env["UAART_RECEIPT_PATH"] = paths[operation]
        if backup_sha is not None:
            self.env["UAART_BACKUP_MANIFEST_SHA256"] = backup_sha
        if operation == "rollback":
            self.env["UAART_ROLLBACK_RECEIPT_PATH"] = c.ROLLBACK_RECEIPT_REL
        envelope = self.load(operation)
        phase_root = self.root / ("actual-phase-" + operation)
        phase_root.mkdir(mode=0o700)
        identity = {"task_id": c.TASK_ID, "workflow_run_id": envelope.run_id,
            "transaction_id": envelope.transaction_id, "request_sha256": envelope.request_sha256,
            "manifest_sha256": envelope.manifest_sha256, "operation": operation}
        context_path = phase_root / "context.json"
        context_path.write_bytes(self.phase_module.wire_encoded(identity))
        plan = {"package_manifest_sha256": self.package, "installation_policy_sha256": self.policy,
                "http_checks": self.request["http_checks"]}
        transport = SimpleNamespace(root=phase_root, path=context_path, sha256=c.sha(context_path.read_bytes()),
            operation=operation, backup_sha256=backup_sha, manifest_path=self.stage / "manifest.json", plan=plan,
            value=identity, identity=lambda: dict(identity), revalidate=lambda: None)
        watcher = {"owner_pid": 999991, "start_ticks": 123, "pgid": 999991,
                   "result_path": str(phase_root / "watchdog-terminal.json")}

        class Provider:
            def __init__(self):
                self.enabled = True
                self.effects = []

            def supervisor(self):
                return {"id": 266084, "enabled": self.enabled, "state": "Running" if self.enabled else "Stopped"}

            def set_enabled(self, enabled):
                self.effects.append(("enabled", enabled))
                self.enabled = enabled
                return self.supervisor()

            def reload(self):
                self.effects.append(("reload",))

        api = Provider()
        admission = SimpleNamespace(check=lambda **kw: {"status": "EXISTING_AUTHORITY_PASS"})
        runner = self.phase_module.PhaseRunner(transport=transport, watchdog_context=watcher,
            watchdog_sha256=c.sha(self.install.encoded(watcher)), plan=plan, admission=admission,
            api=api, worker=self.worker, watchdog_ready=lambda: True, inventory=lambda *args: {},
            probe=lambda plan, installed: [dict(item, observed_epoch=1234567890)
                for item in plan["http_checks"]["installed" if installed else "baseline"]])
        return envelope, runner

    @staticmethod
    def validator(name):
        # Exercise the actual repository validators, which are side-effect-free
        # modules. They are never imported by the production controller.
        path = Path(__file__).resolve().parents[3] / "automation" / (name + ".py")
        specification = importlib.util.spec_from_file_location("_crm_contract_test_" + name, path)
        module = importlib.util.module_from_spec(specification)
        sys.modules[specification.name] = module
        specification.loader.exec_module(module)
        return module

    def validate_existing_auxiliary(self, envelope, receipt):
        existing = self.validator("execution_contract")
        specification = SimpleNamespace(task_id=c.TASK_ID, request_sha256=envelope.request_sha256,
            critical_manifest_sha256=envelope.manifest_sha256, backup_receipt_path=c.BACKUP_RECEIPT_REL,
            rollback_receipt_path=c.ROLLBACK_RECEIPT_REL)
        self.write(envelope.values["UAART_RECEIPT_PATH"], c.canonical_json(receipt))
        with mock.patch.object(existing, "ROOT", self.root), mock.patch.dict("os.environ", self.env):
            verified = existing.validate_backup_receipt(specification) if envelope.operation == "backup" else existing.validate_rollback_receipt(specification)
        self.assertEqual(receipt, verified)

    def test_actual_three_phase_proofs_interoperate_with_existing_receipt_validators(self):
        envelope, runner = self.runner("backup")
        result = runner.run()
        self.assertEqual("PASS", result["status"])
        receipt = c.receipt_from_result(envelope, result)
        self.validate_existing_auxiliary(envelope, receipt)
        backup_sha = receipt["backup_manifest_sha256"]
        backup = result["proofs"]["backup"]
        self.assertEqual(3, len({backup_sha, backup["code_manifest_sha256"], backup["database"]["snapshot_sha256"]}))
        self.assertEqual(backup_sha, c.sha(self.install.encoded(backup["manifest"])))
        self.assertEqual(backup["code_manifest_sha256"], c.sha(self.install.encoded(backup["code_manifest"])))
        original_snapshot = (self.worker.transaction.folder / "crm.snapshot.db").read_bytes()
        self.assertEqual([("enabled", False), ("reload",), ("enabled", True)], runner.api.effects)

        envelope, runner = self.runner("execute", backup_sha)
        result = runner.run()
        self.assertEqual("PASS", result["status"])
        receipt = c.receipt_from_result(envelope, result)
        critical = self.validator("critical_adapter")
        flat = dict(envelope.request)
        flat.update(envelope.request["critical"])
        critical_request = critical.CriticalRequest.from_mapping(flat)
        self.assertEqual(receipt, critical.validate_final_receipt(critical_request, receipt))
        self.assertEqual(receipt, self.validator("task_orchestrator").validate_receipt(receipt))
        self.assertEqual("PASS", receipt["rollback"])
        self.assertFalse(receipt["rollback_performed"])
        self.assertEqual(c.PARENT_PENDING, receipt["parent_status"])
        self.assertEqual(self.deletion_schema, result["proofs"]["preservation"]["deletion_schema_projection"])
        self.assertEqual(original_snapshot, (self.worker.transaction.folder / "crm.snapshot.db").read_bytes())

        self.database.execute("UPDATE cars SET price=19900 WHERE id=8")
        self.database.commit()
        envelope, runner = self.runner("rollback", backup_sha)
        result = runner.run()
        self.assertEqual("PASS", result["status"])
        receipt = c.receipt_from_result(envelope, result)
        self.validate_existing_auxiliary(envelope, receipt)
        self.assertEqual(19900, self.database.execute("SELECT price FROM cars WHERE id=8").fetchone()[0])
        self.assertEqual(self.deletion_schema, result["proofs"]["preservation"]["deletion_schema_projection"])
        self.assertTrue((self.live_root / "ua_crm_deletion_state/runtime.json").is_file())
        self.assertEqual(original_snapshot, (self.worker.transaction.folder / "crm.snapshot.db").read_bytes())
        self.assertFalse(result["proofs"]["preservation"]["database_restored"])


if __name__ == "__main__":
    unittest.main()
