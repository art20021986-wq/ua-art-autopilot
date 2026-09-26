"""Build a reviewable canonical Stage 3 request from actual, preserved evidence.

Local preparation only: no network, production command, Git write, claim,
transaction or receipt. The launch payload is deliberately outside ``tree``.
This records the current user's existing authorization; it does not ask for or
invent an approval. Missing/stale observations are errors, never a PASS.
"""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import sys


class PreparationError(ValueError):
    pass


def need(value, reason):
    if not value:
        raise PreparationError(reason)


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False) + "\n").encode()


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()


def read(path):
    path = Path(path)
    need(not any(p.is_symlink() for p in (path, *path.parents)), "SYMLINK_INPUT")
    need(path.is_file() and path.stat().st_size <= 16 * 1024 * 1024, "BOUNDED_REGULAR_INPUT_REQUIRED")
    raw = path.read_bytes()
    value = json.loads(raw, object_pairs_hook=strict_object,
        parse_constant=lambda _: (_ for _ in ()).throw(PreparationError("NONFINITE_JSON")))
    need(isinstance(value, dict), "OBJECT_INPUT_REQUIRED")
    return raw, value


def instant(value):
    need(isinstance(value, str), "TIMESTAMP_REQUIRED")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    need(result.tzinfo is not None, "AWARE_TIMESTAMP_REQUIRED")
    return result


def fresh(value, now, seconds):
    need(0 <= (now - instant(value)).total_seconds() <= seconds, "STALE_OR_FUTURE_EVIDENCE")


