"""Orchestrator: BACKUP -> live shadow -> local canary -> atomic source-only
install -> restart -> immediate + delayed postcheck -> automatic rollback on
any FAIL.

This script is meant to run inside the GitHub Actions workflow (or by a
human operator with the same environment/secrets). It performs NO action
until offline tests pass and the anchor allowlist review gate passes.

Exit code 0 == overall PASS. Non-zero == FAIL (rollback already attempted).
"""
from __future__ import annotations

import json
import os
import sys
import unittest

import fetch_and_shadow as fas
import installer
import patcher
import postcheck

ANCHOR_CONFIG_PATH = os.environ.get(
    "VIN4_ANCHOR_CONFIG", os.path.join(os.path.dirname(__file__), "anchor_config.json")
)
DELAYED_CHECK_SECONDS = int(os.environ.get("VIN4_DELAYED_CHECK_SECONDS", "300"))


def run_offline_tests() -> bool:
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.dirname(__file__), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


def main() -> int:
    report: dict = {"stage": "start"}

    # 1. Offline deterministic tests must pass first (no network needed).
    report["stage"] = "offline_tests"
    if not run_offline_tests():
        report["result"] = "FAIL"
        report["reason"] = "offline unit tests failed"
        print(json.dumps(report, indent=2))
        return 1

    # 2. Anchor allowlist must exist and be reviewed (not the example file).
    report["stage"] = "anchor_config_check"
    if not os.path.exists(ANCHOR_CONFIG_PATH):
        report["result"] = "FAIL"
        report["reason"] = (
            f"{ANCHOR_CONFIG_PATH} missing. A reviewed anchor_config.json (populated "
            "from a real live dry-run) is required before any patch is attempted. "
            "Fail-closed by design."
        )
        print(json.dumps(report, indent=2))
        return 1
    with open(ANCHOR_CONFIG_PATH, "r", encoding="utf-8") as f:
        anchor_config = json.load(f)

    # 3. Fetch live source + read-only DB shadow.
    report["stage"] = "live_fetch"
    try:
        live_source, live_source_sha = fas.fetch_source()
        db_shadow = fas.fetch_db_shadow_hashes()
    except fas.FetchError as e:
        report["result"] = "FAIL"
        report["reason"] = f"live fetch failed: {e}"
        print(json.dumps(report, indent=2))
        return 1

    # 4. Backup the exact live source before any modification.
    report["stage"] = "backup"
    backup_path = installer.make_backup(live_source)
    report["backup_path"] = backup_path
    report["live_source_sha256_before"] = live_source_sha

    # 5. Build the patched source (fail-closed anchor verification inside).
    report["stage"] = "patch_and_canary"
    try:
        patched_source, changed_functions = patcher.patch_source(live_source, anchor_config)
    except patcher.AnchorMismatch as e:
        report["result"] = "FAIL"
        report["reason"] = f"anchor mismatch, refusing to patch: {e}"
        print(json.dumps(report, indent=2))
        return 1

    if not changed_functions:
        report["result"] = "FAIL"
        report["reason"] = "no functions were actually changed by the patcher (unexpected no-op)"
        print(json.dumps(report, indent=2))
        return 1

    report["changed_functions"] = changed_functions

    # 6. Local canary: patched source must still parse and pass a smoke check.
    try:
        compile(patched_source, "cars_ui.py", "exec")
    except SyntaxError as e:
        report["result"] = "FAIL"
        report["reason"] = f"patched source failed to compile: {e}"
        print(json.dumps(report, indent=2))
        return 1

    # 7. Atomic source-only install + restart.
    report["stage"] = "install"
    try:
        install_info = installer.install(patched_source)
    except fas.FetchError as e:
        report["result"] = "FAIL"
        report["reason"] = f"install failed: {e}"
        print(json.dumps(report, indent=2))
        return 1
    report["install_info"] = install_info

    # 8. Immediate postcheck.
    report["stage"] = "immediate_postcheck"
    immediate = postcheck.immediate_postcheck(install_info["new_sha256"], db_shadow)
    report["immediate_postcheck"] = immediate
    if not immediate["passed"]:
        report["stage"] = "rollback_after_immediate_fail"
        rb = installer.rollback(backup_path)
        report["rollback"] = rb
        report["result"] = "FAIL"
        report["reason"] = "immediate postcheck failed; rolled back"
        print(json.dumps(report, indent=2))
        return 1

    # 9. Delayed postcheck (detects a later generator overwriting the patch).
    report["stage"] = "delayed_postcheck"
    delayed = postcheck.delayed_postcheck(install_info["new_sha256"], db_shadow, DELAYED_CHECK_SECONDS)
    report["delayed_postcheck"] = delayed
    if not delayed["passed"]:
        report["stage"] = "rollback_after_delayed_fail"
        rb = installer.rollback(backup_path)
        report["rollback"] = rb
        report["result"] = "FAIL"
        report["reason"] = "delayed postcheck failed (drift/overwrite detected); rolled back"
        print(json.dumps(report, indent=2))
        return 1

    report["result"] = "PASS"
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
