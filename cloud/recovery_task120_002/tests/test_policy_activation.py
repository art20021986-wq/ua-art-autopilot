"""Narrow regression checks for runtime authorization extension, without writes to main."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT.parent / "recovery-work"
BASE_COMMIT = "2ce0c3a886f124c5865c564a7073ef1805861f1c"


def original_bytes(relative):
    if BASE.is_dir():
        return (BASE / relative).read_bytes()
    # A full repository checkout contains the immutable pre-registration parent.
    # This fallback reads local Git objects only and never fetches or writes.
    return subprocess.check_output(
        ["git", "-c", "core.hooksPath=/dev/null", "show", BASE_COMMIT + ":" + relative],
        cwd=ROOT, stderr=subprocess.PIPE,
    )


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pa = load("route_policy_activation", ROOT / "cloud/recovery_task120_002/integration/policy_activation.py")
cp = load("route_control_plane", ROOT / "automation/control_plane.py")


class RuntimeActivationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "candidate"
        self.original = Path(self.temp.name) / "original"
        manifest = json.loads(original_bytes(pa.MANIFEST))
        inputs = set(manifest["files"]) | {pa.MODE, pa.MANIFEST, pa.APPROVAL, pa.HALT,
                                         "state/MANUAL_MODE.md", "state/receipts/TASK107-R2.json"}
        for root in (self.root, self.original):
            for relative in inputs:
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
                (root / relative).write_bytes(original_bytes(relative))
        shutil.copyfile(ROOT / "automation/control_plane.py", self.root / "automation/control_plane.py")
        for relative in pa.CHANGED - {"automation/control_plane.py"}:
            with (self.root / relative).open("ab") as handle:
                handle.write(b"\n# local authorization test fixture\n")
        self.kwargs = dict(root=self.root, original_root=self.original,
                           registered_at="2026-09-09T10:00:00Z", source_commit="2ce0c3a886f124c5865c564a7073ef1805861f1c")

    def activate(self):
        result = pa.build_registration(**self.kwargs)
        for relative, data in result.items():
            (self.root / relative).parent.mkdir(parents=True, exist_ok=True)
            (self.root / relative).write_bytes(data)
        return result

    def verify(self):
        mode = json.loads((self.root / pa.MODE).read_bytes())
        return cp._verify_runtime_activation(
            root=self.root, mode=mode,
            approval=json.loads((self.root / pa.APPROVAL).read_bytes()),
            runtime=json.loads((self.root / pa.MANIFEST).read_bytes()),
            runtime_sha=mode["runtime_manifest_sha256"],
        )

    def alter_activation(self, key, value):
        record = json.loads((self.root / pa.ACTIVATION).read_bytes())
        record[key] = value
        data = pa.encode(record)
        (self.root / pa.ACTIVATION).write_bytes(data)
        mode = json.loads((self.root / pa.MODE).read_bytes())
        mode["runtime_activation_sha256"] = pa.digest(data)
        (self.root / pa.MODE).write_bytes(pa.encode(mode))

    def test_builder_data_only_exact_five_files(self):
        before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        result = pa.build_registration(**self.kwargs)
        self.assertEqual(set(result), {pa.OLD_MANIFEST, pa.OLD_MODE, pa.MANIFEST, pa.ACTIVATION, pa.MODE})
        after = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(result[pa.OLD_MODE], (self.original / pa.MODE).read_bytes())
        self.assertEqual(result[pa.OLD_MANIFEST], (self.original / pa.MANIFEST).read_bytes())

    def test_exact_registration_passes_and_preserves_original_owner_command(self):
        self.activate()
        self.assertEqual(self.verify().isoformat(), "2026-09-09T10:00:00+00:00")
        self.assertEqual((self.root / pa.APPROVAL).read_bytes(), (self.original / pa.APPROVAL).read_bytes())
        self.assertEqual((self.root / pa.HALT).read_bytes(), (self.original / pa.HALT).read_bytes())

    def test_halt_still_blocks_normal_execution(self):
        self.activate()
        with self.assertRaisesRegex(cp.ControlPlaneError, "AUTOMATIC_MODE_HALTED"):
            cp.verify_execution_mode(root=self.root, required_mode="AUTOMATIC")

    def test_recovery_readonly_validation_keeps_all_original_mode_guards(self):
        self.activate()
        # These fixture YAML bytes are intentionally not the deployable workflow.
        # Isolate mode authorization checks; the real workflow has its own full test.
        with patch.object(cp, "verify_production_credential_workflow_policy", return_value={"status": "PASS"}):
            result = cp.verify_execution_mode(root=self.root, allow_halt_for_recovery=True)
            self.assertTrue(result["production_requires_gate_b"])
            self.assertTrue(result["production_requires_owner_approval"])
            self.assertFalse(result["allow_replay_existing_launch_markers"])
            mode = json.loads((self.root / pa.MODE).read_bytes())
            mode["production_requires_gate_b"] = False
            (self.root / pa.MODE).write_bytes(pa.encode(mode))
            with self.assertRaisesRegex(cp.ControlPlaneError, "EXECUTION_MODE_REQUIRED_TRUE"):
                cp.verify_execution_mode(root=self.root, allow_halt_for_recovery=True)

    def test_builder_rejects_fourth_runtime_change(self):
        with (self.root / "automation/task_ticket.py").open("ab") as handle:
            handle.write(b"\n# unauthorized\n")
        with self.assertRaisesRegex(pa.ActivationError, "RUNTIME_CHANGED_SET"):
            pa.build_registration(**self.kwargs)

    def test_builder_rejects_modified_original_authority(self):
        (self.original / pa.APPROVAL).write_bytes(b"{}")
        with self.assertRaisesRegex(pa.ActivationError, "BASELINE_SHA"):
            pa.build_registration(**self.kwargs)

    def test_builder_rejects_changed_halt(self):
        (self.root / pa.HALT).write_bytes(b"{}")
        with self.assertRaisesRegex(pa.ActivationError, "INPUT_ALREADY_CHANGED"):
            pa.build_registration(**self.kwargs)

    def test_builder_rejects_repeated_activation(self):
        self.activate()
        with self.assertRaises(pa.ActivationError):
            pa.build_registration(**self.kwargs)

    def test_scope_cannot_authorize_halt_or_production(self):
        self.activate()
        for key in ("halt_removal_authorized", "production_changes_authorized"):
            self.alter_activation(key, True)
            with self.assertRaisesRegex(cp.ControlPlaneError, "SCOPE_ESCALATION"):
                self.verify()
            self.alter_activation(key, False)

    def test_foreign_command_and_owner_rejected_even_with_new_record_hash(self):
        self.activate()
        self.alter_activation("owner_command", "resume")
        with self.assertRaisesRegex(cp.ControlPlaneError, "IDENTITY_MISMATCH"):
            self.verify()

    def test_previous_mode_cannot_be_rewritten(self):
        self.activate()
        old = json.loads((self.root / pa.OLD_MODE).read_bytes())
        old["activated_at"] = "2026-09-05T10:00:00Z"
        data = pa.encode(old)
        (self.root / pa.OLD_MODE).write_bytes(data)
        self.alter_activation("previous_mode_sha256", pa.digest(data))
        with self.assertRaisesRegex(cp.ControlPlaneError, "IDENTITY_MISMATCH"):
            self.verify()

    def test_activation_duplicate_keys_rejected(self):
        self.activate()
        data = (self.root / pa.ACTIVATION).read_bytes().rstrip()[:-1] + b', "task_id": "foreign"}\n'
        (self.root / pa.ACTIVATION).write_bytes(data)
        mode = json.loads((self.root / pa.MODE).read_bytes())
        mode["runtime_activation_sha256"] = pa.digest(data)
        (self.root / pa.MODE).write_bytes(pa.encode(mode))
        with self.assertRaisesRegex(cp.ControlPlaneError, "DUPLICATE_KEY"):
            self.verify()

    def test_activation_parent_symlink_rejected(self):
        self.activate()
        parent = self.root / "state/runtime_activations"
        other = self.root / "state/elsewhere"
        parent.rename(other)
        parent.symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(cp.ControlPlaneError, "SYMLINK"):
            self.verify()

    def test_record_hash_mismatch_rejected(self):
        self.activate()
        with (self.root / pa.ACTIVATION).open("ab") as handle:
            handle.write(b" ")
        with self.assertRaisesRegex(cp.ControlPlaneError, "SHA_MISMATCH"):
            self.verify()


class RecoveryWorkflowPolicyTests(unittest.TestCase):
    relative = ".github/workflows/uaart_transaction_watchdog.yml"

    def setUp(self):
        self.source = (ROOT / self.relative).read_text()

    def verify(self, source=None):
        cp._verify_recovery_route_workflow_policy(source or self.source, self.relative)

    def change_job(self, job_id, old, new):
        job = dict(cp._workflow_job_blocks(self.source, self.relative))[job_id]
        self.assertIn(old, job)
        return self.source.replace(job, job.replace(old, new), 1)

    def test_actual_complete_workflow_policy_without_mocks(self):
        self.assertEqual(cp.verify_production_credential_workflow_policy(root=ROOT)["status"], "PASS")

    def test_push_cannot_trigger_on_general_state_changes(self):
        source = self.source.replace("      - 'state/runtime_activations/UA-ART-RECOVERY-TASK120-002.json'", "      - 'state/**'", 1)
        with self.assertRaisesRegex(cp.ControlPlaneError, "PUSH_SCOPE"):
            self.verify(source)

    def test_execute_cannot_run_from_push(self):
        source = self.change_job("recovery_execute", "github.event_name == 'workflow_dispatch' &&", "(github.event_name == 'workflow_dispatch' || github.event_name == 'push') &&")
        with self.assertRaisesRegex(cp.ControlPlaneError, "MANUAL_ONLY"):
            self.verify(source)

    def test_canary_cannot_remove_halt(self):
        source = self.change_job("recovery_canary", "EXPECTED_PATHS=", "# git update-index --force-remove\n          EXPECTED_PATHS=")
        with self.assertRaisesRegex(cp.ControlPlaneError, "CANARY_HALT_PRESERVATION"):
            self.verify(source)

    def test_execute_requires_independent_command_and_plan(self):
        source = self.change_job("recovery_execute", "inputs.owner_confirmation", "inputs.unrelated")
        with self.assertRaisesRegex(cp.ControlPlaneError, "EXECUTE_APPROVAL_BINDING"):
            self.verify(source)

    def test_old_recovery_jobs_cannot_start_from_registration(self):
        source = self.change_job("discover", "github.event_name == 'schedule'", "github.event_name == 'push'")
        with self.assertRaisesRegex(cp.ControlPlaneError, "LEGACY_EVENT_SCOPE"):
            self.verify(source)

    def test_canary_requires_exact_ref_compare_and_swap(self):
        source = self.change_job("recovery_canary", '--force-with-lease="refs/heads/main:$PARENT"', "--force")
        with self.assertRaisesRegex(cp.ControlPlaneError, "EXACT_CAS"):
            self.verify(source)

    def test_accepted_descendant_must_preserve_reviewed_runtime(self):
        source = self.change_job("recovery_execute", '/usr/bin/git diff --quiet "$PARENT" "$ACCEPTED" -- "${RUNTIME_PATHS[@]}"', "true")
        with self.assertRaisesRegex(cp.ControlPlaneError, "EXACT_CAS"):
            self.verify(source)


if __name__ == "__main__":
    unittest.main()
