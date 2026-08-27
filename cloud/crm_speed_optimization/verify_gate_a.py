"""Canonical, read-only verification of a Gate A receipt (TASK 032).
Enumerates the fixed REQUIRED_PREDICATES set; every absent, malformed, or
non-OK/BLOCKED predicate value blocks. Verifies receipt/manifest hashes
and bound outputs when a manifest is supplied. Never executes Gate A and
never touches production. No pass is derived from hard-coded booleans,
self-referential presence checks, or caller-supplied after snapshots --
only from the evidence already recorded in the receipt itself.
"""
import os
import sys
import json
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crm_speed_gate_a import REQUIRED_PREDICATES  # noqa: E402

VALID_STATUSES = ("GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", "BLOCKED")


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_receipt(receipt_path, manifest_path=None):
    if os.path.islink(receipt_path):
        return False, "receipt_is_symlink"
    with open(receipt_path, "r") as fh:
        receipt = json.load(fh)

    if receipt.get("production_write") != "NO":
        return False, "production_write_not_declared_no"
    if receipt.get("status") not in VALID_STATUSES:
        return False, f"unexpected_status:{receipt.get('status')}"

    evidence = receipt.get("evidence", {}) or {}
    for key in REQUIRED_PREDICATES:
        item = evidence.get(key)
        if not isinstance(item, dict) or "status" not in item:
            return False, f"missing_or_malformed_predicate:{key}"
        if item["status"] not in ("OK", "BLOCKED"):
            return False, f"unknown_predicate_status:{key}"

    if receipt.get("status") == "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL":
        if receipt.get("unmet_predicates"):
            return False, "pass_status_with_unmet_predicates"
        for key in REQUIRED_PREDICATES:
            if evidence.get(key, {}).get("status") != "OK":
                return False, f"pass_status_but_predicate_not_ok:{key}"

    if manifest_path is not None:
        if os.path.islink(manifest_path):
            return False, "manifest_is_symlink"
        with open(manifest_path, "r") as fh:
            manifest = json.load(fh)
        run_dir = os.path.dirname(os.path.abspath(receipt_path))
        actual_receipt_hash = _sha256_file(receipt_path)
        if manifest.get("receipt_sha256") != actual_receipt_hash:
            return False, "receipt_hash_mismatch"
        report_path = os.path.join(run_dir, "report.md")
        if os.path.isfile(report_path):
            if os.path.islink(report_path):
                return False, "report_is_symlink"
            actual_report_hash = _sha256_file(report_path)
            if manifest.get("report_sha256") != actual_report_hash:
                return False, "report_hash_mismatch"

    return True, "ok"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: verify_gate_a.py <receipt.json> [manifest.json]")
        sys.exit(2)
    manifest_path = sys.argv[2] if len(sys.argv) > 2 else None
    ok, reason = verify_receipt(sys.argv[1], manifest_path)
    print(json.dumps({"ok": ok, "reason": reason}))
    sys.exit(0 if ok else 1)
