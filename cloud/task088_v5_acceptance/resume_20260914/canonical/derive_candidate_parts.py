#!/usr/bin/env python3
"""Dry-run local construction from real inputs; never issue authority or deploy.

Default output is a hash/count-only plan on stdout. --output-directory writes
non-executable *.parts.json files into a NEW private local directory, never into
tasks/ or state/. No network, subprocess, credential access, private source copy,
approval, claim, transaction, launch marker, Gate PASS or installation is created.
Input authenticity remains the caller's responsibility; hashes are integrity
checks, not independent proof of observations. Missing input is BLOCKED.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE_MAIN = "0c85a6561d80c4d8789b3a482ae41cdaf9d0f667"
RELEASE = "cloud/task088_v5_install/release"
CHANGED_RUNTIME = (".github/workflows/uaart_critical.yml",
                   ".github/workflows/uaart_maintenance.yml", "automation/control_plane.py")
REQUIRED_INPUTS = {"preflight", "preview", "quota", "writers", "routing", "delegation", "software"}
PREVIEW_CHECKS = {"all_published_cars", "homepage", "catalog", "full_cards", "ru", "ua", "ge",
    "language_switching", "ua_price", "ge_price", "missing_ge", "desktop", "mobile", "links",
    "buttons", "vin", "photos", "specifications", "additional_specification", "stages",
    "counters", "no_unrelated_diff", "source_generation", "independent_db_readback"}


class Blocked(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Blocked(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def engine_encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def pairs(items):
    value = {}
    for key, item in items:
        require(key not in value, "DUPLICATE_JSON_KEY")
        value[key] = item
    return value


def read(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "SYMLINK_INPUT")
    require(path.is_file() and path.stat().st_size <= 24 * 1024 * 1024, "INPUT_FILE_MISSING_OR_UNBOUNDED")
    raw = path.read_bytes()
    value = json.loads(raw, object_pairs_hook=pairs)
    require(type(value) is dict, "JSON_OBJECT_REQUIRED")
    return raw, value


def relative(path):
    require(type(path) is str, "REPOSITORY_PATH_REQUIRED")
    p = PurePosixPath(path)
    require(p.parts and not p.is_absolute() and p.as_posix() == path and ".." not in p.parts,
            "REPOSITORY_PATH_SCOPE")
    return path


def fresh(value, seconds):
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(at.tzinfo is not None, "AWARE_OBSERVATION_REQUIRED")
        require(0 <= (datetime.now(timezone.utc) - at).total_seconds() <= seconds, "STALE_OBSERVATION")
    except (AttributeError, TypeError, ValueError) as error:
        if isinstance(error, Blocked):
            raise
        raise Blocked("INVALID_OBSERVATION_TIME") from None


def literals(path, names):
    result = {}
    for node in ast.parse(path.read_bytes()).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    result[target.id] = ast.literal_eval(node.value)
    require(set(result) == set(names), "REVIEWED_CONSTANTS_MISSING")
    return result


def build(index_path):
    _, index = read(index_path)
    require(index.get("contract") == "TASK088-ACTUAL-CONSTRUCTION-INPUTS-1", "INPUT_INDEX_CONTRACT")
    task = index.get("task_id", "")
    require(re.fullmatch(r"TASK088-GE-PRICE-SITE-STAGE3-[A-Za-z0-9-]+", task) is not None, "REAL_STAGE3_IDENTITY_REQUIRED")
    require(index.get("baseline_main_sha") == BASE_MAIN, "UNREVIEWED_BASELINE_MAIN")
    refs = index.get("inputs")
    require(type(refs) is dict and set(refs) == REQUIRED_INPUTS, "COMPLETE_ACTUAL_INPUT_REFS_REQUIRED")
    data, hashes = {}, {}
    for name, reference in refs.items():
        require(type(reference) is dict and set(reference) == {"path", "sha256"}, "EXACT_INPUT_REFERENCE")
        require(re.fullmatch(r"[0-9a-f]{64}", reference["sha256"]) is not None, "INPUT_SHA256_REQUIRED")
        raw, data[name] = read(reference["path"])
        require(digest(raw) == reference["sha256"], "INPUT_HASH_MISMATCH:" + name)
        hashes[name] = reference["sha256"]

    report, preview, quota, writers, routing, delegation, software = (data[n] for n in
        ("preflight", "preview", "quota", "writers", "routing", "delegation", "software"))
    require(report.get("contract") == "TASK088-PRICE-SYNC-READONLY-PREFLIGHT-5"
        and report.get("environment") == "PRODUCTION_READ_ONLY"
        and report.get("candidate_verification") == "PASS"
        and report.get("offline_schema_test") == "PASS_CRM_AND_AUDIT_UNCHANGED"
        and report.get("protected_system_readback") == "PASS", "REAL_PRIVATE_PREFLIGHT_REQUIRED")
    fresh(report.get("observed_at"), 1800)
    require(report.get("candidate_manifest_sha256") == digest(engine_encoded(report["candidate_files"]))
        and report.get("published_count") == len(report["database"]["published_codes"]),
        "PREFLIGHT_MANIFEST_OR_PUBLISHED_COUNT_MISMATCH")
    require(quota.get("source") == "PYTHONANYWHERE_AUTHENTICATED_ACCOUNT" and quota.get("account") == "Carix"
        and type(quota.get("used_bytes")) is int and type(quota.get("limit_bytes")) is int
        and 0 <= quota["used_bytes"] < quota["limit_bytes"], "ACTUAL_ACCOUNT_QUOTA_REQUIRED")
    fresh(quota.get("observed_at"), 1800)
    require(writers.get("task_id") == task and writers.get("install_files_sha256") == report.get("candidate_manifest_sha256")
        and writers.get("publication_lock") == "/home/Carix/.ua_art_publish_transaction.lock"
        and writers.get("uncovered_writers") == [] and type(writers.get("writers")) is list
        and bool(writers["writers"]) and all(w.get("fence") == "VERIFIED" for w in writers["writers"]),
        "ACTUAL_ALL_WRITER_FENCES_REQUIRED")
    fresh(writers.get("observed_at"), 300)
    require(preview.get("contract") == "TASK088-FINAL-V5-PREVIEW-GATE-1" and preview.get("task_id") == task
        and preview.get("status") == "PASS" and set(preview.get("checks", {})) == PREVIEW_CHECKS
        and all(v == "PASS" for v in preview["checks"].values()), "REAL_FULL_PREVIEW_REQUIRED")
    fresh(preview.get("evaluated_at"), 1800)
    require(preview.get("candidate_manifest_sha256") == report.get("candidate_manifest_sha256")
        and preview.get("database") == report.get("database")
        and preview.get("schema_sha256") == report.get("schema_sha256")
        and preview.get("published_codes") == report["database"]["published_codes"]
        and preview.get("system_inventory_sha256") == digest(engine_encoded(report["system_inventory"])),
        "PREVIEW_PREFLIGHT_BINDING_MISMATCH")
    require(software.get("software_status") == "PASS" and software.get("contract") == "UA-GE-PRICE-PROTECTION-SOFTWARE-1",
        "ACTUAL_SOFTWARE_GATE_REQUIRED")
    gate_path = ROOT / "cloud/ua_ge_price_protection/gate.py"
    require(software.get("source_files_sha256", {}).get("cloud/ua_ge_price_protection/gate.py") == digest(gate_path.read_bytes()),
        "SOFTWARE_GATE_SOURCE_DRIFT")
    spec = importlib.util.spec_from_file_location("task088_derive_existing_inventory", gate_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    inventory = module.source_inventory(ROOT)
    require(software["source_files_sha256"] == inventory == preview.get("source_files_sha256"), "CURRENT_SOURCE_CLOSURE_MISMATCH")
    engine_spec = importlib.util.spec_from_file_location("task088_derive_existing_engine", ROOT / "cloud/task088_price_sync/install_package.py")
    engine = importlib.util.module_from_spec(engine_spec)
    engine_spec.loader.exec_module(engine)
    engine.validate_routing(routing)
    require(delegation.get("contract") == "UA-ART-PRICE-EVENT-DELEGATION-2" and delegation.get("task_id") == task
        and delegation.get("environment") == "PRODUCTION" and delegation.get("root") == "/home/Carix"
        and delegation.get("operation") == "UPDATE_PUBLISHED_CAR_HOME_CATALOG_PRICES"
        and delegation.get("identity_policy") == "AUTHENTICATED_CRM_PUBLISHED_CARS", "REAL_REVIEWED_V2_DELEGATION_REQUIRED")

    constants = literals(ROOT / "automation/control_plane.py", {"PRICE_V5_PREVIOUS_MODE_SHA256",
        "PRICE_V5_PREVIOUS_MANIFEST_SHA256", "PRICE_V5_PREVIOUS_ACTIVATION_SHA256", "PRICE_V5_WORKFLOW_SHA256"})
    old_mode_raw, old_mode = read(ROOT / "state/EXECUTION_MODE.json")
    old_runtime_raw, old_runtime = read(ROOT / "state/AUTOPILOT_RUNTIME_MANIFEST.json")
    require(digest(old_mode_raw) == constants["PRICE_V5_PREVIOUS_MODE_SHA256"]
        and digest(old_runtime_raw) == constants["PRICE_V5_PREVIOUS_MANIFEST_SHA256"], "BASELINE_RUNTIME_ALREADY_CHANGED_RECONCILE_FIRST")
    activation_raw, _ = read(ROOT / relative(old_mode["runtime_activation_path"]))
    require(digest(activation_raw) == constants["PRICE_V5_PREVIOUS_ACTIVATION_SHA256"], "BASELINE_ACTIVATION_DRIFT")
    stage2_raw, stage2 = read(ROOT / "state/receipts/TASK088-GE-PRICE-CRM-STAGE2.json")
    require(digest(stage2_raw) == "d0b731b93a73da0d041a1af6e987f0e6634823001a2461bc882c927a588faae7"
        and stage2.get("status") == "FINISHED" and stage2.get("stage2_status") == "PASS"
        and stage2.get("installed_source_sha256") == report["candidate_files"]["cars_ui.py"]["before_sha256"],
        "STAGE2_RECEIPT_OR_PREFLIGHT_PREIMAGE_DRIFT")
    runtime = dict(old_runtime, files=dict(old_runtime["files"]), generated_at=preview["evaluated_at"])
    for path in CHANGED_RUNTIME:
        runtime["files"][path] = digest((ROOT / path).read_bytes())
    require(all(runtime["files"][path] == sha for path, sha in constants["PRICE_V5_WORKFLOW_SHA256"].items()),
        "UNREVIEWED_RUNTIME_WORKFLOW_CANDIDATE")

    _, release = read(ROOT / RELEASE / "release_sources.json")
    package_hashes = {}
    require(release.get("contract") == "TASK088-V5-REVIEWED-RELEASE-SOURCE-MAP-1", "RELEASE_SOURCE_MAP_CONTRACT")
    for name, provenance in release["sources"].items():
        require(Path(name).name == name and name.endswith(".py"), "RELEASE_FILE_SCOPE")
        expected = provenance["sha256"]
        require(digest((ROOT / RELEASE / name).read_bytes()) == expected
            == digest((ROOT / relative(provenance["source_path"])).read_bytes()), "RELEASE_SOURCE_DRIFT")
        package_hashes[RELEASE + "/" + name] = expected

    blueprint = {"contract": "UA-ART-GE-PRICE-STAGE3-INSTALL-5", "observed_at": report["observed_at"],
        "files": report["candidate_files"], "manifest_sha256": report["candidate_manifest_sha256"],
        "database": report["database"], "schema_sha256": report["schema_sha256"],
        "candidate_schema_sha256": report["candidate_schema_sha256"], "published_count": report["published_count"],
        "system_inventory": report["system_inventory"], "runtime_journal_relative": ".uaart_price_sync_journal",
        "dependencies_sha256": report["dependencies"], "preflight_report_sha256": hashes["preflight"]}
    require(report.get("homepage_policy") and report.get("routing_evidence_sha256") == hashes["routing"],
        "ACTUAL_EXISTING_ROUTING_POLICY_REQUIRED")
    blueprint.update(homepage_policy=report["homepage_policy"], routing_evidence_sha256=hashes["routing"])
    operations = [{"path": "production/" + relative(name),
        "action": "create" if info["before_sha256"] is None else "replace",
        "expected_before_sha256": info["before_sha256"], "expected_after_sha256": info["after_sha256"]}
        for name, info in sorted(report["candidate_files"].items())]
    operations.append({"path": "production/crm.db/schema", "action": "replace", "content_kind": "SQLITE_SCHEMA",
        "expected_before_sha256": report["schema_sha256"], "expected_after_sha256": report["candidate_schema_sha256"]})
    registration = {"contract": "UA-ART-TASK088-PRICE-V5-RUNTIME-1", "runtime_manifest_sha256": digest(canonical(runtime)),
        "previous_runtime_manifest_sha256": digest(old_runtime_raw), "changed_runtime_paths": sorted(CHANGED_RUNTIME),
        "runtime_file_sha256": {p: runtime["files"][p] for p in sorted(CHANGED_RUNTIME)},
        "preview_validator_sha256": digest((ROOT / "cloud/ua_ge_price_protection/verify_preview.py").read_bytes()),
        "software_gate_sha256": digest(gate_path.read_bytes()),
        "installer_sha256": digest((ROOT / "cloud/task088_price_sync/install_package.py").read_bytes())}
    execution = {"controller_path": RELEASE + "/controller.py", "controller_sha256": package_hashes[RELEASE + "/controller.py"],
        "backup_controller_path": RELEASE + "/backup_controller.py", "backup_controller_sha256": package_hashes[RELEASE + "/backup_controller.py"],
        "rollback_controller_path": RELEASE + "/rollback_controller.py", "rollback_controller_sha256": package_hashes[RELEASE + "/rollback_controller.py"],
        "test_paths": release["test_paths"], "file_sha256": package_hashes, "production_required": True,
        "receipt_path": "state/receipts/" + task + ".json", "backup_receipt_path": "state/receipts/" + task + "-BACKUP.json",
        "rollback_receipt_path": "state/receipts/" + task + "-ROLLBACK.json"}
    return {"install_blueprint.parts.json": blueprint, "runtime_manifest.parts.json": runtime,
        "runtime_registration.parts.json": registration, "request_execution.parts.json": execution,
        "manifest_fields.parts.json": {"task_id": task, "install_files_sha256": report["candidate_manifest_sha256"],
            "price_event_delegation_sha256": digest(engine_encoded(delegation)), "operations": operations},
        "construction_receipt.json": {"contract": "TASK088-DERIVED-PARTS-NOT-AUTHORITY-1", "task_id": task,
            "status": "CANDIDATE_PARTS_DERIVED_NOT_AUTHORIZED", "input_sha256": hashes,
            "stage2_raw_sha256": digest(stage2_raw), "private_source_copied": False,
            "gate_created": False, "approval_created": False, "claim_created": False,
            "transaction_created": False, "launch_created": False, "production_written": False,
            "not_complete_documents": True,
            "remaining": ["independently validate actual input provenance and candidate bytes",
                "complete reviewed manifest protected scope, deployment paths and actual nonce",
                "produce actual Gate for exact final manifest", "materialize existing owner authorization and final request bindings",
                "complete runtime activation and validate full candidate", "canonical marker-only launch after fresh final checks"]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--output-directory", type=Path)
    args = parser.parse_args()
    try:
        parts = build(args.inputs)
        outputs = {name: canonical(value) for name, value in parts.items()}
        if args.output_directory:
            out = args.output_directory.absolute()
            require(not any(p.is_symlink() for p in (out, *out.parents)), "SYMLINK_OUTPUT")
            require(not out.is_relative_to(ROOT / "state") and not out.is_relative_to(ROOT / "tasks")
                and not out.is_relative_to(Path("/home/Carix")), "OUTPUT_MUST_BE_LOCAL_NONCANONICAL_PARTS")
            out.mkdir(mode=0o700)
            for name, raw in outputs.items():
                fd = os.open(out / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(raw); handle.flush(); os.fsync(handle.fileno())
                require((out / name).read_bytes() == raw, "OUTPUT_READBACK_MISMATCH")
        print(json.dumps({"status": "LOCAL_CANDIDATE_PARTS_DERIVED_NOT_AUTHORIZED", "dry_run": not bool(args.output_directory),
            "files": {name: {"sha256": digest(raw), "bytes": len(raw)} for name, raw in outputs.items()},
            "canonical_files_written": False, "production_written": False}))
        return 0
    except (Blocked, OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error) if isinstance(error, Blocked) else type(error).__name__,
            "canonical_files_written": False, "production_written": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
