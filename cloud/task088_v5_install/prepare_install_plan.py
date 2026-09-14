"""Bind actual private preflight and canonical evidence into an immutable plan.

This is a preparation command, never an installer or authorization source. It
refuses incomplete preview checks and does not manufacture claims/approvals.
Candidate files may contain credentials, so all output stays private. Existing
output is never replaced. Execution adapter must independently retrieve and
revalidate canonical evidence immediately before invoking install().
"""
from datetime import datetime, timezone
import argparse
import importlib.util
import json
import os
from pathlib import Path
import hashlib


def prepare(engine, *, preflight_report, candidate_root, evidence_directory, output_directory, test_root=None, now=None):
    report_raw = Path(preflight_report).read_bytes()
    report = json.loads(report_raw)
    if (report.get("contract") != "TASK088-PRICE-SYNC-READONLY-PREFLIGHT-5"
            or report.get("candidate_verification") != "PASS"
            or report.get("offline_schema_test") != "PASS_CRM_AND_AUDIT_UNCHANGED"
            or report.get("protected_system_readback") != "PASS"):
        raise ValueError("COMPLETE_EXACT_PRIVATE_PREFLIGHT_REQUIRED")
    expected_environment = "TEST" if test_root else "PRODUCTION_READ_ONLY"
    if report.get("environment") != expected_environment:
        raise ValueError("PREFLIGHT_ENVIRONMENT_MISMATCH")
    observed_now = datetime.now(timezone.utc).timestamp() if now is None else now
    if now is not None and test_root is None:
        raise ValueError("PRODUCTION_CLOCK_OVERRIDE_FORBIDDEN")
    engine._fresh(report.get("observed_at"), observed_now)
    root = Path(test_root) if test_root else engine.LIVE_ROOT
    evidence_root = Path(evidence_directory)
    evidence_names = set(engine.EVIDENCE_NAMES) | ({"routing"} if report.get("homepage_policy") else set())
    evidence = {name: engine._read(engine._path(evidence_root, name + ".json")) for name in evidence_names}
    request = json.loads(evidence["request"])
    transaction = json.loads(evidence["transaction"])
    candidates = Path(candidate_root)
    files = {name: engine._read(engine._path(candidates, name)) for name in report["candidate_files"]}
    if (engine.candidate_manifest(files, {name: entry["before_sha256"] for name, entry in report["candidate_files"].items()})
            != report["candidate_files"]):
        raise ValueError("PRIVATE_CANDIDATE_BYTES_DRIFT")
    plan = {"contract": engine.CONTRACT, "environment": "TEST" if test_root else "PRODUCTION",
        "root": str(root), "task_id": request["task_id"], "transaction_id": transaction["transaction_id"],
        "observed_at": report["observed_at"], "files": report["candidate_files"],
        "manifest_sha256": report["candidate_manifest_sha256"], "database": report["database"],
        "schema_sha256": report["schema_sha256"], "candidate_schema_sha256": report["candidate_schema_sha256"],
        "published_count": report["published_count"], "system_inventory": report["system_inventory"],
        "runtime_journal_relative": ".uaart_price_sync_journal",
        "dependencies_sha256": report["dependencies"],
        "preflight_report_sha256": engine.sha(report_raw),
        "evidence_sha256": {name: engine.sha(raw) for name, raw in evidence.items()}}
    if report.get("homepage_policy"):
        plan.update({"homepage_policy": report["homepage_policy"], "routing_evidence_sha256": report["routing_evidence_sha256"]})
    # Bind actual canonical documents without creating or replacing any of them.
    engine._validate(plan, files, evidence, observed_now, root, testing=test_root is not None)
    output = Path(output_directory)
    if any(parent.is_symlink() for parent in (output, *output.parents)):
        raise ValueError("SYMLINK_OUTPUT_FORBIDDEN")
    output.mkdir(mode=0o700)  # Immutable one-time preparation, never reuse.
    def write(path, raw):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if engine._read(path) != raw:
            raise ValueError("PREPARATION_READBACK_FAILED")
    raw = engine.encoded(plan)
    write(output / "plan.json", raw)
    for name, content in evidence.items():
        write(output / "evidence" / (name + ".json"), content)
    for name, content in files.items():
        write(output / "candidate_root" / name, content)
    return {"status": "IMMUTABLE_PLAN_PREPARED_NOT_EXECUTED", "task_id": plan["task_id"],
        "plan_sha256": engine.sha(raw), "plan_path": str(output / "plan.json"),
        "files": len(files), "live_files_written": False, "gate_b_created": False,
        "claim_created": False, "bot_restarted": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True)
    parser.add_argument("--engine-sha256", required=True)
    parser.add_argument("--preflight-report", required=True)
    parser.add_argument("--candidate-root", required=True)
    parser.add_argument("--evidence-directory", required=True)
    parser.add_argument("--output-directory", required=True)
    args = parser.parse_args()
    path = Path(args.engine)
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != args.engine_sha256:
        raise ValueError("EXACT_REVIEWED_ENGINE_REQUIRED")
    spec = importlib.util.spec_from_file_location("task088_reviewed_install_engine", path)
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    print(json.dumps(prepare(engine, preflight_report=args.preflight_report,
        candidate_root=args.candidate_root, evidence_directory=args.evidence_directory,
        output_directory=args.output_directory), sort_keys=True))


if __name__ == "__main__":
    main()
