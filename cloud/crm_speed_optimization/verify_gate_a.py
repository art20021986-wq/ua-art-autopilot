"""
verify_gate_a.py (TASK 034 / TASK 035 dual-schema fail-closed verifier)

Standalone, bounded, fail-closed verification of a Gate A receipt (and
optionally a bound manifest). This module never imports or executes
any candidate code and never touches production. All expected failure
conditions (OSError, UnicodeError, JSONDecodeError, ValueError,
TypeError, duplicate JSON keys, symlinks, hard links, oversized files,
files outside the run directory) are caught and returned as
(False, sanitized_reason) -- this module never raises for them.

Two receipt schemas are explicitly recognized:

A. Historical orchestration receipts (crm_speed_gate_a.orchestrate_gate_a
   / run_gate_a): status is GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL or
   BLOCKED; the fixed required predicates live under "evidence";
   production_write must be "NO".

B. Standalone focused receipts (TASK 034 style): status is PASS or
   BLOCKED; the fixed required predicates live under "predicates";
   production_write must be "NO"; pii_emitted must be "NO".

A receipt containing both "evidence" and "predicates" is rejected as
mixed_schema_forms. For the historical schema, required predicates are
checked before any other optional/schema-specific field, so a missing
predicate always returns exactly missing_or_malformed_predicate:<key>.
"""
import json
import os
import stat
import sys
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Focused (TASK 034 standalone) schema predicates -- preserved exactly.
REQUIRED_PREDICATES = [
    "sqlite_quick_check_ok",
    "ua0009_fingerprint_unchanged",
    "ua0009_not_public",
    "pii_not_emitted",
    "production_write_no",
]

# Historical orchestration schema predicates -- must match
# crm_speed_gate_a.REQUIRED_PREDICATES exactly (data only, no logic
# duplication).
HISTORICAL_REQUIRED_PREDICATES = [
    "inputs_present_and_regular",
    "backup_verified",
    "candidates_compile",
    "protected_fingerprints_unchanged",
    "sqlite_readonly_quickcheck_ok",
    "ua0009_fingerprint_unchanged",
    "ua0009_not_public",
    "site_inventory_unchanged",
    "admin_routes_text_only",
    "media_persistence_unchanged",
    "usercustomize_inert",
    "singleton_guard_present",
    "rebuild_queue_bound_no_process_spawn",
    "db_closed_before_slow_work",
    "deterministic_repeat_all_transforms",
    "no_production_write",
]

FOCUSED_VALID_STATUSES = ("PASS", "BLOCKED")
HISTORICAL_VALID_STATUSES = ("GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", "BLOCKED")
VALID_STATUSES = FOCUSED_VALID_STATUSES  # backward-compatible alias
MAX_JSON_BYTES = 2_000_000


def _sanitize(exc):
    return type(exc).__name__


def _secure_stat_check(path, run_dir_real):
    if os.path.islink(path):
        return False, "symlink_rejected"
    try:
        st = os.lstat(path)
    except OSError as exc:
        return False, f"stat_failed:{_sanitize(exc)}"
    if not stat.S_ISREG(st.st_mode):
        return False, "not_regular_file"
    if st.st_nlink != 1:
        return False, "hard_linked_rejected"
    real = os.path.realpath(path)
    try:
        common = os.path.commonpath([real, run_dir_real])
    except ValueError:
        return False, "path_outside_run_dir"
    if common != run_dir_real:
        return False, "path_outside_run_dir"
    if st.st_size > MAX_JSON_BYTES:
        return False, "file_too_large"
    return True, "ok"


