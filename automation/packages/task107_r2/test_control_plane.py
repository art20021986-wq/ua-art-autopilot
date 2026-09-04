#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[3]
PATH = ROOT / "automation/control_plane.py"
SPEC = importlib.util.spec_from_file_location("task107_r2_control_plane", PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("CONTROL_PLANE_SPEC")
CP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CP
SPEC.loader.exec_module(CP)
sys.path.insert(0, str(ROOT / "automation"))
import critical_adapter as CA  # noqa: E402
import task_ticket as TT  # noqa: E402


class FakeResponse:
    def __init__(self, status: int = 200, url: str = "https://example.test/health"):
        self.status = status
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getcode(self):
        return self.status

    def geturl(self):
        return self.url

    def read(self, _amount):
        return b"ok"


class ControlPlaneTests(unittest.TestCase):
    def test_repo_paths_reject_shell_metacharacters(self):
        for value in (
            "tasks/requests/x$(id).json",
            "tasks/requests/x;id.json",
            "tasks/requests/x'quote.json",
            'tasks/requests/x"quote.json',
            "tasks//requests/x.json",
        ):
            with self.subTest(value=value), self.assertRaisesRegex(
                CP.ControlPlaneError, "UNSAFE_REPO_PATH"
            ):
                CP.safe_repo_path(value)

    def test_critical_paths_reject_shell_metacharacters(self):
        for value in (
            "tasks/requests/x$(id).json",
            "tasks/requests/x;id.json",
            "tasks/requests/x'quote.json",
            'tasks/requests/x"quote.json',
            "tasks//requests/x.json",
        ):
            with self.subTest(value=value), self.assertRaisesRegex(
                CA.CriticalAdapterError, "UNSAFE_REPO_PATH"
            ):
                CA.safe_repo_path(value)

    def test_ticket_paths_reject_shell_metacharacters(self):
        for value in (
            "tasks/requests/x$(id).json",
            "tasks/requests/x;id.json",
            "tasks/requests/x'quote.json",
            'tasks/requests/x"quote.json',
            "tasks//requests/x.json",
        ):
            with self.subTest(value=value), self.assertRaisesRegex(
                TT.TicketError, "UNSAFE_REQUEST_PATH"
            ):
                TT.safe_request_path(value)

    def write_manual_mode(self, root: pathlib.Path) -> None:
        marker = root / "state/MANUAL_MODE.md"
        marker.parent.mkdir(parents=True, exist_ok=True)
        if not (root / "state/EXECUTION_MODE.json").exists():
            marker.write_text("# Test mode\n\nSTATUS: ACTIVE\n", encoding="utf-8")

    def write_automatic_mode(self, root: pathlib.Path) -> dict:
        activated_at = "2026-09-04T13:51:01Z"
        for relative in CP.RUNTIME_PINNED_PATHS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if relative in CP.ACTIVE_WORKFLOW_EVENT_POLICY:
                name = pathlib.PurePosixPath(relative).name
                canonical_workflow = True
                if canonical_workflow:
                    source = (ROOT / relative).read_text(encoding="utf-8")
                elif name in {
                    "uaart_maintenance.yml",
                    "uaart_monitor.yml",
                    "uaart_transaction_watchdog.yml",
                }:
                    cron = {
                        "uaart_maintenance.yml": "31 3 * * *",
                        "uaart_monitor.yml": "17 */6 * * *",
                        "uaart_transaction_watchdog.yml": "*/10 * * * *",
                    }[name]
                    source = (
                        "name: fixture\n"
                        "on:\n"
                        "  schedule:\n"
                        f"    - cron: '{cron}'\n"
                    )
                    if name != "uaart_transaction_watchdog.yml":
                        source += "  workflow_dispatch:\n"
                else:
                    events = CP.ACTIVE_WORKFLOW_EVENT_POLICY[relative]
                    source = "name: fixture\non:\n" + "".join(
                        f"  {event}:\n" for event in sorted(events)
                    )
                if canonical_workflow:
                    pass
                elif name == "uaart_critical.yml":
                    source += (
                        "jobs:\n  backup:\n"
                        "    if: github.ref == 'refs/heads/main' && github.run_attempt == 1\n"
                        "    permissions:\n      contents: read\n"
                        "    environment:\n      name: production\n"
                        "    runs-on: ubuntu-latest\n    steps:\n"
                        "      - name: Checkout\n"
                        "        uses: actions/checkout@pinned\n"
                        "        with:\n          ref: main\n          persist-credentials: false\n"
                        "      - name: Backup\n"
                        "        if: inputs.production_required == 'true' && github.run_attempt == 1 && steps.preparing.outputs.validated == 'true'\n"
                        "        env:\n"
                        "          TOKEN: ${{ secrets.PYTHONANYWHERE_API_TOKEN }}\n"
                        "        run: |\n"
                        "          test \"$GITHUB_RUN_ATTEMPT\" = '1'\n"
                        "          python3 -I automation/execution_contract.py backup request.json\n"
                        "  controller_production:\n    if: github.ref == 'refs/heads/main' && github.run_attempt == 1\n"
                        "    permissions:\n      contents: read\n"
                        "    environment:\n      name: production\n"
                        "    runs-on: ubuntu-latest\n    steps:\n"
                        "      - name: Run\n"
                        "        if: inputs.production_required == 'true' && github.run_attempt == 1 && steps.open_state.outputs.validated == 'true'\n"
                        "        env:\n"
                        "          TOKEN: ${{ secrets.PYTHONANYWHERE_API_TOKEN }}\n"
                        "        run: |\n"
                        "          test \"$GITHUB_RUN_ATTEMPT\" = '1'\n"
                        "          python3 -I automation/execution_contract.py run request.json\n"
                        "  rollback_execute:\n    if: github.ref == 'refs/heads/main' && github.run_attempt == 1\n"
                        "    permissions:\n      contents: read\n"
                        "    environment:\n      name: production\n"
                        "    runs-on: ubuntu-latest\n    steps:\n"
                        "      - name: Rollback\n"
                        "        if: inputs.production_required == 'true' && github.run_attempt == 1 && steps.rolling_back.outputs.validated == 'true'\n"
                        "        env:\n"
                        "          TOKEN: ${{ secrets.PYTHONANYWHERE_API_TOKEN }}\n"
                        "        run: |\n"
                        "          test \"$GITHUB_RUN_ATTEMPT\" = '1'\n"
                        "          python3 -I automation/execution_contract.py rollback request.json\n"
                        "      - name: Download rollback receipt outside checkout\n"
                        "        if: github.run_attempt == 1\n"
                        "        run: 'true'\n"
                        "      - name: Strictly validate data-only rollback artifact\n"
                        "        if: github.run_attempt == 1\n"
                        "        run: 'true'\n"
                    )
                elif name == "uaart_transaction_watchdog.yml":
                    source += (
                        "jobs:\n  rollback_task:\n"
                        "    if: github.ref == 'refs/heads/main'\n"
                        "    permissions:\n      contents: read\n"
                        "    runs-on: ubuntu-latest\n    steps:\n"
                        "      - name: Checkout\n"
                        "        uses: actions/checkout@pinned\n"
                        "        with:\n          ref: main\n          persist-credentials: false\n"
                        "      - name: Rollback\n"
                        "        if: needs.discover.outputs.transaction_status == 'OPEN' && needs.mark_rollback.outputs.marked == 'true' && github.run_attempt == 1\n"
                        "        env:\n"
                        "          TOKEN: ${{ secrets.PYTHONANYWHERE_API_TOKEN }}\n"
                        "        run: |\n"
                        "          test \"$GITHUB_RUN_ATTEMPT\" = '1'\n"
                        "          python3 -I automation/execution_contract.py rollback request.json\n"
                    )
                else:
                    source += "jobs:\n  fixture:\n    runs-on: ubuntu-latest\n"
                if not canonical_workflow and name in {
                    "uaart_critical.yml",
                    "uaart_transaction_watchdog.yml",
                }:
                    source += (
                        "  persist_fixture:\n"
                        "    if: github.ref == 'refs/heads/main'\n"
                        "    permissions:\n      contents: write\n"
                        "    runs-on: ubuntu-latest\n    steps:\n"
                        "      - name: Checkout trusted\n"
                        "        uses: actions/checkout@pinned\n"
                        "        with:\n          ref: main\n"
                        "          persist-credentials: false\n"
                        "      - name: Persist isolated tree\n"
                        "        env:\n          GH_TOKEN: ${{ github.token }}\n"
                        "        run: |\n"
                        "          INDEX=\"$RUNNER_TEMP/index\"\n"
                        "          GIT_INDEX_FILE=\"$INDEX\" git read-tree main\n"
                        "          TREE=\"$(GIT_INDEX_FILE=\"$INDEX\" git write-tree)\"\n"
                        "          COMMIT=\"$(git commit-tree \"$TREE\")\"\n"
                        "          git push origin \"$COMMIT:refs/heads/main\"\n"
                    )
                path.write_text(source, encoding="utf-8")
            else:
                path.write_text("fixture:" + relative + "\n", encoding="utf-8")
        runtime = {
            "files": {
                relative: CP.sha256_file(root / relative)
                for relative in CP.RUNTIME_PINNED_PATHS
            },
            "generated_at": activated_at,
            "mode_epoch": "auto-20260904T135101Z-testfixture0001",
            "schema_version": CP.RUNTIME_MANIFEST_SCHEMA,
        }
        CP.atomic_json(root / CP.RUNTIME_MANIFEST_PATH, runtime)
        runtime_sha = CP.sha256_file(root / CP.RUNTIME_MANIFEST_PATH)
        receipt_rel = "state/receipts/TASK107-R2.json"
        receipt = {
            "task_id": "TASK107-R2",
            "status": "FINISHED",
            "canary_result": "3/3 PASS",
            "tests": "PASS",
            "rollback_drill": "PASS",
            "unexpected_changes": 0,
            "production_touched": False,
        }
        CP.atomic_json(root / receipt_rel, receipt)
        approval_rel = "tasks/approvals/TASK107-R2-AUTOMATIC-MODE.json"
        approval = {
            "allow_replay_existing_launch_markers": False,
            "approved_at": activated_at,
            "automatic_nonproduction": True,
            "automatic_production": True,
            "mode_epoch": "auto-20260904T135101Z-testfixture0001",
            "owner": "Артём Бровинский / UA ART COMPANY LLC",
            "owner_authorized": True,
            "owner_command": "Включай глобальный продакшн автопилот.",
            "production_requires_backup": True,
            "production_requires_exact_launch": True,
            "production_requires_gate_b": True,
            "production_requires_live_receipt": True,
            "production_requires_owner_approval": True,
            "production_requires_pre_post_health": True,
            "runtime_manifest_path": CP.RUNTIME_MANIFEST_PATH,
            "runtime_manifest_sha256": runtime_sha,
            "schema_version": CP.AUTOMATIC_APPROVAL_SCHEMA,
            "stop_on_safety_failure": True,
            "task107_receipt_path": receipt_rel,
            "task107_receipt_sha256": CP.sha256_file(root / receipt_rel),
            "task_id": "TASK107-R2-AUTOMATIC-MODE",
        }
        CP.atomic_json(root / approval_rel, approval)
        mode = {
            "activated_at": activated_at,
            "allow_replay_existing_launch_markers": False,
            "automatic_nonproduction": True,
            "automatic_production": True,
            "mode_epoch": "auto-20260904T135101Z-testfixture0001",
            "mode": "AUTOMATIC",
            "owner_approval_path": approval_rel,
            "owner_approval_sha256": CP.sha256_file(root / approval_rel),
            "production_requires_backup": True,
            "production_requires_exact_launch": True,
            "production_requires_gate_b": True,
            "production_requires_live_receipt": True,
            "production_requires_owner_approval": True,
            "production_requires_pre_post_health": True,
            "runtime_manifest_path": CP.RUNTIME_MANIFEST_PATH,
            "runtime_manifest_sha256": runtime_sha,
            "schema_version": CP.EXECUTION_MODE_SCHEMA,
            "stop_on_safety_failure": True,
            "task107_receipt_path": receipt_rel,
            "task107_receipt_sha256": CP.sha256_file(root / receipt_rel),
        }
        manual = root / "state/MANUAL_MODE.md"
        manual.parent.mkdir(parents=True, exist_ok=True)
        manual.write_text("# Test mode\n\nSTATUS: INACTIVE\n", encoding="utf-8")
        CP.atomic_json(root / "state/EXECUTION_MODE.json", mode)
        return mode

    def write_request(
        self,
        root: pathlib.Path,
        task_id: str,
        *,
        changed_paths=None,
        production=False,
        ai_requested=False,
        health_checks=None,
        storage_probe=None,
        requested_min_class=None,
        critical=None,
    ) -> str:
        self.write_manual_mode(root)
        controller_sha = "a" * 64
        test_sha = "b" * 64
        value = {
            "task_id": task_id,
            "title": "Bounded request",
            "description": "replace exact checksum",
            "changed_paths": changed_paths or ["cloud/%s.txt" % task_id.lower()],
            "production_required": production,
            "read_only": False,
            "complexity": 1,
            "ai_requested": ai_requested,
            "execution": {
                "controller_path": "automation/packages/task107_r2/canary_controller.py",
                "controller_sha256": controller_sha,
                "test_paths": ["automation/packages/task107_r2/test_canary_controller.py"],
                "file_sha256": {
                    "automation/packages/task107_r2/test_canary_controller.py": test_sha,
                },
                "receipt_path": "state/receipts/%s.json" % task_id,
                "evidence_paths": ["state/receipts/%s.json" % task_id],
                "production_required": production,
            },
        }
        if health_checks is not None:
            value["health_checks"] = health_checks
        if storage_probe is not None:
            value["storage_probe"] = storage_probe
        if production and requested_min_class is None:
            value["requested_min_class"] = "CRITICAL"
        elif requested_min_class is not None:
            value["requested_min_class"] = requested_min_class
        if critical is not None:
            value["critical"] = critical
        relative = "tasks/requests/%s.json" % task_id
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return relative

    def test_valid_automatic_mode_is_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            result = CP.verify_execution_mode(root=root, required_mode="AUTOMATIC")
            self.assertEqual(result["mode"], "AUTOMATIC")
            self.assertTrue(result["automatic_production"])

    def test_recovery_mode_accepts_only_same_epoch_emergency_halt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            mode = self.write_automatic_mode(root)
            CP.atomic_json(root / "state/AUTOPILOT_HALT.json", {
                "halted_at": "2026-09-04T14:00:00Z",
                "mode_epoch": mode["mode_epoch"],
                "reason": "test recovery",
                "request_path": "",
                "request_sha256": "0" * 64,
                "run_id": "watchdog-test",
                "status": "EMERGENCY_HALT",
                "task_id": "SYSTEM-WATCHDOG",
            })
            with self.assertRaisesRegex(CP.ControlPlaneError, "AUTOMATIC_MODE_HALTED"):
                CP.verify_execution_mode(root=root, required_mode="AUTOMATIC")
            recovered = CP.verify_execution_mode(
                root=root,
                required_mode="AUTOMATIC",
                allow_halt_for_recovery=True,
            )
            self.assertEqual(recovered["mode_epoch"], mode["mode_epoch"])
            halt = CP.read_json(root / "state/AUTOPILOT_HALT.json")
            halt["mode_epoch"] = "auto-other-1234567890123456"
            CP.atomic_json(root / "state/AUTOPILOT_HALT.json", halt)
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "AUTOMATIC_HALT_IDENTITY_INVALID"
            ):
                CP.verify_execution_mode(
                    root=root,
                    required_mode="AUTOMATIC",
                    allow_halt_for_recovery=True,
                )

    def test_automatic_mode_rejects_tampered_task107_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            receipt_path = root / "state/receipts/TASK107-R2.json"
            receipt_path.write_text(receipt_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(CP.ControlPlaneError, "TASK107_RECEIPT_SHA_MISMATCH"):
                CP.verify_execution_mode(root=root)

    def test_automatic_mode_rejects_tampered_owner_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            approval_path = root / "tasks/approvals/TASK107-R2-AUTOMATIC-MODE.json"
            approval_path.write_text(approval_path.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(CP.ControlPlaneError, "AUTOMATIC_APPROVAL_SHA_MISMATCH"):
                CP.verify_execution_mode(root=root)

    def test_automatic_mode_rejects_tampered_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / CP.RUNTIME_PINNED_PATHS[0]
            target.write_text(target.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(CP.ControlPlaneError, "RUNTIME_PINNED_FILE_SHA_MISMATCH"):
                CP.verify_execution_mode(root=root)

    def test_automatic_mode_requires_manual_marker_inactive(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            (root / "state/MANUAL_MODE.md").write_text("STATUS: ACTIVE\n", encoding="utf-8")
            with self.assertRaisesRegex(CP.ControlPlaneError, "MANUAL_MODE_NOT_INACTIVE"):
                CP.verify_execution_mode(root=root)

    def test_automatic_mode_rejects_legacy_production_credential_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            legacy = root / ".github/workflows/legacy.yml"
            legacy.write_text(
                "name: legacy\non:\n  workflow_dispatch:\njobs:\n  unsafe:\n"
                "    runs-on: ubuntu-latest\n    steps:\n      - run: echo unsafe\n"
                "        env:\n          TOKEN: ${{ secrets.PYTHONANYWHERE_API_TOKEN }}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                CP.ControlPlaneError,
                "ACTIVE_WORKFLOW_SET_MISMATCH",
            ):
                CP.verify_execution_mode(root=root)

    def test_workflow_policy_rejects_bracket_secret_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_fast.yml"
            target.write_text(
                target.read_text(encoding="utf-8")
                + "# ${{ secrets['PYTHONANYWHERE_API_TOKEN'] }}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CP.ControlPlaneError, "PRODUCTION_CREDENTIAL_WORKFLOW_BYPASS"):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_workflow_policy_accepts_disabled_legacy_placeholder(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_fast.yml"
            target.write_text(
                target.read_text(encoding="utf-8")
                + "# ${{ secrets.UAART_LEGACY_PYTHONANYWHERE_TOKEN_DISABLED }}\n",
                encoding="utf-8",
            )
            result = CP.verify_production_credential_workflow_policy(root=root)
            self.assertEqual(result["status"], "PASS")

    def test_workflow_policy_rejects_real_token_in_fast(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_fast.yml"
            target.write_text(
                target.read_text(encoding="utf-8")
                + "# ${{ secrets.PYTHONANYWHERE_API_TOKEN }}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "PRODUCTION_CREDENTIAL_WORKFLOW_BYPASS"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_workflow_policy_rejects_case_changed_real_token_in_fast(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_fast.yml"
            target.write_text(
                target.read_text(encoding="utf-8")
                + "# ${{ secrets.pythonanywhere_api_token }}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "PRODUCTION_CREDENTIAL_WORKFLOW_BYPASS"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_workflow_policy_rejects_production_secret_outside_gated_step(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_critical.yml"
            source = target.read_text(encoding="utf-8").replace(
                "          github.run_attempt == 1 && inputs.production_required == 'true' &&\n"
                "          steps.preparing.outputs.validated == 'true'",
                "          github.run_attempt == 1 && always() &&\n"
                "          steps.preparing.outputs.validated == 'true'",
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "CRITICAL_PRODUCTION_CREDENTIAL_GATE"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_workflow_policy_requires_production_environment_on_secret_job(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_critical.yml"
            source = target.read_text(encoding="utf-8").replace(
                "    environment:\n      name: production\n",
                "    environment:\n      name: staging\n",
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "CRITICAL_PRODUCTION_CREDENTIAL_ENVIRONMENT"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_workflow_policy_requires_exact_secret_output_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_critical.yml"
            source = target.read_text(encoding="utf-8").replace(
                "steps.preparing.outputs.validated == 'true'",
                "steps.untrusted.outputs.validated == 'true'",
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "CRITICAL_PRODUCTION_CREDENTIAL_OUTPUT_GATE"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_workflow_policy_rejects_critical_secret_job_on_rerun(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_critical.yml"
            source = target.read_text(encoding="utf-8").replace(
                "      github.ref == 'refs/heads/main' && github.run_attempt == 1 &&\n"
                "      inputs.production_required == 'true' &&\n"
                "      needs.prepare.result == 'success'",
                "      github.ref == 'refs/heads/main' &&\n"
                "      inputs.production_required == 'true' &&\n"
                "      needs.prepare.result == 'success'",
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError,
                "CRITICAL_PRODUCTION_CREDENTIAL_JOB_RERUN_GATE",
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_workflow_policy_rejects_missing_critical_secret_shell_rerun_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_critical.yml"
            source = target.read_text(encoding="utf-8").replace(
                "          test \"$GITHUB_RUN_ATTEMPT\" = '1'\n",
                "          true # missing rerun guard\n",
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "CRITICAL_PRODUCTION_CREDENTIAL_GATE"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_workflow_policy_rejects_rollback_artifact_import_on_rerun(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_critical.yml"
            source = target.read_text(encoding="utf-8").replace(
                "      - name: Download rollback receipt outside checkout\n"
                "        if: >-\n"
                "          github.run_attempt == 1 &&\n"
                "          needs.rollback_execute.outputs.performed == 'true'\n",
                "      - name: Download rollback receipt outside checkout\n"
                "        if: always()\n",
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "CRITICAL_ROLLBACK_ARTIFACT_RERUN_GATE"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_workflow_policy_rejects_inherited_secrets_outside_central_callers(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_fast.yml"
            target.write_text(
                target.read_text(encoding="utf-8") + "  secrets: inherit\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "WORKFLOW_SECRET_INHERIT_BYPASS"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_workflow_policy_rejects_extra_automatic_event(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_fast.yml"
            source = target.read_text(encoding="utf-8").replace(
                "  workflow_call:\n", "  workflow_call:\n  pull_request:\n"
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "WORKFLOW_EVENT_POLICY_MISMATCH"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_autostart_policy_rejects_persisted_checkout_credential(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_autostart.yml"
            source = target.read_text(encoding="utf-8").replace(
                "persist-credentials: false", "persist-credentials: true", 1
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "AUTOSTART_CHECKOUT_CREDENTIAL_POLICY"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_autostart_policy_rejects_expression_inside_run_body(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_autostart.yml"
            source = target.read_text(encoding="utf-8").replace(
                "          set -euo pipefail\n",
                "          echo '${{ github.sha }}'\n          set -euo pipefail\n",
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "AUTOSTART_RUN_EXPRESSION_FORBIDDEN"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_autostart_policy_rejects_rerun_route_gate_removal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_autostart.yml"
            source = target.read_text(encoding="utf-8").replace(
                "github.ref == 'refs/heads/main' && github.run_attempt == 1",
                "github.ref == 'refs/heads/main'",
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "AUTOSTART_JOB_REPLAY_GATE:intake"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_autostart_policy_rejects_nonisolated_python_startup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_autostart.yml"
            source = target.read_text(encoding="utf-8").replace(
                "python3 -I -W error", "python3 -W error", 1
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "AUTOSTART_PYTHON_NOT_ISOLATED"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_autostart_policy_requires_source_pinned_privileged_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_autostart.yml"
            source = target.read_text(encoding="utf-8").replace(
                '            python3 -I "$TRUSTED_RUNTIME/automation/autostart_intake.py" \\\n',
                '            python3 -I automation/autostart_intake.py \\\n',
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "AUTOSTART_PRIVILEGED_PERSIST_CONTRACT"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_nonproduction_policy_rejects_controller_rerun_gate_removal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_fast.yml"
            source = target.read_text(encoding="utf-8").replace(
                " && github.run_attempt == 1", "", 1
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "NONPRODUCTION_RERUN_JOB_GATE"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_nonproduction_policy_rejects_nonterminal_rerun_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_fast.yml"
            source = target.read_text(encoding="utf-8").replace(
                "FAILURE_MODE_ARGS+=(--terminal)",
                "FAILURE_MODE_ARGS=() # terminal removed",
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError,
                "NONPRODUCTION_RERUN_TERMINAL_GATE",
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_nonproduction_policy_rejects_missing_runtime_bootstrap(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_fast.yml"
            source = target.read_text(encoding="utf-8").replace(
                "UAART_TRUSTED_RUNTIME_CLOSURE_VALIDATED",
                "UAART_RUNTIME_CHECK_REMOVED",
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError,
                "NONPRODUCTION_RUNTIME_BOOTSTRAP_MISSING",
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_nonproduction_policy_rejects_token_before_bootstrap(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_standard.yml"
            source = target.read_text(encoding="utf-8").replace(
                "          unset GH_TOKEN\n",
                "          true # token remains exported\n",
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError,
                "NONPRODUCTION_TOKEN_BOOTSTRAP_ORDER",
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_nonproduction_policy_rejects_unbound_running_workflow(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_fast.yml"
            source = target.read_text(encoding="utf-8").replace(
                "VALIDATION_WORKFLOW_BLOB_BINDING",
                "VALIDATION_WORKFLOW_BLOB_REMOVED",
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError,
                "NONPRODUCTION_WORKFLOW_BLOB_BINDING",
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_nonproduction_policy_rejects_unbound_retry_parent_workflow(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_standard.yml"
            source = target.read_text(encoding="utf-8").replace(
                '            test "$(git rev-parse "$PARENT:$WORKFLOW_PATH")" = \\\n'
                '              "$WORKFLOW_BLOB_OID"\n',
                "            true # parent workflow binding removed\n",
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError,
                "NONPRODUCTION_WORKFLOW_BLOB_BINDING",
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_nonproduction_policy_rejects_accepted_push_path_overwrite_gap(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_fast.yml"
            source = target.read_text(encoding="utf-8").replace(
                "ACCEPTED_PUSH_OWNED_PATHS_CHANGED",
                "ACCEPTED_PUSH_PATH_CHECK_REMOVED",
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError,
                "NONPRODUCTION_ACCEPTED_PUSH_OWNERSHIP",
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_nonproduction_policy_rejects_weak_artifact_root_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_standard.yml"
            source = target.read_text(encoding="utf-8").replace(
                "ARTIFACT_IMPORT_ROOT_INVALID",
                "ARTIFACT_IMPORT_ROOT_CHECK_REMOVED",
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError,
                "NONPRODUCTION_ARTIFACT_SCHEMA",
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_fresh_runner_policy_allows_multiple_safe_checkouts(self):
        source = (
            "name: fixture\non:\n  workflow_call:\njobs:\n"
            "  task:\n    if: github.ref == 'refs/heads/main'\n"
            "    permissions:\n      contents: read\n"
            "    runs-on: ubuntu-latest\n    steps:\n"
            "      - name: Checkout task\n        uses: actions/checkout@pinned\n"
            "        with:\n          ref: main\n          persist-credentials: false\n"
            "      - name: Test task\n"
            "        run: python3 -I automation/execution_contract.py test request.json\n"
            "  persist:\n    if: github.ref == 'refs/heads/main'\n"
            "    permissions:\n      contents: write\n"
            "    runs-on: ubuntu-latest\n    steps:\n"
            "      - name: Checkout trusted\n        uses: actions/checkout@pinned\n"
            "        with:\n          ref: main\n          persist-credentials: false\n"
            "      - name: Persist\n        env:\n"
            "          GH_TOKEN: ${{ github.token }}\n        run: |\n"
            "          INDEX=\"$RUNNER_TEMP/index\"\n"
            "          GIT_INDEX_FILE=\"$INDEX\" git read-tree main\n"
            "          TREE=\"$(GIT_INDEX_FILE=\"$INDEX\" git write-tree)\"\n"
            "          COMMIT=\"$(git commit-tree \"$TREE\")\"\n"
            "          git push origin \"$COMMIT:refs/heads/main\"\n"
        )
        CP._verify_fresh_runner_job_policy(source, "fixture.yml")

    def test_fresh_runner_policy_rejects_nonisolated_python_startup(self):
        source = (
            "name: fixture\non:\n  workflow_call:\njobs:\n"
            "  task:\n    if: github.ref == 'refs/heads/main'\n"
            "    permissions:\n      contents: read\n"
            "    runs-on: ubuntu-latest\n    steps:\n"
            "      - name: Checkout\n        uses: actions/checkout@pinned\n"
            "        with:\n          ref: main\n          persist-credentials: false\n"
            "      - name: Test\n"
            "        run: python3 automation/execution_contract.py test request.json\n"
        )
        with self.assertRaisesRegex(
            CP.ControlPlaneError, "WORKFLOW_PYTHON_NOT_ISOLATED"
        ):
            CP._verify_fresh_runner_job_policy(source, "fixture.yml")

    def test_fresh_runner_policy_rejects_task_job_write_permission(self):
        source = (
            "name: fixture\non:\n  workflow_call:\njobs:\n"
            "  task:\n    if: github.ref == 'refs/heads/main'\n"
            "    permissions:\n      contents: write\n"
            "    runs-on: ubuntu-latest\n    steps:\n"
            "      - name: Checkout\n        uses: actions/checkout@pinned\n"
            "        with:\n          ref: main\n          persist-credentials: false\n"
            "      - name: Run\n"
            "        run: python3 -I automation/execution_contract.py run request.json\n"
        )
        with self.assertRaisesRegex(
            CP.ControlPlaneError, "TASK_JOB_CONTENTS_NOT_READ_ONLY"
        ):
            CP._verify_fresh_runner_job_policy(source, "fixture.yml")

    def test_fresh_runner_policy_rejects_github_token_anywhere_in_task_job(self):
        source = (
            "name: fixture\non:\n  workflow_call:\njobs:\n"
            "  task:\n    if: github.ref == 'refs/heads/main'\n"
            "    permissions:\n      contents: read\n"
            "    runs-on: ubuntu-latest\n    env:\n"
            "      GH_TOKEN: ${{ github.token }}\n    steps:\n"
            "      - name: Checkout\n        uses: actions/checkout@pinned\n"
            "        with:\n          ref: main\n          persist-credentials: false\n"
            "      - name: Run\n"
            "        run: python3 -I automation/execution_contract.py run request.json\n"
        )
        with self.assertRaisesRegex(
            CP.ControlPlaneError, "TASK_JOB_GITHUB_CREDENTIAL_EXPOSURE"
        ):
            CP._verify_fresh_runner_job_policy(source, "fixture.yml")

    def test_fresh_runner_policy_does_not_treat_backup_receipt_as_task_command(self):
        source = (
            "name: fixture\non:\n  workflow_call:\njobs:\n"
            "  task:\n    if: github.ref == 'refs/heads/main'\n"
            "    permissions:\n      contents: read\n"
            "    runs-on: ubuntu-latest\n    steps:\n"
            "      - name: Checkout\n        uses: actions/checkout@pinned\n"
            "        with:\n          ref: main\n          persist-credentials: false\n"
            "      - name: Test\n"
            "        run: python3 -I automation/execution_contract.py test request.json\n"
            "  receipt:\n    if: github.ref == 'refs/heads/main'\n"
            "    permissions:\n      contents: write\n"
            "    runs-on: ubuntu-latest\n    steps:\n"
            "      - name: Validate receipt\n"
            "        run: python3 -I automation/execution_contract.py backup-receipt request.json\n"
            "      - name: Persist\n        run: |\n"
            "          INDEX=\"$RUNNER_TEMP/index\"\n"
            "          GIT_INDEX_FILE=\"$INDEX\" git read-tree main\n"
            "          TREE=\"$(GIT_INDEX_FILE=\"$INDEX\" git write-tree)\"\n"
            "          COMMIT=\"$(git commit-tree \"$TREE\")\"\n"
            "          git push origin \"$COMMIT:refs/heads/main\"\n"
        )
        CP._verify_fresh_runner_job_policy(source, "fixture.yml")

    def test_fresh_runner_policy_requires_temp_data_only_artifact(self):
        workspace_source = (
            "name: fixture\non:\n  workflow_call:\njobs:\n"
            "  task:\n    if: github.ref == 'refs/heads/main'\n"
            "    permissions:\n      contents: read\n"
            "    runs-on: ubuntu-latest\n    steps:\n"
            "      - name: Checkout\n        uses: actions/checkout@pinned\n"
            "        with:\n          ref: main\n          persist-credentials: false\n"
            "      - name: Run\n"
            "        run: python3 -I automation/execution_contract.py run request.json\n"
            "  persist:\n    if: github.ref == 'refs/heads/main'\n"
            "    permissions:\n      contents: write\n"
            "    runs-on: ubuntu-latest\n    steps:\n"
            "      - name: Download\n        uses: actions/download-artifact@pinned\n"
            "        with:\n          path: ${{ github.workspace }}/evidence\n"
        )
        with self.assertRaisesRegex(
            CP.ControlPlaneError, "ARTIFACT_DOWNLOAD_WORKSPACE_FORBIDDEN"
        ):
            CP._verify_fresh_runner_job_policy(workspace_source, "fixture.yml")

        unvalidated = workspace_source.replace(
            "${{ github.workspace }}/evidence", "${{ runner.temp }}/evidence"
        )
        with self.assertRaisesRegex(
            CP.ControlPlaneError, "PRIVILEGED_ARTIFACT_NOT_DATA_ONLY_VALIDATED"
        ):
            CP._verify_fresh_runner_job_policy(unvalidated, "fixture.yml")

        validated = unvalidated.replace(
            "      - name: Download\n",
            "    # UAART_DATA_ONLY_ARTIFACT_VALIDATED\n      - name: Download\n",
        )
        validated += (
            "      - name: Persist\n        run: |\n"
            "          INDEX=\"$RUNNER_TEMP/index\"\n"
            "          GIT_INDEX_FILE=\"$INDEX\" git read-tree main\n"
            "          TREE=\"$(GIT_INDEX_FILE=\"$INDEX\" git write-tree)\"\n"
            "          COMMIT=\"$(git commit-tree \"$TREE\")\"\n"
            "          git push origin \"$COMMIT:refs/heads/main\"\n"
        )
        CP._verify_fresh_runner_job_policy(validated, "fixture.yml")

    def test_exact_intake_uses_requested_path_not_highest_task_number(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            first = self.write_request(root, "TASK-2")
            self.write_request(root, "TASK-999")
            claim = CP.claim_request(first, "run-1", root=root)
            self.assertEqual(claim["identity"]["task_id"], "TASK-2")
            self.assertEqual(claim["request_path"], first)

    def test_claim_rejects_changed_request_when_sha_is_pinned(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-PINNED")
            with self.assertRaisesRegex(CP.ControlPlaneError, "CLAIM_REQUEST_SHA_MISMATCH"):
                CP.claim_request(
                    request,
                    "run-1",
                    root=root,
                    expected_request_sha256="f" * 64,
                )

    def test_atomic_duplicate_protection_blocks_second_active_run(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-DUP")
            CP.claim_request(request, "run-1", root=root)
            with self.assertRaisesRegex(CP.ControlPlaneError, "DUPLICATE_ACTIVE_CLAIM"):
                CP.claim_request(request, "run-2", root=root)

    def test_same_exact_run_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-IDEMPOTENT")
            first = CP.claim_request(request, "run-1", root=root)
            second = CP.claim_request(request, "run-1", root=root)
            self.assertFalse(first["idempotent"])
            self.assertTrue(second["idempotent"])
            self.assertEqual(first["identity"], second["identity"])

    def test_resource_queue_allows_independent_cards(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            one = self.write_request(root, "TASK-CARD-1", changed_paths=["cards/UA-0001/meta.json"])
            two = self.write_request(root, "TASK-CARD-2", changed_paths=["cards/UA-0002/meta.json"])
            first = CP.claim_request(one, "run-1", root=root)
            second = CP.claim_request(two, "run-2", root=root)
            self.assertNotEqual(first["queue_key"], second["queue_key"])

    def test_resource_queue_blocks_overlapping_control_plane(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            one = self.write_request(root, "TASK-CP-1", changed_paths=[".github/workflows/a.yml"])
            two = self.write_request(root, "TASK-CP-2", changed_paths=[".github/workflows/b.yml"])
            CP.claim_request(one, "run-1", root=root)
            with self.assertRaisesRegex(CP.ControlPlaneError, "RESOURCE_BUSY"):
                CP.claim_request(two, "run-2", root=root)

    def test_actual_control_plane_path_is_critical(self):
        value = {
            "task_id": "TASK-CLASS",
            "title": "Change pipeline",
            "changed_paths": [".github/workflows/uaart_fast.yml"],
        }
        self.assertEqual(CP.classify_request(value), "CRITICAL")

    def test_ai_response_status_cannot_finish_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-AI", ai_requested=True)
            claim = CP.claim_request(request, "run-1", root=root)
            self.assertEqual(claim["ai_response_status"], "PENDING")
            self.assertEqual(claim["task_execution_status"], "CLAIMED")
            plan_path = root / "state/ai_plans/TASK-AI.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text('{"steps":["review"]}\n', encoding="utf-8")
            plan_sha = hashlib.sha256(plan_path.read_bytes()).hexdigest()
            updated = CP.record_ai_plan(
                request,
                "run-1",
                "state/ai_plans/TASK-AI.json",
                plan_sha,
                root=root,
            )
            self.assertEqual(updated["ai_response_status"], "RECEIVED")
            self.assertNotEqual(updated["task_execution_status"], "FINISHED")

    def test_ai_plan_cannot_supply_executable_fields(self):
        with self.assertRaisesRegex(CP.ControlPlaneError, "EXECUTABLE_FIELD_FORBIDDEN"):
            CP.validate_ai_plan({"steps": [{"shell": "rm anything"}]})

    def test_no_ai_planning_is_explicit_and_non_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-NO-AI")
            CP.claim_request(request, "run-1", root=root)
            result = CP.prepare_request_planning(request, "run-1", root=root)
            self.assertEqual(result["status"], "NOT_REQUESTED")
            self.assertFalse(result["executable_content_accepted"])

    def test_storage_thresholds_and_required_space(self):
        self.assertEqual(CP.storage_decision(69.99, 1000, 10, heavy=True)["status"], "PASS")
        self.assertEqual(CP.storage_decision(70, 1000, 10, heavy=True)["status"], "WARN_70")
        self.assertFalse(CP.storage_decision(80, 1000, 10, heavy=True)["allowed"])
        self.assertEqual(CP.storage_decision(90, 1000, 10, heavy=False)["status"], "STOP_90")
        self.assertEqual(
            CP.storage_decision(10, 9, 10, heavy=False)["status"],
            "BLOCK_INSUFFICIENT_FREE_SPACE",
        )

    def test_production_health_is_mandatory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-HEALTH", production=True)
            CP.claim_request(request, "run-1", root=root)
            with self.assertRaisesRegex(CP.ControlPlaneError, "PRODUCTION_HEALTH_CHECKS_REQUIRED"):
                CP.health_phase(request, "run-1", "pre", root=root)

    def test_production_cannot_route_fast_or_standard(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-PROD-CLASS", production=True)
            raw = CP.read_json(root / request)
            raw.pop("requested_min_class")
            CP.atomic_json(root / request, raw)
            with self.assertRaisesRegex(CP.ControlPlaneError, "PRODUCTION_MUST_ROUTE_CRITICAL"):
                CP.claim_request(request, "run-1", root=root)

    def test_production_storage_requires_target_probe_not_runner_disk(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-STORAGE-PROD", production=True)
            CP.claim_request(request, "run-1", root=root)
            with self.assertRaisesRegex(CP.ControlPlaneError, "TARGET_STORAGE_PROBE_REQUIRED"):
                CP.storage_preflight(request, "run-1", root=root)

    def test_recent_pinned_production_storage_probe_passes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            probe_rel = "state/storage/production.json"
            probe_path = root / probe_rel
            probe_path.parent.mkdir(parents=True)
            probe = {
                "target_environment": "production",
                "read_only": True,
                "measured_at": CP.utc_now(),
                "total_bytes": 1_000_000_000,
                "used_bytes": 600_000_000,
                "free_bytes": 400_000_000,
            }
            probe_path.write_text(json.dumps(probe, sort_keys=True) + "\n", encoding="utf-8")
            probe_sha = hashlib.sha256(probe_path.read_bytes()).hexdigest()
            request = self.write_request(
                root,
                "TASK-STORAGE-PROD-PASS",
                production=True,
                storage_probe={"evidence_path": probe_rel, "evidence_sha256": probe_sha},
            )
            CP.claim_request(request, "run-1", root=root)
            result = CP.storage_preflight(request, "run-1", root=root)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["measurement_scope"], "production_target_read_only_probe")

    def test_pre_and_post_health_record_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(
                root,
                "TASK-HEALTH-PASS",
                production=True,
                health_checks=["https://example.test/health"],
            )
            CP.claim_request(request, "run-1", root=root)

            def opener(_request, timeout):
                self.assertGreater(timeout, 0)
                return FakeResponse()

            self.assertEqual(CP.health_phase(request, "run-1", "pre", root=root, opener=opener)["status"], "PASS")
            self.assertEqual(CP.health_phase(request, "run-1", "post", root=root, opener=opener)["status"], "PASS")

    def test_stall_detector_marks_old_active_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-STALL")
            result = CP.claim_request(request, "run-1", root=root)
            claim_path = root / result["claim_path"]
            claim = CP.read_json(claim_path)
            claim["heartbeat_at"] = "2026-01-01T00:00:00Z"
            CP.atomic_json(claim_path, claim)
            now = dt.datetime(2026, 1, 1, 0, 10, tzinfo=dt.timezone.utc)
            state = CP.detect_stall(claim_path, 60, now=now)
            self.assertTrue(state["stalled"])
            self.assertEqual(state["task_execution_status"], "STALLED")

    def test_durable_production_rollback_is_single_attempt_and_precommitted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request_rel = "tasks/requests/TASK-TX.json"
            raw = {
                "task_id": "TASK-TX",
                "title": "Transaction test",
                "production_required": True,
                "execution": {
                    "backup_receipt_path": "state/receipts/TASK-TX-BACKUP.json"
                },
                "critical": {"manifest_sha256": "c" * 64},
            }
            CP.atomic_json(root / request_rel, raw)
            request_sha = CP.sha256_file(root / request_rel)
            identity = CP._identity(raw, request_sha, "run-tx")
            claim_path = root / CP.claim_relative_path(identity)
            ledger_rel = "state/autostart_consumed/tx.json"
            CP.atomic_json(root / ledger_rel, {"expires_at": "2099-01-01T00:00:00Z"})
            backup_rel = raw["execution"]["backup_receipt_path"]
            claim = {
                "autostart_ledger_path": ledger_rel,
                "critical_gate_status": "PASS_PRODUCTION",
                "execution_mode": "AUTOMATIC",
                "identity": identity,
                "mode_epoch": "auto-test-1234567890123456",
                "package_compile_status": "PASS",
                "pre_health_status": "PASS",
                "request_path": request_rel,
                "storage_preflight": {"allowed": True},
                "task_execution_status": "RUNNING",
            }
            CP.atomic_json(claim_path, claim)
            transaction_id = "tx-run-tx-abcdef0123456789"
            with mock.patch.object(
                CP,
                "_load_exact_claim",
                return_value=(claim_path, claim, raw, request_sha),
            ):
                prepared = CP.prepare_production_transaction(
                    request_rel,
                    "run-tx",
                    transaction_id,
                    root=root,
                )
                self.assertEqual(prepared["status"], "PREPARING")
                backup_manifest_sha = "a" * 64
                CP.atomic_json(root / backup_rel, {
                    "backup": "PASS",
                    "backup_manifest_sha256": backup_manifest_sha,
                    "manifest_sha256": raw["critical"]["manifest_sha256"],
                    "operation": "backup",
                    "request_sha256": request_sha,
                    "run_id": "run-tx",
                    "schema_version": "UA-ART-PRODUCTION-BACKUP-RECEIPT-1",
                    "status": "PASS",
                    "task_id": "TASK-TX",
                    "transaction_id": transaction_id,
                    "unexpected_changes": 0,
                })
                opened = CP.open_production_transaction(
                    request_rel,
                    "run-tx",
                    transaction_id,
                    CP.sha256_file(root / backup_rel),
                    backup_manifest_sha,
                    root=root,
                )
            self.assertEqual(opened["status"], "OPEN")
            with mock.patch.object(
                CP,
                "_load_claim_for_recovery",
                return_value=(claim_path, CP.read_json(claim_path), raw, request_sha),
            ):
                rolling = CP.start_production_rollback(
                    request_rel, "run-tx", transaction_id, root=root
                )
            self.assertEqual(rolling["status"], "ROLLING_BACK")
            self.assertEqual(
                CP.read_json(claim_path)["production_transaction_status"],
                "ROLLING_BACK",
            )
            with mock.patch.object(
                CP,
                "_load_claim_for_recovery",
                return_value=(claim_path, CP.read_json(claim_path), raw, request_sha),
            ):
                with self.assertRaisesRegex(
                    CP.ControlPlaneError,
                    "TRANSACTION_ROLLBACK_START_IDENTITY_MISMATCH",
                ):
                    CP.start_production_rollback(
                        request_rel, "run-tx", transaction_id, root=root
                    )
            recovered = CP.close_production_transaction(
                request_rel, "run-tx", transaction_id, "ROLLED_BACK", root=root
            )
            self.assertEqual(recovered["status"], "ROLLED_BACK")

    def test_preparing_transaction_is_durable_before_backup_credential_use(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request_rel = "tasks/requests/TASK-TX-PREPARE.json"
            raw = {
                "task_id": "TASK-TX-PREPARE",
                "title": "Transaction prepare test",
                "production_required": True,
                "execution": {
                    "backup_receipt_path": "state/receipts/TASK-TX-PREPARE-BACKUP.json"
                },
            }
            CP.atomic_json(root / request_rel, raw)
            request_sha = CP.sha256_file(root / request_rel)
            identity = CP._identity(raw, request_sha, "run-prepare")
            claim_path = root / CP.claim_relative_path(identity)
            ledger_rel = "state/autostart_consumed/prepare.json"
            CP.atomic_json(root / ledger_rel, {"expires_at": "2099-01-01T00:00:00Z"})
            claim = {
                "autostart_ledger_path": ledger_rel,
                "critical_gate_status": "PASS_PRODUCTION",
                "execution_mode": "AUTOMATIC",
                "identity": identity,
                "mode_epoch": "auto-test-1234567890123456",
                "package_compile_status": "PASS",
                "pre_health_status": "PASS",
                "request_path": request_rel,
                "storage_preflight": {"allowed": True},
                "task_execution_status": "RUNNING",
            }
            CP.atomic_json(claim_path, claim)
            transaction_id = "tx-run-prepare-abcdef0123456789"
            with mock.patch.object(
                CP,
                "_load_exact_claim",
                return_value=(claim_path, claim, raw, request_sha),
            ):
                prepared = CP.prepare_production_transaction(
                    request_rel, "run-prepare", transaction_id, root=root
                )
            self.assertEqual(prepared["status"], "PREPARING")
            self.assertIsNone(prepared["backup_receipt_sha256"])
            self.assertFalse((root / raw["execution"]["backup_receipt_path"]).exists())
            durable_claim = CP.read_json(claim_path)
            self.assertEqual(durable_claim["production_transaction_status"], "PREPARING")

    def test_retry_is_bounded_and_logical_failure_enters_root_cause(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-RETRY")
            CP.claim_request(request, "run-1", root=root)
            transient = CP.record_failure(request, "run-1", "HTTP 503 temporary", root=root)
            self.assertTrue(transient["retry_allowed"])
            logical = CP.record_failure(request, "run-1", "SyntaxError line 1", root=root)
            self.assertFalse(logical["retry_allowed"])
            logical_again = CP.record_failure(request, "run-1", "SyntaxError line 1", root=root)
            self.assertEqual(logical_again["action"], "ROOT_CAUSE_MODE")

    def test_failure_record_never_clobbers_terminal_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-TERMINAL-FAIL-GUARD")
            claimed = CP.claim_request(request, "run-1", root=root)
            claim_path = root / claimed["claim_path"]
            claim = CP.read_json(claim_path)
            claim["task_execution_status"] = "FINISHED"
            CP.atomic_json(claim_path, claim)
            result = CP.record_failure(
                request, "run-1", "runner lost after accepted push", root=root
            )
            self.assertEqual(result["action"], "TERMINAL_UNCHANGED")
            self.assertEqual(result["task_execution_status"], "FINISHED")
            self.assertEqual(
                CP.read_json(claim_path)["task_execution_status"], "FINISHED"
            )

    def test_terminal_rerun_failure_mutates_history_once_then_is_immutable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-RERUN-TERMINAL")
            claimed = CP.claim_request(request, "run-1", root=root)
            claim_path = root / claimed["claim_path"]
            first = CP.record_failure(
                request, "run-1", "pipeline failed", root=root
            )
            self.assertEqual(first["task_execution_status"], "BLOCKED_ROOT_CAUSE")
            second = CP.record_failure(
                request,
                "run-1",
                "pipeline failed",
                root=root,
                terminal=True,
            )
            self.assertEqual(second["task_execution_status"], "FAILED")
            self.assertEqual(second["action"], "STOP_FAIL_CLOSED_TERMINAL")
            after_second = claim_path.read_bytes()
            self.assertEqual(len(CP.read_json(claim_path)["failure_history"]), 2)
            third = CP.record_failure(
                request,
                "run-1",
                "pipeline failed",
                root=root,
                terminal=True,
            )
            self.assertEqual(third["action"], "TERMINAL_UNCHANGED")
            self.assertEqual(third["task_execution_status"], "FAILED")
            self.assertEqual(claim_path.read_bytes(), after_second)
            self.assertEqual(len(CP.read_json(claim_path)["failure_history"]), 2)

    def test_verify_identity_can_bind_exact_claim_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-CLAIM-PATH-BINDING")
            claimed = CP.claim_request(request, "run-1", root=root)
            valid = CP.verify_exact_identity(
                request,
                "TASK-CLAIM-PATH-BINDING",
                claimed["request_sha256"],
                "run-1",
                expected_claim_path=claimed["claim_path"],
                root=root,
            )
            self.assertEqual(valid["claim_path"], claimed["claim_path"])
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "AUTOSTART_CLAIM_PATH_MISMATCH"
            ):
                CP.verify_exact_identity(
                    request,
                    "TASK-CLAIM-PATH-BINDING",
                    claimed["request_sha256"],
                    "run-1",
                    expected_claim_path="state/claims/forged.json",
                    root=root,
                )

    def test_finished_requires_exact_validated_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-FINISH")
            claim = CP.claim_request(request, "run-1", root=root)
            CP.storage_preflight(request, "run-1", root=root, usage_percent=10, free_bytes=10**9)
            CP.mark_compiled(request, "run-1", root=root)
            with self.assertRaisesRegex(CP.ControlPlaneError, "INVALID_JSON"):
                CP.finish_request(request, "run-1", root=root)
            receipt_path = root / "state/receipts/TASK-FINISH.json"
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt = {
                "task_id": "TASK-FINISH",
                "status": "FINISHED",
                "task_class": "FAST",
                "target_environment": "sandbox",
                "tests": "PASS",
                "unexpected_changes": 0,
                "rollback_ready": True,
                "production_required": False,
                "request_sha256": claim["request_sha256"],
                "run_id": "run-1",
            }
            receipt_path.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
            finished = CP.finish_request(request, "run-1", root=root)
            self.assertEqual(finished["task_execution_status"], "FINISHED")
            self.assertEqual(finished["receipt_validation_status"], "PASS")

    def test_autostart_guard_matches_exact_identity_not_recent_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            request = self.write_request(root, "TASK-GUARD")
            claim = CP.claim_request(request, "run-1", root=root)
            passed = CP.verify_exact_identity(
                request,
                "TASK-GUARD",
                claim["request_sha256"],
                "run-1",
                root=root,
            )
            self.assertFalse(passed["generic_recent_run_accepted"])
            with self.assertRaisesRegex(CP.ControlPlaneError, "AUTOSTART_TASK_ID_MISMATCH"):
                CP.verify_exact_identity(
                    request,
                    "TASK-OTHER",
                    claim["request_sha256"],
                    "run-1",
                    root=root,
                )

    def test_nonproduction_critical_gate_is_separate_from_gate_b(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            task_id = "TASK-CRITICAL"
            owner_rel = "tasks/approvals/critical.md"
            manifest_rel = "tasks/manifests/critical.json"
            gate_rel = "tasks/gates/critical.json"
            owner_path = root / owner_rel
            owner_path.parent.mkdir(parents=True)
            owner_path.write_text(
                "%s TASK107-R2 OWNER_APPROVED MANUAL_ONLY\n" % task_id,
                encoding="utf-8",
            )
            changed = [".github/workflows/uaart_orchestrator.yml"]
            manifest = {
                "task_id": task_id,
                "task_class": "CRITICAL",
                "operations": [{"action": "noop", "path": changed[0]}],
                "protected_paths": ["crm.db", "video/UA-0009.html"],
                "rollback_required": True,
            }
            manifest_path = root / manifest_rel
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            manifest_sha = hashlib.sha256(CP.canonical_json(manifest)).hexdigest()
            gate = {
                "task_id": task_id,
                "status": "PASS",
                "production_write": False,
                "tests": "PASS",
                "unexpected_changes": 0,
                "rollback_plan_ready": True,
                "manifest_sha256": manifest_sha,
                "protected_snapshot": {"crm.db": {"sha256": "c" * 64}},
            }
            gate_path = root / gate_rel
            gate_path.parent.mkdir(parents=True)
            gate_path.write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
            critical = {
                "owner_approval_path": owner_rel,
                "owner_approval_sha256": hashlib.sha256(owner_path.read_bytes()).hexdigest(),
                "manifest_path": manifest_rel,
                "manifest_sha256": manifest_sha,
                "gate_a_path": gate_rel,
                "gate_a_sha256": hashlib.sha256(gate_path.read_bytes()).hexdigest(),
                "gate_b_authorized": False,
            }
            request = self.write_request(
                root,
                task_id,
                changed_paths=changed,
                requested_min_class="CRITICAL",
                critical=critical,
            )
            CP.claim_request(request, "run-1", root=root)
            result = CP.validate_critical_nonproduction(request, "run-1", root=root)
            self.assertEqual(result["status"], "PASS_NONPRODUCTION")
            self.assertFalse(result["production_write"])

    def test_active_workflow_policy_rejects_ambient_python_startup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_backup.yml"
            source = target.read_text(encoding="utf-8").replace(
                "python3 -I - <<'PY'", "python3 - <<'PY'", 1
            )
            self.assertNotEqual(source, target.read_text(encoding="utf-8"))
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "ACTIVE_WORKFLOW_PYTHON_NOT_ISOLATED"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_active_workflow_policy_rejects_persisted_checkout_token(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_backup.yml"
            source = target.read_text(encoding="utf-8").replace(
                "persist-credentials: false", "persist-credentials: true", 1
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "ACTIVE_WORKFLOW_CHECKOUT_CREDENTIAL_POLICY"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_critical_policy_rejects_package_or_manifest_drift_guard_removal(self):
        mutations = {
            'git diff --quiet "$SOURCE_COMMIT" HEAD -- "$package_root"':
                'true # removed package drift guard',
            "sha256sum state/AUTOPILOT_RUNTIME_MANIFEST.json":
                "sha256sum state/REMOVED_RUNTIME_MANIFEST.json",
        }
        for marker, replacement in mutations.items():
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as folder:
                root = pathlib.Path(folder)
                self.write_automatic_mode(root)
                target = root / ".github/workflows/uaart_critical.yml"
                source = target.read_text(encoding="utf-8").replace(
                    marker, replacement
                )
                self.assertNotEqual(source, target.read_text(encoding="utf-8"))
                target.write_text(source, encoding="utf-8")
                with self.assertRaisesRegex(
                    CP.ControlPlaneError, "CRITICAL_FORWARD_RUNTIME_DRIFT_GUARD"
                ):
                    CP.verify_production_credential_workflow_policy(root=root)

    def test_critical_policy_rejects_workflow_blob_or_pinned_recovery_removal(self):
        mutations = {
            "VALIDATION_WORKFLOW_BLOB_BINDING": "REMOVED_WORKFLOW_BLOB_BINDING",
            "UAART_PINNED_RUNTIME_CLOSURE_VALIDATED": "REMOVED_PINNED_RUNTIME",
        }
        for marker, replacement in mutations.items():
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as folder:
                root = pathlib.Path(folder)
                self.write_automatic_mode(root)
                target = root / ".github/workflows/uaart_critical.yml"
                source = target.read_text(encoding="utf-8").replace(
                    marker, replacement, 1
                )
                target.write_text(source, encoding="utf-8")
                with self.assertRaisesRegex(
                    CP.ControlPlaneError,
                    "CRITICAL_(?:VALIDATION_RUNTIME_BINDING|PINNED_ROLLBACK_RUNTIME_MISSING)",
                ):
                    CP.verify_production_credential_workflow_policy(root=root)

    def test_critical_policy_rejects_runtime_closure_or_full_drift_guard_removal(self):
        mutations = (
            (
                "UAART_CRITICAL_VALIDATION_RUNTIME_CLOSURE_VALIDATED",
                "REMOVED_CRITICAL_VALIDATION_RUNTIME_CLOSURE",
                "CRITICAL_VALIDATION_RUNTIME_CLOSURE",
            ),
            (
                'git diff --quiet "$WORKFLOW_SOURCE_COMMIT" HEAD -- "${runtime_paths[@]}"',
                "true # removed full runtime drift guard",
                "CRITICAL_FULL_RUNTIME_DRIFT_GUARD",
            ),
            (
                'git diff --quiet "$WORKFLOW_SOURCE_COMMIT" "$parent" -- "${runtime_paths[@]}"',
                "true # removed parent runtime drift guard",
                "CRITICAL_PERSIST_WORKFLOW_RUNTIME_BINDING",
            ),
        )
        for marker, replacement, expected in mutations:
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as folder:
                root = pathlib.Path(folder)
                self.write_automatic_mode(root)
                target = root / ".github/workflows/uaart_critical.yml"
                original = target.read_text(encoding="utf-8")
                source = original.replace(marker, replacement)
                self.assertNotEqual(source, original)
                target.write_text(source, encoding="utf-8")
                with self.assertRaisesRegex(CP.ControlPlaneError, expected):
                    CP.verify_production_credential_workflow_policy(root=root)

    def test_write_job_policy_rejects_cross_step_environment_poisoning(self):
        mutations = (
            'echo "BASH_ENV=/tmp/uaart-evil" >>"$GITHUB_ENV"',
            'echo /tmp/uaart-bin >>"$GITHUB_PATH"',
            "git config --global credential.helper /tmp/uaart-steal",
        )
        for payload in mutations:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as folder:
                root = pathlib.Path(folder)
                self.write_automatic_mode(root)
                target = root / ".github/workflows/uaart_critical.yml"
                original = target.read_text(encoding="utf-8")
                marker = (
                    "          # Without a successful read-only attestation no trusted runtime exists;\n"
                )
                source = original.replace(
                    marker, "          " + payload + "\n" + marker, 1
                )
                target.write_text(source, encoding="utf-8")
                with self.assertRaisesRegex(
                    CP.ControlPlaneError, "WRITE_JOB_ENVIRONMENT_POISONING"
                ):
                    CP.verify_production_credential_workflow_policy(root=root)

    def test_write_job_policy_rejects_recovery_runtime_guard_removal(self):
        for name in ("uaart_critical.yml", "uaart_transaction_watchdog.yml"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = pathlib.Path(folder)
                self.write_automatic_mode(root)
                target = root / ".github/workflows" / name
                original = target.read_text(encoding="utf-8")
                source = original.replace(
                    "UAART_SOURCE_PINNED_WRITER_RUNTIME_VALIDATED",
                    "REMOVED_SOURCE_PINNED_WRITER_RUNTIME",
                    1,
                )
                self.assertNotEqual(source, original)
                target.write_text(source, encoding="utf-8")
                with self.assertRaisesRegex(
                    CP.ControlPlaneError, "WRITE_JOB_RUNTIME_BOOTSTRAP_ORDER"
                ):
                    CP.verify_production_credential_workflow_policy(root=root)

    def test_watchdog_writer_policy_rejects_retry_parent_runtime_gap(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_transaction_watchdog.yml"
            original = target.read_text(encoding="utf-8")
            source = original.replace(
                'git diff --quiet "$WORKFLOW_SOURCE_COMMIT" "$PARENT" -- "${RUNTIME_PATHS[@]}"',
                "true # removed watchdog retry runtime binding",
                1,
            )
            self.assertNotEqual(source, original)
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "WRITE_JOB_RETRY_RUNTIME_BINDING"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_exact_write_workflow_hash_rejects_marker_spoof_bypasses(self):
        cases = (
            (
                "uaart_critical.yml",
                "          unset GH_TOKEN\n",
                "          curl -fsS -H \"Authorization: $GH_TOKEN\" https://example.invalid/\n"
                "          unset GH_TOKEN\n",
            ),
            (
                "uaart_transaction_watchdog.yml",
                "          print('UAART_SOURCE_PINNED_WRITER_RUNTIME_VALIDATED')\n",
                "          print('UAART_SOURCE_PINNED_WRITER_RUNTIME_VALIDATED') # marker-only bypass\n",
            ),
        )
        for name, marker, replacement in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = pathlib.Path(folder)
                self.write_automatic_mode(root)
                target = root / ".github/workflows" / name
                original = target.read_text(encoding="utf-8")
                source = original.replace(marker, replacement, 1)
                self.assertNotEqual(source, original)
                target.write_text(source, encoding="utf-8")
                with self.assertRaisesRegex(
                    CP.ControlPlaneError, "WRITE_WORKFLOW_EXACT_SHA256_MISMATCH"
                ):
                    CP.verify_production_credential_workflow_policy(root=root)

    def test_watchdog_policy_rejects_unpinned_secret_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_transaction_watchdog.yml"
            source = target.read_text(encoding="utf-8").replace(
                "UAART_PINNED_RECOVERY_IDENTITY_VALIDATED",
                "REMOVED_PINNED_RECOVERY_IDENTITY",
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "WATCHDOG_PINNED_RECOVERY_RUNTIME_MISSING"
            ):
                CP.verify_production_credential_workflow_policy(root=root)

    def test_production_policy_rejects_ambiguous_accepted_push(self):
        cases = (
            (
                "uaart_critical.yml",
                'git diff --quiet "$last_commit" "$parent" -- "${accepted_paths[@]}"',
                "CRITICAL_ACCEPTED_PUSH_PATH_DRIFT_GUARD",
            ),
            (
                "uaart_transaction_watchdog.yml",
                'git diff --quiet "$LAST_COMMIT" "$PARENT" -- "${ACCEPTED_PATHS[@]}"',
                "WATCHDOG_ACCEPTED_PUSH_PATH_DRIFT_GUARD",
            ),
        )
        for name, marker, error in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as folder:
                root = pathlib.Path(folder)
                self.write_automatic_mode(root)
                target = root / ".github/workflows" / name
                source = target.read_text(encoding="utf-8").replace(
                    marker, "true # removed accepted-push path proof", 1
                )
                target.write_text(source, encoding="utf-8")
                with self.assertRaisesRegex(CP.ControlPlaneError, error):
                    CP.verify_production_credential_workflow_policy(root=root)

    def test_privileged_token_policy_rejects_python_before_unset(self):
        with tempfile.TemporaryDirectory() as folder:
            root = pathlib.Path(folder)
            self.write_automatic_mode(root)
            target = root / ".github/workflows/uaart_transaction_watchdog.yml"
            source = target.read_text(encoding="utf-8").replace(
                "          unset GH_TOKEN\n",
                "          python3 -I -c 'pass'\n          unset GH_TOKEN\n",
                1,
            )
            target.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(
                CP.ControlPlaneError, "PRIVILEGED_GITHUB_TOKEN_PYTHON_EXPOSURE"
            ):
                CP.verify_production_credential_workflow_policy(root=root)


if __name__ == "__main__":
    unittest.main()
