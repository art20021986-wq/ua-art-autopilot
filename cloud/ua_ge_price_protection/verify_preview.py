#!/usr/bin/env python3
"""Verify canonical Preview evidence bindings; never generate observations.

Call only after the canonical control-plane mode, request, claim and transaction
checks. This adds a required current UA/GE Preview to relevant Production work.
It cannot replace those authority checks or the deployer's fresh DB/file CAS.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import sys

specification = importlib.util.spec_from_file_location("ua_ge_gate", Path(__file__).with_name("gate.py"))
G = importlib.util.module_from_spec(specification)
sys.modules[specification.name] = G
specification.loader.exec_module(G)

SOURCE_NAMES = frozenset({
    "cars_ui.py", "db.py", "cars_schema.py", "team_bot.py", "start_safe.py",
    "yadro.py", "stranica.py", "master_card.py", "publikaciya.py",
    "catalog_design_guard.py", "publish_transaction_guard.py", "ua_site_counters.py",
    "site_ge_inject.py", "ua_stage_catalog_sync.py", "crm.db", "katalog.html", "index.html",
})
PRICE_ROOTS = ("cloud/task088_", "cloud/ua_ge_price_protection/", "automation/", ".github/workflows/")


def relevant(paths):
    """Scope the extra live gate to components named in FINAL v5 section 26."""
    if not isinstance(paths, list) or not paths or any(type(p) is not str for p in paths):
        raise G.ProtectionError("PRICE_CHANGED_PATHS_REQUIRED")
    for text in paths:
        path = PurePosixPath(text)
        if path.is_absolute() or ".." in path.parts:
            raise G.ProtectionError("PRICE_CHANGED_PATH_SCOPE")
        if (path.name in SOURCE_NAMES or "crm.db" in path.parts or text.startswith(PRICE_ROOTS)
                or re.fullmatch(r"UA-[0-9]{4}\.html", path.name)
                or (path.suffix.lower() in {".html", ".htm", ".js", ".css"}
                    and any(part in {"site", "video", "public", "assets", "static", "templates"} for part in path.parts))
                or re.search(r"(?:price|crm|publish|generator|autopilot)", path.name, re.I)):
            return True
    return False


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise G.ProtectionError("PRICE_EVIDENCE_DUPLICATE_KEY")
        result[key] = value
    return result


def read(root, relative):
    if type(relative) is not str or not re.fullmatch(r"[A-Za-z0-9._/-]+", relative):
        raise G.ProtectionError("PRICE_EVIDENCE_PATH")
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "//" in relative:
        raise G.ProtectionError("PRICE_EVIDENCE_PATH")
    target = root / path
    if target.is_symlink() or not target.is_file() or target.resolve(strict=True) != target or target.stat().st_size > 4 * 1024 * 1024:
        raise G.ProtectionError("PRICE_EVIDENCE_FILE")
    raw = target.read_bytes()
    value = json.loads(raw, object_pairs_hook=strict_object)
    if not isinstance(value, dict):
        raise G.ProtectionError("PRICE_EVIDENCE_OBJECT")
    return raw, value


def hash_value(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def preview_checks(root):
    """Reuse the installer's exact literal contract without importing live code."""
    tree = ast.parse((root / "cloud/task088_price_sync/install_package.py").read_bytes())
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "PREVIEW_CHECKS" for target in statement.targets):
            call = statement.value
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                    and call.func.id == "frozenset" and len(call.args) == 1 and not call.keywords):
                break
            checks = ast.literal_eval(call.args[0])
            if type(checks) is set and checks and all(type(item) is str for item in checks):
                return frozenset(checks)
    raise G.ProtectionError("PRICE_INSTALLER_PREVIEW_CONTRACT_UNAVAILABLE")


