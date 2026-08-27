"""
verify_gate_a.py

Independent verifier: recomputes the manifest for a completed Gate A run
directory and checks it against the recorded receipt. Exits nonzero on
any mismatch or missing required fail-closed predicate. Never claims a
run is a production fix.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_manifest import build_run_manifest  # noqa: E402

REQUIRED_TRUE_FIELDS = [
    "inputs_regular_non_symlink",
    "backup_archive_sha256_matches",
    "all_candidates_compile",
    "no_production_write",
    "protected_fingerprints_unchanged",
    "sqlite_readonly_query_only",
    "sqlite_quick_check_ok",
    "ua0009_fingerprint_unchanged",
    "ua0009_publication_proven_unpublished",
    "site_inventory_unchanged",
    "admin_routes_no_reachable_media_send",
    "media_persistence_functions_unchanged",
    "usercustomize_no_default_startup",
    "singleton_guard_present",
    "no_process_spawn_in_rebuild_path",
    "db_handles_closed_before_slow_work",
    "repeat_runs_byte_identical",
]


def verify(run_dir: str) -> int:
    receipt_path = os.path.join(run_dir, "receipt.json")
    manifest_path = os.path.join(run_dir, "manifest.json")
    if not os.path.isfile(receipt_path) or not os.path.isfile(manifest_path):
        print("BLOCKED: receipt.json or manifest.json missing")
        return 1
    with open(receipt_path, "r", encoding="utf-8") as fh:
        receipt = json.load(fh)
    with open(manifest_path, "r", encoding="utf-8") as fh:
        recorded_manifest = json.load(fh)

    recomputed = build_run_manifest(run_dir)
    recomputed_entries = [e for e in recomputed["entries"]
                           if e["path"] not in ("manifest.json", "receipt.json")]
    recorded_entries = [e for e in recorded_manifest["entries"]
                         if e["path"] not in ("manifest.json", "receipt.json")]
    if recomputed_entries != recorded_entries:
        print("BLOCKED: manifest entries do not match recomputation")
        return 1

    checks = receipt.get("checks", {})
    if receipt.get("final_status") == "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL":
        missing_or_false = [f for f in REQUIRED_TRUE_FIELDS if checks.get(f) is not True]
        if missing_or_false:
            print(f"BLOCKED: required checks not proven true: {missing_or_false}")
            return 1

    if receipt.get("final_status") not in (
        "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", "BLOCKED",
    ):
        print(f"BLOCKED: unexpected final_status {receipt.get('final_status')!r}")
        return 1

    if receipt.get("final_status") == "BLOCKED":
        print("Receipt final_status is BLOCKED; verifier confirms internal consistency only.")
        return 1

    print("VERIFIED: receipt is internally consistent and all required checks are true.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: verify_gate_a.py <run_dir>")
        raise SystemExit(2)
    raise SystemExit(verify(sys.argv[1]))
