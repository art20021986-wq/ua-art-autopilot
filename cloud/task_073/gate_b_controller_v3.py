"""
TASK_073 ROUND 4 - gate_b_controller_v3.py

Manual-only, owner-approved production controller. Invoked exclusively via
the workflow_dispatch workflow in cloud/task_073/workflows/gate_b_v3.yml with
an exact approval token. Claude/Cloud never executes this module; it exists
so Codex can run the already-approved Gate B after independent Gate A V3 PASS.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(__file__))

import gate_a_v3 as ga  # noqa: E402
import gate_b_installer_v3 as gi  # noqa: E402
import bundle_publisher_v3 as bp  # noqa: E402
import postcheck_v3 as pc  # noqa: E402

REQUIRED_APPROVAL_TOKEN = "CRM-UNIFIED-CATALOG-001-V1.0-APPROVED"

VERIFIED_USERNAME = "Carix"


class GateBV3Error(RuntimeError):
    pass


@dataclass
class GateBReport:
    steps: List[str] = field(default_factory=list)
    passed: bool = False
    failure_reason: Optional[str] = None
    rollback_performed: bool = False

    def log(self, message: str) -> None:
        self.steps.append(message)


@dataclass
class CanaryResult:
    ok: bool
    message: str


def check_approval(token: str) -> None:
    if token != REQUIRED_APPROVAL_TOKEN:
        raise GateBV3Error("APPROVAL_TOKEN_MISMATCH")


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise GateBV3Error("missing required environment variable: {}".format(name))
    return value


def run_canary_publish(client: gi.PythonAnywhereWriteClient, probe: Dict) -> CanaryResult:
    remote_primary = probe.get("public_primary_remote_path", "")
    remote_diag = probe.get("public_diag_remote_path", "")
    remote_catalog = probe.get("public_catalog_remote_path", "")
    all_numbers = probe.get(
        "all_published_auto_numbers",
        ["UA-{:04d}".format(i) for i in range(1, 11)] + ["UA-0011"],
    )

    if not (remote_primary and remote_diag and remote_catalog):
        return CanaryResult(False, "CANARY_BLOCKED_MISSING_REMOTE_TARGET_PATHS")

    tmp_dir = tempfile.mkdtemp(prefix="task073_canary_")
    preexisting_catalog: Optional[str] = None
    try:
        local_primary = os.path.join(tmp_dir, "primary.html")
        local_diag = os.path.join(tmp_dir, "diag.html")
        local_catalog = os.path.join(tmp_dir, "catalog.html")

        try:
            preexisting_catalog = client.get_file_text(remote_catalog)
        except gi.InstallerV3Error:
            preexisting_catalog = None
        if preexisting_catalog is not None:
            with open(local_catalog, "w", encoding="utf-8") as fh:
                fh.write(preexisting_catalog)

        targets = bp.CardTargets(
            auto_number="UA-0011",
            primary_path=local_primary,
            diag_path=local_diag,
            catalog_path=local_catalog,
        )
        result = bp.publish_card(targets, all_numbers, existing_diag_text=None, proba=False)
        if not result.ok:
            return CanaryResult(False, "CANARY_BUILD_FAILED:{}".format(result.message))

        with open(local_primary, "r", encoding="utf-8") as fh:
            primary_text = fh.read()
        with open(local_diag, "r", encoding="utf-8") as fh:
            diag_text = fh.read()
        with open(local_catalog, "r", encoding="utf-8") as fh:
            catalog_text = fh.read()

        try:
            client.put_file_text(remote_primary, primary_text)
            client.put_file_text(remote_diag, diag_text)
            client.put_file_text(remote_catalog, catalog_text)
        except Exception as exc:  # noqa: BLE001
            if preexisting_catalog is not None:
                try:
                    client.put_file_text(remote_catalog, preexisting_catalog)
                except Exception:  # noqa: BLE001 - best effort restore
                    pass
            return CanaryResult(False, "CANARY_WRITE_FAILED:{}".format(exc))

        for remote_path, expected_text in (
            (remote_primary, primary_text),
            (remote_diag, diag_text),
            (remote_catalog, catalog_text),
        ):
            on_remote = client.get_file_text(remote_path)
            if on_remote != expected_text:
                return CanaryResult(False, "CANARY_READBACK_MISMATCH:{}".format(remote_path))

        return CanaryResult(True, "CANARY_PUBLISH_PASS")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_gate_b(approval_token: str, always_on_task_id: str) -> GateBReport:
    report = GateBReport()

    check_approval(approval_token)
    report.log("approval_token_verified")

    username = os.environ.get("PYTHONANYWHERE_USERNAME", VERIFIED_USERNAME)
    if username != VERIFIED_USERNAME:
        report.failure_reason = "username drift: expected {} got {}".format(VERIFIED_USERNAME, username)
        return report
    token = require_env("PYTHONANYWHERE_API_TOKEN")

    probe_path = os.path.join(os.path.dirname(__file__), "evidence", "live_probe.json")
    if not os.path.isfile(probe_path):
        report.failure_reason = "GATE_B_V3_BLOCKED_NO_LIVE_PROBE"
        return report
    with open(probe_path, "r", encoding="utf-8") as fh:
        probe = json.load(fh)

    client = gi.PythonAnywhereWriteClient(username, token)

    remote_paths = probe.get("remote_paths", {})
    expected_sha = probe.get("full_file_sha256", {})

    report.log("preflight_get_only_start")
    current_sources: Dict[str, str] = {}
    for label, remote_path in remote_paths.items():
        text = client.get_file_text(remote_path)
        actual_sha = ga.patcher_v3.sha256_text(text)
        expected = expected_sha.get(label)
        if expected is None or actual_sha != expected:
            report.failure_reason = "SHA_DRIFT_PREFLIGHT:{}".format(label)
            return report
        current_sources[label] = text
    report.log("preflight_get_only_pass")

    ekran_anchor = probe.get("ekran_rows_anchor")
    if ekran_anchor:
        current_sources["_ekran_rows_anchor"] = ekran_anchor
    old_block = probe.get("toggle_publish_old_block")
    new_block = probe.get("toggle_publish_new_block")
    if old_block:
        current_sources["_toggle_publish_old_block"] = old_block
    if new_block:
        current_sources["_toggle_publish_new_block"] = new_block

    dry_report = ga.GateAReport()
    patched = ga.run_transform_stage(current_sources, dry_report)
    ga.compile_check_all(patched, dry_report)
    if not dry_report.all_passed:
        report.failure_reason = "SHADOW_DRY_RUN_FAILED:{}".format(dry_report.summary_text())
        return report
    report.log("shadow_dry_run_pass")

    backup_dir = os.path.join(os.path.dirname(__file__), "_gate_b_runtime_backup")
    write_set: Dict[str, gi.WriteSetEntry] = {}
    for label in gi.CODE_FILES:
        if label not in patched:
            continue
        write_set[label] = gi.WriteSetEntry(
            remote_path=remote_paths[label],
            new_content=patched[label],
            preimage_sha256=expected_sha.get(label),
        )

    install_report = gi.install_write_set(client, write_set, backup_dir)
    if install_report.error:
        report.failure_reason = "INSTALL_FAILED:{}".format(install_report.error)
        report.rollback_performed = install_report.rolled_back
        return report
    report.log("code_install_pass:{}".format(",".join(install_report.installed)))

    try:
        client.restart_launcher(always_on_task_id)
        report.log("launcher_restarted")
    except Exception as exc:  # noqa: BLE001
        for label, entry in write_set.items():
            with open(install_report.backups[label], "r", encoding="utf-8") as fh:
                preimage = fh.read()
            client.put_file_text(entry.remote_path, preimage)
        report.rollback_performed = True
        report.failure_reason = "RESTART_FAILED_ROLLED_BACK:{}".format(exc)
        return report

    canary = run_canary_publish(client, probe)
    if not canary.ok:
        for label, entry in write_set.items():
            with open(install_report.backups[label], "r", encoding="utf-8") as fh:
                preimage = fh.read()
            client.put_file_text(entry.remote_path, preimage)
        client.restart_launcher(always_on_task_id)
        report.rollback_performed = True
        report.failure_reason = "CANARY_PUBLISH_FAILED:{}".format(canary.message)
        return report
    report.log("canary_publish_pass")

    primary_url = probe.get("public_primary_url", "")
    diag_url = probe.get("public_diag_url", "")
    catalog_url = probe.get("public_catalog_url", "")

    def _rollback_everything() -> None:
        for label, entry in write_set.items():
            with open(install_report.backups[label], "r", encoding="utf-8") as fh:
                preimage = fh.read()
            client.put_file_text(entry.remote_path, preimage)
        client.restart_launcher(always_on_task_id)

    immediate_results = pc.verify_card_bundle(
        primary_url, diag_url, catalog_url, "UA-0011", bp.DIAG_PLACEHOLDER_TEXT
    )
    if not all(result.ok for result in immediate_results):
        _rollback_everything()
        report.rollback_performed = True
        report.failure_reason = "IMMEDIATE_PUBLIC_VERIFY_FAILED"
        return report
    report.log("immediate_public_verify_pass")

    time.sleep(60)
    delayed_results = pc.verify_card_bundle(
        primary_url, diag_url, catalog_url, "UA-0011", bp.DIAG_PLACEHOLDER_TEXT
    )
    if not all(result.ok for result in delayed_results):
        _rollback_everything()
        report.rollback_performed = True
        report.failure_reason = "DELAYED_PUBLIC_VERIFY_FAILED"
        return report
    report.log("delayed_public_verify_pass")

    report.passed = True
    return report


if __name__ == "__main__":
    supplied_token = os.environ.get("TASK073_APPROVAL_TOKEN", "")
    task_id = os.environ.get("TASK073_ALWAYS_ON_TASK_ID", "")
    final_report = run_gate_b(supplied_token, task_id)
    print("\n".join(final_report.steps))
    if final_report.passed:
        print("GATE_B_V3: PASS")
        sys.exit(0)
    print("GATE_B_V3: FAIL - {}".format(final_report.failure_reason))
    sys.exit(1)
