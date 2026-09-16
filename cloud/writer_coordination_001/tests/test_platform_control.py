import copy
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import urllib.error

MODULE = Path(__file__).resolve().parents[1] / "platform_control.py"
spec = importlib.util.spec_from_file_location("platform_control_under_test", MODULE)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def inventory():
    result = {"always_on": [], "schedule": []}
    for (kind, ident), fields in p.KNOWN.items():
        result[kind].append({"id": ident, "enabled": True, **fields})
    result["always_on"][0]["state"] = "Running"
    return result


def plan_for(rows):
    return p.build_plan(rows, main_sha="a" * 40, run_id="34323968311", nonce="a" * 64,
                        epoch=12, owner_review="owner-approved-exact-reviewed-plan")


def authorization(plan):
    return {"status": "AUTHORIZED", **{k: plan[k] for k in ("plan_sha256", "main_sha", "run_id", "nonce", "epoch")}}


def terminal(receipt, plan):
    return {"status": "VERIFIED_NO_DATA_WRITE", "receipt_sha256": p.digest(receipt),
            **{k: plan[k] for k in ("plan_sha256", "run_id", "nonce", "epoch")}}


def completion(plan, intent):
    return {"status": "REMOTE_REQUEST_COMPLETED", "plan_sha256": plan["plan_sha256"],
            "intent_seq": intent["seq"], "receipt_sha256": "c" * 64}