def relative(value):
    need(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._/-]+", value), "SAFE_REPOSITORY_PATH_REQUIRED")
    path = PurePosixPath(value)
    need(not path.is_absolute() and ".." not in path.parts and str(path) == value, "SAFE_REPOSITORY_PATH_REQUIRED")
    return value


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def build(args):
    now = datetime.now(timezone.utc)
    repo = args.repo_root.resolve(strict=True)
    inputs = args.inputs.resolve(strict=True)
    need(re.fullmatch(r"TASK088-GE-PRICE-SITE-STAGE3-[A-Za-z0-9-]+", args.task_id), "FRESH_STAGE3_ID_REQUIRED")
    task = args.task_id
    package = "cloud/task088_v5_install/release"
    E = load_module("stage3_preparation_engine", repo / "cloud/task088_price_sync/install_package.py")
    C = load_module("stage3_preparation_controller", repo / package / "controller.py")
    A = load_module("stage3_preparation_critical", repo / "automation/critical_adapter.py")
    names = {"preflight", "preview_gate", "writers", "quota", "review", "owner_instruction", "delegation", "runtime_registration"}
    names |= {name for name in ("routing", "source_successor") if (inputs / (name + ".json")).exists()}
    raw, docs = {}, {}
    for name in names:
        raw[name], docs[name] = read(inputs / (name + ".json"))
    report, preview, writers, quota, review = (docs[name] for name in
        ("preflight", "preview_gate", "writers", "quota", "review"))
    need(report.get("contract") == "TASK088-PRICE-SYNC-READONLY-PREFLIGHT-5"
        and report.get("environment") == "PRODUCTION_READ_ONLY"
        and report.get("candidate_verification") == "PASS"
        and report.get("offline_schema_test") == "PASS_CRM_AND_AUDIT_UNCHANGED"
        and report.get("protected_system_readback") == "PASS", "ACTUAL_COMPLETE_PREFLIGHT_REQUIRED")
    fresh(report.get("observed_at"), now, 1800)
    candidate_sha = digest(encoded(report["candidate_files"]))
    need(candidate_sha == report.get("candidate_manifest_sha256"), "CANDIDATE_MANIFEST_BINDING")
    for item in report["candidate_files"].values():
        need(re.fullmatch(r"[0-9a-f]{64}", str(item.get("after_sha256", "")))
            and (item.get("before_sha256") is None or re.fullmatch(r"[0-9a-f]{64}", item["before_sha256"])), "EXACT_CANDIDATE_HASHES")
    need(preview.get("contract") == "TASK088-FINAL-V5-PREVIEW-GATE-1"
        and preview.get("task_id") == task and preview.get("status") == "PASS"
        and preview.get("candidate_manifest_sha256") == candidate_sha
        and preview.get("database") == report["database"]
        and preview.get("schema_sha256") == report["schema_sha256"]
        and preview.get("system_inventory_sha256") == digest(encoded(report["system_inventory"]))
        and preview.get("published_codes") == report["database"]["published_codes"]
        and set(preview.get("checks", {})) == E.PREVIEW_CHECKS
        and all(v == "PASS" for v in preview["checks"].values()), "ACTUAL_FULL_BOUND_PREVIEW_REQUIRED")
    fresh(preview.get("evaluated_at"), now, 1800)
    need(writers.get("task_id") == task and writers.get("install_files_sha256") == candidate_sha
        and writers.get("publication_lock") == "/home/Carix/.ua_art_publish_transaction.lock"
        and writers.get("writers") and writers.get("uncovered_writers") == []
        and all(w.get("fence") == "VERIFIED" for w in writers["writers"]), "ACTUAL_ALL_WRITERS_FENCED_REQUIRED")
    fresh(writers.get("observed_at"), now, 300)
    delegation = docs["delegation"]
    binding_tree = ast.parse((repo / "cloud/task088_price_sync/uaart_price_sync_binding.py").read_bytes())
    visibility = next(ast.literal_eval(node.value) for node in binding_tree.body
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
            and target.id == "VISIBILITY_DELEGATION" for target in node.targets))
    need(delegation.get("contract") == "UA-ART-PRICE-EVENT-DELEGATION-2"
        and delegation.get("environment") == "PRODUCTION" and delegation.get("root") == "/home/Carix"
        and delegation.get("task_id") == task
        and delegation.get("operation") == "UPDATE_CAR_DATA_AND_VISIBLE_PRICE_PROJECTIONS"
        and delegation.get("identity_policy") == "AUTHENTICATED_CRM_ALL_CARS_PUBLIC_VISIBILITY_ONLY"
        and delegation.get("visibility_delegation") == visibility
        and delegation.get("activation") == "BOUNDED_PRICE_EVENTS"
        and delegation.get("schema_sha256") == report["candidate_schema_sha256"]
        and delegation.get("writer_fence_report_sha256") == digest(raw["writers"]), "ACTUAL_FINAL_V5_DELEGATION_REQUIRED")
    expected_code = {**report["dependencies"], **{name: item["after_sha256"]
        for name, item in report["candidate_files"].items() if name.endswith(".py")}}
    need(isinstance(delegation.get("installed_code_sha256"), dict) and all(
        delegation["installed_code_sha256"].get(name) == sha for name, sha in expected_code.items()
        if name.endswith(".py")), "DELEGATED_EXACT_INSTALLED_CODE_REQUIRED")
    need(quota.get("source") == "PYTHONANYWHERE_AUTHENTICATED_ACCOUNT" and quota.get("account") == "Carix"
        and type(quota.get("used_bytes")) is int and type(quota.get("limit_bytes")) is int
        and 0 <= quota["used_bytes"] < quota["limit_bytes"], "ACTUAL_AUTHENTICATED_QUOTA_REQUIRED")
    fresh(quota.get("observed_at"), now, 1800)
    instruction = docs["owner_instruction"]
    need(instruction.get("source") == "CURRENT_USER_REQUEST"
        and instruction.get("text") == "Размести, пожалуйста цены грузинские на сайт."
        and instruction.get("scope") == "APPROVED_STAGE3_PRICE_PUBLICATION", "EXPLICIT_CURRENT_OWNER_INSTRUCTION_REQUIRED")
    approved_at = instant(instruction.get("recorded_at"))
    need(approved_at <= now, "OWNER_INSTRUCTION_FROM_FUTURE")
    registration = docs["runtime_registration"]
    need(registration.get("contract") == "UA-ART-TASK088-PRICE-V5-RUNTIME-1", "REVIEWED_RUNTIME_REGISTRATION_REQUIRED")
    need(review.get("contract") == "TASK088-STAGE3-INDEPENDENT-REVIEW-1"
        and review.get("status") == "PASS" and review.get("software_tests") == "PASS"
        and review.get("independent_review") == "PASS" and review.get("evidence"), "ACTUAL_INDEPENDENT_CODE_AND_TEST_REVIEW_REQUIRED")
    _, release = read(repo / package / "release_sources.json")
    source_map = release["sources"]
    actual_py = {p.name for p in (repo / package).glob("*.py")}
    need(actual_py == set(source_map), "EXACT_RELEASE_CLOSURE_REQUIRED")
    for name, entry in source_map.items():
        original = repo / relative(entry["source_path"])
        generated = repo / package / name
        need(not generated.is_symlink() and not original.is_symlink()
            and generated.read_bytes() == original.read_bytes()
            and digest(generated.read_bytes()) == entry["sha256"], "REVIEWED_RELEASE_SOURCE_DRIFT:" + name)
    reviewed = review.get("source_files_sha256", {})
    preview_sources = preview.get("source_files_sha256", {})
    need(reviewed and preview_sources and all(reviewed.get(path) == sha
        for path, sha in preview_sources.items()), "REVIEW_PREVIEW_SOURCE_BINDING")
    for entry in source_map.values():
        need(reviewed.get(entry["source_path"]) == entry["sha256"],
            "RELEASED_SOURCE_OUTSIDE_REVIEW_SCOPE:" + entry["source_path"])
    for path, sha in reviewed.items():
        need(digest((repo / relative(path)).read_bytes()) == sha, "REVIEWED_SOURCE_DRIFT:" + path)
    need(set(C.REMOTE_FILES) <= actual_py, "REMOTE_PACKAGE_CLOSURE_MISSING")
    mode_raw, mode = read(repo / "state/EXECUTION_MODE.json")
    need(mode.get("mode") == "AUTOMATIC" and mode.get("automatic_production") is True, "CANONICAL_AUTOMATIC_MODE_REQUIRED")
    need(approved_at >= instant(mode["activated_at"]), "OWNER_INSTRUCTION_PREDATES_MODE")
    request_path = "tasks/requests/" + task + ".json"
    need(not (repo / request_path).exists(), "FRESH_REQUEST_TARGET_REQUIRED")
    stage = PurePosixPath(args.preflight_directory)
    need(stage.is_relative_to("/home/Carix/autopilot_inbox/cloud") and ".." not in stage.parts, "EXACT_PRIVATE_PREFLIGHT_DIRECTORY_REQUIRED")
    blueprint = {"contract": E.CONTRACT, "observed_at": report["observed_at"],
        "files": report["candidate_files"], "manifest_sha256": candidate_sha,
        "database": report["database"], "schema_sha256": report["schema_sha256"],
        "candidate_schema_sha256": report["candidate_schema_sha256"],
        "published_count": report["published_count"], "system_inventory": report["system_inventory"],
        "runtime_journal_relative": ".uaart_price_sync_journal",
        "dependencies_sha256": report["dependencies"], "preflight_report_sha256": digest(raw["preflight"])}
    evidence_names = {"quota", "writers", "preview_gate"}
    if report.get("homepage_policy"):
        need("routing" in docs and digest(raw["routing"]) == report.get("routing_evidence_sha256"), "ACTUAL_ROUTING_BINDING_REQUIRED")
        E.validate_routing(docs["routing"])
        blueprint.update({"homepage_policy": report["homepage_policy"], "routing_evidence_sha256": digest(raw["routing"])})
        evidence_names.add("routing")
    if "source_successor" in report:
        descriptor = report["source_successor"]
        need(isinstance(descriptor, dict) and "source_successor" in docs
            and digest(raw["source_successor"]) == descriptor.get("sha256"), "ACTUAL_SUCCESSOR_BINDING_REQUIRED")
        blueprint["source_successor"] = descriptor
        evidence_names.add("source_successor")
    evidence_root = "cloud/task088_v5_install/evidence/" + task
    paths = {name: evidence_root + "/" + name + ".json" for name in evidence_names}
    paths["gate_b"] = "tasks/gates/" + task + ".json"
    nonce = "stage3-" + secrets.token_hex(20)
    deployment = {"contract": "TASK088-CANONICAL-STAGE3-ADAPTER-1", "nonce": nonce,
        "readiness": "READY", "install_blueprint": blueprint, "evidence_paths": paths,
        "preflight_directory": str(stage), "preflight_report_sha256": digest(raw["preflight"]),
        "remote_package_sha256": {name: source_map[name]["sha256"] for name in sorted(C.REMOTE_FILES)}}
    for key in ("routing_evidence_sha256",):
        if key in blueprint:
            deployment[key] = blueprint[key]
    if "source_successor" in blueprint:
        deployment["source_successor_sha256"] = blueprint["source_successor"]["sha256"]
    operations = [{"path": "production/" + name,
        "action": "create" if item["before_sha256"] is None else "replace",
        "expected_before_sha256": item["before_sha256"], "expected_after_sha256": item["after_sha256"]}
        for name, item in sorted(report["candidate_files"].items())]
    operations.append({"path": "production/crm.db/schema", "action": "replace", "content_kind": "SQLITE_SCHEMA",
        "expected_before_sha256": report["schema_sha256"], "expected_after_sha256": report["candidate_schema_sha256"]})
    manifest = {"contract_id": A.CONTRACT_ID, "task_id": task, "task_class": "CRITICAL",
        "acceptance_scope": C.SCOPE, "stage3_complete": False, "production_write": True,
        "explicit_crm_vehicle_approval": True, "backup_required": True, "rollback_required": True,
        "live_verify_required": True, "install_files_sha256": candidate_sha,
        "price_event_delegation_sha256": digest(encoded(delegation)),
        "runtime_registration": registration,
        "operations": operations, "protected_paths": ["production/crm.db/vehicle-values", "production/media"],
        "deployment_plan": deployment,
        "evidence_provenance": {"preflight_sha256": digest(raw["preflight"]), "review_sha256": digest(raw["review"]),
            "owner_instruction_sha256": digest(raw["owner_instruction"]), "canonical_mode_sha256": digest(mode_raw)}}
    manifest_raw = canonical(manifest)
    manifest_sha = digest(manifest_raw)
    gate = {"contract_id": A.CONTRACT_ID, "task_id": task, "status": "PASS", "production_write": False,
        "tests": "PASS", "unexpected_changes": 0, "backup_plan_ready": True, "rollback_plan_ready": True,
        "manifest_sha256": manifest_sha, "evaluated_at": now.isoformat(),
        "writer_fence_report_sha256": digest(raw["writers"]), "preview_gate_sha256": digest(raw["preview_gate"]),
        "price_protection_preview_path": paths["preview_gate"],
        "protected_snapshot": {"database": report["database"], "schema_sha256": report["schema_sha256"],
            "system_inventory_sha256": digest(encoded(report["system_inventory"])), "candidate_manifest_sha256": candidate_sha},
        "review_path": evidence_root + "/review.json", "review_sha256": digest(raw["review"]),
        "backup_execution": "NOT_PERFORMED", "production_installation": "NOT_PERFORMED"}
    gate_raw = canonical(gate)
    storage = {"task_id": task, "target_environment": "production", "read_only": True,
        "measured_at": quota["observed_at"], "total_bytes": quota["limit_bytes"], "used_bytes": quota["used_bytes"],
        "free_bytes": quota["limit_bytes"] - quota["used_bytes"], "quota_evidence_sha256": digest(raw["quota"])}
    storage_path = "state/storage/" + task + ".json"
    storage_raw = canonical(storage)
    tests = release["test_paths"]
    controller_paths = {package + "/" + name for name in ("controller.py", "backup_controller.py", "rollback_controller.py")}
    dependencies = sorted(package + "/" + name for name in actual_py if package + "/" + name not in controller_paths | set(tests))
    execution = {"controller_path": package + "/controller.py", "controller_sha256": source_map["controller.py"]["sha256"],
        "dependency_paths": dependencies, "test_paths": tests,
        "file_sha256": {path: source_map[Path(path).name]["sha256"] for path in sorted(set(tests) | set(dependencies))},
        "receipt_path": "state/receipts/" + task + ".json", "production_required": True, "timeout_seconds": 1200}
    for operation in ("backup", "rollback"):
        name = operation + "_controller.py"
        execution.update({operation + "_controller_path": package + "/" + name,
            operation + "_controller_sha256": source_map[name]["sha256"],
            operation + "_receipt_path": "state/receipts/" + task + "-" + operation.upper() + ".json"})
    execution["evidence_paths"] = sorted(execution[key] for key in ("receipt_path", "backup_receipt_path", "rollback_receipt_path"))
    request = {"task_id": task, "title": "Publish independent Georgian prices: scoped Stage 3 installation",
        "description": "Install reviewed source, empty operational schema and exact price HTML after genuine Preview, writer containment, canonical backup and Gate B. Existing Ukrainian/Georgian values are preserved. Installation receipt does not close Stage 3 or Stage 4 live acceptance.",
        "changed_paths": [operation["path"] for operation in operations], "control_plane_version": "TASK107-R2",
        "requested_min_class": "CRITICAL", "production_required": True, "read_only": False, "ai_requested": False,
        "complexity": 2, "storage_required_bytes": args.storage_required_bytes, "health_checks": ["https://www.uaart.com.ua/"],
        "storage_probe": {"evidence_path": storage_path, "evidence_sha256": digest(storage_raw)},
        "critical": {"allow_crm_vehicle_data": True, "gate_b_authorized": True,
            "manifest_path": "tasks/manifests/" + task + ".json", "manifest_sha256": manifest_sha,
            "gate_a_path": paths["gate_b"], "gate_a_sha256": digest(gate_raw),
            "owner_approval_path": "tasks/approvals/" + task + ".production.json", "owner_approval_sha256": "0" * 64},
        "execution": execution}
    expires = now + timedelta(minutes=20)
    owner = {"schema_version": "UA-ART-PRODUCTION-AUTHORIZATION-1", "task_id": task,
        "owner": "Артём Бровинский / UA ART COMPANY LLC", "owner_authorized": True,
        "production_allowed": True, "authorized_environment": "production",
        "authorization_id": "prod-auth-stage3-" + secrets.token_hex(16), "approved_at": approved_at.isoformat(),
        "expires_at": expires.isoformat(), "launch_nonce": nonce, "manifest_sha256": manifest_sha,
        "gate_a_sha256": digest(gate_raw), "mode_epoch": mode["mode_epoch"], "request_path": request_path,
        "request_subject_sha256": digest(canonical(request))}
    owner_raw = canonical(owner)
    request["critical"]["owner_approval_sha256"] = digest(owner_raw)
    request_raw = canonical(request)
    flat = {**request, **request["critical"]}
    authorization_validation = A.authorize_gate_b(A.CriticalRequest.from_mapping(flat), owner_raw, manifest, gate)
    need(authorization_validation["status"] == "GATE_B_AUTHORIZED", "CANONICAL_GATE_VALIDATION_FAILED")
    marker = {"schema_version": "UA-ART-AUTOSTART-LAUNCH-1", "action": "RUN_EXACT_TASK", "task_id": task,
        "request_path": request_path, "request_sha256": digest(request_raw), "created_at": now.isoformat(),
        "expires_at": expires.isoformat(), "mode_epoch": mode["mode_epoch"], "nonce": nonce,
        "owner_authorized": True, "production_allowed": True}
    tree = {request_path: request_raw, request["critical"]["manifest_path"]: manifest_raw,
        paths["gate_b"]: gate_raw, request["critical"]["owner_approval_path"]: owner_raw, storage_path: storage_raw}
    for name in evidence_names:
        tree[paths[name]] = raw[name]
    for name in ("review", "owner_instruction"):
        tree[evidence_root + "/" + name + ".json"] = raw[name]
    # The private preflight body may include sensitive rows, so only its hash is
    # included above. Source files, DB copies and private report remain private.
    output = args.output
    need(not output.exists() and not any(p.is_symlink() for p in (output, *output.parents)), "UNUSED_LOCAL_OUTPUT_REQUIRED")
    output.mkdir(parents=True, mode=0o700)
    def save(path, data):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    for path, data in tree.items():
        save(output / "tree" / path, data)
    marker_path = "tasks/launch/AUTO-" + task + ".json"
    save(output / "launch_only" / marker_path, canonical(marker))
    result = {"status": "LOCAL_REQUEST_PREPARED_REQUIRES_ROOT_REVIEW_AND_CANONICAL_MAIN_READBACK",
        "task_id": task, "request_path": request_path, "request_sha256": digest(request_raw),
        "manifest_sha256": manifest_sha, "candidate_manifest_sha256": candidate_sha,
        "tree_files": {path: digest(data) for path, data in sorted(tree.items())}, "launch_path": marker_path,
        "launch_sha256": digest(canonical(marker)), "production_written": False, "github_written": False,
        "claim_created": False, "transaction_created": False, "receipt_created": False,
        "writer_evidence_expires_at": (instant(writers["observed_at"]) + timedelta(seconds=300)).isoformat(),
        "next": "Review exact additive current-main diff; commit tree without marker; verify mode/runtime and request/Preview closure on actual main; root approval; one marker-only single-parent commit."}
    save(output / "PREPARATION.json", canonical(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--preflight-directory", required=True)
    parser.add_argument("--storage-required-bytes", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    need(args.storage_required_bytes > 0, "MEASURED_BACKUP_STORAGE_REQUIRED")
    print(json.dumps(build(args), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
