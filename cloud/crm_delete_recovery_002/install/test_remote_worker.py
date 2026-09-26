"""Offline boundaries plus real SQLite/files/locks; provider/HTTP/processes fake."""
from contextlib import contextmanager
import copy
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import remote_worker as remote
from package_install import encoded, sha, atomic
from lifecycle_worker import InstallWorker
import test_lifecycle as lifecycle_fixture
import test_package_install as install_fixture


class Interrupted(BaseException):
    pass


class Admission:
    def __init__(self):
        self.calls = []
        self.reject_at = None

    def check(self, *, operation):
        self.calls.append(operation)
        if len(self.calls) == self.reject_at:
            raise RuntimeError("fixture_admission_rejected")
        return {"status": "EXISTING_AUTHORITY_PASS", "operation": operation}


class PhaseProvider(lifecycle_fixture.Provider):
    def request(self, method, endpoint, fields=None):
        return super().request(method, endpoint)

    def supervisor(self):
        return dict(super().supervisor(), state="Running" if self.enabled else "Stopped")


class RealPhaseTests(unittest.TestCase):
    """Reusable real worker fixture; only external admission/provider are fakes."""
    setUp = install_fixture.InstallTests.setUp
    tearDown = install_fixture.InstallTests.tearDown
    load_package = install_fixture.InstallTests.load_package

    def make_worker(self):
        if hasattr(self, "phase_worker"):
            return self.phase_worker
        lifecycle_fixture.WorkerTests.make_worker(self)
        for path in self.stage.rglob("*"):
            if path.is_file():
                path.chmod(0o600)
        self.phase_worker = InstallWorker(self.package, allowed_python_sha256=(), root=self.root,
            wsgi_path=self.wsgi_path, inventory=lambda: [], transaction_id="tx-fixture01234567890123456789")
        self.phase_worker.pre_pause_namespace = mock.Mock(return_value={"status": "CRM_NAMESPACE_VERIFIED", "pid": 9001})
        self.phase_worker.startup = mock.Mock(side_effect=lambda **kw: {
            "status": "RUNTIME_RUNNING" if kw["installed"] else "BASELINE_PROCESS_RUNNING",
            "pid": 9001, "start_ticks": 1001, "config_sha256": self.package.runtime_config["payload_sha256"],
            "live_telegram_action_verified": False})
        return self.phase_worker

    def make_runner(self, operation, backup_sha=None, *, fault=lambda stage: None):
        worker = self.make_worker()
        phase = self.base / ("phase-" + operation)
        phase.mkdir(mode=0o700)
        api = PhaseProvider()
        plan = dict(lifecycle_fixture.plan_for(api), installation_policy_sha256="f" * 64,
                    package_manifest_sha256=self.package.manifest_sha)
        identity = {"task_id": remote.TASK, "workflow_run_id": "12345", "transaction_id": worker.transaction_id,
                    "request_sha256": "a" * 64, "manifest_sha256": "b" * 64, "operation": operation}
        context_path = phase / "context.json"
        atomic(context_path, remote.wire_encoded(identity))
        transport = SimpleNamespace(root=phase, path=context_path, sha256=sha(context_path.read_bytes()), operation=operation,
            backup_sha256=backup_sha, manifest_path=self.stage / "manifest.json", plan=plan, value=identity,
            identity=lambda: identity.copy(), revalidate=lambda: None)
        watcher = {"owner_pid": os.getpid(), "start_ticks": int(Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()[19]),
                   "pgid": os.getpid(),
                   "result_path": str(phase / "watchdog-terminal.json"), "package_manifest_sha256": self.package.manifest_sha,
                   "lifecycle_plan_path": str(context_path), "lifecycle_plan_sha256": transport.sha256}
        atomic(phase / "watchdog-context.json", encoded(watcher))
        digest = sha((phase / "watchdog-context.json").read_bytes())
        admission = Admission()
        runner = remote.PhaseRunner(transport=transport, watchdog_context=watcher, watchdog_sha256=digest,
            plan=plan, admission=admission, api=api, worker=worker, watchdog_ready=lambda: True,
            probe=lambda plan, installed: [{"url": "https://uaart.com.ua/", "status": 200,
                                           "body_sha256": "d" * 64, "observed_epoch": 1234567890}], fault=fault)
        return runner

    def backup(self):
        runner = self.make_runner("backup")
        result = runner.run()
        self.assertEqual("PASS", result["status"])
        return result["backup_manifest_sha256"]

    def test_backup_then_execute_use_same_original_digest_and_resume_each_phase(self):
        backup_runner = self.make_runner("backup")
        backup = backup_runner.run()
        self.assertEqual("BACKUP_VERIFIED", backup["phase_status"])
        self.assertTrue(backup_runner.api.enabled)
        self.assertEqual([("enabled", False), ("reload",), ("enabled", True)], backup_runner.api.effects)
        original = (self.make_worker().transaction.folder / "crm.snapshot.db").read_bytes()
        execute_runner = self.make_runner("execute", backup["backup_manifest_sha256"])
        execute = execute_runner.run()
        self.assertEqual("PASS", execute["status"])
        self.assertEqual("COMPLETE", execute["phase_status"])
        self.assertEqual(backup["backup_manifest_sha256"], execute["backup_manifest_sha256"])
        self.assertEqual(original, (self.make_worker().transaction.folder / "crm.snapshot.db").read_bytes())
        self.assertTrue(execute_runner.api.enabled)
        self.assertEqual(["execute", "execute"], execute_runner.admission.calls)
        self.assertFalse(execute["live_telegram_action_verified"])
        self.assertIn("package_manifest_text", execute["proofs"])
        self.assertIn("guarded_observed_sha256", execute["proofs"]["files"])

    def test_operator_edit_between_phases_refuses_install_and_preserves_new_data(self):
        digest = self.backup()
        self.conn.execute("UPDATE cars SET price=19900 WHERE id=8")
        self.conn.commit()
        runner = self.make_runner("execute", digest)
        result = runner.run()
        self.assertEqual("FAIL", result["status"])
        self.assertEqual("RESTORED_AFTER_FAILURE", result["phase_status"])
        self.assertTrue(result["safe_to_stop"])
        self.assertTrue(runner.api.enabled)
        self.assertEqual(19900, self.conn.execute("SELECT price FROM cars").fetchone()[0])
        self.assertEqual(self.originals["cars_ui.py"], (self.root / "cars_ui.py").read_bytes())
        self.assertEqual(digest, self.make_worker().verify_existing_backup(digest)["backup_manifest_sha256"])

    def test_rollback_preserves_new_operator_data_and_retained_config(self):
        digest = self.backup()
        self.assertEqual("PASS", self.make_runner("execute", digest).run()["status"])
        self.conn.execute("UPDATE cars SET price=21100 WHERE id=8")
        self.conn.commit()
        runner = self.make_runner("rollback", digest)
        result = runner.run()
        self.assertEqual("PASS", result["status"])
        self.assertEqual("ROLLED_BACK", result["phase_status"])
        self.assertEqual(21100, self.conn.execute("SELECT price FROM cars").fetchone()[0])
        self.assertTrue((self.root / "ua_crm_deletion_state/runtime.json").exists())
        self.assertEqual(self.originals["cars_ui.py"], (self.root / "cars_ui.py").read_bytes())
        evidence = remote.current_evidence(self.make_worker(), installed=False)
        self.assertIn("/var/www/www_uaart_com_ua_wsgi.py", evidence["files"]["observed_sha256"])
        self.assertNotIn("ua_crm_deletion_state/runtime.json", evidence["files"]["observed_sha256"])

    def test_wrong_original_backup_refuses_before_provider_pause(self):
        self.backup()
        runner = self.make_runner("execute", "0" * 64)
        with self.assertRaisesRegex(RuntimeError, "ORIGINAL_PHASE_BACKUP_HASH_MISMATCH"):
            runner.run()
        self.assertEqual([], runner.api.effects)

    def test_namespace_unknown_refuses_before_pause(self):
        runner = self.make_runner("backup")
        runner.worker.pre_pause_namespace.side_effect = RuntimeError("not same host")
        result = runner.run()
        self.assertEqual("FAIL", result["status"])
        self.assertEqual("NOT_STARTED", result["phase_status"])
        self.assertEqual([], runner.api.effects)
        self.assertFalse(runner.worker.transaction.folder.exists())

    def test_fresh_admission_rejected_before_pause_cannot_enter_restore_path(self):
        runner = self.make_runner("backup")
        runner.admission.reject_at = 2
        result = runner.run()
        self.assertEqual("FAIL", result["status"])
        self.assertEqual([], runner.api.effects)

    def test_interrupted_backup_after_snapshot_recovers_without_new_backup(self):
        def fault(stage):
            if stage == "OPERATION_DONE":
                raise Interrupted()
        runner = self.make_runner("backup", fault=fault)
        with self.assertRaises(Interrupted):
            runner.run()
        journal = json.loads(runner.path.read_bytes())
        snapshot = runner.worker.transaction.folder / "crm.snapshot.db"
        original = snapshot.read_bytes()
        runner.fault = lambda stage: None
        with mock.patch.object(runner.worker, "perform_phase", side_effect=AssertionError("must not repeat")):
            result = runner.run(recovery=True)
        self.assertEqual("PASS", result["status"])
        self.assertEqual(journal["backup_manifest_sha256"], result["backup_manifest_sha256"])
        self.assertEqual(original, snapshot.read_bytes())
        self.assertTrue(runner.api.enabled)

    def test_uncertain_resume_recovery_retries_resume_without_reinstall(self):
        digest = self.backup()
        runner = self.make_runner("execute", digest)
        runner.api.timeout_enable_once = True
        with self.assertRaises(RuntimeError):
            runner.run()
        self.assertEqual("RESUME_INTENT", json.loads(runner.path.read_bytes())["stage"])
        with mock.patch.object(runner.worker, "perform_phase", side_effect=AssertionError("must not reinstall")):
            result = runner.run(recovery=True)
        self.assertEqual("PASS", result["status"])
        self.assertTrue(runner.api.enabled)

    def test_restore_proof_failure_still_resumes_but_cannot_emit_pass(self):
        runner = self.make_runner("backup")
        runner.probe = mock.Mock(side_effect=RuntimeError("HTTP fixture fail"))
        result = runner.run()
        self.assertEqual("FAIL", result["status"])
        self.assertEqual("RESTORATION_UNVERIFIED", result["phase_status"])
        self.assertTrue(result["safe_to_stop"])
        self.assertTrue(runner.api.enabled)
        self.assertTrue((runner.root / "completed-backup.json").exists())
        self.assertEqual("RECOVERED", json.loads(runner.terminal_path.read_bytes())["status"])

    def test_failed_resume_does_not_emit_safe_completion(self):
        runner = self.make_runner("backup")
        original = runner.api.set_enabled
        def change(enabled):
            if enabled:
                raise RuntimeError("provider unavailable")
            return original(enabled)
        runner.api.set_enabled = change
        with self.assertRaises(RuntimeError):
            runner.run()
        self.assertFalse((runner.root / "completed-backup.json").exists())
        self.assertFalse(runner.terminal_path.exists())

    def test_terminal_autorestart_replays_exact_receipt_without_effects(self):
        runner = self.make_runner("backup")
        result = runner.run()
        before = (runner.root / "result-backup.json").read_bytes()
        runner.api.effects.clear()
        runner.admission.calls.clear()
        (runner.root / "completed-backup.json").unlink()
        with mock.patch.object(remote, "TransportContext", return_value=runner.transport), \
                mock.patch.object(remote, "checkout_authority", side_effect=AssertionError("no clone")), \
                mock.patch.object(remote, "normalize_credential", side_effect=AssertionError("no credentials")):
            self.assertEqual(0, remote.main(["--context", str(runner.transport.path), "--context-sha256", runner.transport.sha256,
                                             "--operation", "backup"]))
        self.assertEqual([], runner.api.effects)
        self.assertEqual([], runner.admission.calls)
        self.assertEqual(before, (runner.root / "completed-backup.json").read_bytes())
        self.assertEqual(before, remote.receipt_bytes(result))

    def test_global_phase_lock_prevents_second_owner_effects(self):
        first = self.make_runner("backup")
        second = self.make_runner("execute", "1" * 64)
        with first._lock():
            with self.assertRaises(BlockingIOError):
                second.run()
        self.assertEqual([], second.api.effects)

    def test_early_missing_native_credential_emits_idempotent_refusal_without_pause(self):
        runner = self.make_runner("backup")
        with mock.patch.object(remote, "TransportContext", return_value=runner.transport), \
                mock.patch.object(remote, "execute_context", side_effect=RuntimeError("NATIVE_API_TOKEN_MISSING")):
            self.assertEqual(1, remote.main(["--context", str(runner.transport.path), "--context-sha256", runner.transport.sha256,
                                             "--operation", "backup"]))
        result = json.loads((runner.root / "completed-backup.json").read_bytes())
        self.assertEqual("FAIL", result["status"])
        self.assertTrue(result["safe_to_stop"])
        self.assertTrue(result["no_pause_or_write"])
        self.assertEqual([], runner.api.effects)
        before = (runner.root / "completed-backup.json").read_bytes()
        self.assertEqual(result, remote.terminal_reentry(runner.transport))
        self.assertEqual(before, (runner.root / "completed-backup.json").read_bytes())

    def test_prepause_refusal_cannot_close_an_owned_pause(self):
        runner = self.make_runner("backup")
        runner.save(runner.identity(), "PAUSE_INTENT")
        self.assertFalse(remote.prepause_refusal(runner.transport, "fixture"))
        self.assertFalse((runner.root / "completed-backup.json").exists())

    def test_supervisor_restart_cannot_disarm_another_owners_admitted_watchdog(self):
        runner = self.make_runner("backup")
        watcher_path = runner.root / "watchdog-context.json"
        watcher = json.loads(watcher_path.read_bytes())
        watcher["owner_pid"] = os.getpid() + 1000
        atomic(watcher_path, encoded(watcher))
        runner.save(runner.identity(), "ADMITTED")
        self.assertFalse(remote.prepause_refusal(runner.transport, "fixture"))
        self.assertFalse((runner.root / "prepause-refusal.json").exists())
        self.assertFalse(runner.terminal_path.exists())

    def test_partial_install_can_be_rolled_back_in_separate_phase(self):
        digest = self.backup()
        worker = self.make_worker()
        def fault(phase, name):
            if phase == "file_replaced":
                raise Interrupted()
        worker.transaction.fault = fault
        with self.assertRaises(Interrupted):
            worker.apply_existing(digest)
        worker.transaction.fault = lambda phase, name: None
        runner = self.make_runner("rollback", digest)
        result = runner.run()
        self.assertEqual("PASS", result["status"])
        self.assertEqual("ROLLED_BACK", result["phase_status"])
        self.assertTrue(runner.api.enabled)


class InputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.context_path = self.root / "context.json"
        self.files = {}
        for name in remote.SOURCES:
            self.put(name, b"# bound offline fixture\n")
        self.put("package/manifest.json", b'{"format":1}')
        self.plan = {"version": 1, "task_id": remote.TASK, "parent_task_id": remote.PARENT_TASK,
            "acceptance_scope": remote.SCOPE, "installation_policy_sha256": "f" * 64,
            "maximum_seconds": 600, "package_sources": {name: self.files[name] for name in remote.SOURCES},
            "package_manifest_path": "package/manifest.json", "package_manifest_sha256": self.files["package/manifest.json"],
            "authority": {"repository_root": "authority", "source_repository_root": "authority",
                "main_commit": "a" * 40, "code_source_commit": "a" * 40, "request_sha256": "a" * 64,
                "run_id": "12345", "transaction_id": "tx-fixture01234567890123456789"}}
        self.put("plan.json", encoded(self.plan))
        self.value = {"schema": remote.TRANSPORT_SCHEMA, "task_id": remote.TASK, "workflow_run_id": "12345",
            "transaction_id": self.plan["authority"]["transaction_id"], "request_sha256": "a" * 64,
            "manifest_sha256": "b" * 64, "operation": "backup", "stage": str(self.root), "files": self.files,
            "parameters": {"plan_path": str(self.root / "plan.json"), "plan_sha256": self.files["plan.json"],
                           "installation_policy_sha256": "f" * 64, "backup_manifest_sha256": None}}
        self.bind()

    def put(self, name, raw):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        path.write_bytes(raw)
        path.chmod(0o644)  # Uploaded provider files must be hash-checked before normalization.
        self.files[name] = sha(raw)

    def bind(self):
        self.context_path.write_bytes(remote.wire_encoded(self.value))
        self.digest = sha(self.context_path.read_bytes())
        return remote.TransportContext(self.context_path, self.digest, self.value["operation"],
                                       own_source=self.root / "remote_worker.py")

    def test_uploaded_0644_normalized_only_after_hash_verification(self):
        for path in self.root.rglob("*"):
            if path.is_file():
                path.chmod(0o644)
        context = self.bind()
        self.assertEqual(0o600, self.context_path.stat().st_mode & 0o777)
        for path in context.pins:
            self.assertEqual(0o600, path.stat().st_mode & 0o777)
        target = self.root / "lifecycle_worker.py"
        target.write_bytes(b"altered")
        target.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError, "INPUT_HASH_MISMATCH"):
            self.bind()
        self.assertEqual(0o644, target.stat().st_mode & 0o777)

    def test_source_drift_refused_before_effects(self):
        context = self.bind()
        (self.root / "package_install.py").write_bytes(b"changed")
        with self.assertRaisesRegex(RuntimeError, "INPUT_HASH_MISMATCH"):
            context.revalidate()

    def test_plan_path_escape_refused(self):
        self.value["parameters"]["plan_path"] = str(self.root.parent / "elsewhere")
        with self.assertRaises((RuntimeError, FileNotFoundError)):
            self.bind()

    def test_native_credential_is_only_mapped_in_memory(self):
        with mock.patch.dict(os.environ, {"API_TOKEN": "offline-secret-marker"}, clear=True):
            remote.normalize_credential()
            self.assertEqual("offline-secret-marker", os.environ["PYTHONANYWHERE_API_TOKEN"])
            self.assertNotIn("offline-secret-marker", self.context_path.read_text())
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "NATIVE_API_TOKEN_MISSING"):
                remote.normalize_credential()
        with mock.patch.dict(os.environ, {"PYTHONANYWHERE_API_TOKEN": "recovery-only"}, clear=True):
            remote.normalize_credential(recovery=True)

    def test_fixed_public_checkout_has_no_inherited_credentials(self):
        context = self.bind()
        calls = []
        def run(argv, **kwargs):
            calls.append(argv)
            self.assertNotIn("API_TOKEN", kwargs["env"])
            self.assertNotIn("PYTHONANYWHERE_API_TOKEN", kwargs["env"])
            self.assertEqual(90, kwargs["timeout"])
            output = b""
            if "rev-parse" in argv:
                output = b"a" * 40
            elif "get-url" in argv:
                output = remote.ORIGIN.encode()
            elif "ls-remote" in argv:
                output = b"a" * 40 + b"\trefs/heads/main\n"
            return SimpleNamespace(returncode=0, stdout=output)
        plan = remote.checkout_authority(context, run=run)
        self.assertEqual(str(self.root / "authority"), plan["authority"]["repository_root"])
        self.assertEqual("authority", context.plan["authority"]["repository_root"])
        self.assertIn(remote.ORIGIN, calls[0])
        self.assertEqual(4, len(calls))

    def test_rollback_checkout_uses_pinned_source_and_exact_five_json_overlays(self):
        context = self.bind()
        context.operation = "rollback"
        context.plan["authority"].update(source_repository_root="source_authority", code_source_commit="b" * 40)
        context.plan["authority"]["request_path"] = "tasks/requests/install.json"
        authority = self.root / "authority"
        source = self.root / "source_authority"
        claim_rel = "state/claims/%s.%s.%s.json" % (remote.TASK, "a" * 64, "12345")
        documents = {claim_rel: {"production_transaction_path": "state/transactions/tx.json", "autostart_ledger_path": "state/ledger/run.json"},
                     "tasks/requests/install.json": {"execution": {"backup_receipt_path": "state/receipts/backup.json"}},
                     "state/transactions/tx.json": {"status": "ROLLING_BACK"}, "state/ledger/run.json": {"source_commit": "b" * 40},
                     "state/receipts/backup.json": {"status": "PASS"}}
        calls = []
        def run(argv, **kwargs):
            calls.append(argv)
            output = b""
            if "clone" in argv:
                for name, value in documents.items():
                    target = authority / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(encoded(value))
            elif "worktree" in argv:
                source.mkdir(mode=0o700)
            elif "rev-parse" in argv:
                output = ("b" if str(source) in argv else "a").encode() * 40
            elif "get-url" in argv:
                output = remote.ORIGIN.encode()
            elif "ls-remote" in argv:
                output = b"a" * 40 + b"\trefs/heads/main\n"
            return SimpleNamespace(returncode=0, stdout=output)
        plan = remote.checkout_authority(context, run=run)
        self.assertEqual(str(source), plan["authority"]["source_repository_root"])
        self.assertEqual(set(documents), {str(path.relative_to(source)) for path in source.rglob("*.json")})
        for name in documents:
            self.assertEqual((authority / name).read_bytes(), (source / name).read_bytes())
        self.assertTrue(any("--depth=256" in args for args in calls))
        self.assertTrue(any("merge-base" in args and "--is-ancestor" in args for args in calls))

    def test_owned_trigger_excludes_only_exact_context_command(self):
        context = self.bind()
        argv = ["python3.10", "-I", "-B", str(self.root / "remote_worker.py"), "--context", str(self.context_path),
                "--context-sha256", context.sha256, "--operation", "backup"]
        owned = {"id": 777, "command": shlex.join(argv), "description": remote.TASK + " backup", "enabled": True, "state": "Running"}
        other = {"id": 888, "command": "python3.10 unrelated.py", "enabled": True}
        api = mock.Mock()
        api.request.return_value = [owned, other]
        bound = remote.OwnedTriggerAPI(api, context, command_reader=lambda: b"\x00".join(x.encode() for x in argv))
        self.assertEqual([other], bound.request("GET", "always_on/"))
        api.request.return_value = [owned, dict(owned, id=779), other]
        with self.assertRaisesRegex(RuntimeError, "EXACT_OWNED_TRIGGER_REQUIRED"):
            bound.request("GET", "always_on/")

    def test_default_cli_never_starts_network_or_phase(self):
        with mock.patch.object(remote.subprocess, "run") as run, mock.patch("builtins.print"):
            self.assertEqual(0, remote.main([]))
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
