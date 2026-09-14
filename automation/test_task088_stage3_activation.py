"""Canonical v5 registration tests in disposable, explicitly synthetic roots.

These fixtures test acceptance and rejection of evidence bindings. They do not
observe a live Preview, create a launch marker, or grant Production authority.
The complete earlier authority chain comes from the immutable Stage 2 commit;
the real mode and workflow verifiers run without substitute PASS functions.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.dont_write_bytecode = True

REPOSITORY = Path(__file__).resolve().parents[1]
STAGE2_COMMIT = "0c85a6561d80c4d8789b3a482ae41cdaf9d0f667"
CHANGED = (
    ".github/workflows/uaart_critical.yml",
    ".github/workflows/uaart_maintenance.yml",
    "automation/control_plane.py",
)
ACTIVATION = "state/runtime_activations/TASK088-PRICE-V5-STAGE3.json"
PREVIOUS_MODE = "state/runtime_activations/TASK088-PRICE-V5-STAGE3.previous-mode.json"
PREVIOUS_MANIFEST = "state/runtime_activations/TASK088-PRICE-V5-STAGE3.previous-manifest.json"
MODE = "state/EXECUTION_MODE.json"
MANIFEST = "state/AUTOPILOT_RUNTIME_MANIFEST.json"


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class Stage3RuntimeActivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.preview_verifier = load_module(
            "task088_activation_test_preview", REPOSITORY / "cloud/ua_ge_price_protection/verify_preview.py"
        )
        archive = subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "archive", STAGE2_COMMIT,
             "automation", "state", "tasks", ".github/workflows",
             "cloud/task088_crm_preflight", "cloud/task_088_ge_price_crm_stage1"],
            cwd=REPOSITORY, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        ).stdout
        cls.baseline_files = {}
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            for member in source.getmembers():
                relative = PurePosixPath(member.name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise AssertionError("Unsafe immutable baseline member")
                if member.isfile():
                    cls.baseline_files[relative.as_posix()] = source.extractfile(member).read()
                elif not member.isdir():
                    raise AssertionError("Immutable baseline must contain regular files only")
        cls.candidate_files = {relative: (REPOSITORY / relative).read_bytes() for relative in CHANGED}
        for relative in getattr(cls.preview_verifier.G, "CANONICAL_SOURCES", ()):
            cls.candidate_files[relative] = (REPOSITORY / relative).read_bytes()
        for relative in cls.preview_verifier.G.SOURCE_ROOTS:
            for path in (REPOSITORY / relative).rglob("*.py"):
                if path.is_symlink():
                    raise AssertionError("Candidate source symlink")
                cls.candidate_files[path.relative_to(REPOSITORY).as_posix()] = path.read_bytes()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="TEST-task088-stage3-authority-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        for relative, raw in self.baseline_files.items():
            self.put_bytes(relative, raw)
        for relative, raw in self.candidate_files.items():
            self.put_bytes(relative, raw)
        self.cp = load_module("task088_activation_test_control_plane", self.root / "automation/control_plane.py")
        self.old_mode = json.loads(self.baseline_files[MODE])
        self.old_runtime = json.loads(self.baseline_files[MANIFEST])
        self.registered_at = "2026-09-14T07:00:00Z"
        self.task = "TASK088-GE-PRICE-SITE-STAGE3-TEST-ONLY"
        self.request_path = "tasks/requests/" + self.task + ".json"
        self.manifest_path = "tasks/manifests/" + self.task + ".json"
        self.owner_path = "tasks/approvals/" + self.task + ".production.json"
        self.gate_path = "tasks/gates/" + self.task + ".json"
        self.preview_path = "state/receipts/" + self.task + ".preview.json"
        self.put_bytes(PREVIOUS_MODE, self.baseline_files[MODE])
        self.put_bytes(PREVIOUS_MANIFEST, self.baseline_files[MANIFEST])
        self.runtime = deepcopy(self.old_runtime)
        self.runtime["generated_at"] = self.registered_at
        for relative in CHANGED:
            self.runtime["files"][relative] = digest((self.root / relative).read_bytes())
        self.runtime_sha = self.put(MANIFEST, self.runtime)
        self.preview = {
            "contract": "TASK088-FINAL-V5-PREVIEW-GATE-1",
            "task_id": self.task, "status": "PASS",
            "candidate_manifest_sha256": digest(b"SYNTHETIC TEST candidate only"),
            "database": {
                "cars_sha256": digest(b"SYNTHETIC TEST cars only"),
                "audit_sha256": digest(b"SYNTHETIC TEST audit only"),
                "published_sha256": digest(b"SYNTHETIC TEST published only"),
                "published_codes": ["UA-0001", "UA-0019"],
            },
            "schema_sha256": digest(b"SYNTHETIC TEST schema only"),
            "system_inventory_sha256": digest(b"SYNTHETIC TEST inventory only"),
            "published_codes": ["UA-0001", "UA-0019"],
            "evaluated_at": self.registered_at,
            "checks": {name: "PASS" for name in self.preview_verifier.preview_checks(self.root)},
            "source_files_sha256": self.preview_verifier.G.source_inventory(self.root),
        }
        self.manifest = {
            "contract_id": "UA-ART-CRITICAL-ADAPTER-V1.0", "task_class": "CRITICAL",
            "task_id": self.task,
            "install_files_sha256": self.preview["candidate_manifest_sha256"],
            "price_event_delegation_sha256": digest(b"SYNTHETIC TEST delegation only"),
            "operations": [{"action": "replace", "path": "production/operator-ui/yadro.py",
                            "expected_before_sha256": digest(b"SYNTHETIC TEST original generator"),
                            "expected_after_sha256": digest(b"SYNTHETIC TEST candidate generator")}],
            "protected_paths": ["production/protected-vehicle-data.json"],
            "backup_required": True, "rollback_required": True, "live_verify_required": True,
            "explicit_crm_vehicle_approval": True,
            "runtime_registration": {
                "contract": "UA-ART-TASK088-PRICE-V5-RUNTIME-1",
                "runtime_manifest_sha256": self.runtime_sha,
                "previous_runtime_manifest_sha256": digest(self.baseline_files[MANIFEST]),
                "changed_runtime_paths": list(CHANGED),
                "runtime_file_sha256": {path: self.runtime["files"][path] for path in CHANGED},
                "preview_validator_sha256": digest((self.root / "cloud/ua_ge_price_protection/verify_preview.py").read_bytes()),
                "software_gate_sha256": digest((self.root / "cloud/ua_ge_price_protection/gate.py").read_bytes()),
                "installer_sha256": digest((self.root / "cloud/task088_price_sync/install_package.py").read_bytes()),
            },
        }
        self.bind()

    def put_bytes(self, relative, raw):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return digest(raw)

    def put(self, relative, value):
        return self.put_bytes(relative, encode(value))

    def read(self, relative):
        return json.loads((self.root / relative).read_bytes())

    def bind(self, *, gate_overrides=None):
        """Build coherent synthetic bindings so semantic failures are exercised."""
        preview_sha = self.put(self.preview_path, self.preview)
        manifest_sha = self.put(self.manifest_path, self.manifest)
        self.gate = {
            "contract_id": "UA-ART-CRITICAL-ADAPTER-V1.0", "production_write": False,
            "task_id": self.task, "status": "PASS", "manifest_sha256": manifest_sha,
            "tests": "PASS", "unexpected_changes": 0,
            "backup_plan_ready": True, "rollback_plan_ready": True,
            "preview_gate_sha256": preview_sha, "price_protection_preview_path": self.preview_path,
            "evaluated_at": self.registered_at,
            "protected_snapshot": {"production/protected-vehicle-data.json": digest(b"SYNTHETIC TEST protected data")},
        }
        if gate_overrides:
            self.gate.update(gate_overrides)
        gate_sha = self.put(self.gate_path, self.gate)
        self.request = {
            "task_id": self.task, "title": "SYNTHETIC TEST ONLY: v5 authority binding",
            "production_required": True, "read_only": False, "requested_min_class": "CRITICAL",
            "changed_paths": ["production/operator-ui/yadro.py"],
            "critical": {
                "manifest_path": self.manifest_path, "manifest_sha256": manifest_sha,
                "gate_a_path": self.gate_path, "gate_a_sha256": gate_sha,
                "owner_approval_path": self.owner_path, "owner_approval_sha256": "0" * 64,
                "gate_b_authorized": True, "allow_crm_vehicle_data": True,
            },
        }
        self.owner = {
            "schema_version": "UA-ART-PRODUCTION-AUTHORIZATION-1",
            "task_id": self.task, "owner": "Артём Бровинский / UA ART COMPANY LLC",
            "owner_authorized": True, "production_allowed": True, "authorized_environment": "production",
            "manifest_sha256": manifest_sha, "gate_a_sha256": gate_sha,
            "request_subject_sha256": digest(encode(self.request)),
            "authorization_id": "prod-auth-TEST-only-v5-price-registration",
            "mode_epoch": self.old_mode["mode_epoch"],
            "approved_at": "2026-09-14T06:59:00Z", "expires_at": "2026-09-14T07:30:00Z",
            "request_path": self.request_path, "launch_nonce": "TEST-only-v5-price-registration",
        }
        owner_sha = self.put(self.owner_path, self.owner)
        self.request["critical"]["owner_approval_sha256"] = owner_sha
        request_sha = self.put(self.request_path, self.request)
        self.activation = {
            "schema_version": "UA-ART-TASK088-PRICE-V5-ACTIVATION-1",
            "task_id": self.task, "scope": "REGISTER_TASK088_V5_PRICE_PIPELINE",
            "contract_id": "UA-ART-GE-UA-MARKET-PRICE-001 FINAL v5.0",
            "owner": "Артём Бровинский / UA ART COMPANY LLC", "owner_actor_id": "321059821",
            "repository": "art20021986-wq/ua-art-autopilot", "mode_epoch": self.old_mode["mode_epoch"],
            "registered_at": self.registered_at, "source_commit": STAGE2_COMMIT,
            "runtime_manifest_path": MANIFEST, "runtime_manifest_sha256": self.runtime_sha,
            "previous_mode_path": PREVIOUS_MODE, "previous_mode_sha256": digest(self.baseline_files[MODE]),
            "previous_manifest_path": PREVIOUS_MANIFEST, "previous_manifest_sha256": digest(self.baseline_files[MANIFEST]),
            "previous_activation_path": self.old_mode["runtime_activation_path"],
            "previous_activation_sha256": self.old_mode["runtime_activation_sha256"],
            "changed_runtime_paths": list(CHANGED),
            "artifacts": {name: {"path": path, "sha256": sha} for name, path, sha in (
                ("request", self.request_path, request_sha),
                ("manifest", self.manifest_path, manifest_sha),
                ("owner_approval", self.owner_path, owner_sha),
                ("gate_b", self.gate_path, gate_sha),
                ("preview_gate", self.preview_path, preview_sha),
            )},
        }
        self.rehash_activation()

    def rehash_activation(self):
        activation_sha = self.put(ACTIVATION, self.activation)
        self.mode = dict(self.old_mode, runtime_manifest_sha256=self.runtime_sha,
                         runtime_activation_path=ACTIVATION, runtime_activation_sha256=activation_sha)
        self.put(MODE, self.mode)

    def rehash_owner(self):
        """Preserve request-subject binding after an intentional owner mutation."""
        owner_sha = self.put(self.owner_path, self.owner)
        self.request["critical"]["owner_approval_sha256"] = owner_sha
        self.activation["artifacts"]["owner_approval"]["sha256"] = owner_sha
        self.activation["artifacts"]["request"]["sha256"] = self.put(self.request_path, self.request)
        self.rehash_activation()

    def verify(self):
        return self.cp.verify_execution_mode(root=self.root, required_mode="AUTOMATIC")

    def test_complete_synthetic_registration_passes_real_mode_and_workflow_verifiers(self):
        result = self.verify()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["mode"], "AUTOMATIC")
        self.assertTrue(result["production_requires_gate_b"])
        self.assertTrue(result["production_requires_owner_approval"])
        self.assertFalse(result["allow_replay_existing_launch_markers"])
        self.assertEqual(self.cp.verify_production_credential_workflow_policy(root=self.root)["status"], "PASS")

    def test_candidate_workflow_policy_pass_does_not_activate_unregistered_runtime(self):
        self.put_bytes(MODE, self.baseline_files[MODE])
        self.put_bytes(MANIFEST, self.baseline_files[MANIFEST])
        (self.root / ACTIVATION).unlink()
        self.assertEqual(self.cp.verify_production_credential_workflow_policy(root=self.root)["status"], "PASS")
        with self.assertRaisesRegex(self.cp.ControlPlaneError, "RUNTIME_PINNED_FILE_SHA_MISMATCH"):
            self.verify()

    def test_original_immutable_stage2_chain_still_passes_new_verifier(self):
        for relative in (*CHANGED, MODE, MANIFEST):
            self.put_bytes(relative, self.baseline_files[relative])
        (self.root / ACTIVATION).unlink()
        result = self.verify()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["runtime_activation_path"], self.old_mode["runtime_activation_path"])

    def test_missing_preview_file_blocks_registration(self):
        (self.root / self.preview_path).unlink()
        with self.assertRaises(self.cp.ControlPlaneError):
            self.verify()

    def test_failed_missing_and_boolean_preview_checks_block_even_with_new_hashes(self):
        pristine = deepcopy(self.preview)
        check = sorted(pristine["checks"])[0]
        for value in ("FAIL", "NOT_RUN", True, None):
            with self.subTest(value=value):
                self.preview = deepcopy(pristine)
                if value is None:
                    del self.preview["checks"][check]
                else:
                    self.preview["checks"][check] = value
                self.bind()
                with self.assertRaisesRegex(self.cp.ControlPlaneError, "PREVIEW"):
                    self.verify()

    def test_preview_must_be_fresh_at_registration(self):
        for evaluated_at in ("2026-09-14T06:29:59Z", "2026-09-14T07:00:01Z"):
            with self.subTest(evaluated_at=evaluated_at):
                self.preview["evaluated_at"] = evaluated_at
                self.bind()
                with self.assertRaisesRegex(self.cp.ControlPlaneError, "PREVIEW"):
                    self.verify()

    def test_runtime_file_cannot_change_after_registration(self):
        path = self.root / "automation/control_plane.py"
        path.write_bytes(path.read_bytes() + b"\n# TEST unauthorized later edit\n")
        # Even a coherently refreshed synthetic Preview cannot substitute for
        # the independent exact runtime pins in the registered manifest.
        self.preview["source_files_sha256"] = self.preview_verifier.G.source_inventory(self.root)
        self.bind()
        with self.assertRaisesRegex(self.cp.ControlPlaneError, "RUNTIME_PINNED_FILE_SHA_MISMATCH"):
            self.verify()

    def test_unrelated_workflow_change_is_not_granted_by_v5_registration(self):
        path = self.root / ".github/workflows/uaart_monitor.yml"
        path.write_bytes(path.read_bytes() + b"\n# TEST unrelated workflow edit\n")
        with self.assertRaisesRegex(self.cp.ControlPlaneError, "SHA|SCOPE|DRIFT|BINDING"):
            self.verify()

    def test_rehashing_an_unrelated_fourth_runtime_change_cannot_extend_scope(self):
        relative = ".github/workflows/uaart_monitor.yml"
        path = self.root / relative
        path.write_bytes(path.read_bytes() + b"\n# TEST unrelated workflow edit\n")
        self.runtime["files"][relative] = digest(path.read_bytes())
        self.runtime_sha = self.put(MANIFEST, self.runtime)
        self.manifest["runtime_registration"]["runtime_manifest_sha256"] = self.runtime_sha
        self.bind()
        with self.assertRaisesRegex(self.cp.ControlPlaneError, "PRICE_V5_RUNTIME_CHANGE_SCOPE"):
            self.verify()

    def test_only_exact_reviewed_critical_workflow_can_be_registered(self):
        relative = ".github/workflows/uaart_critical.yml"
        path = self.root / relative
        path.write_bytes(path.read_bytes() + b"\n# TEST changed reviewed workflow\n")
        self.runtime["files"][relative] = digest(path.read_bytes())
        self.runtime_sha = self.put(MANIFEST, self.runtime)
        self.manifest["runtime_registration"]["runtime_manifest_sha256"] = self.runtime_sha
        self.manifest["runtime_registration"]["runtime_file_sha256"][relative] = self.runtime["files"][relative]
        self.preview["source_files_sha256"] = self.preview_verifier.G.source_inventory(self.root)
        self.bind()
        with self.assertRaisesRegex(self.cp.ControlPlaneError, "PRICE_V5_EXACT_WORKFLOW_CANDIDATES_REQUIRED"):
            self.verify()

    def test_missing_owner_artifact_cannot_be_replaced_by_generic_authorized_flag(self):
        del self.activation["artifacts"]["owner_approval"]
        self.rehash_activation()
        with self.assertRaisesRegex(self.cp.ControlPlaneError, "COMPLETE_AUTHORITY_CHAIN_REQUIRED"):
            self.verify()

    def test_missing_runtime_manifest_scope_cannot_use_generic_production_boolean(self):
        del self.manifest["runtime_registration"]
        self.manifest["stage3_authorized"] = True
        self.bind()
        with self.assertRaises(self.cp.ControlPlaneError):
            self.verify()

    def test_owner_approval_must_bind_exact_manifest(self):
        self.owner["manifest_sha256"] = digest(b"TEST foreign manifest")
        self.rehash_owner()
        with self.assertRaisesRegex(self.cp.ControlPlaneError, "OWNER|BINDING"):
            self.verify()

    def test_owner_approval_cannot_be_reused_for_changed_request_subject(self):
        self.request["title"] = "TEST a different request, while preserving all other pins"
        self.activation["artifacts"]["request"]["sha256"] = self.put(self.request_path, self.request)
        self.rehash_activation()
        with self.assertRaisesRegex(self.cp.ControlPlaneError, "OWNER|SUBJECT|BINDING"):
            self.verify()

    def test_stage1_and_stage2_closing_receipts_are_immutable(self):
        for stage in (1, 2):
            relative = f"state/receipts/TASK088-GE-PRICE-CRM-STAGE{stage}.json"
            original = (self.root / relative).read_bytes()
            with self.subTest(stage=stage):
                self.put_bytes(relative, original + b" ")
                with self.assertRaisesRegex(self.cp.ControlPlaneError, "STAGE|PREREQUISITE"):
                    self.verify()
            self.put_bytes(relative, original)

    def test_prior_mode_and_prior_activation_cannot_be_rewritten(self):
        for relative in (PREVIOUS_MODE, self.old_mode["runtime_activation_path"]):
            original = (self.root / relative).read_bytes()
            with self.subTest(relative=relative):
                self.put_bytes(relative, original + b" ")
                with self.assertRaisesRegex(self.cp.ControlPlaneError, "PREVIOUS|ACTIVATION|SHA"):
                    self.verify()
            self.put_bytes(relative, original)

    def test_manual_and_halt_remain_hard_stops(self):
        self.put("state/AUTOPILOT_HALT.json", {})
        with self.assertRaisesRegex(self.cp.ControlPlaneError, "AUTOMATIC_MODE_HALTED"):
            self.verify()
        (self.root / "state/AUTOPILOT_HALT.json").unlink()
        self.put_bytes("state/MANUAL_MODE.md", b"Status: ACTIVE\n")
        with self.assertRaisesRegex(self.cp.ControlPlaneError, "MANUAL_MODE_NOT_INACTIVE"):
            self.verify()

    def test_generic_stage3_boolean_cannot_replace_exact_registration(self):
        self.put(ACTIVATION, {"stage3_authorized": True, "preview_pass": True})
        self.mode["runtime_activation_sha256"] = digest((self.root / ACTIVATION).read_bytes())
        self.put(MODE, self.mode)
        with self.assertRaises(self.cp.ControlPlaneError):
            self.verify()

    def test_full_preview_does_not_replace_real_canonical_gate_b(self):
        for mutation in ({"protected_snapshot": {}}, {"production_write": True}, {"contract_id": "TEST-FAKE-GATE"}):
            with self.subTest(mutation=mutation):
                self.bind(gate_overrides=mutation)
                with self.assertRaisesRegex(self.cp.ControlPlaneError, "GATE"):
                    self.verify()

    def test_canonical_manifest_operation_scope_must_match_exact_request(self):
        self.manifest["operations"][0]["path"] = "production/operator-ui/unrelated.py"
        self.bind()
        with self.assertRaisesRegex(self.cp.ControlPlaneError, "GATE|MANIFEST|SCOPE"):
            self.verify()

    def test_missing_manifest_protected_paths_blocks_even_with_rehashed_owner(self):
        del self.manifest["protected_paths"]
        self.bind()
        with self.assertRaisesRegex(self.cp.ControlPlaneError, "GATE|MANIFEST|PROTECTED"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
