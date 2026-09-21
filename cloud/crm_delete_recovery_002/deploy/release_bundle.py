"""Build private release bytes from an admitted, immutable recipe and sources.

This module does not stage files or execute production commands. Its transport
calls are authenticated, narrowly scoped GETs. Rollback reconstructs the same
candidate from the original, receipt-bound code backup, never from installed
code and never by downloading the CRM database.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any

from contract import (APPROVAL_REL, PACKAGE_REL, PARENT_TASK_ID, REQUEST_REL,
                      TASK_ID, Envelope, canonical_json, decode_object,
                      read_file, repo_path, require, require_sha, sha)
from transport import Payload, TransportBundle, WORKER_FILES
from package_install import encoded

RECIPE_REL = PACKAGE_REL + "/recipe"
PLAN_PATH = "lifecycle_plan.json"
SOURCE_PATHS = {
    name: "/home/Carix/" + name for name in (
        "cars_ui.py", "db.py", "run_all.py", "start_safe.py", "publication_fence.py",
        "ua_site_counters.py", "ua_crm_catalog_folders.py", "ua_stage_catalog_sync.py",
        "ua_additional_spec.py", "uaart_connection_monitor.py", "kadry_diagnostiki.py",
        "publikaciya.py", "publish_transaction_guard.py", "stranica.py",
        "ua_spec84_runtime.py", "ua_spec_permanent.py", "yadro.py")
}
SOURCE_PATHS.update({
    "www_uaart_com_ua_wsgi.py": "/var/www/www_uaart_com_ua_wsgi.py",
    "seo_rehab_guard_068_repair.py": "/home/Carix/autopilot_inbox/cloud/seo_rehab_guard_068/seo_rehab_guard_068_repair.py",
    "emergency-plan.json": "/home/Carix/uploads/ua0002_job/plan.json",
    "public_fixture_tree/uploads/ua0002_job/console-result.json": "/home/Carix/uploads/ua0002_job/console-result.json",
})
HISTORICAL = frozenset({"emergency-plan.json", "public_fixture_tree/uploads/ua0002_job/console-result.json"})
POLICY_KEYS = frozenset({"version", "task_id", "parent_task_id", "acceptance_scope",
    "package_sources", "package_manifest_path", "package_manifest_sha256", "maximum_seconds",
    "provider", "http_checks", "authority_policy"})
AUTHORITY_KEYS = frozenset({"control_plane_sha256", "critical_workflow_sha256", "trusted_controller_sha256"})
MAX_BYTES = 64 * 1024 * 1024


def _object(value: Any, code: str) -> dict:
    require(isinstance(value, dict), code)
    return value


def _deployment(envelope: Envelope) -> tuple[dict, dict, dict]:
    value = _object(envelope.request.get("deployment"), "DEPLOYMENT_REQUIRED")
    require(set(value) == {"version", "source_sha256", "data_sha256", "policy"}
            and type(value["version"]) is int and value["version"] == 1, "DEPLOYMENT_SCHEMA")
    sources = _object(value["source_sha256"], "DEPLOYMENT_SOURCES")
    require(set(sources) == set(SOURCE_PATHS), "EXACT_SOURCE_SET_REQUIRED")
    for name, digest in sources.items():
        require_sha(digest, "source:" + name)
    data = _object(value["data_sha256"], "RECIPE_DATA_REQUIRED")
    require(0 < len(data) <= 100, "RECIPE_DATA_COUNT")
    for name, digest in data.items():
        require(isinstance(name, str) and name.startswith(RECIPE_REL + "/")
                and Path(name).suffix in {".json", ".txt"}, "RECIPE_DATA_SCOPE")
        repo_path(envelope.root, name)
        require_sha(digest, "recipe_data:" + name)
    policy = _object(value["policy"], "INSTALLATION_POLICY_REQUIRED")
    require(set(policy) == POLICY_KEYS, "INSTALLATION_POLICY_FIELDS")
    require(type(policy["version"]) is int and policy["version"] == 1
            and policy["task_id"] == TASK_ID and policy["parent_task_id"] == PARENT_TASK_ID
            and policy["acceptance_scope"] == "INSTALLATION_AND_RUNTIME_HTTP_VERIFY", "INSTALLATION_POLICY_SCOPE")
    require(policy["package_manifest_path"] == "package/manifest.json"
            and policy["package_manifest_sha256"] == envelope.package_manifest_sha256, "PACKAGE_POLICY_BINDING")
    require(type(policy["maximum_seconds"]) is int and 60 <= policy["maximum_seconds"] <= 1200,
            "INSTALLATION_POLICY_TIMEOUT")
    require(set(_object(policy["package_sources"], "POLICY_SOURCE_MAP")) == set(WORKER_FILES),
            "POLICY_WORKER_CLOSURE")
    for name, digest in policy["package_sources"].items():
        require_sha(digest, "worker:" + name)
    require(envelope.request.get("http_checks") == policy["http_checks"], "REQUEST_HTTP_POLICY_BINDING")
    authority = _object(policy["authority_policy"], "AUTHORITY_POLICY_REQUIRED")
    require(set(authority) == AUTHORITY_KEYS, "AUTHORITY_POLICY_FIELDS")
    for name, digest in authority.items():
        require_sha(digest, name)
    require(sha(encoded(policy)) == envelope.installation_policy_sha256,
            "INSTALLATION_POLICY_HASH_MISMATCH")
    for name, digest in (("automation/control_plane.py", authority["control_plane_sha256"]),
                         (".github/workflows/uaart_critical.yml", authority["critical_workflow_sha256"]),
                         (PACKAGE_REL + "/controller.py", authority["trusted_controller_sha256"])):
        require(sha(read_file(envelope.root, name)) == digest, "AUTHORITY_SOURCE_CHANGED:" + name)
    require(envelope.file_sha256.get(PACKAGE_REL + "/controller.py") == authority["trusted_controller_sha256"],
            "TRUSTED_CONTROLLER_CLOSURE_BINDING")
    return sources, data, policy


def _main_commit(envelope: Envelope) -> tuple[str, str]:
    result = subprocess.run(["git", "-C", str(envelope.root), "rev-parse", "--verify", "HEAD"],
                            capture_output=True, timeout=20, check=False)
    require(result.returncode == 0, "AUTHORITY_CHECKOUT_REQUIRED")
    try:
        value = result.stdout.decode("ascii").strip()
    except UnicodeDecodeError:
        value = ""
    require(re.fullmatch(r"[0-9a-f]{40}", value) is not None, "AUTHORITY_COMMIT_REQUIRED")
    if envelope.operation != "rollback":
        return value, value
    current = subprocess.run(["git", "-C", str(envelope.root), "ls-remote", "origin", "refs/heads/main"],
                             capture_output=True, timeout=30, check=False)
    require(current.returncode == 0, "AUTHORITATIVE_MAIN_UNAVAILABLE")
    try:
        fields = current.stdout.decode("ascii").split()
    except UnicodeDecodeError:
        fields = []
    require(len(fields) == 2 and re.fullmatch(r"[0-9a-f]{40}", fields[0]) is not None
            and fields[1] == "refs/heads/main", "AUTHORITATIVE_MAIN_IDENTITY")
    return fields[0], value


def _private_file(root: Path, relative: str, raw: bytes) -> None:
    root.mkdir(mode=0o700, exist_ok=True)
    target = root
    for part in Path(relative).parts[:-1]:
        target = target / part
        target.mkdir(mode=0o700, exist_ok=True)
    target = root / relative
    target.write_bytes(raw)
    target.chmod(0o600)


def _snapshot_recipe(envelope: Envelope, data: dict, destination: Path) -> None:
    code = {name: digest for name, digest in envelope.file_sha256.items()
            if name.startswith(RECIPE_REL + "/")}
    require(RECIPE_REL + "/build_release.py" in code, "BOUND_RELEASE_BUILDER_REQUIRED")
    declared = dict(code, **data)
    require(len(declared) == len(code) + len(data), "RECIPE_CODE_DATA_COLLISION")
    source_root = repo_path(envelope.root, RECIPE_REL)
    actual = set()
    for path in source_root.rglob("*"):
        require(not path.is_symlink(), "RECIPE_SYMLINK")
        if path.is_dir():
            continue
        require(path.is_file(), "RECIPE_REGULAR_FILE_REQUIRED")
        actual.add(path.relative_to(envelope.root).as_posix())
    require(actual == set(declared), "RECIPE_EXACT_INVENTORY")
    for relative, expected in sorted(declared.items()):
        raw = read_file(envelope.root, relative)
        require(sha(raw) == expected, "RECIPE_HASH_MISMATCH:" + relative)
        _private_file(destination, relative[len(RECIPE_REL) + 1:], raw)


def _backup_sources(envelope: Envelope, transport, expected: dict) -> dict[str, bytes]:
    require(envelope.backup_manifest_sha256 is not None, "ORIGINAL_BACKUP_BINDING_REQUIRED")
    def get(name, digest):
        raw = transport.read_backup_file(envelope.package_manifest_sha256, envelope.transaction_id, name, digest)
        require(isinstance(raw, bytes) and sha(raw) == digest, "BACKUP_GET_DIGEST_MISMATCH")
        return raw
    phase = decode_object(get("phase_backup_manifest.json", envelope.backup_manifest_sha256), "phase_backup")
    require(set(phase) == {"format", "package_manifest_sha256", "transaction_id", "code_backup_manifest_sha256",
            "wsgi_before_sha256", "wsgi_destination", "wsgi_backup_mode"}
            and type(phase["format"]) is int and phase["format"] == 1
            and phase["package_manifest_sha256"] == envelope.package_manifest_sha256
            and phase["transaction_id"] == envelope.transaction_id
            and phase["wsgi_destination"] == SOURCE_PATHS["www_uaart_com_ua_wsgi.py"]
            and phase["wsgi_before_sha256"] == expected["www_uaart_com_ua_wsgi.py"], "PHASE_BACKUP_BINDING")
    code_digest = require_sha(phase["code_backup_manifest_sha256"], "code_backup")
    manifest = decode_object(get("backup_manifest.json", code_digest), "code_backup")
    require(manifest.get("package_sha256") == envelope.package_manifest_sha256, "CODE_BACKUP_PACKAGE_BINDING")
    files = _object(manifest.get("files"), "BACKUP_FILE_MAP_REQUIRED")
    result = {}
    for name, digest in expected.items():
        if name in HISTORICAL:
            continue
        if name == "www_uaart_com_ua_wsgi.py":
            result[name] = get("wsgi.before", digest)
            continue
        relative = SOURCE_PATHS[name].removeprefix("/home/Carix/")
        item = _object(files.get(relative), "BACKUP_SOURCE_REQUIRED:" + name)
        require(set(item) == {"sha256", "stored", "mode"} and item["sha256"] == digest
                and isinstance(item["stored"], str) and re.fullmatch(r"[0-9]{1,4}\.before", item["stored"])
                is not None, "BACKUP_SOURCE_BINDING:" + name)
        result[name] = get(item["stored"], digest)
    return result


def _sources(envelope: Envelope, transport, expected: dict, destination: Path) -> None:
    baselines = _backup_sources(envelope, transport, expected) if envelope.operation != "backup" else {}
    total = 0
    for name, digest in sorted(expected.items()):
        raw = baselines.get(name)
        if raw is None:
            raw = transport.read_source(SOURCE_PATHS[name], digest)
        require(isinstance(raw, bytes) and len(raw) <= 16 * 1024 * 1024 and sha(raw) == digest,
                "SOURCE_GET_DIGEST_MISMATCH:" + name)
        total += len(raw)
        require(total <= MAX_BYTES, "SOURCE_SET_TOO_LARGE")
        _private_file(destination, name, raw)


def _build(recipe: Path, sources: Path, package: Path) -> None:
    result = subprocess.run([sys.executable, "-I", "-B", str(recipe / "build_release.py"),
                             "--sources", str(sources), "--output", str(package)],
                            capture_output=True, timeout=120, check=False)
    # Compiler errors can include complete private source lines; never propagate
    # captured output into workflow logs, public receipts, or raised errors.
    require(result.returncode == 0, "PRIVATE_RELEASE_BUILD_FAILED")


def _payloads(package: Path, expected_manifest: str, policy: dict) -> list[Payload]:
    require(sha(read_file(package, "manifest.json")) == expected_manifest, "BUILT_PACKAGE_MANIFEST_MISMATCH")
    result = []
    total = 0
    for path in sorted(package.rglob("*")):
        require(not path.is_symlink(), "BUILT_PACKAGE_SYMLINK")
        if path.is_dir():
            continue
        require(stat.S_ISREG(path.stat().st_mode), "BUILT_PACKAGE_REGULAR_FILE_REQUIRED")
        relative = path.relative_to(package).as_posix()
        raw = read_file(package, relative)
        total += len(raw)
        require(total <= MAX_BYTES, "BUILT_PACKAGE_TOO_LARGE")
        result.append(Payload("package/" + relative, raw, sha(raw)))
    for name in sorted(WORKER_FILES):
        raw = read_file(package, "install/" + name)
        require(sha(raw) == policy["package_sources"][name], "BUILT_WORKER_POLICY_MISMATCH:" + name)
        result.append(Payload(name, raw, sha(raw)))
    return result


def prepare(envelope: Envelope, transport) -> TransportBundle:
    """Create review-bound bytes without any production mutation or PASS claim."""
    require(isinstance(envelope, Envelope), "VALIDATED_ENVELOPE_REQUIRED")
    sources, data, policy = _deployment(envelope)
    main_commit, code_source_commit = _main_commit(envelope)
    with tempfile.TemporaryDirectory(prefix="uaart-recovery-private-") as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        recipe, source_dir, package = root / "recipe", root / "sources", root / "package"
        _snapshot_recipe(envelope, data, recipe)
        _sources(envelope, transport, sources, source_dir)
        _build(recipe, source_dir, package)
        files = _payloads(package, envelope.package_manifest_sha256, policy)
    # The static policy excludes values that would create an approval/hash cycle.
    # Each dynamic value comes from the already verified workflow envelope.
    plan = {key: value for key, value in policy.items() if key != "authority_policy"}
    plan["installation_policy_sha256"] = envelope.installation_policy_sha256
    plan["authority"] = dict(policy["authority_policy"], repository_root="authority",
        source_repository_root="source_authority" if code_source_commit != main_commit else "authority",
        main_commit=main_commit, code_source_commit=code_source_commit,
        request_path=REQUEST_REL, request_sha256=envelope.request_sha256, run_id=envelope.run_id,
        transaction_id=envelope.transaction_id, installation_approval={
            "path": APPROVAL_REL, "sha256": envelope.request["critical"]["owner_approval_sha256"]})
    raw_plan = encoded(plan)
    files.append(Payload(PLAN_PATH, raw_plan, sha(raw_plan)))
    return TransportBundle(identity={"task_id": TASK_ID, "workflow_run_id": envelope.run_id,
        "transaction_id": envelope.transaction_id, "request_sha256": envelope.request_sha256,
        "manifest_sha256": envelope.manifest_sha256}, files=tuple(files), parameters={
            "plan_path": PLAN_PATH, "plan_sha256": sha(raw_plan),
            "installation_policy_sha256": envelope.installation_policy_sha256,
            "backup_manifest_sha256": envelope.backup_manifest_sha256}, operation=envelope.operation)
