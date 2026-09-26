"""Offline, data-only preparation for the existing Stage 3 registration route.

This does not edit runtime code, weaken a gate, contact production, create a
launch, or manufacture observations. The existing canonical verifier is the
only acceptance test. Outputs belong to a review overlay outside the input
tree; finalization requires real, finalized request/owner/Gate B/Preview files.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile


class PreparationError(ValueError):
    pass


def need(value, reason):
    if not value:
        raise PreparationError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False) + "\n").encode()


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def read(path):
    path = Path(path)
    need(not any(item.is_symlink() for item in (path, *path.parents)), "SYMLINK_INPUT")
    need(path.is_file() and path.stat().st_size <= 16 * 1024 * 1024,
        "BOUNDED_REGULAR_INPUT_REQUIRED")
    return path.read_bytes()


def document(path):
    raw = read(path)
    value = json.loads(raw, object_pairs_hook=strict_pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(PreparationError("NONFINITE_JSON")))
    need(type(value) is dict, "OBJECT_REQUIRED")
    return raw, value


def relative(value):
    need(type(value) is str and re.fullmatch(r"[A-Za-z0-9._/-]+", value), "SAFE_RELATIVE_PATH_REQUIRED")
    path = PurePosixPath(value)
    need(not path.is_absolute() and str(path) == value and ".." not in path.parts,
        "SAFE_RELATIVE_PATH_REQUIRED")
    return value


def module(path):
    read(path)
    name = "reviewed_runtime_activation_control_plane"
    spec = importlib.util.spec_from_file_location(name, path)
    need(spec is not None and spec.loader is not None, "CANONICAL_VERIFIER_REQUIRED")
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def roots(repo, output):
    repo = repo.resolve(strict=True)
    output = output.absolute()
    need(repo.is_dir() and not repo.is_symlink(), "EXACT_REPOSITORY_ROOT_REQUIRED")
    need(not any(item.is_symlink() for item in (output, *output.parents)), "SYMLINK_OUTPUT")
    need(not output.exists(), "NEW_REVIEW_OUTPUT_REQUIRED")
    need(output != repo and repo not in output.parents and output not in repo.parents,
        "REVIEW_OUTPUT_MUST_BE_OUTSIDE_REPOSITORY")
    need(Path("/home/Carix") not in (repo, output, *output.parents), "OFFLINE_OUTPUT_REQUIRED")
    return repo, output


def write_bundle(output, files, report):
    output.mkdir(parents=True, mode=0o700)
    for name, raw in files.items():
        target = output / relative(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)
        target.chmod(0o600)
    (output / "PREPARATION_REPORT.json").write_bytes(canonical(report))
    (output / "PREPARATION_REPORT.json").chmod(0o600)


def prepare(repo, output, source_commit):
    repo, output = roots(repo, output)
    need(re.fullmatch(r"[0-9a-f]{40}", source_commit), "EXACT_REVIEWED_SOURCE_COMMIT_REQUIRED")
    cp = module(repo / "automation/control_plane.py")
    mode_raw, mode = document(repo / "state/EXECUTION_MODE.json")
    old_raw, old = document(repo / cp.RUNTIME_MANIFEST_PATH)
    need(sha(mode_raw) == cp.PRICE_V5_PREVIOUS_MODE_SHA256, "EXACT_PREVIOUS_MODE_BYTES_REQUIRED")
    need(sha(old_raw) == cp.PRICE_V5_PREVIOUS_MANIFEST_SHA256, "EXACT_PREVIOUS_RUNTIME_BYTES_REQUIRED")
    need(mode.get("runtime_activation_path") == cp.TASK088_ACTIVATION_PATH
        and mode.get("runtime_activation_sha256") == cp.PRICE_V5_PREVIOUS_ACTIVATION_SHA256,
        "IMMUTABLE_PREVIOUS_ACTIVATION_REQUIRED")
    need(sha(read(repo / cp.TASK088_ACTIVATION_PATH)) == cp.PRICE_V5_PREVIOUS_ACTIVATION_SHA256,
        "IMMUTABLE_PREVIOUS_ACTIVATION_BYTES_REQUIRED")
    need(set(old) == {"files", "generated_at", "mode_epoch", "schema_version"}
        and old.get("schema_version") == cp.RUNTIME_MANIFEST_SCHEMA
        and old.get("mode_epoch") == mode.get("mode_epoch")
        and set(old.get("files", {})) == set(cp.RUNTIME_PINNED_PATHS), "EXACT_PREVIOUS_RUNTIME_SCHEMA_REQUIRED")
    actual = {name: sha(read(repo / relative(name))) for name in cp.RUNTIME_PINNED_PATHS}
    need({name for name in actual if actual[name] != old["files"][name]} == cp.PRICE_V5_RUNTIME_PATHS,
        "EXACT_THREE_RUNTIME_CHANGES_REQUIRED")
    need(all(actual[name] == expected for name, expected in cp.PRICE_V5_WORKFLOW_SHA256.items()),
        "EXACT_REVIEWED_WORKFLOW_BYTES_REQUIRED")
    for name, expected in cp.PRICE_V5_PREREQUISITES.items():
        need(sha(read(repo / name)) == expected, "CLOSED_PREREQUISITE_CHANGED")
    # This is the existing workflow-policy verifier, not a substitute approval.
    workflow = cp.verify_production_credential_workflow_policy(root=repo)
    need(workflow.get("status") == "PASS", "CANONICAL_WORKFLOW_POLICY_REJECTED")
    generated = datetime.now(timezone.utc).isoformat()
    runtime = dict(old, generated_at=generated, files=actual)
    runtime_raw = canonical(runtime)
    registration = {
        "contract": "UA-ART-TASK088-PRICE-V5-RUNTIME-1",
        "runtime_manifest_sha256": sha(runtime_raw),
        "previous_runtime_manifest_sha256": sha(old_raw),
        "changed_runtime_paths": sorted(cp.PRICE_V5_RUNTIME_PATHS),
        "runtime_file_sha256": {name: actual[name] for name in sorted(cp.PRICE_V5_RUNTIME_PATHS)},
        "preview_validator_sha256": sha(read(repo / "cloud/ua_ge_price_protection/verify_preview.py")),
        "software_gate_sha256": sha(read(repo / "cloud/ua_ge_price_protection/gate.py")),
        "installer_sha256": sha(read(repo / "cloud/task088_price_sync/install_package.py")),
    }
    files = {
        "tree/" + cp.PRICE_V5_PREVIOUS_MODE_PATH: mode_raw,
        "tree/" + cp.PRICE_V5_PREVIOUS_MANIFEST_PATH: old_raw,
        "tree/" + cp.RUNTIME_MANIFEST_PATH: runtime_raw,
        "runtime_registration.json": canonical(registration),
    }
    report = {"contract": "TASK088-OFFLINE-RUNTIME-PREPARATION-1", "status": "PREPARED_NOT_ACTIVATED",
        "source_commit": source_commit, "generated_at": generated,
        "canonical_workflow_policy": workflow,
        "files_sha256": {name: sha(raw) for name, raw in files.items()},
        "production_written": False, "launch_created": False, "stage3_complete": False}
    write_bundle(output, files, report)
    return report


def copy_overlay(source, destination):
    need(source.is_dir() and not source.is_symlink(), "OVERLAY_DIRECTORY_REQUIRED")
    for path in source.rglob("*"):
        need(not path.is_symlink(), "SYMLINK_OVERLAY")
        rel = path.relative_to(source)
        need(rel.parts[0] not in (".git",), "GIT_INTERNAL_OVERLAY_FORBIDDEN")
        if path.is_file():
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(read(path))
        else:
            need(path.is_dir(), "REGULAR_OVERLAY_FILES_REQUIRED")


def finalize(repo, prepared, request_tree, output, task_id):
    repo, output = roots(repo, output)
    need(re.fullmatch(r"TASK088-GE-PRICE-SITE-STAGE3-[A-Za-z0-9-]+", task_id), "EXACT_STAGE3_TASK_REQUIRED")
    prepared = prepared.resolve(strict=True)
    request_tree = request_tree.resolve(strict=True)
    _, report = document(prepared / "PREPARATION_REPORT.json")
    need(report.get("contract") == "TASK088-OFFLINE-RUNTIME-PREPARATION-1"
        and report.get("status") == "PREPARED_NOT_ACTIVATED", "REVIEWED_RUNTIME_PREPARATION_REQUIRED")
    for name, expected in report["files_sha256"].items():
        need(sha(read(prepared / relative(name))) == expected, "PREPARED_RUNTIME_DRIFT")
    with tempfile.TemporaryDirectory(prefix="task088-runtime-review-") as directory:
        snapshot = Path(directory)
        # The input is a reviewed local candidate. Never alter it during checking.
        shutil.copytree(repo, snapshot, dirs_exist_ok=True, symlinks=True,
            ignore=shutil.ignore_patterns(".git", "__pycache__"))
        for path in snapshot.rglob("*"):
            need(not path.is_symlink(), "SYMLINK_CANDIDATE")
        copy_overlay(prepared / "tree", snapshot)
        # Do not accept a launch payload or execution-state update as authority.
        allowed = ("tasks/requests/", "tasks/manifests/", "tasks/gates/", "tasks/approvals/",
            "state/storage/", "cloud/task088_v5_install/evidence/")
        for path in request_tree.rglob("*"):
            if path.is_file():
                need(path.relative_to(request_tree).as_posix().startswith(allowed), "REQUEST_OVERLAY_SCOPE")
        copy_overlay(request_tree, snapshot)
        cp = module(snapshot / "automation/control_plane.py")
        old_mode_raw, mode = document(snapshot / cp.PRICE_V5_PREVIOUS_MODE_PATH)
        need(sha(old_mode_raw) == cp.PRICE_V5_PREVIOUS_MODE_SHA256, "PREVIOUS_MODE_PIN_MISMATCH")
        runtime_raw, runtime = document(snapshot / cp.RUNTIME_MANIFEST_PATH)
        request_path = "tasks/requests/" + task_id + ".json"
        request_raw, request = document(snapshot / request_path)
        critical = request.get("critical", {})
        paths = {"request": request_path, "manifest": critical.get("manifest_path"),
            "owner_approval": critical.get("owner_approval_path"), "gate_b": critical.get("gate_a_path")}
        _, manifest = document(snapshot / relative(paths["manifest"]))
        _, gate = document(snapshot / relative(paths["gate_b"]))
        _, registration = document(prepared / "runtime_registration.json")
        need(manifest.get("runtime_registration") == registration, "MANIFEST_REGISTRATION_MISMATCH")
        need(registration["runtime_manifest_sha256"] == sha(runtime_raw), "RUNTIME_MANIFEST_PIN_MISMATCH")
        paths["preview_gate"] = gate.get("price_protection_preview_path")
        references = {name: {"path": relative(path), "sha256": sha(read(snapshot / relative(path)))}
            for name, path in paths.items()}
        activation = {
            "schema_version": "UA-ART-TASK088-PRICE-V5-ACTIVATION-1", "task_id": task_id,
            "scope": "REGISTER_TASK088_V5_PRICE_PIPELINE", "contract_id": "UA-ART-GE-UA-MARKET-PRICE-001 FINAL v5.0",
            "owner": "Артём Бровинский / UA ART COMPANY LLC", "owner_actor_id": "321059821",
            "repository": "art20021986-wq/ua-art-autopilot", "mode_epoch": mode["mode_epoch"],
            "registered_at": datetime.now(timezone.utc).isoformat(), "source_commit": report["source_commit"],
            "runtime_manifest_path": cp.RUNTIME_MANIFEST_PATH, "runtime_manifest_sha256": sha(runtime_raw),
            "previous_mode_path": cp.PRICE_V5_PREVIOUS_MODE_PATH,
            "previous_mode_sha256": cp.PRICE_V5_PREVIOUS_MODE_SHA256,
            "previous_manifest_path": cp.PRICE_V5_PREVIOUS_MANIFEST_PATH,
            "previous_manifest_sha256": cp.PRICE_V5_PREVIOUS_MANIFEST_SHA256,
            "previous_activation_path": cp.TASK088_ACTIVATION_PATH,
            "previous_activation_sha256": cp.PRICE_V5_PREVIOUS_ACTIVATION_SHA256,
            "changed_runtime_paths": sorted(cp.PRICE_V5_RUNTIME_PATHS), "artifacts": references,
        }
        activation_raw = canonical(activation)
        mode = dict(mode, runtime_manifest_sha256=sha(runtime_raw),
            runtime_activation_path=cp.PRICE_V5_ACTIVATION_PATH, runtime_activation_sha256=sha(activation_raw))
        mode_raw = canonical(mode)
        files = {"tree/" + cp.PRICE_V5_ACTIVATION_PATH: activation_raw,
            "tree/state/EXECUTION_MODE.json": mode_raw}
        for name, raw in files.items():
            target = snapshot / name.removeprefix("tree/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        # This verifies the entire immutable predecessor, owner, workflow,
        # request, Gate B and fresh full Preview chains. No fake PASS function.
        result = cp.verify_execution_mode(root=snapshot, required_mode="AUTOMATIC")
        need(result.get("status") == "PASS", "CANONICAL_MODE_VERIFIER_REJECTED")
        workflow = cp.verify_production_credential_workflow_policy(root=snapshot)
        need(workflow.get("status") == "PASS", "CANONICAL_WORKFLOW_VERIFIER_REJECTED")
        final = {"contract": "TASK088-OFFLINE-RUNTIME-FINALIZATION-1",
            "status": "VALIDATED_OFFLINE_NOT_ACTIVATED", "task_id": task_id,
            "source_commit": report["source_commit"], "canonical_mode_validation": result,
            "canonical_workflow_validation": workflow,
            "files_sha256": {name: sha(raw) for name, raw in files.items()},
            "production_written": False, "launch_created": False, "stage3_complete": False}
    write_bundle(output, files, final)
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    first = sub.add_parser("prepare")
    first.add_argument("--repo-root", type=Path, required=True)
    first.add_argument("--output", type=Path, required=True)
    first.add_argument("--source-commit", required=True)
    second = sub.add_parser("finalize")
    second.add_argument("--repo-root", type=Path, required=True)
    second.add_argument("--prepared", type=Path, required=True)
    second.add_argument("--request-tree", type=Path, required=True)
    second.add_argument("--output", type=Path, required=True)
    second.add_argument("--task-id", required=True)
    args = parser.parse_args()
    try:
        report = (prepare(args.repo_root, args.output, args.source_commit) if args.operation == "prepare"
            else finalize(args.repo_root, args.prepared, args.request_tree, args.output, args.task_id))
        print(json.dumps({"status": report["status"], "output": str(args.output), "production_written": False}))
    except (PreparationError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc), "production_written": False}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
