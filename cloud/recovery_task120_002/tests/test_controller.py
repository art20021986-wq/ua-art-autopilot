"""Independent recovery-controller checks; mutations are confined to temp copies."""
import copy
from datetime import datetime, timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PACKAGE.parents[1]
HALT = "state/AUTOPILOT_HALT.json"
ARCHIVE = "state/halt_history/UA-ART-RECOVERY-TASK120-002/halt.json"
RECEIPT = "state/halt_history/UA-ART-RECOVERY-TASK120-002/receipt.json"


class ControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("recovery_controller_under_test", PACKAGE / "controller.py")
        cls.controller = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.controller
        spec.loader.exec_module(cls.controller)
        cls.base_inventory = json.loads((PACKAGE / "evidence/source-inventory.json").read_text())
        cls.base_queue = json.loads((PACKAGE / "evidence/queue-review.json").read_text())

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repository"
        self.root.mkdir()
        self.inventory = copy.deepcopy(self.base_inventory)
        self.queue = copy.deepcopy(self.base_queue)
        for relative in self.inventory["materialized_files"]:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE_ROOT / relative, target)
        self.evidence = self.root / "cloud/recovery_task120_002/evidence"
        self.evidence.mkdir(parents=True)
        (self.evidence / "source-inventory.json").write_text(json.dumps(self.inventory))
        (self.evidence / "queue-review.json").write_text(json.dumps(self.queue))
        self.now = datetime.fromisoformat(self.queue["produced_at"].replace("Z", "+00:00")) + timedelta(seconds=1)

    def prepare(self):
        return self.controller.prepare_plan(self.root, self.inventory, self.queue, self.now)

    def input_bytes(self):
        return {relative: (self.root / relative).read_bytes() for relative in self.inventory["materialized_files"]}

    def mutate_json(self, relative, **changes):
        path = self.root / relative
        value = json.loads(path.read_text())
        value.update(changes)
        path.write_text(json.dumps(value))

    def test_valid_snapshot_is_deterministic_inert_and_not_execution_ready(self):
        before = self.input_bytes()
        plan = self.prepare()
        self.assertEqual(plan["preflight_status"], "PASS")
        self.assertFalse(plan["execution_ready"])
        self.assertRegex(plan["plan_sha256"], r"^[0-9a-f]{64}$")
        blockers = json.dumps(plan["execution_blockers"])
        for reason in ("LIVE_RUNNER_NOT_REGISTERED", "NO_SEPARATE_EXECUTION_COMMAND", "EXTERNAL_WRITERS_UNVERIFIED"):
            self.assertIn(reason, blockers)
        self.assertEqual(plan, self.prepare())
        self.assertEqual(before, self.input_bytes())
        self.assertTrue((self.root / HALT).is_file())
        self.assertFalse((self.root / ARCHIVE).exists())
        self.assertFalse((self.root / RECEIPT).exists())

    def test_mutation_proposal_contains_only_halt_archive_and_receipt(self):
        plan = self.prepare()
        operations = plan["mutation_plan"]
        self.assertEqual(len(operations), 3)
        self.assertEqual([(row["operation"], row["path"]) for row in operations],
                         [("delete", HALT), ("add", ARCHIVE), ("add", RECEIPT)])
        self.assertEqual(operations[0]["expected_sha256"], operations[1]["content_sha256"])
        self.assertTrue(all(row["must_not_exist"] for row in operations[1:]))
        self.assertEqual(plan["atomic_transition"], "one_git_commit_and_compare_and_swap_of_expected_main_ref")
        encoded = json.dumps(plan["mutation_plan"])
        self.assertIn(HALT, encoded)
        self.assertIn(ARCHIVE, encoded)
        self.assertIn(RECEIPT, encoded)
        self.assertNotIn("state/EXECUTION_MODE.json", encoded)
        self.assertNotIn("tasks/launch/", encoded)
        self.assertNotIn("crm.db", encoded)

    def test_tampered_pinned_source_rejected(self):
        path = self.root / "automation/control_plane.py"
        path.write_bytes(path.read_bytes() + b"\n# changed fixture\n")
        with self.assertRaises(self.controller.RecoveryError):
            self.prepare()

    def test_changed_halt_identity_rejected(self):
        self.mutate_json(HALT, run_id="different-run")
        changed = (self.root / HALT).read_bytes()
        with self.assertRaises(self.controller.RecoveryError):
            self.prepare()
        self.assertEqual(changed, (self.root / HALT).read_bytes())

    def test_changed_reconciliation_rejected(self):
        relative = next(path for path in self.inventory["materialized_files"] if path.startswith("state/reconciliations/TASK120"))
        self.mutate_json(relative, production_touched=True)
        with self.assertRaises(self.controller.RecoveryError):
            self.prepare()

    def test_missing_or_added_scoped_input_rejected(self):
        relative = next(path for path in self.inventory["materialized_files"] if path.startswith("state/claims/"))
        original = (self.root / relative).read_bytes()
        (self.root / relative).unlink()
        with self.assertRaises(self.controller.RecoveryError):
            self.prepare()
        (self.root / relative).write_bytes(original)
        (self.root / "state/claims/UNREVIEWED.json").write_text('{"status":"FINISHED"}')
        with self.assertRaises(self.controller.RecoveryError):
            self.prepare()

    def test_symlinked_scoped_input_rejected(self):
        path = self.root / HALT
        outside = Path(self.temporary.name) / "outside-halt.json"
        outside.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaises(self.controller.RecoveryError):
            self.prepare()

    def test_incomplete_materialized_inventory_rejected(self):
        self.inventory["materialized_files"].pop()
        with self.assertRaises(self.controller.RecoveryError):
            self.prepare()

    def test_claim_cannot_be_hidden_by_removing_file_and_both_inventory_entries(self):
        relative = next(path for path in self.inventory["materialized_files"] if path.startswith("state/claims/"))
        (self.root / relative).unlink()
        self.inventory["materialized_files"].remove(relative)
        self.inventory["tree_entries"] = [entry for entry in self.inventory["tree_entries"] if entry["path"] != relative]
        with self.assertRaisesRegex(self.controller.RecoveryError, "GIT_TREE_CONTENT_MISMATCH:state/claims"):
            self.prepare()

    def test_unreviewed_source_commit_or_root_tree_is_rejected(self):
        for field in ("source_commit", "source_tree"):
            with self.subTest(field=field):
                self.inventory = copy.deepcopy(self.base_inventory)
                self.inventory[field] = "0" * 40
                with self.assertRaisesRegex(self.controller.RecoveryError, "UNREVIEWED_SOURCE_REVISION"):
                    self.prepare()

    def test_consistent_forged_blob_and_entry_still_fail_original_git_tree(self):
        relative = next(path for path in self.inventory["materialized_files"] if path.startswith("state/claims/"))
        record = json.loads((self.root / relative).read_text())
        record["adversarial_fixture_note"] = "changed with matching blob metadata"
        payload = json.dumps(record, sort_keys=True).encode()
        (self.root / relative).write_bytes(payload)
        entry = next(entry for entry in self.inventory["tree_entries"] if entry["path"] == relative)
        entry["sha"] = hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
        entry["size"] = len(payload)
        with self.assertRaisesRegex(self.controller.RecoveryError, "GIT_TREE_CONTENT_MISMATCH:state/claims"):
            self.prepare()

    def test_stale_or_future_actions_observation_rejected(self):
        with self.subTest(case="stale"):
            previous = self.now
            self.now += timedelta(seconds=601)
            with self.assertRaises(self.controller.RecoveryError):
                self.prepare()
            self.now = previous
        with self.subTest(case="future"):
            self.queue["actions"]["statuses"][0]["observed_at"] = (self.now + timedelta(minutes=5)).isoformat()
            with self.assertRaises(self.controller.RecoveryError):
                self.prepare()

    def test_missing_or_incomplete_actions_status_rejected(self):
        self.queue["actions"]["statuses"].pop()
        with self.assertRaises(self.controller.RecoveryError):
            self.prepare()
        self.queue = copy.deepcopy(self.base_queue)
        self.queue["actions"]["statuses"][0]["all_pages_read"] = False
        with self.assertRaises(self.controller.RecoveryError):
            self.prepare()

    def test_actions_raw_body_cannot_hide_an_active_run(self):
        entry = self.queue["actions"]["statuses"][0]
        entry["raw_body"] = '{"total_count":0,"workflow_runs":[{"id":42,"status":"in_progress"}]}'
        entry["raw_body_sha256"] = hashlib.sha256(entry["raw_body"].encode()).hexdigest()
        with self.assertRaises(self.controller.RecoveryError):
            self.prepare()

    def test_wrong_repository_actions_url_rejected(self):
        self.queue["actions"]["statuses"][0]["url"] = "https://api.github.com/repos/unrelated/repo/actions/runs?status=pending&per_page=100&page=1"
        with self.assertRaises(self.controller.RecoveryError):
            self.prepare()

    def test_active_claim_or_pending_transaction_rejected(self):
        for scope, state in (("state/claims/", "RUNNING"), ("state/transactions/", "OPEN")):
            with self.subTest(scope=scope):
                relative = next(path for path in self.inventory["materialized_files"] if path.startswith(scope))
                data = self.input_bytes()
                record = json.loads(data[relative])
                record["task_execution_status" if scope == "state/claims/" else "status"] = state
                data[relative] = json.dumps(record).encode()
                with self.assertRaisesRegex(self.controller.RecoveryError, "ACTIVE_OR_UNKNOWN_CLAIM" if scope == "state/claims/" else "PENDING_OR_UNKNOWN_TRANSACTION"):
                    self.controller.inspect_queue_records(data, self.now)

    def test_naive_now_is_not_accepted_as_utc(self):
        self.now = self.now.replace(tzinfo=None)
        with self.assertRaisesRegex(self.controller.RecoveryError, "NOW_REQUIRES_TIMEZONE"):
            self.prepare()

    def test_new_eligible_auto_launch_rejected(self):
        path = self.root / "tasks/launch/AUTO-UNREVIEWED.json"
        path.write_text(json.dumps({"task_id": "UNREVIEWED", "production_allowed": True,
                                    "expires_at": (self.now + timedelta(hours=1)).isoformat()}))
        with self.assertRaises(self.controller.RecoveryError):
            self.prepare()
        data = self.input_bytes()
        template = next(payload for relative, payload in data.items() if relative.startswith("tasks/launch/AUTO-"))
        record = json.loads(template)
        record["expires_at"] = (self.now + timedelta(hours=1)).isoformat()
        data["tasks/launch/AUTO-UNREVIEWED.json"] = json.dumps(record).encode()
        with self.assertRaisesRegex(self.controller.RecoveryError, "UNREVIEWED_UNEXPIRED_AUTO_LAUNCH"):
            self.controller.inspect_queue_records(data, self.now)

    def test_execute_refuses_before_prepare_or_write(self):
        with patch.object(self.controller, "prepare_plan") as prepare, patch.object(self.controller, "write_plan") as write:
            with self.assertRaisesRegex(self.controller.RecoveryError, "NOT_READY_LIVE_RUNNER_NOT_REGISTERED"):
                self.controller.main(["execute", "--root", str(self.root)])
            prepare.assert_not_called()
            write.assert_not_called()

    def test_output_is_exclusive_and_cannot_escape_or_follow_symlink(self):
        plan = self.prepare()
        before = self.input_bytes()
        target = self.evidence / "test-plan.json"
        self.controller.write_plan(plan, self.root, target)
        self.assertTrue(target.is_file())
        self.assertEqual(before, self.input_bytes())
        with self.assertRaises(self.controller.RecoveryError):
            self.controller.write_plan(plan, self.root, target)
        with self.assertRaises(self.controller.RecoveryError):
            self.controller.write_plan(plan, self.root, self.evidence / ".." / "escaped.json")
        link = self.evidence / "linked"
        link.symlink_to(Path(self.temporary.name), target_is_directory=True)
        with self.assertRaises(self.controller.RecoveryError):
            self.controller.write_plan(plan, self.root, link / "outside.json")
        self.assertFalse((Path(self.temporary.name) / "outside.json").exists())


if __name__ == "__main__":
    unittest.main()
