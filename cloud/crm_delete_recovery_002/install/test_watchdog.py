"""Offline watchdog contracts: no network, real process launch, or real signals."""
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest import mock

import watchdog as w


class FakeClock:
    def __init__(self):
        self.value = 1000.0
        self.on_sleep = None

    def now(self):
        return self.value

    def sleep(self, duration):
        self.value += duration
        if self.on_sleep:
            self.on_sleep()


class FakeProcesses:
    def __init__(self, owner):
        self.owner = owner
        self.records = {owner: self.item(owner, owner), owner + 1: self.item(owner + 1, owner),
                        os.getpid(): self.item(os.getpid(), os.getpgrp(), session=os.getpgrp())}
        self.signals = []
        self.ignore_term = False

    @staticmethod
    def item(pid, group, session=None, ticks=900):
        return {"pid": pid, "pgid": group, "session": session or group,
                "start_ticks": ticks, "state": "S"}

    def identity(self, pid):
        item = self.records.get(pid)
        return dict(item) if item else None

    def members(self, pgid):
        return [dict(item) for item in self.records.values()
                if item["pgid"] == pgid and item["state"] not in ("Z", "X")]

    def send(self, identity, sig):
        actual = self.identity(identity["pid"])
        w.require(actual is None or w.same_process(actual, identity), "PID_REUSE_REFUSED")
        self.signals.append((identity["pid"], sig))
        if not self.ignore_term or sig == signal.SIGKILL:
            self.records.pop(identity["pid"], None)

    def preflight(self, identity):
        w.require(w.same_process(self.identity(identity["pid"]), identity), "PREFLIGHT_IDENTITY")


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "context.json"
        self.source = self.root / "lifecycle_controller.py"
        self.watchdog_source = self.root / "watchdog.py"
        self.manifest = self.root / "manifest.json"
        self.plan = self.root / "lifecycle-plan.json"
        for path, raw in ((self.source, b"RECOVERY_ONLY = True\n"),
                          (self.watchdog_source, b"WATCHDOG = True\n"),
                          (self.manifest, b'{"task":"fixture"}'),
                          (self.plan, b'{"mode":"recovery"}')):
            self.write(path, raw)
        self.owner = 991231
        self.data = dict(owner_pid=self.owner, start_ticks=900, pgid=self.owner, deadline_epoch=1100,
                         result_path=str(self.root / "result.json"),
                         recovery_argv=[sys.executable, "-I", "-B", str(self.source), "--recover", str(self.path),
                                        "--context-sha256", w.CONTEXT_HASH_MARKER],
                         recovery_source_sha256=w.sha(self.source.read_bytes()),
                         watchdog_source_sha256=w.sha(self.watchdog_source.read_bytes()),
                         package_manifest_path=str(self.manifest), package_manifest_sha256=w.sha(self.manifest.read_bytes()),
                         lifecycle_plan_path=str(self.plan), lifecycle_plan_sha256=w.sha(self.plan.read_bytes()),
                         credential_env_names=[])
        self.clock = FakeClock()
        self.proc = FakeProcesses(self.owner)
        self.calls = []
        self.context = self.bind()

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write(path, raw):
        path.write_bytes(raw)
        path.chmod(0o600)

    def bind(self):
        self.write(self.path, w.encoded(self.data))
        self.digest = w.sha(self.path.read_bytes())
        argv = self.data["recovery_argv"][:-1] + [self.digest]
        return w.BoundContext(self.path, self.digest, self.data["watchdog_source_sha256"], argv,
                              watchdog_source=self.watchdog_source)

    def terminal(self, status="RECOVERED", **changes):
        w.durable_json(self.context.result, {**self.context.binding(), "status": status, **changes})

    def recover(self, context):
        self.assertEqual([], self.proc.members(self.owner))
        self.calls.append(context.recovery_argv)
        self.terminal()
        return 0

    def watch(self, recover=None):
        return w.watch(self.context, processes=self.proc, now=self.clock.now, sleep=self.clock.sleep,
                       monotonic=self.clock.now, recover=recover or self.recover)

    def outcome(self):
        return json.loads(self.context.outcome.read_bytes())

    def test_context_raw_hash_and_fixed_expanded_argv(self):
        self.assertEqual(w.sha(self.path.read_bytes()), self.context.sha256)
        self.assertEqual(self.digest, self.context.recovery_argv[-1])
        self.assertEqual(w.CONTEXT_HASH_MARKER, self.data["recovery_argv"][-1])
        with self.assertRaisesRegex(w.WatchdogError, "FIXED_RECOVERY_ARGV"):
            w.BoundContext(self.path, self.digest, self.data["watchdog_source_sha256"],
                           ["sh", "-c", "anything"], watchdog_source=self.watchdog_source)

    def test_changed_context_hash_refused(self):
        self.write(self.path, self.path.read_bytes() + b" ")
        with self.assertRaisesRegex(w.WatchdogError, "HASH_MISMATCH"):
            w.BoundContext(self.path, self.digest, self.data["watchdog_source_sha256"], watchdog_source=self.watchdog_source)

    def test_changed_recovery_watchdog_plan_manifest_refused(self):
        for path in (self.source, self.watchdog_source, self.plan, self.manifest):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                self.write(path, original + b" ")
                with self.assertRaisesRegex(w.WatchdogError, "BOUND_FILE_CHANGED"):
                    self.context.revalidate()
                self.write(path, original)
                self.context = self.bind()

    def test_identical_source_replacement_refused(self):
        replacement = self.root / "replacement.py"
        self.write(replacement, self.source.read_bytes())
        replacement.replace(self.source)
        with self.assertRaisesRegex(w.WatchdogError, "BOUND_FILE_CHANGED"):
            self.context.revalidate()

    def test_path_escape_and_symlink_refused(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "result.json"
            self.data["result_path"] = str(target)
            with self.assertRaisesRegex(w.WatchdogError, "CONTEXT_PATH_ESCAPE"):
                self.bind()
        self.data["result_path"] = str(self.root / "result.json")
        self.context = self.bind()
        original = self.source.read_bytes()
        target = self.root / "actual.py"
        self.write(target, original)
        self.source.unlink()
        self.source.symlink_to(target)
        with self.assertRaisesRegex(w.WatchdogError, "CANONICAL_PATH"):
            self.bind()

    def test_public_context_directory_refused(self):
        self.root.chmod(0o755)
        try:
            with self.assertRaisesRegex(w.WatchdogError, "PRIVATE_CONTEXT_DIRECTORY"):
                self.bind()
        finally:
            self.root.chmod(0o700)

    def test_argv_token_or_extra_switch_refused(self):
        for bad in ([sys.executable, "-c", "print('TOKEN')"],
                    self.data["recovery_argv"] + ["--token=secret"],
                    [sys.executable, "-I", "-B", str(self.source), "--install", str(self.path),
                     "--context-sha256", w.CONTEXT_HASH_MARKER]):
            with self.subTest(argv_length=len(bad)):
                self.data["recovery_argv"] = bad
                with self.assertRaisesRegex(w.WatchdogError, "FIXED_RECOVERY_ARGV"):
                    self.bind()

    def test_owner_pid_reuse_refuses_all_signals_and_dispatch(self):
        self.clock.on_sleep = lambda: self.proc.records[self.owner].update(start_ticks=901)
        self.assertEqual(1, self.watch())
        self.assertEqual([], self.proc.signals)
        self.assertEqual([], self.calls)
        self.assertEqual("OWNER_PID_REUSE_REFUSED", self.outcome()["error_code"])

    def test_child_pid_reuse_refuses_group_signals(self):
        self.clock.on_sleep = lambda: self.proc.records[self.owner + 1].update(start_ticks=901)
        self.assertEqual(1, self.watch())
        self.assertEqual([], self.proc.signals)
        self.assertEqual([], self.calls)
        self.assertEqual("GROUP_PID_REUSE_REFUSED", self.outcome()["error_code"])

    def test_death_stops_only_observed_children_before_dispatch(self):
        self.clock.on_sleep = lambda: self.proc.records.pop(self.owner, None)
        self.assertEqual(0, self.watch())
        self.assertEqual([(self.owner + 1, signal.SIGTERM)], self.proc.signals)
        self.assertEqual(1, len(self.calls))
        ready = json.loads(self.context.ready.read_bytes())
        self.assertEqual("READY", ready["status"])
        self.assertEqual(self.digest, ready["context_sha256"])
        self.assertEqual(0o600, self.context.ready.stat().st_mode & 0o777)
        self.assertEqual("RECOVERY_COMPLETE", self.outcome()["status"])

    def test_unobserved_surviving_child_blocks_unsafe_recovery(self):
        def changed():
            self.proc.records.pop(self.owner, None)
            self.proc.records[self.owner + 2] = self.proc.item(self.owner + 2, self.owner, ticks=950)
        self.clock.on_sleep = changed
        self.assertEqual(1, self.watch())
        self.assertEqual([], self.proc.signals)
        self.assertEqual([], self.calls)
        self.assertEqual("UNOBSERVED_SURVIVING_GROUP_MEMBER", self.outcome()["error_code"])

    def test_deadline_term_then_bounded_kill(self):
        self.data["deadline_epoch"] = 1000.1
        self.context = self.bind()
        self.proc.ignore_term = True
        self.assertEqual(0, self.watch())
        self.assertEqual([(self.owner, signal.SIGTERM), (self.owner + 1, signal.SIGTERM),
                          (self.owner, signal.SIGKILL), (self.owner + 1, signal.SIGKILL)], self.proc.signals)
        self.assertLess(self.clock.value, 1010)
        self.assertEqual(1, len(self.calls))

    def test_new_child_during_term_is_stopped_while_leader_anchors_group(self):
        self.proc.ignore_term = True
        def fork_once():
            if self.owner + 2 not in self.proc.records:
                self.proc.records[self.owner + 2] = self.proc.item(self.owner + 2, self.owner, ticks=901)
                self.clock.on_sleep = None
        self.clock.on_sleep = fork_once
        w.stop_owner_group(self.context, self.proc, {}, monotonic=self.clock.now, sleep=self.clock.sleep)
        self.assertIn((self.owner + 2, signal.SIGTERM), self.proc.signals)
        self.assertIn((self.owner + 2, signal.SIGKILL), self.proc.signals)
        self.assertEqual([], self.proc.members(self.owner))
        self.assertLess(self.clock.value, 1009)

    def test_valid_terminal_result_skips_signals_and_recovery(self):
        self.terminal("COMPLETE")
        self.assertEqual(0, self.watch())
        self.assertEqual([], self.proc.signals)
        self.assertEqual([], self.calls)
        self.assertEqual("OWNER_TERMINAL", self.outcome()["status"])

    def test_wrong_terminal_binding_cannot_suppress_watchdog(self):
        self.terminal("COMPLETE", context_sha256="f" * 64)
        self.assertEqual(1, self.watch())
        self.assertEqual([], self.calls)
        self.assertEqual("TERMINAL_RESULT_BINDING", self.outcome()["error_code"])

    def test_recovery_blocked_is_failure_without_repeat(self):
        self.clock.on_sleep = lambda: self.proc.records.pop(self.owner, None)
        def recovery(context):
            self.calls.append(True)
            self.terminal("BLOCKED")
            return 1
        self.assertEqual(1, self.watch(recovery))
        self.assertEqual("BLOCKED", self.outcome()["status"])
        with self.assertRaisesRegex(w.WatchdogError, "ALREADY_CONSUMED"):
            self.watch(recovery)
        self.assertEqual(1, len(self.calls))

    def test_subprocess_zero_without_bound_terminal_is_not_success(self):
        self.clock.on_sleep = lambda: self.proc.records.pop(self.owner, None)
        def recovery(context):
            self.calls.append(True)
            self.assertEqual("RECOVERY_DISPATCHED", self.outcome()["status"])
            return 0
        self.assertEqual(1, self.watch(recovery))
        self.assertEqual("BLOCKED", self.outcome()["status"])
        self.assertEqual(1, len(self.calls))

    def test_verified_rollback_exit_one_is_successful_recovery(self):
        self.clock.on_sleep = lambda: self.proc.records.pop(self.owner, None)
        def recovery(context):
            self.calls.append(True)
            self.terminal("ROLLED_BACK")
            return 1
        self.assertEqual(0, self.watch(recovery))
        self.assertEqual("RECOVERY_COMPLETE", self.outcome()["status"])
        self.assertEqual("ROLLED_BACK", self.outcome()["owner_status"])

    def test_source_drift_after_ready_never_dispatches(self):
        self.clock.on_sleep = lambda: self.write(self.source, b"UNAPPROVED = True\n")
        self.assertEqual(1, self.watch())
        self.assertEqual([], self.calls)
        self.assertEqual([], self.proc.signals)
        self.assertEqual("BOUND_FILE_CHANGED", self.outcome()["error_code"])

    def test_recovery_environment_filters_all_unrequested_credentials(self):
        self.data["credential_env_names"] = ["PYTHONANYWHERE_API_TOKEN"]
        self.context = self.bind()
        with mock.patch.dict(os.environ, {"PYTHONANYWHERE_API_TOKEN": "private-fixture-value",
                                          "TELEGRAM_TOKEN": "do-not-forward", "PYTHONPATH": "/untrusted"}):
            process = mock.Mock(pid=self.owner)
            process.wait.return_value = 0
            self.proc.records[self.owner]["state"] = "Z"
            with mock.patch.object(w.subprocess, "Popen", return_value=process) as run, \
                    mock.patch.object(w, "LinuxProcesses", return_value=self.proc):
                self.assertEqual(0, w._recover(self.context))
                args, kwargs = run.call_args
                self.assertEqual(self.context.recovery_argv, args[0])
                self.assertEqual({"PATH", "LANG", "PYTHONANYWHERE_API_TOKEN"}, set(kwargs["env"]))
                self.assertFalse(kwargs["shell"])
                self.assertEqual(w.subprocess.DEVNULL, kwargs["stdout"])
                self.assertEqual(w.subprocess.DEVNULL, kwargs["stderr"])
                self.assertTrue(kwargs["start_new_session"])
                process.wait.assert_called_once_with(timeout=w.KILL_SECONDS)
                process.poll.assert_not_called()
                self.assertEqual([(self.owner + 1, signal.SIGTERM)], self.proc.signals)
        self.assertNotIn("private-fixture-value", self.path.read_text())

    def test_arbitrary_credential_name_refused(self):
        self.data["credential_env_names"] = ["TELEGRAM_TOKEN"]
        with self.assertRaisesRegex(w.WatchdogError, "CREDENTIAL_ALLOWLIST"):
            self.bind()

    def test_singleton_lock_refuses_duplicate_watchdog(self):
        with w.watchdog_lock(self.context):
            with self.assertRaisesRegex(w.WatchdogError, "ALREADY_ACTIVE"):
                with w.watchdog_lock(self.context):
                    self.fail("duplicate lock acquired")

    def test_inspection_cli_has_no_launch_or_recovery(self):
        with mock.patch.object(w.subprocess, "Popen") as launch, mock.patch.object(w.subprocess, "run") as run:
            with mock.patch("builtins.print") as output:
                self.assertEqual(0, w.main([]))
            self.assertEqual("INSPECT_ONLY", json.loads(output.call_args.args[0])["mode"])
            launch.assert_not_called()
            run.assert_not_called()

    def prepare_launcher(self):
        self.watchdog_source = Path(w.__file__).absolute()
        self.data.update(watchdog_source_sha256=w.sha(self.watchdog_source.read_bytes()),
                         owner_pid=os.getpid(), pgid=os.getpid())
        self.context = self.bind()
        self.proc.records[os.getpid()] = self.proc.item(os.getpid(), os.getpid())
        child = 991245
        self.proc.records[child] = self.proc.item(child, child, ticks=1200)
        process = mock.Mock(pid=child)
        process.poll.return_value = None
        return process

    def test_launcher_waits_for_hash_and_identity_bound_durable_ready(self):
        process = self.prepare_launcher()
        def spawn(argv, **kwargs):
            self.assertEqual([sys.executable, "-I", "-B", str(self.watchdog_source), "--watch", str(self.path),
                              "--context-sha256", self.digest, "--watchdog-sha256", self.data["watchdog_source_sha256"]], argv)
            self.assertTrue(kwargs["start_new_session"])
            self.assertFalse(kwargs["shell"])
            self.assertEqual({"PATH", "LANG"}, set(kwargs["env"]))
            w.durable_json(self.context.ready, {**self.context.binding(), "status": "READY", "watchdog_pid": process.pid,
                           "watchdog_start_ticks": 1200, "watchdog_source_sha256": self.data["watchdog_source_sha256"],
                           "recovery_source_sha256": self.data["recovery_source_sha256"]})
            return process
        with mock.patch.object(w, "LinuxProcesses", return_value=self.proc), mock.patch.object(w.time, "time", return_value=1000):
            with mock.patch.object(w.subprocess, "Popen", side_effect=spawn):
                receipt = w.launch_watchdog(self.path, self.digest, self.data["watchdog_source_sha256"], self.context.recovery_argv)
        self.assertEqual("READY", receipt["status"])
        process.terminate.assert_not_called()

    def test_launcher_rejects_forged_readiness_and_terminates_its_child(self):
        process = self.prepare_launcher()
        def spawn(*args, **kwargs):
            w.durable_json(self.context.ready, {**self.context.binding(), "status": "READY", "watchdog_pid": process.pid,
                           "watchdog_start_ticks": 1201, "watchdog_source_sha256": self.data["watchdog_source_sha256"],
                           "recovery_source_sha256": self.data["recovery_source_sha256"]})
            return process
        with mock.patch.object(w, "LinuxProcesses", return_value=self.proc), mock.patch.object(w.time, "time", return_value=1000):
            with mock.patch.object(w.subprocess, "Popen", side_effect=spawn):
                with self.assertRaisesRegex(w.WatchdogError, "READINESS_PROCESS_IDENTITY"):
                    w.launch_watchdog(self.path, self.digest, self.data["watchdog_source_sha256"], self.context.recovery_argv)
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=1)

    def test_launcher_rejects_ready_after_watchdog_has_blocked(self):
        process = self.prepare_launcher()
        def spawn(*args, **kwargs):
            w.durable_json(self.context.ready, {**self.context.binding(), "status": "READY", "watchdog_pid": process.pid,
                           "watchdog_start_ticks": 1200, "watchdog_source_sha256": self.data["watchdog_source_sha256"],
                           "recovery_source_sha256": self.data["recovery_source_sha256"]})
            w.durable_json(self.context.outcome, {**self.context.binding(), "status": "BLOCKED"})
            return process
        with mock.patch.object(w, "LinuxProcesses", return_value=self.proc), mock.patch.object(w.time, "time", return_value=1000):
            with mock.patch.object(w.subprocess, "Popen", side_effect=spawn):
                with self.assertRaisesRegex(w.WatchdogError, "NO_LONGER_READY"):
                    w.launch_watchdog(self.path, self.digest, self.data["watchdog_source_sha256"], self.context.recovery_argv)
        process.terminate.assert_called_once()

    def test_pidfd_failure_prevents_readiness(self):
        with mock.patch.object(self.proc, "preflight", side_effect=PermissionError("fixture")):
            self.assertEqual(1, self.watch())
        self.assertFalse(self.context.ready.exists())
        self.assertEqual([], self.calls)
        self.assertEqual("PermissionError", self.outcome()["error_code"])

    def test_wall_clock_backwards_does_not_extend_deadline(self):
        self.data["deadline_epoch"] = 1000.1
        self.context = self.bind()
        wall = mock.Mock(side_effect=[1000])
        self.assertEqual(0, w.watch(self.context, processes=self.proc, now=wall, sleep=self.clock.sleep,
                                   monotonic=self.clock.now, recover=self.recover))
        self.assertEqual(1, wall.call_count)
        self.assertLess(self.clock.value, 1001)

    def test_recovery_timeout_cleans_child_group_before_reaping_leader(self):
        process = mock.Mock(pid=self.owner)
        def wait(**kwargs):
            self.assertEqual([], self.proc.members(self.owner))
            return -15
        process.wait.side_effect = wait
        with mock.patch.object(w.subprocess, "Popen", return_value=process), \
                mock.patch.object(w, "LinuxProcesses", return_value=self.proc), \
                mock.patch.object(w.time, "monotonic", side_effect=self.clock.now), \
                mock.patch.object(w.time, "sleep", side_effect=lambda duration: self.clock.sleep(10)):
            with self.assertRaisesRegex(w.WatchdogError, "RECOVERY_DEADLINE_EXCEEDED"):
                w._recover(self.context)
        self.assertEqual([(self.owner, signal.SIGTERM), (self.owner + 1, signal.SIGTERM)], self.proc.signals)
        process.poll.assert_not_called()
        process.wait.assert_called_once_with(timeout=w.KILL_SECONDS)

    def test_slow_provider_recovery_finishes_within_reserved_budget(self):
        process = mock.Mock(pid=self.owner)
        process.wait.return_value = 0
        def progress(duration):
            self.clock.value += 60
            if self.clock.value >= 1300:
                self.proc.records[self.owner]["state"] = "Z"
                self.proc.records.pop(self.owner + 1, None)
        with mock.patch.object(w.subprocess, "Popen", return_value=process), \
                mock.patch.object(w, "LinuxProcesses", return_value=self.proc), \
                mock.patch.object(w.time, "monotonic", side_effect=self.clock.now), \
                mock.patch.object(w.time, "sleep", side_effect=progress):
            self.assertEqual(0, w._recover(self.context))
        self.assertGreater(self.clock.value - 1000, 120)
        self.assertLess(self.clock.value - 1000, w.RECOVERY_SECONDS)
        self.assertEqual([], self.proc.signals)
        process.wait.assert_called_once_with(timeout=w.KILL_SECONDS)

    def test_initial_recovery_identity_failure_stops_owned_child_and_blocks(self):
        process = mock.Mock(pid=self.owner)
        process.wait.return_value = -15
        with mock.patch.object(w.subprocess, "Popen", return_value=process), \
                mock.patch.object(w, "LinuxProcesses", return_value=self.proc), \
                mock.patch.object(self.proc, "identity", side_effect=OSError("fixture")):
            with self.assertRaisesRegex(w.WatchdogError, "IDENTITY_UNPROVEN_GROUP_CLEANUP_REQUIRED"):
                w._recover(self.context)
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=w.TERM_SECONDS)

    def test_recovery_source_drift_still_cleans_launched_process_group(self):
        process = mock.Mock(pid=self.owner)
        process.wait.return_value = -15
        self.clock.on_sleep = lambda: self.write(self.source, b"CHANGED = True\n")
        with mock.patch.object(w.subprocess, "Popen", return_value=process), \
                mock.patch.object(w, "LinuxProcesses", return_value=self.proc), \
                mock.patch.object(w.time, "monotonic", side_effect=self.clock.now), \
                mock.patch.object(w.time, "sleep", side_effect=self.clock.sleep):
            with self.assertRaisesRegex(w.WatchdogError, "BOUND_FILE_CHANGED"):
                w._recover(self.context)
        self.assertEqual([], self.proc.members(self.owner))
        self.assertEqual([(self.owner, signal.SIGTERM), (self.owner + 1, signal.SIGTERM)], self.proc.signals)
        process.wait.assert_called_once_with(timeout=w.KILL_SECONDS)

    def test_proc_parser_handles_spaces_and_closing_parenthesis(self):
        fields = ["S", "1", "17", "17"] + ["0"] * 15 + ["987654"] + ["0"] * 10
        line = "17 (owner ) with spaces) " + " ".join(fields)
        with mock.patch.object(Path, "read_text", return_value=line):
            item = w.LinuxProcesses().identity(17)
        self.assertEqual(987654, item["start_ticks"])
        self.assertEqual(17, item["pgid"])
        self.assertEqual(17, item["session"])

    def test_pidfd_rechecks_identity_before_signal(self):
        proc = w.LinuxProcesses()
        identity = self.proc.item(self.owner, self.owner)
        with mock.patch.object(os, "pidfd_open", return_value=54321), mock.patch.object(os, "close") as close:
            with mock.patch.object(proc, "identity", return_value={**identity, "start_ticks": 999}), \
                    mock.patch.object(signal, "pidfd_send_signal") as send:
                with self.assertRaisesRegex(w.WatchdogError, "PID_REUSE_REFUSED"):
                    proc.send(identity, signal.SIGTERM)
                send.assert_not_called()
            close.assert_called_once_with(54321)


if __name__ == "__main__":
    unittest.main()
