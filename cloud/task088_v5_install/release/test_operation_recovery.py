"""Isolated failure/concurrency fixtures; no provider or production access."""
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

from test_adapter import C, R, E


def payload():
    return {"task_id": "TASK088-GE-PRICE-SITE-STAGE3-TEST", "request_sha256": "a" * 64,
        "run_id": "123", "transaction_id": "tx-isolated-test", "manifest_sha256": "b" * 64,
        "operation": "backup", "remote_package_sha256": {"remote_adapter.py": E.sha(Path(R.__file__).read_bytes())}}


def success(value):
    return {**{key: value[key] for key in R.BINDINGS}, "operation": value["operation"],
        "status": {"backup": "BACKUP_PASS", "execute": "INSTALLED_AWAITING_VERIFICATION",
                   "verify": "INSTALLATION_VERIFIED", "rollback": "ROLLED_BACK"}[value["operation"]],
        "backup_manifest_sha256": "c" * 64,
        "database_unchanged": True, "protected_files_unchanged": True,
        "live_price_writes": False, "stage1_reinstalled": False, "stage2_reinstalled": False,
        "public_acceptance": "NOT_RUN", "telegram_acceptance": "NOT_RUN"}


def blocked_child(path, effect_path, entered, release):
    def effect(*args, **kwargs):
        with open(effect_path, "ab") as handle:
            handle.write(b"one protected effect\n")
            handle.flush()
        entered.set()
        if not release.wait(10):
            raise RuntimeError("TEST_FIXTURE_RELEASE_TIMEOUT")
        return success(payload())
    with patch.object(R, "run", side_effect=effect):
        R.run_once(path)


class RemoteOperationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / "backup-plan.json"
        self.path.write_bytes(E.encoded(payload()))

    def test_duplicate_completed_child_reads_result_without_repeating_effect(self):
        with patch.object(R, "run", return_value=success(payload())) as protected:
            first = R.run_once(self.path)
            second = R.run_once(self.path)
        self.assertEqual(first, second)
        self.assertEqual(protected.call_count, 1)
        self.assertTrue(first["execution"]["operation_returned"])

    def test_second_process_cannot_enter_while_first_effect_is_running(self):
        ctx = multiprocessing.get_context("fork")
        entered, release = ctx.Event(), ctx.Event()
        effect = self.directory / "effects.txt"
        child = ctx.Process(target=blocked_child, args=(self.path, effect, entered, release))
        child.start()
        try:
            self.assertTrue(entered.wait(5))
            with patch.object(R, "run") as protected:
                with self.assertRaisesRegex(E.InstallError, "IN_FLIGHT_RECONCILIATION"):
                    R.run_once(self.path)
                protected.assert_not_called()
            self.assertEqual(effect.read_bytes(), b"one protected effect\n")
        finally:
            release.set()
            child.join(5)
            if child.is_alive():
                child.terminate()
                child.join(5)
        self.assertEqual(child.exitcode, 0)

    def test_crash_after_effect_before_receipt_never_replays(self):
        ctx = multiprocessing.get_context("fork")
        entered, release = ctx.Event(), ctx.Event()
        effect = self.directory / "effects.txt"
        child = ctx.Process(target=blocked_child, args=(self.path, effect, entered, release))
        child.start()
        try:
            self.assertTrue(entered.wait(5))
        finally:
            child.terminate()
            child.join(5)
        with patch.object(R, "run") as protected:
            with self.assertRaisesRegex(E.InstallError, "CLAIMED_RECONCILIATION"):
                R.run_once(self.path)
            protected.assert_not_called()
        self.assertEqual(effect.read_bytes(), b"one protected effect\n")

    def test_claim_fsync_failure_prevents_effect_and_does_not_retry(self):
        with patch.object(R.os, "fsync", side_effect=OSError("TEST fsync failure")), patch.object(R, "run") as protected:
            with self.assertRaises(OSError):
                R.run_once(self.path)
            protected.assert_not_called()
        with patch.object(R, "run") as protected:
            with self.assertRaisesRegex(E.InstallError, "CLAIMED_RECONCILIATION"):
                R.run_once(self.path)
            protected.assert_not_called()

    def test_result_publication_failure_retains_claim_and_never_repeats(self):
        with patch.object(R, "run", return_value=success(payload())) as protected:
            with patch.object(R, "_publish_result", side_effect=OSError("TEST disk full")):
                with self.assertRaises(OSError):
                    R.run_once(self.path)
            with self.assertRaisesRegex(E.InstallError, "CLAIMED_RECONCILIATION"):
                R.run_once(self.path)
        self.assertEqual(protected.call_count, 1)

    def test_failed_engine_result_is_bound_but_not_terminal_authority(self):
        with patch.object(R, "run", side_effect=RuntimeError("TEST failure after unknown effect")) as protected:
            first = R.run_once(self.path)
            self.assertEqual(first["status"], "FAIL")
            self.assertFalse(first["execution"]["operation_returned"])
            with self.assertRaisesRegex(E.InstallError, "TERMINAL_RESULT_RECONCILIATION"):
                R.run_once(self.path)
        self.assertEqual(protected.call_count, 1)

    def test_claim_rebinding_is_rejected(self):
        with patch.object(R, "run", return_value=success(payload())):
            R.run_once(self.path)
        changed = {**payload(), "transaction_id": "tx-different-test"}
        self.path.write_bytes(E.encoded(changed))
        with patch.object(R, "run") as protected:
            with self.assertRaisesRegex(E.InstallError, "CLAIM_DRIFT"):
                R.run_once(self.path)
            protected.assert_not_called()

    def test_partial_claim_and_symlink_fail_closed(self):
        claim = self.directory / "backup-claim.json"
        claim.write_bytes(b"{")
        with patch.object(R, "run") as protected:
            with self.assertRaisesRegex(E.InstallError, "CLAIM_DRIFT"):
                R.run_once(self.path)
            protected.assert_not_called()
        claim.unlink()
        target = self.directory / "foreign.json"
        target.write_bytes(b"unchanged")
        claim.symlink_to(target)
        with self.assertRaisesRegex(E.InstallError, "REGULAR_BOUNDED_FILE_REQUIRED"):
            R.run_once(self.path)
        self.assertEqual(target.read_bytes(), b"unchanged")

    def test_changed_plan_hash_rejected_before_full_validation_or_effect(self):
        with self.assertRaisesRegex(E.InstallError, "PLAN_DRIFT"):
            R.load_operation(self.path, expected_payload_sha256="f" * 64)

    def prepare_operation(self, operation):
        value = {**payload(), "operation": operation}
        if operation != "backup":
            value["backup_manifest_sha256"] = "c" * 64
        path = self.directory / (operation + "-plan.json")
        path.write_bytes(E.encoded(value))
        return path, value

    def complete_operation(self, operation):
        path, value = self.prepare_operation(operation)
        with patch.object(R, "run", return_value=success(value)):
            result = R.run_once(path)
        self.assertTrue(result["execution"]["operation_returned"])
        return result

    def test_execute_requires_actual_same_run_backup_terminal_proof(self):
        path, _value = self.prepare_operation("execute")
        with patch.object(R, "run") as protected:
            result = R.run_once(path)
            protected.assert_not_called()
        self.assertFalse(result["execution"]["operation_returned"])
        self.assertIn("PREDECESSOR_TERMINAL", result["error"])

    def test_terminal_execute_allows_rollback_and_prevents_forward_reentry(self):
        self.complete_operation("backup")
        self.complete_operation("execute")
        restored = self.complete_operation("rollback")
        self.assertEqual(restored["status"], "ROLLED_BACK")
        # Completed execute may be read back, but can never execute again.
        with patch.object(R, "run") as protected:
            old = R.run_once(self.directory / "execute-plan.json")
            protected.assert_not_called()
        self.assertEqual(old["status"], "INSTALLED_AWAITING_VERIFICATION")
        path, _value = self.prepare_operation("verify")
        with patch.object(R, "run") as protected:
            refused = R.run_once(path)
            protected.assert_not_called()
        self.assertIn("ROLLBACK_BARRIER", refused["error"])

    def test_failed_execute_result_does_not_authorize_rollback(self):
        self.complete_operation("backup")
        path, _value = self.prepare_operation("execute")
        with patch.object(R, "run", side_effect=RuntimeError("TEST unknown effect")):
            R.run_once(path)
        path, _value = self.prepare_operation("rollback")
        with patch.object(R, "run") as protected:
            refused = R.run_once(path)
            protected.assert_not_called()
        self.assertIn("PREDECESSOR_TERMINAL", refused["error"])

    def test_lost_post_delayed_execute_cannot_run_after_rollback_attempt(self):
        self.complete_operation("backup")
        fake = MemoryProvider(self.directory)
        fake.post_mode = "lost_without_task"
        with self.assertRaisesRegex(C.ControllerError, "LAUNCH_OUTCOME_UNKNOWN"):
            fake.run("execute")
        # The provider accepted/request outcome is unknown; its command may run
        # later. Preserve its real uploaded plan/intent in the target namespace.
        for name in ("execute-plan.json", "execute-launch.json"):
            (self.directory / name).write_bytes(fake.files[name])
        rollback, _value = self.prepare_operation("rollback")
        with patch.object(R, "run") as protected:
            refused = R.run_once(rollback)
            late = R.run_once(self.directory / "execute-plan.json")
            protected.assert_not_called()
        self.assertIn("PREDECESSOR_TERMINAL", refused["error"])
        self.assertIn("ROLLBACK_BARRIER", late["error"])
        self.assertTrue((self.directory / "rollback-claim.json").is_file())
        self.assertFalse(refused["execution"]["operation_returned"])
        self.assertFalse(late["execution"]["operation_returned"])

    def test_active_execute_excludes_rollback_until_terminal_result_published(self):
        self.complete_operation("backup")
        execute, execute_value = self.prepare_operation("execute")
        ctx = multiprocessing.get_context("fork")
        entered, release = ctx.Event(), ctx.Event()
        effect = self.directory / "effects.txt"

        def active_execute():
            def effect_once(*args, **kwargs):
                effect.write_bytes(b"execute once")
                entered.set()
                if not release.wait(10):
                    raise RuntimeError("TEST release timeout")
                return success(execute_value)
            with patch.object(R, "run", side_effect=effect_once):
                R.run_once(execute)

        child = ctx.Process(target=active_execute)
        child.start()
        try:
            self.assertTrue(entered.wait(5))
            rollback, rollback_value = self.prepare_operation("rollback")
            with patch.object(R, "run") as protected:
                with self.assertRaisesRegex(E.InstallError, "IN_FLIGHT_RECONCILIATION"):
                    R.run_once(rollback)
                protected.assert_not_called()
            self.assertFalse((self.directory / "rollback-claim.json").exists())
        finally:
            release.set()
            child.join(5)
            if child.is_alive():
                child.terminate()
                child.join(5)
        self.assertEqual(child.exitcode, 0)
        with patch.object(R, "run", return_value=success(rollback_value)) as protected:
            restored = R.run_once(rollback)
        self.assertEqual(protected.call_count, 1)
        self.assertTrue(restored["execution"]["operation_returned"])