class FakeAPI:
    def __init__(self, rows=None):
        self.rows = copy.deepcopy(rows or inventory())
        self.calls = []
        self.failure = None
        self.before_mutation = None

    def inventory(self):
        return copy.deepcopy(self.rows)

    def set_enabled(self, kind, ident, enabled):
        if self.before_mutation:
            self.before_mutation(kind, ident, enabled)
        self.calls.append((kind, ident, enabled))
        if self.failure == "before":
            self.failure = None
            raise TimeoutError("secret must not escape")
        for row in self.rows[kind]:
            if row["id"] == ident:
                row["enabled"] = enabled
        if self.failure == "after":
            self.failure = None
            raise TimeoutError("secret must not escape")


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "journal"
        self.api = FakeAPI()
        self.plan = plan_for(self.api.rows)
        self.controller = p.Controller(self.api, self.root, verify_plan=authorization)

    def test_import_and_plan_never_mutate(self):
        self.assertEqual([], self.api.calls)
        self.assertFalse(self.root.exists())
        p.validate_plan(self.plan)

    def test_happy_pause_restore_and_repeat_are_idempotent(self):
        outcome = self.controller.pause(self.plan)
        self.assertEqual("PAUSED_CONFIGURATION_VERIFIED", outcome["status"])
        self.assertFalse(outcome["external_writer_proof"])
        self.assertEqual(4, len(self.api.calls))
        self.controller.pause(self.plan)
        self.assertEqual(4, len(self.api.calls))
        result = self.controller.restore(self.plan, {"terminal": 1}, verify_terminal=terminal)
        self.assertEqual("TASK_CONFIGURATION_RESTORED", result["status"])
        self.assertFalse(result["runtime_health_verified"])
        self.assertEqual(("always_on", 266084, True), self.api.calls[-1])
        self.assertEqual(self.plan["tasks"], p.normalize_inventory(self.api.rows))
        self.controller.restore(self.plan, {"terminal": 1}, verify_terminal=terminal)
        self.assertEqual(8, len(self.api.calls))

    def test_original_disabled_task_never_enabled(self):
        self.api.rows["schedule"][0]["enabled"] = False
        self.plan = plan_for(self.api.rows)
        self.controller.pause(self.plan)
        self.controller.restore(self.plan, {}, verify_terminal=terminal)
        self.assertNotIn(("schedule", 1502215, True), self.api.calls)
        self.assertEqual(6, len(self.api.calls))

    def test_unknown_missing_duplicate_and_config_drift_refuse_before_write(self):
        variations = []
        rows = inventory(); rows["schedule"].append({**rows["schedule"][0], "id": 999}); variations.append(rows)
        rows = inventory(); rows["schedule"].pop(); variations.append(rows)
        rows = inventory(); rows["schedule"].append(rows["schedule"][0]); variations.append(rows)
        rows = inventory(); rows["schedule"][0]["minute"] = 27; variations.append(rows)
        rows = inventory(); rows["always_on"][0]["command"] += " changed"; variations.append(rows)
        for rows in variations:
            with self.subTest(rows=rows), self.assertRaises(p.CoordinationError):
                plan_for(rows)
        self.assertEqual([], self.api.calls)

    def test_enabled_is_strict_boolean(self):
        self.api.rows["always_on"][0]["enabled"] = 1
        with self.assertRaises(p.CoordinationError):
            plan_for(self.api.rows)

    def test_drift_after_plan_refuses(self):
        self.api.rows["schedule"][1]["enabled"] = False
        with self.assertRaisesRegex(p.CoordinationError, "INVENTORY_CHANGED"):
            self.controller.pause(self.plan)
        self.assertEqual([], self.api.calls)

    def test_additional_provider_field_preserved_and_drift_detected(self):
        self.api.rows["schedule"][0]["new_setting"] = "old"
        self.plan = plan_for(self.api.rows)
        self.api.rows["schedule"][0]["new_setting"] = "changed"
        with self.assertRaisesRegex(p.CoordinationError, "INVENTORY_CHANGED"):
            self.controller.pause(self.plan)

    def test_runtime_state_not_configuration_or_quiescence_proof(self):
        self.api.rows["always_on"][0]["state"] = "Starting"
        result = self.controller.pause(self.plan)
        self.assertFalse(result["external_writer_proof"])

    def test_intent_is_durable_before_first_patch(self):
        def observe(*_):
            data = self.root.joinpath("journal.jsonl").read_text()
            latest = json.loads(data.splitlines()[-1])
            self.assertEqual("INTENT", latest["event"])
        self.api.before_mutation = observe
        self.controller.pause(self.plan)

    def test_timeout_after_effect_blocks_retry_until_explicit_readback(self):
        self.api.failure = "after"
        with self.assertRaisesRegex(p.CoordinationError, "MUTATION_UNCERTAIN"):
            self.controller.pause(self.plan)
        self.assertEqual(1, len(self.api.calls))
        with self.assertRaisesRegex(p.CoordinationError, "MUTATION_UNCERTAIN"):
            self.controller.pause(self.plan)
        self.assertEqual(1, len(self.api.calls))
        self.assertEqual("INTENT_EFFECT_OBSERVED", self.controller.reconcile(self.plan, verify_completion=completion)["status"])
        self.controller.pause(self.plan)
        self.assertEqual(4, len(self.api.calls))

    def test_timeout_without_effect_remains_uncertain_without_retry(self):
        self.api.failure = "before"
        with self.assertRaises(p.CoordinationError):
            self.controller.pause(self.plan)
        with self.assertRaises(p.CoordinationError):
            self.controller.reconcile(self.plan)
        with self.assertRaises(p.CoordinationError):
            self.controller.pause(self.plan)
        self.assertEqual(1, len(self.api.calls))

    def test_partial_pause_drift_does_not_unpause_blindly(self):
        def drift(kind, ident, enabled):
            self.api.rows["schedule"][2]["description"] = "owner changed this"
        self.api.before_mutation = drift
        with self.assertRaises(p.CoordinationError):
            self.controller.pause(self.plan)
        with self.assertRaises(p.CoordinationError):
            self.controller.restore(self.plan, {}, verify_terminal=terminal)
        self.assertEqual(1, len(self.api.calls))

    def test_failed_restore_is_not_reported_complete_or_retried(self):
        self.controller.pause(self.plan)
        self.api.failure = "after"
        with self.assertRaises(p.CoordinationError):
            self.controller.restore(self.plan, {}, verify_terminal=terminal)
        with self.assertRaises(p.CoordinationError):
            self.controller.restore(self.plan, {}, verify_terminal=terminal)
        self.assertEqual(5, len(self.api.calls))
        self.assertNotIn('"event":"RESTORED"', self.root.joinpath("journal.jsonl").read_text())
        self.controller.reconcile(self.plan, verify_completion=completion)
        self.controller.restore(self.plan, {}, verify_terminal=terminal)
        self.assertEqual(8, len(self.api.calls))

    def test_verified_terminal_receipt_required_not_boolean(self):
        self.controller.pause(self.plan)
        for value in (True, {}, {"status": "VERIFIED_COMMITTED"}):
            with self.subTest(value=value), self.assertRaises(p.CoordinationError):
                self.controller.restore(self.plan, {}, verify_terminal=lambda *_: value)
        self.assertEqual(4, len(self.api.calls))

    def test_terminal_cannot_be_replaced_mid_restore(self):
        self.controller.pause(self.plan)
        self.api.failure = "after"
        with self.assertRaises(p.CoordinationError):
            self.controller.restore(self.plan, {"v": 1}, verify_terminal=terminal)
        self.controller.reconcile(self.plan, verify_completion=completion)
        with self.assertRaisesRegex(p.CoordinationError, "TERMINAL_RECEIPT_CHANGED"):
            self.controller.restore(self.plan, {"v": 2}, verify_terminal=terminal)

    def test_authorization_must_bind_all_fields(self):
        for key in ("plan_sha256", "main_sha", "run_id", "nonce", "epoch"):
            auth = authorization(self.plan); auth[key] = "wrong"
            bad = p.Controller(self.api, self.root, verify_plan=lambda *_: auth)
            with self.subTest(key=key), self.assertRaisesRegex(p.CoordinationError, "AUTHORIZATION"):
                bad.pause(self.plan)
        self.assertEqual([], self.api.calls)

    def test_authorization_rechecked_before_each_patch(self):
        calls = []
        def auth(plan):
            calls.append(1)
            return authorization(plan) if len(calls) < 3 else False
        self.controller.verify_plan = auth
        with self.assertRaisesRegex(p.CoordinationError, "AUTHORIZATION"):
            self.controller.pause(self.plan)
        self.assertEqual(1, len(self.api.calls))

    def test_concurrent_controller_refused(self):
        self.root.mkdir(mode=0o700)
        with self.root.joinpath("coordinator.lock").open("w") as lock:
            os.fchmod(lock.fileno(), 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(p.CoordinationError, "COORDINATOR_BUSY"):
                self.controller.pause(self.plan)
        self.assertEqual([], self.api.calls)

    def test_other_plan_cannot_take_journal(self):
        self.controller.pause(self.plan)
        other = p.build_plan(self.api.rows, main_sha="b" * 40, run_id="22", nonce="b" * 64, epoch=13, owner_review="new")
        with self.assertRaisesRegex(p.CoordinationError, "OWNERSHIP"):
            self.controller.pause(other)
        self.assertEqual(4, len(self.api.calls))

    def test_torn_journal_refuses(self):
        self.root.mkdir(mode=0o700)
        self.root.joinpath("journal.jsonl").write_bytes(b'{"incomplete":')
        self.root.joinpath("journal.jsonl").chmod(0o600)
        with self.assertRaisesRegex(p.CoordinationError, "JOURNAL_INCOMPLETE"):
            self.controller.pause(self.plan)
        self.assertEqual([], self.api.calls)

    def test_symlink_journal_refuses(self):
        self.root.mkdir(mode=0o700)
        target = Path(self.tmp.name) / "target"
        target.write_text("private")
        self.root.joinpath("journal.jsonl").symlink_to(target)
        with self.assertRaises(OSError):
            self.controller.pause(self.plan)
        self.assertEqual("private", target.read_text())

    def test_hardlinked_journal_refuses_without_touching_other_file(self):
        self.root.mkdir(mode=0o700)
        target = Path(self.tmp.name) / "other"
        target.touch(mode=0o600)
        os.link(target, self.root / "journal.jsonl")
        with self.assertRaisesRegex(p.CoordinationError, "RESOURCE_CHANGED_OR_UNSAFE"):
            self.controller.pause(self.plan)
        self.assertEqual(b"", target.read_bytes())
        self.assertEqual([], self.api.calls)

    def test_fifo_journal_refuses_without_hanging(self):
        self.root.mkdir(mode=0o700)
        os.mkfifo(self.root / "journal.jsonl", 0o600)
        with self.assertRaisesRegex(p.CoordinationError, "RESOURCE_CHANGED_OR_UNSAFE"):
            self.controller.pause(self.plan)
        self.assertEqual([], self.api.calls)

    def test_replaced_lock_refuses_next_mutation(self):
        def replace_once(*_):
            self.api.before_mutation = None
            self.root.joinpath("coordinator.lock").unlink()
            self.root.joinpath("coordinator.lock").touch(mode=0o600)
        self.api.before_mutation = replace_once
        with self.assertRaisesRegex(p.CoordinationError, "RESOURCE_CHANGED_OR_UNSAFE"):
            self.controller.pause(self.plan)
        self.assertEqual(1, len(self.api.calls))

    def test_plain_target_readback_keeps_uncertainty(self):
        self.api.failure = "after"
        with self.assertRaises(p.CoordinationError):
            self.controller.pause(self.plan)
        result = self.controller.reconcile(self.plan)
        self.assertEqual("INTENT_EFFECT_OBSERVED_UNSETTLED", result["status"])
        with self.assertRaises(p.CoordinationError):
            self.controller.pause(self.plan)
        with self.assertRaises(p.CoordinationError):
            self.controller.restore(self.plan, {}, verify_terminal=terminal)
        with self.assertRaisesRegex(p.CoordinationError, "REMOTE_COMPLETION_PROOF_REQUIRED"):
            self.controller.reconcile(self.plan, verify_completion=lambda *_: True)
        self.assertEqual(1, len(self.api.calls))

    def test_forged_journal_transition_refuses(self):
        self.root.mkdir(mode=0o700)
        event = {"seq": 0, "plan_sha256": self.plan["plan_sha256"], "event": "RESTORED", "receipt_sha256": "a" * 64}
        self.root.joinpath("journal.jsonl").write_bytes(p.canonical(event) + b"\n")
        self.root.joinpath("journal.jsonl").chmod(0o600)
        with self.assertRaisesRegex(p.CoordinationError, "JOURNAL_TRANSITION"):
            self.controller.pause(self.plan)
        self.assertEqual([], self.api.calls)

    def test_parent_symlink_refuses(self):
        real = Path(self.tmp.name) / "real"
        real.mkdir()
        alias = Path(self.tmp.name) / "alias"
        alias.symlink_to(real, target_is_directory=True)
        c = p.Controller(self.api, alias / "journal", verify_plan=authorization)
        with self.assertRaisesRegex(p.CoordinationError, "JOURNAL_PARENT_SYMLINK"):
            c.pause(self.plan)
        self.assertEqual([], self.api.calls)

    def test_fence_compatible_binding_limits(self):
        for override in ({"run_id": "0"}, {"run_id": "1" * 21}, {"nonce": "x" * 64},
                         {"nonce": "a" * 63}, {"epoch": 2**63}, {"epoch": True}):
            args = {"main_sha": "a" * 40, "run_id": "1", "nonce": "b" * 64, "epoch": 1, "owner_review": "ref"}
            args.update(override)
            with self.subTest(override=override), self.assertRaises(p.CoordinationError):
                p.build_plan(inventory(), **args)

    def test_malformed_plan_is_structured_failure(self):
        for tasks in (None, [None] * 4, [{"kind": []}] * 4):
            bad = {**self.plan, "tasks": tasks}
            with self.subTest(tasks=tasks), self.assertRaises(p.CoordinationError):
                self.controller.pause(bad)


class FakeResponse:
    def __init__(self, url, data=b"[]", status=200):
        self.url, self.data, self.status = url, data, status
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def geturl(self): return self.url
    def read(self, size): return self.data[:size]


class TransportTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"API_TOKEN": "s" * 40})
        patcher.start(); self.addCleanup(patcher.stop)
        self.transport = p.PATransport()
        self.requests = []
        self.transport._opener = mock.Mock()
        def opened(req, timeout):
            self.requests.append(req)
            self.assertEqual(20, timeout)
            return FakeResponse(req.full_url)
        self.transport._opener.open.side_effect = opened
        sleeper = mock.patch.object(p.time, "sleep")
        self.sleep = sleeper.start(); self.addCleanup(sleeper.stop)

    def test_only_fixed_get_and_enabled_patch(self):
        self.transport.inventory()
        self.transport.set_enabled("always_on", 266084, False)
        self.assertEqual(["GET", "GET", "PATCH"], [r.method for r in self.requests])
        self.assertEqual({"enabled": False}, json.loads(self.requests[-1].data))
        self.assertTrue(all(r.full_url.startswith(p.BASE) for r in self.requests))
        self.assertTrue(self.sleep.called)

    def test_arbitrary_task_or_endpoint_refused(self):
        for args in (("schedule", 999, False), ("files", 266084, False), ("schedule", 1502215, 0)):
            with self.subTest(args=args), self.assertRaises(p.CoordinationError):
                self.transport.set_enabled(*args)
        self.assertEqual([], self.requests)

    def test_redirect_rejected(self):
        with self.assertRaisesRegex(p.CoordinationError, "REDIRECT"):
            p._NoRedirect().redirect_request(None, None, 302, "", {}, "https://evil.invalid")

    def test_response_origin_rejected(self):
        self.transport._opener.open.side_effect = lambda *_args, **_kw: FakeResponse("https://evil.invalid")
        with self.assertRaisesRegex(p.CoordinationError, "ORIGIN"):
            self.transport.inventory()

    def test_large_inventory_rejected(self):
        self.transport._opener.open.side_effect = lambda req, **_kw: FakeResponse(req.full_url, b"x" * (p.MAX_BYTES + 1))
        with self.assertRaisesRegex(p.CoordinationError, "TOO_LARGE"):
            self.transport.inventory()

    def test_error_body_and_credentials_never_leak(self):
        secret = "private token or response"
        self.transport._opener.open.side_effect = urllib.error.HTTPError(p.BASE, 403, secret, {}, io.BytesIO(secret.encode()))
        with self.assertRaisesRegex(p.CoordinationError, "^PA_HTTP_403$") as caught:
            self.transport.inventory()
        self.assertNotIn(secret, str(caught.exception))

    def test_ambiguous_patch_not_retried(self):
        self.transport._opener.open.side_effect = TimeoutError("private token")
        with self.assertRaisesRegex(p.CoordinationError, "^PA_REQUEST_UNCERTAIN$"):
            self.transport.set_enabled("always_on", 266084, False)
        self.assertEqual(1, self.transport._opener.open.call_count)


if __name__ == "__main__":
    unittest.main()
