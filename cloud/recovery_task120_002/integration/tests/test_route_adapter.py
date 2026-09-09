"""Independent integration checks in new local Git repositories.

No network or production commands run here. GitHub workflow context and Actions
responses are explicit fixtures. One labelled local three-path transition
rehearsal mocks the intentionally unavailable external-writer proof; a separate
unpatched test verifies that live preparation is refused. All policy, source
identity, Git commits, tree differences and other validation execute normally.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


INTEGRATION = Path(__file__).resolve().parents[1]
PACKAGE = INTEGRATION.parent
SOURCE_ROOT = PACKAGE.parents[1]
TASK = "UA-ART-RECOVERY-TASK120-002"
REPOSITORY = "art20021986-wq/ua-art-autopilot"
HALT = "state/AUTOPILOT_HALT.json"
ARCHIVE = f"state/halt_history/{TASK}/halt.json"
RECEIPT = f"state/halt_history/{TASK}/receipt.json"


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    original = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = original
    return module


class RouteAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads((PACKAGE / "evidence/source-inventory.json").read_text())
        cls.activation = load_module("route_test_activation", INTEGRATION / "policy_activation.py")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="uaart-route-test-")
        self.addCleanup(self.temporary.cleanup)
        self.temporary_root = Path(self.temporary.name)
        self.root = self.temporary_root / "repository"
        self.root.mkdir()
        self.runner_temp = self.temporary_root / "runner"
        self.runner_temp.mkdir()
        self.home = self.temporary_root / "home"
        self.home.mkdir()
        self.original_root = self.temporary_root / "baseline-policy"
        self.original_root.mkdir()
        self.env = {
            "PATH": os.environ["PATH"], "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home), "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "Local recovery test", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Local recovery test", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_AUTHOR_DATE": "2026-09-09T07:00:00Z", "GIT_COMMITTER_DATE": "2026-09-09T07:00:00Z",
            "TZ": "UTC", "LANG": "C.UTF-8",
        }
        for relative in self.inventory["materialized_files"]:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            baseline_name = {
                self.activation.MODE: self.activation.OLD_MODE,
                self.activation.MANIFEST: self.activation.OLD_MANIFEST,
            }.get(relative)
            source = SOURCE_ROOT / relative
            if baseline_name and (SOURCE_ROOT / baseline_name).is_file():
                source = SOURCE_ROOT / baseline_name
            shutil.copyfile(source, target)
        for relative in (self.activation.MODE, self.activation.MANIFEST,
                         self.activation.APPROVAL, self.activation.HALT):
            target = self.original_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.root / relative, target)
        for relative in self.activation.CHANGED:
            shutil.copyfile(SOURCE_ROOT / relative, self.root / relative)
        for relative, content in self.activation.build_registration(
                root=self.root, original_root=self.original_root,
                registered_at="2026-09-09T07:00:00Z",
                source_commit=self.inventory["source_commit"]).items():
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        self.git("init", "--initial-branch=main")
        self.git("add", "--all")
        self.git("commit", "-m", "Explicit local route-registration fixture")
        self.initial_head = self.git("rev-parse", "HEAD").strip()
        self.initial_files = self.tracked_bytes()
        self.adapter = load_module("route_test_watchdog", self.root / "automation/transaction_watchdog.py")
        self.now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        self.queue_dir = self.runner_temp / "uaart-recovery-queue"
        self.queue_dir.mkdir()
        self.output = self.runner_temp / "uaart-recovery-proposal"
        self.run_id = "900000001"
        self.workflow_env = dict(
            self.env,
            GITHUB_ACTIONS="true", GITHUB_EVENT_NAME="workflow_dispatch",
            GITHUB_REPOSITORY=REPOSITORY, GITHUB_REPOSITORY_ID="1346296029",
            GITHUB_REF="refs/heads/main", GITHUB_SHA=self.initial_head,
            GITHUB_WORKFLOW_REF=f"{REPOSITORY}/.github/workflows/uaart_transaction_watchdog.yml@refs/heads/main",
            GITHUB_WORKFLOW_SHA=self.initial_head,
            GITHUB_ACTOR="art20021986-wq", GITHUB_ACTOR_ID="321059821",
            GITHUB_TRIGGERING_ACTOR="art20021986-wq",
            GITHUB_RUN_ID=self.run_id, GITHUB_RUN_ATTEMPT="1",
            GITHUB_WORKSPACE=str(self.root), RUNNER_TEMP=str(self.runner_temp),
            WORKFLOW_SOURCE_COMMIT=self.initial_head,
        )
        self.write_queue()

    def write_queue(self, *, observed_at=None, active=None):
        instant = observed_at or self.now
        stamp = instant.isoformat().replace("+00:00", "Z")
        metadata = {
            "schema_version": "UA-ART-RECOVERY-QUEUE-CAPTURE-1",
            "repository": REPOSITORY, "expected_main": self.initial_head,
            "capture_started_at": stamp, "capture_finished_at": stamp,
            "run_id": self.run_id,
        }
        (self.queue_dir / "metadata.json").write_text(json.dumps(metadata))
        self_record = {
            "id": int(self.run_id), "run_attempt": 1, "status": "in_progress",
            "conclusion": None, "event": "workflow_dispatch", "head_branch": "main",
            "head_sha": self.initial_head,
            "path": ".github/workflows/uaart_transaction_watchdog.yml",
            "repository": {"full_name": REPOSITORY, "id": 1346296029},
            "actor": {"login": "art20021986-wq", "id": 321059821},
            "triggering_actor": {"login": "art20021986-wq", "id": 321059821},
        }
        for status in ("pending", "queued", "in_progress", "requested", "waiting"):
            runs = [self_record] if status == "in_progress" else []
            if active and active.get("status") == status:
                runs.append(active)
            (self.queue_dir / f"{status}.json").write_text(json.dumps([
                {"total_count": len(runs), "workflow_runs": runs}
            ]))

    def git(self, *arguments):
        result = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *arguments],
            cwd=self.root, env=self.env, text=True, capture_output=True, check=True,
        )
        return result.stdout

    def tracked_bytes(self):
        return {name: (self.root / name).read_bytes()
                for name in self.git("ls-files", "-z").split("\0") if name and (self.root / name).exists()}

    def mutate_json(self, relative, **changes):
        path = self.root / relative
        data = json.loads(path.read_text())
        data.update(changes)
        path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n")

    def commit_fixture(self, message="Explicit fixture mutation"):
        self.git("add", "--all")
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD").strip()

    def assert_unchanged(self, before=None, head=None):
        self.assertEqual(self.initial_files if before is None else before, self.tracked_bytes())
        self.assertEqual(self.initial_head if head is None else head, self.git("rev-parse", "HEAD").strip())

    def propose(self, command="recovery-plan", **kwargs):
        return self.adapter.recovery_proposal(
            command, kwargs.pop("expected_main", self.initial_head), self.queue_dir,
            root=self.root, env=kwargs.pop("env", self.workflow_env),
            now=kwargs.pop("now", self.now), **kwargs)

    def rebind(self):
        self.initial_head = self.git("rev-parse", "HEAD").strip()
        self.initial_files = self.tracked_bytes()
        for key in ("GITHUB_SHA", "GITHUB_WORKFLOW_SHA", "WORKFLOW_SOURCE_COMMIT"):
            self.workflow_env[key] = self.initial_head
        self.write_queue()

    def persist_fixture_proposal(self, proposal, payloads, *, extra_file=None):
        """Commit only inside this newly created local test repository."""
        self.assertEqual(proposal["parent_commit"], self.git("rev-parse", "HEAD").strip())
        for change in proposal["changes"]:
            target = self.root / change["path"]
            if change["operation"] == "delete":
                target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                self.assertFalse(target.exists())
                target.write_bytes(payloads[change["source"]])
        if extra_file:
            (self.root / extra_file).write_text("Deliberate out-of-scope fixture mutation\n")
        return self.commit_fixture("Local fixture records " + proposal["operation"])

    def add_canary(self):
        proposal, payloads = self.propose("recovery-canary")
        commit = self.persist_fixture_proposal(proposal, payloads)
        verified = self.adapter.recovery_verify(
            proposal, commit, self.initial_head, root=self.root, env=self.workflow_env)
        self.assertEqual(verified["status"], "PASS")
        self.rebind()
        return proposal, commit

    def test_valid_plan_is_read_only_and_bound_to_real_git_tree(self):
        proposal, payloads = self.propose()
        self.assertEqual(proposal["operation"], "PLAN")
        self.assertFalse(proposal["ready"])
        self.assertEqual(proposal["parent_commit"], self.initial_head)
        self.assertEqual(proposal["parent_tree"], self.git("rev-parse", "HEAD^{tree}").strip())
        self.assertEqual(proposal["durable_queue"]["terminal_claims"], 19)
        self.assertEqual(proposal["durable_queue"]["terminal_transactions"], 6)
        self.assertEqual(proposal["changes"], [])
        self.assertEqual(payloads, {})
        self.assert_unchanged()

    def test_plan_hash_stable_across_run_and_capture_time(self):
        first, _ = self.propose()
        self.run_id = "900000002"
        self.workflow_env["GITHUB_RUN_ID"] = self.run_id
        self.now += dt.timedelta(seconds=20)
        self.write_queue()
        second, _ = self.propose()
        self.assertEqual(first["plan_sha256"], second["plan_sha256"])
        self.assertNotEqual(first["context"], second["context"])
        self.assert_unchanged()

    def test_foreign_expected_main_is_rejected(self):
        with self.assertRaisesRegex(self.adapter.WatchdogError, "SOURCE_MAIN_MISMATCH"):
            self.propose(expected_main="f" * 40)
        self.assert_unchanged()

    def test_git_head_movement_requires_new_plan(self):
        (self.root / "local-fixture-note.txt").write_text("Fixture-only concurrent Git writer\n")
        moved = self.commit_fixture()
        before = self.tracked_bytes()
        with self.assertRaisesRegex(self.adapter.WatchdogError, "HEAD_DRIFT"):
            self.propose()
        self.assert_unchanged(before, moved)

    def test_dirty_checkout_cannot_supply_recovery_inputs(self):
        path = self.root / HALT
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(self.adapter.WatchdogError, "DIRTY_CHECKOUT"):
            self.propose()

    def test_foreign_halt_refused_even_when_committed(self):
        self.mutate_json(HALT, run_id="900000099")
        self.commit_fixture()
        self.rebind()
        with self.assertRaisesRegex(self.adapter.WatchdogError, "HALT_IDENTITY"):
            self.propose()
        self.assert_unchanged()

    def test_active_claim_blocks_before_any_proposal_write(self):
        path = next(p for p in self.initial_files if p.startswith("state/claims/TASK110"))
        self.mutate_json(path, task_execution_status="RUNNING")
        self.commit_fixture()
        self.rebind()
        with self.assertRaisesRegex(self.adapter.WatchdogError, "ACTIVE_CLAIM"):
            self.propose()
        self.assert_unchanged()

    def test_pending_transaction_blocks_recovery(self):
        path = next(p for p in self.initial_files if p.startswith("state/transactions/") and "TASK120" not in p)
        self.mutate_json(path, status="OPEN")
        self.commit_fixture()
        self.rebind()
        with self.assertRaisesRegex(self.adapter.WatchdogError, "PENDING_TRANSACTION"):
            self.propose()
        self.assert_unchanged()

    def test_unexpired_auto_launch_blocks_recovery(self):
        path = next(p for p in self.initial_files if p.startswith("tasks/launch/AUTO-"))
        self.mutate_json(path, expires_at=(self.now + dt.timedelta(hours=1)).isoformat())
        self.commit_fixture()
        self.rebind()
        with self.assertRaisesRegex(self.adapter.WatchdogError, "UNEXPIRED_AUTO_LAUNCH"):
            self.propose()
        self.assert_unchanged()

    def test_stale_or_future_actions_capture_is_rejected(self):
        for offset in (-121, 1):
            with self.subTest(offset=offset):
                self.write_queue(observed_at=self.now + dt.timedelta(seconds=offset))
                with self.assertRaisesRegex(self.adapter.WatchdogError, "STALE_QUEUE"):
                    self.propose()
        self.assert_unchanged()

    def test_incomplete_pagination_cannot_look_like_empty_queue(self):
        (self.queue_dir / "queued.json").write_text(json.dumps([{"total_count": 1, "workflow_runs": []}]))
        with self.assertRaisesRegex(self.adapter.WatchdogError, "PAGINATION_INCOMPLETE"):
            self.propose()
        self.assert_unchanged()

    def test_missing_queue_status_is_rejected(self):
        (self.queue_dir / "waiting.json").unlink()
        with self.assertRaises((self.adapter.WatchdogError, FileNotFoundError)):
            self.propose()
        self.assert_unchanged()

    def test_foreign_active_run_blocks_recovery(self):
        self.write_queue(active={"id": 900000099, "status": "queued"})
        with self.assertRaisesRegex(self.adapter.WatchdogError, "ACTIVE_OR_UNTRUSTED_ACTION_RUN"):
            self.propose()
        self.assert_unchanged()

    def test_matching_run_id_does_not_allow_foreign_workflow(self):
        path = self.queue_dir / "in_progress.json"
        value = json.loads(path.read_text())
        value[0]["workflow_runs"][0]["path"] = ".github/workflows/attacker.yml"
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(self.adapter.WatchdogError, "ACTIVE_OR_UNTRUSTED_ACTION_RUN"):
            self.propose()
        self.assert_unchanged()

    def test_queue_must_include_this_trusted_workflow_run(self):
        (self.queue_dir / "in_progress.json").write_text(json.dumps([
            {"total_count": 0, "workflow_runs": []}
        ]))
        with self.assertRaisesRegex(self.adapter.WatchdogError, "CURRENT_RUN"):
            self.propose()
        self.assert_unchanged()

    def test_manual_actor_and_repeat_attempt_are_rejected(self):
        for changes in ({"GITHUB_ACTOR": "someone-else"}, {"GITHUB_TRIGGERING_ACTOR": "someone-else"},
                        {"GITHUB_RUN_ATTEMPT": "2"}, {"GITHUB_REPOSITORY_ID": "999"}):
            with self.subTest(changes=changes):
                with self.assertRaises(self.adapter.WatchdogError):
                    self.propose(env=dict(self.workflow_env, **changes))
        self.assert_unchanged()

    def test_output_must_be_outside_checkout_and_cannot_overwrite(self):
        proposal, payloads = self.propose()
        with self.assertRaisesRegex(self.adapter.WatchdogError, "OUTPUT_MUST_BE_OUTSIDE_CHECKOUT"):
            self.adapter._rwrite_output(self.root / "report", self.root, proposal, payloads)
        self.adapter._rwrite_output(self.output, self.root, proposal, payloads)
        report = (self.output / "proposal.json").read_bytes()
        with self.assertRaisesRegex(self.adapter.WatchdogError, "OUTPUT_ALREADY_EXISTS"):
            self.adapter._rwrite_output(self.output, self.root, proposal, payloads)
        self.assertEqual(report, (self.output / "proposal.json").read_bytes())
        self.assert_unchanged()

    def test_output_symlink_is_not_followed(self):
        proposal, payloads = self.propose()
        target = self.temporary_root / "external"
        target.mkdir()
        self.output.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(self.adapter.WatchdogError, "SYMLINK_REFUSED"):
            self.adapter._rwrite_output(self.output, self.root, proposal, payloads)
        self.assertEqual(list(target.iterdir()), [])
        self.assert_unchanged()

    def test_canary_writes_one_exact_path_and_preserves_halt(self):
        before = self.initial_files
        parent = self.initial_head
        proposal, commit = self.add_canary()
        self.assertEqual(self.git("diff-tree", "--no-commit-id", "--name-status", "-r", parent, commit).splitlines(),
                         ["A\t" + self.adapter.RECOVERY_CANARY])
        for path, content in before.items():
            self.assertEqual((self.root / path).read_bytes(), content, path)
        self.assertFalse((self.root / ARCHIVE).exists())
        self.assertFalse((self.root / RECEIPT).exists())
        self.assertEqual(proposal["application_writes"], 0)

    def test_canary_repeat_is_noop_without_second_commit(self):
        self.add_canary()
        proposal, payloads = self.propose("recovery-canary")
        self.assertEqual(proposal["operation"], "NOOP")
        self.assertFalse(proposal["ready"])
        self.assertEqual(proposal["changes"], [])
        self.assertEqual(payloads, {})
        self.assert_unchanged()

    def test_canary_noop_still_requires_current_runtime_policy(self):
        self.add_canary()
        path = self.root / "automation/control_plane.py"
        path.write_bytes(path.read_bytes() + b"\n# Deliberate fixture policy drift\n")
        self.commit_fixture()
        self.rebind()
        with self.assertRaises(self.adapter.cp.ControlPlaneError):
            self.propose("recovery-canary")
        self.assert_unchanged()

    def test_canary_changed_then_restored_is_not_immutable_evidence(self):
        self.add_canary()
        path = self.root / self.adapter.RECOVERY_CANARY
        original = path.read_bytes()
        path.write_bytes(original + b"\n")
        self.commit_fixture("Fixture-only receipt alteration")
        path.write_bytes(original)
        self.commit_fixture("Fixture-only restoration cannot erase history")
        self.rebind()
        with self.assertRaisesRegex(self.adapter.WatchdogError, "CANARY_IMMUTABLE_HISTORY_REQUIRED"):
            self.propose("recovery-canary")
        self.assert_unchanged()

    def test_execute_requires_exact_separate_owner_command(self):
        self.add_canary()
        plan, _ = self.propose()
        for command in ("", "подключай проверенный маршрут исполнения.", "СНЯТЬ HALT " + TASK):
            with self.subTest(command=command):
                with self.assertRaisesRegex(self.adapter.WatchdogError, "SEPARATE_OWNER_COMMAND_REQUIRED"):
                    self.propose("recovery-execute", plan_sha256=plan["plan_sha256"], owner_confirmation=command)
        self.assert_unchanged()

    def test_execute_requires_exact_plan_hash(self):
        self.add_canary()
        with self.assertRaisesRegex(self.adapter.WatchdogError, "PLAN_APPROVAL_MISMATCH"):
            self.propose("recovery-execute", plan_sha256="0" * 64,
                         owner_confirmation="СНЯТЬ HALT " + TASK + " " + "0" * 64)
        self.assert_unchanged()

    def test_execute_requires_immutable_committed_canary(self):
        plan, _ = self.propose()
        with self.assertRaisesRegex(self.adapter.WatchdogError, "VERIFIED_CANARY_REQUIRED"):
            self.propose("recovery-execute", plan_sha256=plan["plan_sha256"],
                         owner_confirmation="СНЯТЬ HALT " + TASK + " " + plan["plan_sha256"])
        self.assert_unchanged()

    def test_real_execute_refuses_without_external_writer_verification(self):
        self.add_canary()
        plan, _ = self.propose()
        with self.assertRaisesRegex(self.adapter.WatchdogError, "EXTERNAL_WRITER_VERIFICATION_REQUIRED"):
            self.propose("recovery-execute", plan_sha256=plan["plan_sha256"],
                         owner_confirmation="СНЯТЬ HALT " + TASK + " " + plan["plan_sha256"])
        self.assert_unchanged()

    def test_local_rehearsal_changes_three_paths_and_verifies_real_git_commit(self):
        self.add_canary()
        before = self.initial_files
        parent = self.initial_head
        plan, _ = self.propose()
        # Explicit local-only fixture exception. The unpatched test above
        # proves this unavailable live prerequisite continues to block.
        with patch.object(self.adapter, "_rexternal_writers_verified", return_value=None):
            proposal, payloads = self.propose("recovery-execute", plan_sha256=plan["plan_sha256"],
                             owner_confirmation="СНЯТЬ HALT " + TASK + " " + plan["plan_sha256"])
        self.assert_unchanged()
        commit = self.persist_fixture_proposal(proposal, payloads)
        verified = self.adapter.recovery_verify(proposal, commit, parent, root=self.root, env=self.workflow_env)
        self.assertEqual(verified["status"], "PASS")
        self.assertEqual(verified["verified_operation"], "EXECUTE")
        self.assertTrue(verified["git_commit_verified"])
        self.assertFalse(verified["live_write_verified"])
        self.assertEqual(set(verified["changes"]), {HALT, ARCHIVE, RECEIPT})
        self.assertFalse((self.root / HALT).exists())
        self.assertEqual((self.root / ARCHIVE).read_bytes(), before[HALT])
        for path, content in before.items():
            if path != HALT:
                self.assertEqual((self.root / path).read_bytes(), content, path)

    def test_readback_rejects_extra_git_change(self):
        proposal, payloads = self.propose("recovery-canary")
        commit = self.persist_fixture_proposal(proposal, payloads, extra_file="unexpected-fixture.txt")
        with self.assertRaisesRegex(self.adapter.WatchdogError, "RESULT_WRITE_SCOPE"):
            self.adapter.recovery_verify(proposal, commit, self.initial_head, root=self.root, env=self.workflow_env)

    def test_readback_rejects_modified_proposal_hash(self):
        proposal, payloads = self.propose("recovery-canary")
        commit = self.persist_fixture_proposal(proposal, payloads)
        proposal["plan_sha256"] = "0" * 64
        with self.assertRaisesRegex(self.adapter.WatchdogError, "RESULT_PLAN_HASH"):
            self.adapter.recovery_verify(proposal, commit, self.initial_head, root=self.root, env=self.workflow_env)

    def test_committed_symlink_input_is_rejected(self):
        target = self.temporary_root / "foreign-halt"
        target.write_bytes((self.root / HALT).read_bytes())
        (self.root / HALT).unlink()
        (self.root / HALT).symlink_to(target)
        self.commit_fixture()
        self.rebind()
        with self.assertRaisesRegex(self.adapter.WatchdogError, "NONREGULAR_INPUT"):
            self.propose()


if __name__ == "__main__":
    unittest.main()