def _no_dup_keys(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError(f"duplicate_key:{k}")
        d[k] = v
    return d


def _secure_read_json(path, run_dir_real):
    ok, reason = _secure_stat_check(path, run_dir_real)
    if not ok:
        return None, reason
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        text = raw.decode("utf-8")
        data = json.loads(text, object_pairs_hook=_no_dup_keys)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return None, f"read_failed:{_sanitize(exc)}"
    return data, "ok"


def _secure_hash_file(path, run_dir_real):
    ok, reason = _secure_stat_check(path, run_dir_real)
    if not ok:
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _classify_schema(data):
    has_evidence = isinstance(data, dict) and "evidence" in data
    has_predicates = isinstance(data, dict) and "predicates" in data
    if has_evidence and has_predicates:
        return None, "mixed_schema_forms"
    if has_evidence:
        return "historical", None
    if has_predicates:
        return "focused", None
    return None, "missing_predicates_block"


def _check_predicate_block(predicates, required_keys):
    if not isinstance(predicates, dict):
        return "missing_predicates_block"
    for key in required_keys:
        item = predicates.get(key)
        if not isinstance(item, dict) or "status" not in item:
            return f"missing_or_malformed_predicate:{key}"
        if item["status"] not in ("OK", "BLOCKED"):
            return f"unknown_predicate_status:{key}"
    return None


def verify_receipt(receipt_path, manifest_path=None, run_dir=None, report_path=None):
    """Verify a Gate A receipt against exactly two recognized schemas
    (historical orchestration / focused standalone). `run_dir` defaults
    to the receipt's own directory, preserving the historical
    two-positional-argument call pattern
    verify_receipt(receipt_path, manifest_path). When manifest_path is
    given and report_path is omitted, `<run_dir>/report.md` is used
    automatically whenever the manifest binds a report hash. Never
    raises for expected malformed/tampered/oversized/symlink/hard-link/
    missing-evidence/mixed-schema conditions -- always returns
    (bool, reason)."""
    try:
        effective_run_dir = run_dir if run_dir is not None else os.path.dirname(os.path.abspath(receipt_path))
        if os.path.islink(effective_run_dir) or not os.path.isdir(effective_run_dir):
            return False, "invalid_run_dir"
        run_dir_real = os.path.realpath(effective_run_dir)

        data, reason = _secure_read_json(receipt_path, run_dir_real)
        if data is None:
            return False, reason
        if not isinstance(data, dict):
            return False, "receipt_not_object"

        if data.get("production_write") != "NO":
            return False, "production_write_not_no"

        schema, err = _classify_schema(data)
        if schema is None:
            return False, err

        if schema == "historical":
            status = data.get("status")
            if status not in HISTORICAL_VALID_STATUSES:
                return False, f"unexpected_status:{status}"
            predicates = data.get("evidence")
            pred_err = _check_predicate_block(predicates, HISTORICAL_REQUIRED_PREDICATES)
            if pred_err:
                return False, pred_err
            if status == "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL":
                if data.get("unmet_predicates"):
                    return False, "pass_status_with_unmet_predicates"
                for key in HISTORICAL_REQUIRED_PREDICATES:
                    if predicates.get(key, {}).get("status") != "OK":
                        return False, f"pass_status_but_predicate_not_ok:{key}"
        else:
            if data.get("pii_emitted") != "NO":
                return False, "pii_emitted_not_no"
            status = data.get("status")
            if status not in FOCUSED_VALID_STATUSES:
                return False, f"unexpected_status:{status}"
            predicates = data.get("predicates")
            pred_err = _check_predicate_block(predicates, REQUIRED_PREDICATES)
            if pred_err:
                return False, pred_err
            if status == "PASS":
                if data.get("unmet_predicates"):
                    return False, "pass_status_with_unmet_predicates"
                for key in REQUIRED_PREDICATES:
                    if predicates.get(key, {}).get("status") != "OK":
                        return False, f"pass_status_but_predicate_not_ok:{key}"

        if manifest_path is not None:
            manifest, mreason = _secure_read_json(manifest_path, run_dir_real)
            if manifest is None:
                return False, mreason
            if not isinstance(manifest, dict):
                return False, "manifest_not_object"
            actual_receipt_hash = _secure_hash_file(receipt_path, run_dir_real)
            if actual_receipt_hash is None:
                return False, "receipt_rehash_failed"
            if manifest.get("receipt_sha256") != actual_receipt_hash:
                return False, "receipt_hash_mismatch"

            effective_report_path = report_path
            if effective_report_path is None and "report_sha256" in manifest:
                effective_report_path = os.path.join(effective_run_dir, "report.md")
            if effective_report_path is not None:
                actual_report_hash = _secure_hash_file(effective_report_path, run_dir_real)
                if actual_report_hash is None:
                    return False, "report_rehash_failed"
                if manifest.get("report_sha256") != actual_report_hash:
                    return False, "report_hash_mismatch"

        return True, "ok"
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        return False, f"unexpected_error:{_sanitize(exc)}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: verify_gate_a.py <receipt.json> [manifest.json]")
        sys.exit(2)
    manifest_arg = sys.argv[2] if len(sys.argv) > 2 else None
    ok, reason = verify_receipt(sys.argv[1], manifest_path=manifest_arg)
    print(json.dumps({"ok": ok, "reason": reason}))
    sys.exit(0 if ok else 1)