def verify(root, request_path, expected_request_sha256, *, now=None):
    root = root.resolve(strict=True)
    request_raw, request = read(root, request_path)
    if not hash_value(expected_request_sha256) or G.digest(request_raw) != expected_request_sha256:
        raise G.ProtectionError("PRICE_REQUEST_BINDING")
    if request.get("production_required") is not True:
        raise G.ProtectionError("PRICE_PRODUCTION_REQUEST_REQUIRED")
    if not relevant(request.get("changed_paths")):
        return {"name": "UA/GE PRICE PROTECTION", "evidence_binding": "NOT_APPLICABLE",
                "reason": "CHANGED_PATHS_OUTSIDE_PRICE_COMPONENTS", "observations_generated": False,
                "production_authorized": False}
    critical = request.get("critical")
    if not isinstance(critical, dict):
        raise G.ProtectionError("PRICE_CANONICAL_CRITICAL_REQUEST_REQUIRED")
    gate_raw, gate = read(root, critical.get("gate_a_path"))
    manifest_raw, manifest = read(root, critical.get("manifest_path"))
    if (G.digest(gate_raw) != critical.get("gate_a_sha256")
            or G.digest(manifest_raw) != critical.get("manifest_sha256")
            or gate.get("manifest_sha256") != critical.get("manifest_sha256")
            or manifest.get("task_id") != request.get("task_id")
            or gate.get("task_id") != request.get("task_id") or gate.get("status") != "PASS"):
        raise G.ProtectionError("PRICE_CANONICAL_GATE_A_BINDING")
    raw, preview = read(root, gate.get("price_protection_preview_path"))
    candidate_hash = manifest.get("install_files_sha256", manifest.get("price_protection_candidate_sha256"))
    if (not hash_value(candidate_hash) or G.digest(raw) != gate.get("preview_gate_sha256")
            or preview.get("contract") != "TASK088-FINAL-V5-PREVIEW-GATE-1"
            or preview.get("task_id") != request.get("task_id") or preview.get("status") != "PASS"
            or preview.get("candidate_manifest_sha256") != candidate_hash):
        raise G.ProtectionError("PRICE_PREVIEW_HASH_TASK_CANDIDATE_BINDING")
    checks = preview.get("checks")
    if not isinstance(checks, dict) or set(checks) != preview_checks(root) or any(value != "PASS" for value in checks.values()):
        raise G.ProtectionError("PRICE_FULL_PREVIEW_NOT_100_PERCENT")
    database = preview.get("database")
    if (not isinstance(database, dict)
            or set(database) != {"cars_sha256", "audit_sha256", "published_sha256", "published_codes"}
            or any(not hash_value(database.get(key)) for key in ("cars_sha256", "audit_sha256", "published_sha256"))
            or not hash_value(preview.get("schema_sha256")) or not hash_value(preview.get("system_inventory_sha256"))):
        raise G.ProtectionError("PRICE_PREVIEW_DATABASE_INVENTORY_BINDING")
    codes = preview.get("published_codes")
    if (not isinstance(codes, list) or any(type(code) is not str or not re.fullmatch(r"UA-[0-9]{4}", code) for code in codes)
            or codes != sorted(set(codes)) or codes != database["published_codes"]):
        raise G.ProtectionError("PRICE_PREVIEW_PUBLISHED_SET_BINDING")
    # The full Preview producer observed this set. There is deliberately no
    # hard-coded count and no inference that absent observations mean PASS.
    observed = preview.get("evaluated_at")
    try:
        observed_at = datetime.fromisoformat(observed.replace("Z", "+00:00"))
        if observed_at.tzinfo is None:
            raise ValueError("timezone")
        timestamp = observed_at.timestamp()
    except (TypeError, ValueError, AttributeError):
        raise G.ProtectionError("PRICE_PREVIEW_TIMESTAMP") from None
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    if not 0 <= now - timestamp <= 1800:
        raise G.ProtectionError("PRICE_PREVIEW_STALE_OR_FUTURE")
    inventory = G.source_inventory(root)
    if preview.get("source_files_sha256") != inventory:
        raise G.ProtectionError("PRICE_PREVIEW_CURRENT_SOURCE_BINDING")
    return {"name": "UA/GE PRICE PROTECTION", "evidence_binding": "PASS",
            "task_id": request["task_id"], "request_sha256": expected_request_sha256,
            "preview_sha256": G.digest(raw), "source_manifest_sha256": G.digest(G.encoded(inventory)),
            "published_count": len(codes), "observations_generated": False,
            "production_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-path", required=True)
    parser.add_argument("--request-sha256", required=True)
    arguments = parser.parse_args()
    try:
        result = verify(G.ROOT, arguments.request_path, arguments.request_sha256)
    except (G.ProtectionError, OSError, ValueError) as error:
        result = {"name": "UA/GE PRICE PROTECTION", "evidence_binding": "FAIL",
                  "reason": str(error) if isinstance(error, G.ProtectionError) else type(error).__name__,
                  "observations_generated": False, "production_authorized": False}
    print(G.encoded(result).decode(), end="")
    return 0 if result["evidence_binding"] in {"PASS", "NOT_APPLICABLE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
