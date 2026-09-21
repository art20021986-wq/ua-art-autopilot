"""Offline transport checks.  No test calls PythonAnywhere or opens a socket."""
import copy
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import urllib.parse

import transport as t


def install_module(name, filename):
    path = Path(__file__).resolve().parents[1] / "install" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class Clock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now

    def sleep(self, duration):
        self.now += duration


def bundle(operation="backup"):
    data = {name: ("# offline exact source: " + name + "\n").encode() for name in t.WORKER_FILES}
    data.update({"plan.json": b'{"scope":"fixture"}\n', "release/payload/a.py": b"x = 1\n"})
    return t.TransportBundle(identity={"task_id": t.TASK_ID, "workflow_run_id": "123456",
        "transaction_id": "tx-fixture-transaction-0017", "request_sha256": "a" * 64,
        "manifest_sha256": "b" * 64},
        files=tuple(t.Payload(name, raw, t.sha256(raw)) for name, raw in sorted(data.items())),
        parameters={"plan_path": "plan.json", "plan_sha256": t.sha256(data["plan.json"]),
                    "installation_policy_sha256": "c" * 64,
                    "backup_manifest_sha256": None if operation == "backup" else "d" * 64},
        operation=operation)


class FakeAPI:
    def __init__(self):
        self.files = {}
        self.tasks = {}
        self.calls = []
        self.transport = None
        self.counter = 100
        self.remote_status = "PASS"
        self.receipt_mutation = None
        self.pair_drift = False
        self.upload_drift = None
        self.no_result = False
        self.stop_unconfirmed = False
        self.create_uncertain = False
        self.create_status = None
        self.worker_commands = []
        self.receipt_producer = None

    def current(self):
        return list(self.transport._stages.values())[-1]["stage"]

    def request(self, method, url, data=None, headers=None, allowed=(200,)):
        self.calls.append((method, url, data))
        parsed = urllib.parse.urlsplit(url)
        suffix = parsed.path.removeprefix("/api/v0/user/Carix/")
        if suffix.startswith("files/path"):
            path = urllib.parse.unquote(suffix.removeprefix("files/path"))
            if method == "GET":
                return (200, self.files[path]) if path in self.files else (404, b"")
            if method == "POST":
                value = data.split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n--", 1)[0]
                self.files[path] = value
                if self.upload_drift and path.endswith(self.upload_drift):
                    self.files[path] += b"DRIFT"
                return 201, b"{}"
            if method == "DELETE":
                self.files.pop(path, None)
                return 204, b""
        if suffix == "always_on/" and method == "POST":
            form = urllib.parse.parse_qs(data.decode())
            argv = shlex.split(form["command"][0])
            if self.create_uncertain:
                raise OSError("Never expose credential: fixture-api-token")
            if self.create_status is not None:
                return self.create_status, b'{"error":"quota unavailable"}'
            self.counter += 1
            self.tasks[self.counter] = argv
            stage = self.current()
            if argv[3] == stage.bootstrap_path:
                self.files[stage.remote_dir + "/stage-ready.json"] = t.canonical({
                    "schema": t.READY_SCHEMA, "task_id": t.TASK_ID,
                    "context_sha256": stage.context_sha256, "stage": stage.remote_dir,
                    "mode": 0o700, "status": "READY"})
            else:
                self.worker_commands.append(argv)
                if not self.no_result:
                    receipt = {key: stage.context[key] for key in ("task_id", "workflow_run_id",
                        "transaction_id", "request_sha256", "manifest_sha256")}
                    receipt.update(schema=t.RECEIPT_SCHEMA, context_sha256=stage.context_sha256,
                        operation=stage.operation, status=self.remote_status,
                        backup_manifest_sha256="d" * 64, production_observed=False, safe_to_stop=True)
                    if self.receipt_mutation:
                        self.receipt_mutation(receipt)
                    if self.receipt_producer:
                        raw, completed = self.receipt_producer(receipt)
                    else:
                        raw = completed = t.canonical(receipt)
                    self.files[stage.remote_dir + "/result-" + stage.operation + ".json"] = raw
                    if completed is not None:
                        self.files[stage.remote_dir + "/completed-" + stage.operation + ".json"] = (
                            completed + b" " if self.pair_drift else completed)
            return 201, json.dumps({"id": self.counter}).encode()
        if suffix.startswith("always_on/"):
            identifier = int(suffix.rstrip("/").rsplit("/", 1)[1])
            if method == "DELETE":
                if not self.stop_unconfirmed:
                    self.tasks.pop(identifier, None)
                return 204, b""
            if method == "GET":
                return (200, b"{}") if identifier in self.tasks else (404, b"")
        raise AssertionError("Unexpected offline API operation")


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.api = FakeAPI()
        self.transport = t.PythonAnywhereTransport("fixture-api-token", request=self.api.request,
            clock=self.clock, sleep=self.clock.sleep)
        self.api.transport = self.transport

    def claim(self, operation="backup"):
        return self.transport.claim_transport(bundle(operation))

    def test_exact_staging_context_fixed_argv_and_release(self):
        stage = self.claim()
        self.assertTrue(stage.remote_dir.startswith(t.STAGE_PARENT + "/" + t.STAGE_PREFIX))
        self.assertEqual(len(stage.remote_dir.rsplit("-", 1)[1]), 32)
        self.assertEqual(stage.context["parameters"]["plan_path"], stage.remote_dir + "/plan.json")
        self.assertEqual(t.sha256(stage.context_bytes), stage.context_sha256)
        result = self.transport.run(stage)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(self.api.worker_commands, [["python3.10", "-I", "-B",
            stage.remote_dir + "/remote_worker.py", "--context", stage.remote_dir + "/context.json",
            "--context-sha256", stage.context_sha256, "--operation", "backup"]])
        self.assertFalse(self.api.tasks)
        self.transport.release_transport(stage)
        self.assertNotIn(stage.bootstrap_path, self.api.files)
        self.assertNotIn(stage.remote_dir + "/remote_worker.py", self.api.files)
        self.assertIn(stage.remote_dir + "/context.json", self.api.files)
        self.assertIn(stage.remote_dir + "/completed-backup.json", self.api.files)
        self.assertNotIn(b"fixture-api-token", b"".join(self.api.files.values()))
        self.assertTrue(all("schedule" not in url and "console" not in url for _, url, _ in self.api.calls))

    def test_upload_drift_stops_before_worker_start(self):
        self.api.upload_drift = "/remote_worker.py"
        with self.assertRaisesRegex(t.TransportError, "UPLOAD_READBACK_MISMATCH"):
            self.claim()
        self.assertFalse(self.api.worker_commands)
        self.assertFalse(self.api.tasks)

    def test_read_source_is_hash_bound_get_only_and_fixed_scope(self):
        path = "/home/Carix/cars_ui.py"
        self.api.files[path] = b"exact-private-source"
        self.assertEqual(self.transport.read_source(path, t.sha256(self.api.files[path])), self.api.files[path])
        self.assertEqual(len(self.api.calls), 1)
        self.assertEqual(self.api.calls[0][0], "GET")
        with self.assertRaisesRegex(t.TransportError, "READ_SOURCE_HASH_MISMATCH"):
            self.transport.read_source(path, "a" * 64)
        count = len(self.api.calls)
        for forbidden in ("/home/Carix/.env", "/home/Carix/token.py", "/etc/passwd",
                          "/home/Carix/../Carix/cars_ui.py"):
            with self.assertRaisesRegex(t.TransportError, "READ_SOURCE_SCOPE"):
                self.transport.read_source(forbidden, "a" * 64)
        self.assertEqual(len(self.api.calls), count)

    def test_read_backup_scope_and_digest_never_allow_database(self):
        package, transaction = "a" * 64, "tx-1234567890123456"
        folder = "/home/Carix/ua_crm_installation_state/install-" + package[:20] + "-" + t.sha256(transaction.encode())[:20]
        self.api.files[folder + "/0.before"] = b"previous-exact-code"
        actual = self.transport.read_backup_file(package, transaction, "0.before", t.sha256(b"previous-exact-code"))
        self.assertEqual(actual, b"previous-exact-code")
        count = len(self.api.calls)
        for name in ("crm.sqlite3", "crm.db", "../0.before", "runtime.json", "phase_backup_manifest.json/child"):
            with self.assertRaisesRegex(t.TransportError, "BACKUP_FILE_SCOPE"):
                self.transport.read_backup_file(package, transaction, name, "b" * 64)
        self.assertEqual(len(self.api.calls), count)

    def test_source_drift_after_staging_stops_before_worker_start(self):
        stage = self.claim()
        self.api.files[stage.remote_dir + "/package_install.py"] += b"changed"
        with self.assertRaisesRegex(t.TransportError, "STAGED_SOURCE_DRIFT"):
            self.transport.run(stage)
        self.assertFalse(self.api.worker_commands)

    def test_context_drift_stops_before_worker_start(self):
        stage = self.claim()
        self.api.files[stage.remote_dir + "/context.json"] += b" "
        with self.assertRaisesRegex(t.TransportError, "CONTEXT_READBACK_MISMATCH"):
            self.transport.run(stage)
        self.assertFalse(self.api.worker_commands)

    def test_stale_receipt_cannot_become_success(self):
        stage = self.claim()
        self.api.files[stage.remote_dir + "/result-backup.json"] = b"{}"
        with self.assertRaisesRegex(t.TransportError, "PREEXISTING_REMOTE_RESULT"):
            self.transport.run(stage)
        self.assertFalse(self.api.worker_commands)

    def test_receipt_identity_including_context_and_operation(self):
        for key in ("task_id", "workflow_run_id", "transaction_id", "request_sha256",
                    "manifest_sha256", "context_sha256", "operation"):
            with self.subTest(key=key):
                self.setUp()
                stage = self.claim()
                self.api.receipt_mutation = lambda receipt, key=key: receipt.update({key: "other"})
                with self.assertRaisesRegex(t.TransportError, "REMOTE_RECEIPT_IDENTITY"):
                    self.transport.run(stage)
                self.assertTrue(self.api.tasks)
                self.assertFalse(self.transport.remote_fenced)
                with self.assertRaises(t.TransportError):
                    self.transport.release_transport(stage)

    def test_pair_readback_drift_is_rejected(self):
        stage = self.claim()
        self.api.pair_drift = True
        with self.assertRaisesRegex(t.TransportError, "REMOTE_RECEIPT_PAIR_MISMATCH"):
            self.transport.run(stage)
        self.assertTrue(self.api.tasks)
        self.assertFalse(self.transport.remote_fenced)

    def test_nonterminal_failure_keeps_owner_and_watchdog_alive(self):
        stage = self.claim()
        self.api.remote_status = "FAIL"
        self.api.receipt_mutation = lambda receipt: receipt.update(safe_to_stop=False)
        with self.assertRaisesRegex(t.RemoteOutcomeUncertain, "REMOTE_RECEIPT_NOT_TERMINAL"):
            self.transport.run(stage)
        self.assertTrue(self.api.tasks)
        self.assertFalse(self.transport.remote_fenced)

    def test_remote_failure_is_never_reported_as_pass(self):
        stage = self.claim()
        self.api.remote_status = "FAIL"
        with self.assertRaisesRegex(t.RemoteOperationFailed, "REMOTE_OPERATION_FAILED") as caught:
            self.transport.run(stage)
        self.assertEqual(caught.exception.receipt["status"], "FAIL")
        self.assertTrue(self.transport.remote_fenced)
        self.transport.release_transport(stage)

    def test_timeout_preserves_owner_recovery_and_evidence_and_forbids_retry(self):
        stage = self.claim()
        self.api.no_result = True
        before = self.clock.now
        with self.assertRaisesRegex(t.RemoteOutcomeUncertain, "REMOTE_RESULT_TIMEOUT"):
            self.transport.run(stage, timeout=5)
        # Includes the full pre-execution source read-back, all provider-paced.
        self.assertLessEqual(self.clock.now - before, 60)
        self.assertTrue(self.api.tasks)
        self.assertFalse(self.transport.remote_fenced)
        self.assertIn(stage.remote_dir + "/remote_worker.py", self.api.files)
        with self.assertRaises(t.TransportError):
            self.transport.run(stage)
        with self.assertRaises(t.TransportError):
            self.transport.release_transport(stage)

    def test_unconfirmed_stop_fences_all_future_actions(self):
        stage = self.claim()
        self.api.stop_unconfirmed = True
        before = self.clock.now
        with self.assertRaisesRegex(t.RemoteOutcomeUncertain, "REMOTE_TRIGGER_STOP_UNCONFIRMED"):
            self.transport.run(stage)
        self.assertFalse(self.transport.remote_fenced)
        self.assertLessEqual(self.clock.now - before, 110)
        for action in (lambda: self.transport.release_transport(stage), lambda: self.claim()):
            with self.assertRaises(t.TransportError):
                action()

    def test_unknown_creation_is_fenced_and_diagnostics_are_redacted(self):
        self.api.create_uncertain = True
        with self.assertRaises(t.RemoteOutcomeUncertain) as caught:
            self.claim()
        self.assertEqual(str(caught.exception), "REMOTE_TRIGGER_CREATION_UNCONFIRMED")
        self.assertNotIn("fixture-api-token", str(caught.exception))
        self.assertFalse(self.transport.remote_fenced)
        with self.assertRaises(t.TransportError):
            self.claim()

    def test_task_capacity_rejection_cannot_pause_crm_or_start_worker(self):
        self.api.create_status = 403
        with self.assertRaisesRegex(t.RemoteOutcomeUncertain, "REMOTE_TRIGGER_CREATION_UNCONFIRMED"):
            self.claim()
        self.assertFalse(self.api.tasks)
        self.assertFalse(self.api.worker_commands)
        self.assertFalse(self.transport.remote_fenced)
        self.assertTrue(all(method in ("GET", "POST") for method, _, _ in self.api.calls))
        self.assertTrue(all("266084" not in url for _, url, _ in self.api.calls))
        self.assertEqual(sum(url.endswith("always_on/") for _, url, _ in self.api.calls), 1)

    def test_changed_entrypoint_is_not_deleted_on_release(self):
        stage = self.claim()
        self.transport.run(stage)
        path = stage.remote_dir + "/remote_worker.py"
        self.api.files[path] = b"newer-source"
        with self.assertRaisesRegex(t.TransportError, "RELEASE_SOURCE_CHANGED"):
            self.transport.release_transport(stage)
        self.assertEqual(self.api.files[path], b"newer-source")

    def test_unique_stage_and_operation_bound_backup(self):
        first, second = self.claim("backup"), self.claim("execute")
        self.assertNotEqual(first.remote_dir, second.remote_dir)
        self.assertIsNone(first.context["parameters"]["backup_manifest_sha256"])
        self.assertEqual(second.context["parameters"]["backup_manifest_sha256"], "d" * 64)
        with self.assertRaisesRegex(t.TransportError, "STAGE_OPERATION_STATE"):
            self.transport.run(second, "rollback")

    def test_invalid_bundle_no_network(self):
        original = bundle()
        variants = [
            t.TransportBundle({**original.identity, "task_id": "another-task"}, original.files,
                              original.parameters, original.operation),
            t.TransportBundle(original.identity, original.files + (t.Payload("../escape", b"x", t.sha256(b"x")),),
                              original.parameters, original.operation),
            t.TransportBundle(original.identity, original.files,
                              {**original.parameters, "plan_sha256": "e" * 64}, original.operation),
            t.TransportBundle(original.identity, original.files,
                              {**original.parameters, "backup_manifest_sha256": "e" * 64}, original.operation),
            t.TransportBundle(original.identity, original.files, original.parameters, "arbitrary-command"),
        ]
        for invalid in variants:
            with self.subTest(invalid=invalid.operation):
                with self.assertRaises(t.TransportError):
                    self.transport.claim_transport(invalid)
        self.assertFalse(self.api.calls)

    def test_foreign_stage_cannot_be_run_or_released(self):
        stage = self.claim()
        forged = copy.copy(stage)
        with self.assertRaisesRegex(t.TransportError, "OWNED_STAGE_REQUIRED"):
            self.transport.run(forged)
        with self.assertRaisesRegex(t.TransportError, "OWNED_STAGE_REQUIRED"):
            self.transport.release_transport(forged)

    def test_authenticated_requests_are_provider_rate_limited(self):
        moments = []
        original = self.api.request
        def observed(*args, **kwargs):
            moments.append(self.clock.now)
            return original(*args, **kwargs)
        self.transport._io = observed
        self.claim()
        self.assertGreater(len(moments), 20)
        self.assertTrue(all(right - left >= 3.199999 for left, right in zip(moments, moments[1:])))

    def test_actual_remote_worker_producer_bytes_are_accepted_over_transport(self):
        worker_module = install_module("crm_transport_wire_worker", "remote_worker.py")
        package_module = install_module("crm_transport_wire_package", "package_install.py")
        stage = self.claim()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            producer = object.__new__(worker_module.PhaseRunner)
            producer.root, producer.operation = root, stage.operation
            producer.terminal_path = root / "watchdog-terminal.json"
            def actual_receipt(receipt):
                receipt["proofs"] = {"wire_example": "перевірено"}
                journal = {"receipt": receipt, "terminal": {"status": "COMPLETE", "safe_to_stop": True}}
                with patch.dict(sys.modules, {"package_install": package_module}):
                    producer._write_terminal(journal)
                return ((root / "result-backup.json").read_bytes(),
                        (root / "completed-backup.json").read_bytes())
            self.api.receipt_producer = actual_receipt
            result = self.transport.run(stage)
            self.assertEqual(result["proofs"]["wire_example"], "перевірено")
            actual = (root / "result-backup.json").read_bytes()
            self.assertEqual(actual, t.canonical(result))
            self.assertTrue(actual.endswith(b"\n"))
            self.assertEqual(actual, worker_module.receipt_bytes(result))
            self.assertFalse(self.api.tasks)

    def test_actual_blocked_worker_producer_never_authorizes_owner_stop(self):
        worker_module = install_module("crm_transport_blocked_worker", "remote_worker.py")
        package_module = install_module("crm_transport_blocked_package", "package_install.py")
        stage = self.claim()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            producer = object.__new__(worker_module.PhaseRunner)
            producer.root, producer.operation = root, stage.operation
            producer.terminal_path, producer.path = root / "watchdog-terminal.json", root / "phase-journal.json"
            producer.context_sha = "a" * 64
            producer.context = {"owner_pid": 1234, "start_ticks": "123", "pgid": 1234}
            producer.plan = {"package_manifest_sha256": "b" * 64, "installation_policy_sha256": "c" * 64}
            producer.fault = lambda phase: None
            producer.transport = SimpleNamespace(sha256=stage.context_sha256, backup_sha256=None,
                identity=lambda: {key: stage.context[key] for key in ("task_id", "workflow_run_id",
                    "transaction_id", "request_sha256", "manifest_sha256", "operation")})
            def blocked_receipt(_receipt):
                with patch.dict(sys.modules, {"package_install": package_module}):
                    result = producer.finish({}, success=False, phase_status="RECOVERY_BLOCKED",
                        watchdog_status="BLOCKED", proofs={"crm_resume": {
                            "id": 266084, "enabled": True, "state": "Running"}})
                self.assertFalse(result["safe_to_stop"])
                self.assertFalse((root / "completed-backup.json").exists())
                return (root / "result-backup.json").read_bytes(), None
            self.api.receipt_producer = blocked_receipt
            with self.assertRaises(t.RemoteOutcomeUncertain):
                self.transport.run(stage)
            self.assertFalse(self.transport.remote_fenced)
            self.assertTrue(self.api.tasks)
            self.assertEqual(json.loads((root / "result-backup.json").read_bytes())["phase_status"], "RECOVERY_BLOCKED")

    def test_actual_fixed_bootstrap_private_modes_and_existing_path_refusal(self):
        # Executes only the generated, fixed staging program against a temporary
        # local directory, never the remote worker or any production path.
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            destination = str(parent / (t.STAGE_PREFIX + "0" * 32))
            with patch.object(t, "STAGE_PARENT", str(parent)):
                raw = self.transport._bootstrap(destination, "a" * 64,
                                                ["remote_worker.py", "release/payload/a.py"])
            source = parent / "bootstrap.py"
            source.write_bytes(raw)
            argv = [sys.executable, "-I", "-B", str(source), "--expected-script-sha256", t.sha256(raw)]
            result = subprocess.run(argv, capture_output=True, check=False, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            for path in (Path(destination), Path(destination) / "release", Path(destination) / "release/payload"):
                self.assertEqual(path.stat().st_mode & 0o777, 0o700)
            receipt = Path(destination) / "stage-ready.json"
            self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(receipt.read_bytes())["context_sha256"], "a" * 64)
            repeated = subprocess.run(argv, capture_output=True, check=False, timeout=10)
            self.assertNotEqual(repeated.returncode, 0)


if __name__ == "__main__":
    unittest.main()