class MemoryProvider(C.API):
    """Explicit fake provider exercising the real controller orchestration."""
    def __init__(self, directory):
        bindings = {key: payload()[key] for key in C.BINDINGS}
        package = directory / "package"
        package.mkdir()
        for name in C.REMOTE_FILES:
            (package / name).write_bytes(Path(R.__file__).read_bytes() if name == "remote_adapter.py" else b"# TEST fixture\n")
        values = {"UAART_RUN_ID": "123", "UAART_REQUEST_SHA256": "a" * 64,
            "UAART_TASK_ID": bindings["task_id"], "PYTHONANYWHERE_API_TOKEN": "TEST ONLY",
            "ROOT": directory, "PACKAGE": "package", "BINDINGS": bindings, "BACKUP_SHA": "c" * 64,
            "INSTALL_PLAN": {"TEST_FIXTURE": True}, "EVIDENCE": {},
            "DEPLOYMENT": {"preflight_directory": "/TEST_ONLY", "preflight_report_sha256": "d" * 64,
                "remote_package_sha256": {name: E.sha((package / name).read_bytes()) for name in C.REMOTE_FILES}}}
        super().__init__(values)
        self.files, self.tasks, self.calls = {}, {}, []
        self.post_mode = "complete"
        self.corrupt_cleanup = False

    def supervisor(self):
        self.calls.append(("SUPERVISOR_GET",))
        return {"id": 266084, "state": "Running", "restarted": False}

    def routing(self):
        self.calls.append(("ROUTING_GET",))
        return {"provider_configuration_written": False}

    def read(self, name):
        self.file_url(name)
        return self.files.get(name)

    def upload(self, name, data):
        self.file_url(name)
        if name in self.files and self.files[name] != data:
            raise C.ControllerError("EXISTING_REMOTE_RUN_FILE_DRIFT")
        self.files[name] = data

    def complete(self, operation="backup"):
        raw = self.files[operation + "-plan.json"]
        value = json.loads(raw)
        claim = R.operation_claim(raw)
        result = {**success(value), "execution": {"contract": "TASK088-REMOTE-OPERATION-RETURN-1",
            "payload_sha256": E.sha(raw), "claim_sha256": E.sha(E.encoded(claim)),
            "adapter_sha256": claim["adapter_sha256"], "operation_returned": True}}
        self.files[operation + "-result.json"] = E.encoded(result)

    def request(self, method, url, data=None, headers=None, allowed=(200,)):
        self.calls.append((method, url))
        collection = C.BASE + "always_on/"
        if method == "GET" and url == collection:
            return 200, E.encoded(list(self.tasks.values()))
        if method == "POST" and url == collection:
            params = parse_qs(data.decode())
            operation = params["description"][0].split()[-1]
            self.assert_launch_before_post(operation)
            if self.post_mode != "lost_without_task":
                self.tasks[7123] = {"id": 7123, "command": params["command"][0],
                    "description": params["description"][0], "enabled": True, "state": "Running"}
            if self.post_mode in ("complete", "lost_complete"):
                self.complete(operation)
            if self.post_mode.startswith("lost"):
                raise C.ControllerError("NETWORK_TEST_LOST_REPLY")
            return 201, E.encoded({"id": 7123})
        identifier = int(url.removeprefix(collection).strip("/"))
        if method == "GET":
            value = self.tasks.get(identifier)
            if self.corrupt_cleanup and value:
                value = {**value, "command": "different unrelated task"}
            return (200, E.encoded(value)) if value else (404, b"")
        if method == "DELETE":
            self.tasks.pop(identifier, None)
            return 204, b""
        raise AssertionError("Unexpected fake-provider action")

    def assert_launch_before_post(self, operation):
        assert json.loads(self.files[operation + "-launch.json"])["contract"] == "TASK088-REMOTE-LAUNCH-INTENT-1"
        assert operation + "-plan.json" in self.files


class ControllerOperationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.api = MemoryProvider(Path(self.temp.name))

    def mutations(self, kind):
        return [call for call in self.api.calls if call[0] == kind]

    def timeout(self):
        with patch.object(C.time, "monotonic", side_effect=(0, 901)):
            with self.assertRaisesRegex(C.ControllerError, "TIMEOUT_RECONCILIATION"):
                self.api.run("backup")

    def test_lost_post_reply_reconciles_finished_runner_without_second_post(self):
        self.api.post_mode = "lost_complete"
        result = self.api.run("backup")
        self.assertEqual(result["status"], "BACKUP_PASS")
        self.assertEqual(len(self.mutations("POST")), 1)
        self.assertEqual(len(self.mutations("DELETE")), 1)
        self.assertFalse(self.api.tasks)

    def test_completed_result_reuses_same_identity_with_fresh_provider_checks(self):
        first = self.api.run("backup")
        second = self.api.run("backup")
        self.assertEqual(first, second)
        self.assertEqual(len(self.mutations("POST")), 1)
        self.assertEqual(len(self.mutations("DELETE")), 1)
        self.assertEqual(len(self.mutations("SUPERVISOR_GET")), 4)
        self.assertEqual(len(self.mutations("ROUTING_GET")), 4)

    def test_timeout_keeps_active_runner_and_later_result_is_reconciled(self):
        self.api.post_mode = "running"
        self.timeout()
        self.assertEqual(len(self.mutations("DELETE")), 0)
        self.assertIn(7123, self.api.tasks)
        self.api.complete()
        result = self.api.run("backup")
        self.assertEqual(result["status"], "BACKUP_PASS")
        self.assertEqual(len(self.mutations("POST")), 1)
        self.assertEqual(len(self.mutations("DELETE")), 1)

    def test_unknown_post_with_no_visible_task_never_posts_again(self):
        self.api.post_mode = "lost_without_task"
        for _ in range(2):
            with self.assertRaisesRegex(C.ControllerError, "LAUNCH_OUTCOME_UNKNOWN"):
                self.api.run("backup")
        self.assertEqual(len(self.mutations("POST")), 1)
        self.assertEqual(len(self.mutations("DELETE")), 0)

    def test_terminal_proof_drift_never_deletes_runner(self):
        self.api.post_mode = "running"
        self.timeout()
        self.api.complete()
        result = json.loads(self.api.files["backup-result.json"])
        result["execution"]["claim_sha256"] = "f" * 64
        self.api.files["backup-result.json"] = E.encoded(result)
        with self.assertRaisesRegex(C.ControllerError, "TERMINAL_PROOF_REQUIRED"):
            self.api.run("backup")
        self.assertEqual(len(self.mutations("DELETE")), 0)

    def test_failed_terminal_boolean_never_deletes_runner(self):
        self.api.post_mode = "running"
        self.timeout()
        self.api.complete()
        result = json.loads(self.api.files["backup-result.json"])
        result["execution"]["operation_returned"] = False
        result["status"] = "FAIL"
        self.api.files["backup-result.json"] = E.encoded(result)
        with self.assertRaisesRegex(C.ControllerError, "TERMINAL_PROOF_REQUIRED"):
            self.api.run("backup")
        self.assertEqual(len(self.mutations("DELETE")), 0)

    def test_cleanup_identity_is_rechecked_after_bound_terminal_receipt(self):
        self.api.corrupt_cleanup = True
        with self.assertRaisesRegex(C.ControllerError, "CLEANUP_IDENTITY_MISMATCH"):
            self.api.run("backup")
        self.assertEqual(len(self.mutations("DELETE")), 0)

    def test_changed_payload_cannot_rebind_launch_or_repeat_post(self):
        self.api.run("backup")
        self.api.values["INSTALL_PLAN"]["changed"] = True
        with self.assertRaisesRegex(C.ControllerError, "LAUNCH_INTENT_DRIFT"):
            self.api.run("backup")
        self.assertEqual(len(self.mutations("POST")), 1)

    def test_duplicate_provider_membership_blocks_mutations(self):
        self.api.post_mode = "running"
        self.timeout()
        self.api.tasks[7124] = {**self.api.tasks[7123], "id": 7124}
        with self.assertRaisesRegex(C.ControllerError, "DUPLICATE_RUNNERS"):
            self.api.run("backup")
        self.assertEqual(len(self.mutations("POST")), 1)
        self.assertEqual(len(self.mutations("DELETE")), 0)


if __name__ == "__main__":
    unittest.main()
