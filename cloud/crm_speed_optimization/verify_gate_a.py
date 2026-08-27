"""
verify_gate_a.py (TASK 034)

Standalone, bounded, fail-closed verification of a Gate A receipt (and
optionally a bound manifest). This module never imports or executes
any candidate code and never touches production. All expected failure
conditions (OSError, UnicodeError, JSONDecodeError, ValueError,
TypeError, duplicate JSON keys, symlinks, hard links, oversized files,
files outside the run directory) are caught and returned as
(False, sanitized_reason) -- this module never raises for them.

Integration with a central orchestrator's exact receipt schema is
deferred to a later task; REQUIRED_PREDICATES below defines the fixed
set of predicate keys this standalone verifier enforces.
"""
import json
import os
import stat
import sys
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REQUIRED_PREDICATES = [
    "sqlite_quick_check_ok",
    "ua0009_fingerprint_unchanged",
    "ua0009_not_public",
    "pii_not_emitted",
    "production_write_no",
]

VALID_STATUSES = ("PASS", "BLOCKED")
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


def verify_receipt(receipt_path, manifest_path=None, run_dir=None, report_path=None):
    """Verify a Gate A receipt. `run_dir` defaults to the receipt's own
    directory, preserving the historical two-positional-argument call
    pattern verify_receipt(receipt_path, manifest_path). Never raises
    for expected malformed/tampered/oversized/symlink/hard-link/
    missing-evidence conditions -- always returns (bool, reason)."""
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
        if data.get("pii_emitted") != "NO":
            return False, "pii_emitted_not_no"
        status = data.get("status")
        if status not in VALID_STATUSES:
            return False, f"unexpected_status:{status}"

        predicates = data.get("predicates")
        if not isinstance(predicates, dict):
            return False, "missing_predicates_block"
        for key in REQUIRED_PREDICATES:
            item = predicates.get(key)
            if not isinstance(item, dict) or "status" not in item:
                return False, f"missing_or_malformed_predicate:{key}"
            if item["status"] not in ("OK", "BLOCKED"):
                return False, f"unknown_predicate_status:{key}"

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
            if report_path is not None:
                actual_report_hash = _secure_hash_file(report_path, run_dir_real)
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
