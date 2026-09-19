#!/usr/bin/env python3
"""Offline PR114 continuation evidence inspection; never an executor or Gate.

Reads a local checkout and prints a sanitized report. An optional --save-name
atomically creates a NEW content-addressed inspection report in this package's
checkpoints directory. No request, claim, receipt, transaction, evidence or
timestamp is updated. Exit zero means inspection ran, never permission to act.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import pathlib
import re
import stat
import tempfile
import zipfile

PACKAGE = pathlib.Path(__file__).resolve().parent
DEFAULT_CHECKPOINT = "cloud/task088_v5_acceptance/resume_20260914/CHECKPOINT.json"
HASH = re.compile(r"[0-9a-f]{64}\Z")
TERMINAL = frozenset({"FINISHED", "ROLLED_BACK"})


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_file(root, relative):
    """Reject absolute/traversal paths and symlinks, including parent links."""
    p = pathlib.PurePosixPath(relative)
    if not relative or p.is_absolute() or ".." in p.parts or str(p) != relative:
        raise ValueError("UNSAFE_PATH")
    target = pathlib.Path(root)
    for part in p.parts:
        target = target / part
        if target.is_symlink():
            raise ValueError("SYMLINK")
    if not stat.S_ISREG(target.stat().st_mode):
        raise ValueError("NOT_REGULAR_FILE")
    with target.open("rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise ValueError("NOT_REGULAR_FILE")
        return f.read()


def read_evidence(root, ref, archives=()):
    try:
        return read_file(root, ref["path"]), {"source": "DIRECT_LOCAL_FILE"}
    except FileNotFoundError:
        # Only this explicitly identified persisted software bundle is supported.
        # Never replace a present but changed direct file with old archive bytes.
        suffix = "/software/gallery_fix_v2/FINAL_CURRENT_CANDIDATE_RESULTS.json"
        if not ref["path"].endswith(suffix):
            raise
    archive_name = "PR114_GALLERY_V2_SOFTWARE_EVIDENCE_20260914.zip"
    choices = [a for a in archives if pathlib.PurePosixPath(a.get("path", "")).name == archive_name]
    if len(choices) != 1:
        raise ValueError("PINNED_SOFTWARE_ARCHIVE_MISSING_OR_AMBIGUOUS")
    archive = choices[0]
    if verify_ref(root, archive)["status"] != "MATCH":
        raise ValueError("ARCHIVE_HASH_MISMATCH")
    raw = read_file(root, archive["path"])
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("ARCHIVE_TOO_LARGE")
    member = "gallery_fix_v2/FINAL_CURRENT_CANDIDATE_RESULTS.json"
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        members = [entry for entry in z.infolist() if entry.filename == member]
        if len(members) != 1 or members[0].file_size > 2 * 1024 * 1024:
            raise ValueError("ARCHIVE_MEMBER_MISSING_DUPLICATE_OR_TOO_LARGE")
        evidence = z.read(members[0])
    return evidence, {"source": "PINNED_ARCHIVE_MEMBER_NO_EXTRACTION", "archive": archive, "member": member}


def verify_ref(root, ref, archives=()):
    result = {"path": ref.get("path"), "expected_sha256": ref.get("sha256")}
    try:
        expected = ref["sha256"]
        if not isinstance(expected, str) or not HASH.fullmatch(expected):
            raise ValueError("INVALID_HASH")
        raw, provenance = read_evidence(root, ref, archives)
        result.update(provenance)
        result.update(actual_sha256=sha(raw), actual_bytes=len(raw))
        size = ref.get("bytes", len(raw))
        if type(size) is not int or size < 0:
            raise ValueError("INVALID_SIZE")
        result["status"] = "MATCH" if sha(raw) == expected and len(raw) == size else "MISMATCH"
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile):
        result["status"] = "MISSING_OR_INVALID"
    return result


def references(value):
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            yield value
        for child in value.values():
            yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def utc(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return parsed.astimezone(dt.timezone.utc)


def freshness(observed_at, now, maximum_seconds):
    try:
        age = (now - utc(observed_at)).total_seconds()
        status = "FUTURE_INVALID" if age < 0 else "EXPIRED" if age >= maximum_seconds else "WITHIN_TIME_WINDOW_ONLY"
        return {"observed_at": observed_at, "maximum_seconds": maximum_seconds,
                "age_seconds": age, "status": status}
    except (ValueError, TypeError, AttributeError):
        return {"observed_at": observed_at, "maximum_seconds": maximum_seconds,
                "status": "MISSING_OR_INVALID"}


def inspect_software(root, checkpoint):
    """Compare the exact bytes named by the hash-bound historical test report."""
    ref = checkpoint.get("software", {}).get("report", {})
    archives = checkpoint.get("archive_index", [])
    result = {"report_integrity": verify_ref(root, ref, archives), "rerun_instruction": "NONE"}
    if result["report_integrity"]["status"] != "MATCH":
        result["disposition"] = "RESTORE_OR_RECONCILE_MISSING_EVIDENCE"
        return result
    report = json.loads(read_evidence(root, ref, archives)[0])
    source_map = report.get("source_files_sha256", {})
    if not isinstance(source_map, dict) or not source_map:
        result["disposition"] = "SOURCE_BINDING_MISSING"
        return result
    checked = [verify_ref(root, {"path": p, "sha256": h}) for p, h in sorted(source_map.items())]
    result["source_files_checked"] = len(checked)
    result["source_differences"] = [x for x in checked if x["status"] != "MATCH"]
    result["original_finished_at"] = report.get("finished_at")
    result["checkpoint_binding_matches"] = all(
        report.get(key) == checkpoint["software"].get(key) and report.get(key)
        for key in ("builder_sha256", "source_manifest_sha256", "finished_at"))
    if result["source_differences"] or not result["checkpoint_binding_matches"]:
        result["disposition"] = "RECONCILE_CHANGED_SCOPE_BEFORE_SELECTIVE_RERUN"
    else:
        result["disposition"] = "RETAIN_UNCHANGED_HISTORICAL_RESULT"
    result["reuse_limits"] = (
        "Local source bytes only. Verify exact private capture, test environment, "
        "dependencies and scope before reusing acceptance. This does not rerun tests "
        "or prove live candidate, browser, CRM or Production state.")
    return result


def inspect_operation(root, relative, kind):
    """Inspect existing identities; never infer safe replay from any status."""
    raw = read_file(root, relative)
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("OPERATION_NOT_OBJECT")
    identity = value.get("identity", {}) if kind == "claim" else value
    if not isinstance(identity, dict):
        raise ValueError("OPERATION_IDENTITY_NOT_OBJECT")
    task_id, run_id = identity.get("task_id"), identity.get("run_id")
    status = value.get("task_execution_status") if kind == "claim" else value.get("status")
    result = {"path": relative, "sha256": sha(raw), "task_id": task_id,
              "run_id": run_id, "saved_status": status, "replay_allowed": False}
    errors = []
    request = {}
    req_ref = {"path": value.get("request_path"), "sha256": value.get("request_sha256")}
    req_check = verify_ref(root, req_ref)
    if req_check["status"] != "MATCH":
        errors.append("REQUEST_HASH_MISSING_OR_CHANGED")
    else:
        request = json.loads(read_file(root, req_ref["path"]))
        if not isinstance(request, dict):
            raise ValueError("REQUEST_NOT_OBJECT")
        if not task_id or request.get("task_id") != task_id or not run_id:
            errors.append("REQUEST_OPERATION_IDENTITY_MISMATCH")
    if kind == "claim":
        if identity.get("task_sha256") != value.get("request_sha256"):
            errors.append("CLAIM_REQUEST_BINDING_MISMATCH")
        receipt_ref = {"path": value.get("receipt_path"), "sha256": value.get("receipt_sha256")}
        result["receipt_integrity"] = verify_ref(root, receipt_ref)
        if result["receipt_integrity"]["status"] != "MATCH":
            errors.append("RECEIPT_MISSING_OR_CHANGED")
        else:
            receipt = json.loads(read_file(root, receipt_ref["path"]))
            if not isinstance(receipt, dict):
                raise ValueError("RECEIPT_NOT_OBJECT")
            expected_path_key = "rollback_receipt_path" if status == "ROLLED_BACK" else "receipt_path"
            execution = request.get("execution", {})
            if not isinstance(execution, dict) or receipt_ref["path"] != execution.get(expected_path_key):
                errors.append("RECEIPT_REQUEST_PATH_MISMATCH")
            if receipt.get("status") != status or status not in TERMINAL:
                errors.append("RECEIPT_TERMINAL_STATUS_NOT_CONFIRMED")
            for key, expected in (("task_id", task_id), ("run_id", run_id),
                                  ("request_sha256", value.get("request_sha256"))):
                if str(receipt.get(key)) != str(expected):
                    errors.append("RECEIPT_IDENTITY_MISMATCH:" + key)
    elif status in TERMINAL:
        # An orphan terminal transaction is not proof of acknowledged completion.
        claim_path = "state/claims/" + pathlib.PurePosixPath(relative).name
        try:
            claim = inspect_operation(root, claim_path, "claim")
            saved_claim = json.loads(read_file(root, claim_path))
            if (claim["disposition"] != "RETAIN_TERMINAL_LOCAL_RECORD"
                    or claim["task_id"] != task_id or claim["run_id"] != run_id
                    or claim["saved_status"] != status
                    or saved_claim.get("production_transaction_path") != relative
                    or saved_claim.get("production_transaction_id") != value.get("transaction_id")
                    or not value.get("transaction_id")):
                errors.append("TERMINAL_TRANSACTION_CLAIM_BINDING_UNCONFIRMED")
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            errors.append("TERMINAL_TRANSACTION_CLAIM_MISSING_OR_INVALID")
    result["binding_issues"] = errors
    result["disposition"] = "RECONCILE_EXISTING_OPERATION" if errors or status not in TERMINAL else "RETAIN_TERMINAL_LOCAL_RECORD"
    result["next_read"] = (
        "Read current canonical request/claim/transaction/receipt, external run and "
        "server outcome for this same identity; use existing reconciliation controls. "
        "A local terminal record or missing receipt never authorizes a retry.")
    return result


def inspect(root, checkpoint_path, now):
    raw = read_file(root, checkpoint_path)
    checkpoint = json.loads(raw)
    # The audit supersedes the old pending-prompt narrative. Never surface
    # checkpoint.next_actions as a live instruction or active console claim.
    notice = {"status": "MISSING_READ_CURRENT_STATE_BEFORE_ACTION", "requires_current_readback": True}
    notice_name = checkpoint.get("audit_continuation_notice")
    if notice_name:
        notice_path = (pathlib.PurePosixPath(checkpoint_path).parent / notice_name).as_posix()
        try:
            notice_raw = read_file(root, notice_path)
            saved_notice = json.loads(notice_raw)
            notice.update(status="HISTORICAL_AUDIT_OVERRIDE_READ", path=notice_path,
                          sha256=sha(notice_raw), observed_at=saved_notice.get("observed_at"),
                          last_saved_console_state=saved_notice.get("credential_console", {}).get("state"),
                          precedence="Audit notice overrides older checkpoint next_actions; neither proves current console state")
        except (OSError, ValueError, TypeError, KeyError):
            notice["status"] = "INVALID_READ_CURRENT_STATE_BEFORE_ACTION"
    refs = list(references(checkpoint))
    checked = [verify_ref(root, ref, checkpoint.get("archive_index", [])) for ref in refs]
    operations = []
    for kind, directory in (("claim", "state/claims"), ("transaction", "state/transactions")):
        for path in sorted((root / directory).glob("TASK088*.json")):
            relative = path.relative_to(root).as_posix()
            try:
                operations.append(inspect_operation(root, relative, kind))
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                operations.append({"path": relative, "disposition": "RECONCILE_INVALID_LOCAL_RECORD", "replay_allowed": False})
    quota_ref = checkpoint.get("quota", {})
    quota_check = verify_ref(root, quota_ref)
    quota_time = None
    if quota_check["status"] == "MATCH":
        quota_time = json.loads(read_file(root, quota_ref["path"])).get("observed_at")
    quota = freshness(quota_time, now, 1800)
    quota["checkpoint_timestamp_matches_raw"] = quota_time is not None and quota_time == checkpoint.get("quota_observed_at")
    quota["policy_source"] = "Existing canonical readiness: quota maximum 1800 seconds"
    issues = [x for x in checked if x["status"] != "MATCH"]
    unclassified_history = sum(x["disposition"].startswith("RECONCILE") for x in operations)
    return {
        "kind": "OFFLINE_CONTINUATION_INSPECTION_NOT_A_GATE",
        "inspector_sha256": sha(pathlib.Path(__file__).read_bytes()),
        "inspected_at": now.isoformat(),
        "checkpoint": {"path": checkpoint_path, "sha256": sha(raw), "original_recorded_at": checkpoint.get("recorded_at")},
        "continuation_notice": notice,
        "referenced_files_checked": len(checked), "reference_issues": issues,
        "reference_integrity": "MATCH" if not issues and checked else "INCOMPLETE",
        "software": inspect_software(root, checkpoint), "quota": quota,
        "operations": operations,
        "operation_scope": "UNCLASSIFIED_LOCAL_TASK088_HISTORY_NOT_A_CURRENT_ACTIVE_OPERATION_LIST",
        "historical_records_requiring_classification": unclassified_history,
        "saved_open_stages": {k: checkpoint.get(k) for k in ("full_preview_gate", "stage3", "stage4")},
        "next_action": "READ_CURRENT_GIT_SERVER_AND_RECEIPTS",
        "next_action_detail": (
            "Read actual main/head, mode/HALT/delegation, candidate/source/DB, canonical "
            "receipts and external jobs before the first incomplete step. Historical "
            "failed/superseded attempts are not presumed active. Do not reinstall closed "
            "Stage 1/2; classify prior attempts using their current canonical records. Preserve saved "
            "evidence and failures. Refresh only expired/changed required observations; "
            "Preview/Gate/quota maximum 1800 seconds, writers 300, reader 30, subject to "
            "the existing canonical validators. Never advance by this report alone."),
        "network_used": False, "canonical_state_written": False,
        "execution_authorized": False, "retry_authorized": False,
        "authenticity": "Hashes verify local integrity, not origin or live freshness; this is not an independent live observation.",
    }


def atomic_report(directory, name, report, hook=lambda stage: None):
    """Publish once using fsync + hard link; never replace a previous report.

    hook is for isolated crash tests only. Abrupt exit may leave an ignored
    temporary file; a complete final report remains discoverable after lost ack.
    """
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", name):
        raise ValueError("INVALID_REPORT_NAME")
    directory = pathlib.Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink():
        raise ValueError("SYMLINK_REPORT_DIRECTORY")
    raw = (json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()
    destination = directory / (name + "." + sha(raw) + ".json")
    if destination.exists():
        if destination.is_symlink() or destination.read_bytes() != raw:
            raise ValueError("EXISTING_REPORT_MISMATCH")
        return destination
    fd, temporary = tempfile.mkstemp(prefix=".partial-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        hook("before_publish")
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if destination.is_symlink() or destination.read_bytes() != raw:
                raise ValueError("EXISTING_REPORT_MISMATCH")
        dir_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        hook("after_publish_before_ack")
        return destination
    finally:
        pathlib.Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, default=PACKAGE.parents[2])
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT)
    parser.add_argument("--save-name", help="New local inspection report, never canonical state")
    args = parser.parse_args()
    root = args.root.resolve()
    report = inspect(root, args.checkpoint, dt.datetime.now(dt.timezone.utc))
    if args.save_name:
        atomic_report(PACKAGE / "checkpoints", args.save_name, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
