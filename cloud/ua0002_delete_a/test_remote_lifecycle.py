import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import shlex
import unittest
from unittest.mock import patch

import remote_lifecycle as lifecycle


class ProviderAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.plan_path = Path('/home/Carix/autopilot_inbox/fixture/plan.json')
        self.result_path = self.plan_path.parent / 'backup-result.json'
        self.sha = 'a' * 64
        self.command = 'python3.10 -I /home/Carix/uaart_connection_monitor.py --watch --interval 300 --evidence /home/Carix/uaart-monitor/latest.json'
        self.rows = [{'id': 266084, 'command': lifecycle.COMMAND, 'enabled': True},
                     {'id': 270984, 'command': self.command, 'enabled': True},
                     {'id': 123456, 'command': 'cd ' + str(self.plan_path.parent)
                      + ' && python3.10 -B remote_lifecycle.py --operation backup --plan ' + str(self.plan_path)
                      + ' --plan-sha256 ' + self.sha + ' --result ' + str(self.result_path), 'enabled': True}]
        normalized = [{"id": r['id'], "enabled": True,
                       "command_sha256": hashlib.sha256(r['command'].encode()).hexdigest()}
                      for r in self.rows[:2]]
        argv = json.dumps(shlex.split(self.command), ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode()
        self.plan = {'writers': {'reviewed': True, 'always_on': normalized, 'scheduled': [],
            'allowed_python_cmdline_sha256': [hashlib.sha256(argv).hexdigest()],
            'safe_window_end_epoch': time.time() + 3600}}
        self.scheduled = []
        test = self
        class API:
            def request(self, method, endpoint):
                if method != 'GET':
                    raise AssertionError('Admission must not mutate provider tasks')
                return test.rows if endpoint == 'always_on/' else test.scheduled
        self.api = API()

    def run_case(self):
        return lifecycle.provider_admission(self.api, self.plan, 'backup', self.plan_path, self.sha, self.result_path)

    def test_exact_observed_background_inventory_admitted(self):
        self.assertIn('scheduled_sha256', self.run_case())

    def test_extra_provider_writer_blocks_before_pause(self):
        self.rows.append({'id': 999, 'command': 'python3.10 /home/Carix/foreign_installer.py', 'enabled': True})
        with self.assertRaisesRegex(RuntimeError, 'PROVIDER_ALWAYS_ON_DRIFT'):
            self.run_case()

    def test_extra_schedule_blocks_before_pause(self):
        self.scheduled.append({'id': 111, 'command': 'python3.10 writer.py', 'hour': 12, 'minute': 0, 'interval': 'daily'})
        with self.assertRaisesRegex(RuntimeError, 'PROVIDER_SCHEDULE_DRIFT'):
            self.run_case()

    def test_wrong_os_argv_binding_rejected(self):
        self.plan['writers']['allowed_python_cmdline_sha256'] = ['b' * 64]
        with self.assertRaisesRegex(RuntimeError, 'MONITOR_OS_COMMAND_BINDING_MISMATCH'):
            self.run_case()

    def test_short_quiet_window_rejected(self):
        self.plan['writers']['safe_window_end_epoch'] = time.time() + 60
        with self.assertRaisesRegex(RuntimeError, 'SCHEDULE_QUIET_WINDOW_TOO_SHORT'):
            self.run_case()


class LifecycleRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(lifecycle.canonical({"alwayson_id": lifecycle.SUPERVISOR,
            "package_sha256": {"remote_lifecycle.py": hashlib.sha256(Path(lifecycle.__file__).read_bytes()).hexdigest()}}))
        self.sha = hashlib.sha256(self.plan.read_bytes()).hexdigest()
        self.result = self.root / "result.json"
        self.operations = []
        self.enabled = []
        test = self

        class API:
            def supervisor(self):
                return {"id": lifecycle.SUPERVISOR, "enabled": True, "state": "Running"}

            def set_enabled(self, enabled):
                test.enabled.append(enabled)
                return {"id": lifecycle.SUPERVISOR, "enabled": enabled,
                        "state": "Running" if enabled else "Disabled"}

        self.api = API()
        admission = patch.object(lifecycle, "provider_admission", return_value={"fixture": True})
        admission.start()
        self.addCleanup(admission.stop)

    def receipt(self, operation, **kwargs):
        return dict(status="PASS", operation=operation, plan_sha256=self.sha, **kwargs)

    def run_case(self, child):
        with patch.object(lifecycle, "API", return_value=self.api), patch.object(lifecycle, "child", side_effect=child):
            return lifecycle._execute("install_verify", self.plan, self.sha, self.result)

    def test_admission_drift_with_durable_untouched_proof_resumes_crm(self):
        def child(operation, *_):
            self.operations.append(operation)
            if operation == "install_verify":
                raise RuntimeError("DATABASE_STATE_DRIFT")
            if operation == "recovery_status":
                return self.receipt(operation, no_mutation=True, durable_stage="BACKED_UP")
            self.fail("Untouched operation must not attempt forward recovery")

        result = self.run_case(child)
        self.assertEqual(self.operations, ["install_verify", "recovery_status"])
        self.assertEqual(self.enabled, [False, True])
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["no_mutation_proof"]["no_mutation"])
        self.assertTrue(result["safe_to_stop"])

    def test_partial_retirement_recovers_before_resume(self):
        def child(operation, *_):
            self.operations.append(operation)
            if operation == "install_verify":
                raise RuntimeError("INTERRUPTED_AFTER_PUBLIC_REPLACE")
            if operation == "recovery_status":
                return self.receipt(operation, no_mutation=False, durable_stage="RETIRE_STARTED")
            return self.receipt(operation, target_retired_local=True)

        result = self.run_case(child)
        self.assertEqual(self.operations, ["install_verify", "recovery_status", "recover"])
        self.assertEqual(self.enabled, [False, True])
        self.assertTrue(result["forward_recovery"]["target_retired_local"])

    def test_uncertain_failed_recovery_keeps_crm_paused(self):
        def child(operation, *_):
            self.operations.append(operation)
            if operation == "recovery_status":
                return self.receipt(operation, no_mutation=False, durable_stage="RETIRE_STARTED")
            raise RuntimeError("UNCONFIRMED_PARTIAL_WRITE")

        result = self.run_case(child)
        self.assertEqual(self.enabled, [False])
        self.assertIn("rollback_error", result)
        self.assertFalse(result["crm_resume"]["enabled"])

    def test_unknown_recovery_status_cannot_imply_untouched(self):
        def child(operation, *_):
            self.operations.append(operation)
            if operation == "recovery_status":
                return self.receipt(operation, no_mutation=True, durable_stage="RETIRE_STARTED")
            raise RuntimeError("UNKNOWN_EFFECT")

        result = self.run_case(child)
        self.assertEqual(self.enabled, [False])
        self.assertIn("recovery_status_error", result)
        self.assertIn("recover", self.operations)

    def test_unconfirmed_repause_of_prior_partial_child_never_resumes(self):
        lifecycle.atomic(self.result.with_suffix(".journal.json"), dict(
            plan_sha256=self.sha, operation="install_verify", stage="CHILD_STARTED"))

        def fail_pause(enabled):
            self.enabled.append(enabled)
            raise RuntimeError("PROVIDER_PAUSE_UNCONFIRMED")

        self.api.set_enabled = fail_pause
        with self.assertRaisesRegex(RuntimeError, "PAUSE_UNCONFIRMED"):
            self.run_case(lambda *_: self.fail("Child must not run"))
        self.assertEqual(self.enabled, [False])
        self.assertFalse(self.result.exists())
        self.assertEqual(json.loads(self.result.with_suffix(".journal.json").read_text())["stage"], "CHILD_STARTED")

    def test_retry_after_resume_failure_never_repeats_completed_child(self):
        def child(operation, *_):
            self.operations.append(operation)
            return self.receipt(operation, target_retired_local=True)

        original = self.api.set_enabled
        first_resume = True

        def transient(enabled):
            nonlocal first_resume
            if enabled and first_resume:
                first_resume = False
                self.enabled.append(True)
                raise RuntimeError("TRANSIENT_RESUME_FAILURE")
            return original(enabled)

        self.api.set_enabled = transient
        with self.assertRaisesRegex(RuntimeError, "TRANSIENT_RESUME"):
            self.run_case(child)
        result = self.run_case(child)
        self.assertEqual(self.operations, ["install_verify"])
        self.assertEqual(self.enabled, [False, True, True])
        self.assertEqual(result["status"], "PASS")

    def test_child_receipt_for_other_plan_rejected(self):
        payload = self.receipt("backup")
        payload["plan_sha256"] = "0" * 64
        completed = SimpleNamespace(returncode=0, stdout=json.dumps(payload).encode(), stderr=b"")
        with patch.object(lifecycle.subprocess, "run", return_value=completed):
            with self.assertRaisesRegex(RuntimeError, "IDENTITY_MISMATCH"):
                lifecycle.child("backup", self.plan, self.sha)


if __name__ == "__main__":
    unittest.main()
