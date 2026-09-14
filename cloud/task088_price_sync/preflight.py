"""Read-only source/CRM/public-file preflight. No live writes or bot imports.

Only unique private output below the owner-approved existing staging directory
is written. A SQLite online backup and its migrated test copy remain private in
that directory. A blocked authority bridge never becomes a fabricated Gate B.
"""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import sys

LIVE_ROOT = Path("/home/Carix")
PACKAGE_RELATIVE = "autopilot_inbox/cloud/task088_price_sync_current"
CONTRACT = "TASK088-PRICE-SYNC-READONLY-PREFLIGHT-5"
MODULES = {"uaart_market_prices.py", "uaart_price_sync_outbox.py", "uaart_price_sync_runtime.py",
           "uaart_price_sync_binding.py", "owner_policy.py", "price_publication.py",
           "uaart_price_sync_confirmation.py", "uaart_price_control_reader.py"}
TOOLS = {"preflight.py", "install_package.py", "patch_cars_ui.py", "patch_yadro.py", "patch_stranica.py",
         "patch_catalog_design_guard.py", "patch_guard.py", "initial_html_prices.py"}
SOURCES = {"cars_ui.py", "yadro.py", "stranica.py", "catalog_design_guard.py", "publish_transaction_guard.py"}
DEPENDENCIES = {"db.py", "cars_schema.py", "start_safe.py", "master_card.py", "publikaciya.py",
                "ua_stage_catalog_sync.py", "catalog_design_golden.html", "team_bot.py"}
MAX_FILE = 8 * 1024 * 1024


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def _safe(root, relative):
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("PATH_OUTSIDE_BOUND_ROOT")
    for parent in (path, *path.parents):
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise ValueError("SYMLINK_PATH_FORBIDDEN")
    return path


def _read(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE:
        raise ValueError("REGULAR_BOUNDED_FILE_REQUIRED:" + path.name)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        with os.fdopen(fd, "rb", closefd=False) as handle:
            result = handle.read(MAX_FILE + 1)
        if len(result) > MAX_FILE:
            raise ValueError("FILE_LIMIT")
        return result
    finally:
        os.close(fd)


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    if _read(path) != value:
        raise ValueError("PRIVATE_CANDIDATE_READBACK_MISMATCH")


def _database_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fresh_quota(quota, now):
    try:
        instant = datetime.fromisoformat(quota["observed_at"].replace("Z", "+00:00"))
        timestamp = instant.timestamp()
        return (instant.tzinfo is not None and quota["source"] == "PYTHONANYWHERE_AUTHENTICATED_ACCOUNT" and quota["account"] == "Carix"
                and 0 <= now - timestamp <= 1800 and type(quota["used_bytes"]) is int
                and type(quota["limit_bytes"]) is int and 0 <= quota["used_bytes"] < quota["limit_bytes"])
    except (KeyError, TypeError, ValueError):
        return False


def run(output_id, expected_bundle_sha256, *, test_root=None, package_relative=PACKAGE_RELATIVE):
    root = Path(test_root) if test_root is not None else LIVE_ROOT
    if root == LIVE_ROOT and test_root is not None:
        raise ValueError("TEST_ROOT_CANNOT_BE_PRODUCTION")
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError("EXACT_EXISTING_ROOT_REQUIRED")
    if not re.fullmatch(r"preflight-[A-Za-z0-9-]{8,90}", output_id):
        raise ValueError("UNIQUE_PREFLIGHT_OUTPUT_ID_REQUIRED")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_bundle_sha256):
        raise ValueError("REVIEWED_BUNDLE_HASH_REQUIRED")
    if not re.fullmatch(r"autopilot_inbox/cloud/task088_price_sync_[A-Za-z0-9_-]+", package_relative):
        raise ValueError("TASK_SCOPED_PRIVATE_STAGING_REQUIRED")
    package = _safe(root, package_relative)
    if not package.is_dir():
        raise ValueError("EXISTING_STAGING_PACKAGE_REQUIRED")
    bundle_bytes = _read(_safe(package, "preflight_bundle.json"))
    if _sha(bundle_bytes) != expected_bundle_sha256:
        raise ValueError("PREFLIGHT_BUNDLE_HASH_MISMATCH")
    bundle = json.loads(bundle_bytes)
    if bundle.get("contract") != CONTRACT:
        raise ValueError("PREFLIGHT_BUNDLE_CONTRACT_MISMATCH")
    output_parent = _safe(package, "preflight_outputs")
    output_parent.mkdir(mode=0o700, exist_ok=True)
    output = _safe(output_parent, output_id)
    output.mkdir(mode=0o700)  # Refuse repeat/reuse of any previous observation.
    report = {"contract": CONTRACT, "environment": "TEST" if test_root else "PRODUCTION_READ_ONLY",
              "observed_at": datetime.now(timezone.utc).isoformat(), "bundle_sha256": expected_bundle_sha256,
              "production_source_written": False, "crm_source_written": False, "public_html_written": False,
              "bot_imported": False, "bot_restarted": False, "gate_b": "NOT_CREATED",
              "output_id": output_id, "blockers": [], "sources": {}, "dependencies": {}, "html": {}}
    failures, candidates, before = [], {}, {}
    try:
        pins = bundle.get("package_sha256", {})
        if set(pins) != MODULES | TOOLS:
            raise ValueError("EXACT_PACKAGE_PIN_SET_REQUIRED")
        for name in sorted(pins):
            data = _read(_safe(package, name))
            if _sha(data) != pins[name]:
                raise ValueError("PACKAGE_SOURCE_HASH_MISMATCH:" + name)
            ast.parse(data.decode("utf-8"))
        # Only the reviewed private package is imported; no live CRM source is imported.
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(package))
        try:
            engine = importlib.import_module("install_package")
            migrator = importlib.import_module("initial_html_prices")
            routing = bundle.get("routing")
            homepage_policy = bundle.get("homepage_policy", {})
            if homepage_policy:
                engine.verify_routing_sources(routing, root=root)
                report["homepage_policy"] = homepage_policy
                report["routing_evidence_sha256"] = bundle["routing_evidence_sha256"]
            patches = {"cars_ui.py": ("patch_cars_ui", "patch_source", False),
                "publish_transaction_guard.py": ("patch_guard", "patch_source", False),
                "yadro.py": ("patch_yadro", "patch_yadro", True),
                "stranica.py": ("patch_stranica", "patch_stranica", True),
                "catalog_design_guard.py": ("patch_catalog_design_guard", "patch_catalog_design_guard", True)}
            if set(bundle.get("source_sha256", {})) != SOURCES:
                raise ValueError("EXACT_LIVE_SOURCE_PINS_REQUIRED")
            for name, (module_name, function_name, byte_api) in patches.items():
                data = _read(_safe(root, name))
                before[name] = _sha(data)
                if before[name] != bundle["source_sha256"][name]:
                    raise ValueError("CURRENT_SOURCE_PIN_MISMATCH:" + name)
                result = getattr(importlib.import_module(module_name), function_name)(data if byte_api else data.decode("utf-8"))
                candidate = result[0] if byte_api else result.encode("utf-8")
                ast.parse(candidate.decode("utf-8"))
                candidates[name] = candidate
                report["sources"][name] = {"before_sha256": before[name], "after_sha256": _sha(candidate), "compile": "PASS"}
            for name in sorted(DEPENDENCIES):
                data = _read(_safe(root, name))
                actual = _sha(data)
                report["dependencies"][name] = actual
                if bundle.get("dependency_sha256", {}).get(name) != actual:
                    report["blockers"].append("DEPENDENCY_PIN_MISSING_OR_DRIFT:" + name)
            inventory = engine.system_inventory(root)
            if inventory != bundle.get("system_inventory"):
                raise ValueError("FULL_REVIEWED_SYSTEM_INVENTORY_REQUIRED")
            report["system_inventory"] = inventory
            report["system_inventory_sha256"] = _sha(_json(inventory))
            db_path = _safe(root, "crm.db")
            if not stat.S_ISREG(db_path.lstat().st_mode):
                raise ValueError("REGULAR_EXISTING_CRM_DATABASE_REQUIRED")
            readonly = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=10)
            readonly.execute("PRAGMA query_only=ON")
            readonly.execute("BEGIN")
            private_db = output / "crm_readonly_online_backup.sqlite"
            target = None
            try:
                report["database"] = engine.database_snapshot(readonly)
                cursor = readonly.execute("SELECT * FROM cars ORDER BY id")
                columns = [description[0] for description in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor]
                published = [row for row in rows if row.get("published") == 1]
                if report["database"]["published_codes"] != bundle.get("expected_published_codes"):
                    raise ValueError("PUBLISHED_SET_DOES_NOT_MATCH_REVIEWED_SNAPSHOT")
                report["schema_sha256"] = _sha(_json(readonly.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()))
                if any(row.get("price_uah") in (None, "", 0) for row in published):
                    raise ValueError("LEGACY_UKRAINE_PRICE_FALLBACK")
                quota = bundle.get("quota_evidence", {})
                if not _fresh_quota(quota, datetime.now(timezone.utc).timestamp()):
                    raise ValueError("FRESH_AUTHENTICATED_PA_QUOTA_REQUIRED_BEFORE_PRIVATE_BACKUP")
                html_names = [f"{folder}/{row['auto_number']}.html" for folder in ("video", "site") for row in published]
                html_names += ["video/katalog.html", "site/katalog.html", "video/index.html", "site/index.html"]
                html_bytes = sum(_safe(root, name).stat().st_size for name in html_names)
                required = 3 * (db_path.stat().st_size + html_bytes + sum(len(value) for value in candidates.values())) + 1024 * 1024
                if (quota["used_bytes"] + required > quota["limit_bytes"] * 0.8
                        or shutil.disk_usage(root).free < required):
                    raise ValueError("PRIVATE_BACKUP_QUOTA_INSUFFICIENT")
                report["estimated_private_space_bytes"] = required
                report["quota_evidence_sha256"] = _sha(_json(quota))
                target = sqlite3.connect(private_db)
                readonly.backup(target)
                if engine.database_snapshot(target) != report["database"]:
                    raise ValueError("PRIVATE_ONLINE_BACKUP_READBACK_FAILED")
            finally:
                if target is not None:
                    target.close()
                readonly.rollback()
                readonly.close()
                if private_db.exists():
                    os.chmod(private_db, 0o600)
            report["online_backup_sha256"] = _database_hash(private_db)
            report["published_count"] = len(published)
            counts = {"korea": 0, "sea": 0, "georgia": 0, "kiev": 0}
            for row in published:
                status = str(row.get("status") or "").lower()
                key = ("korea" if status.startswith("kr_") else "sea" if status.startswith(("sea_", "sold_transit"))
                       else "georgia" if status.startswith("ge_") else "kiev" if status.startswith("ua_") or status in ("sold", "archive") else None)
                if key is None:
                    raise ValueError("UNRECOGNIZED_PUBLIC_STAGE")
                counts[key] += 1
            report["stage_counts"] = counts
            if bundle.get("expected_stage_counts") != counts:
                report["blockers"].append("STAGE_COUNTS_DO_NOT_MATCH_REVIEWED_SNAPSHOT")
            by_code = {row["auto_number"]: row for row in published}
            for folder in ("video", "site"):
                for code in (*sorted(by_code), "katalog", "index"):
                    name = folder + "/" + code + ".html"
                    try:
                        original = _read(_safe(root, name))
                        before[name] = _sha(original)
                        text = original.decode("utf-8")
                        if code == "index":
                            candidate, proof = engine.migrate_home_candidate(name, text, published, homepage_policy, routing)
                        elif code == "katalog":
                            candidate, proof = migrator.migrate_catalog(text, published)
                        else:
                            candidate, proof = migrator.migrate_card(text, by_code[code])
                        candidates[name] = candidate.encode("utf-8")
                        report["html"][name] = dict(proof, status="PASS")
                    except Exception as exc:
                        failures.append(name)
                        report["html"][name] = {"status": "FAIL", "error": str(exc)[:220]}
            for name in sorted(MODULES):
                candidates[name] = _read(_safe(package, name))
                live = _safe(root, name)
                before[name] = _sha(_read(live)) if live.exists() else None
            # Runtime schema install is evaluated only on a second private DB copy.
            migrated = output / "crm_schema_test.sqlite"
            shutil.copyfile(private_db, migrated)
            os.chmod(migrated, 0o600)
            offline = sqlite3.connect(migrated)
            try:
                offline.execute("BEGIN IMMEDIATE")
                runtime = importlib.import_module("uaart_price_sync_runtime")
                schema_before = offline.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
                runtime.install(offline)
                schema_after = offline.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
                engine.validate_schema_change(schema_before, schema_after)
                if not offline.in_transaction:
                    raise ValueError("SCHEMA_INSTALLER_COMMITTED_CALLER_TRANSACTION")
                if engine.database_snapshot(offline) != report["database"]:
                    raise ValueError("OFFLINE_SCHEMA_CHANGED_CARS_OR_AUDIT")
                report["candidate_schema_sha256"] = _sha(_json(offline.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()))
                offline.commit()
                report["offline_schema_test"] = "PASS_CRM_AND_AUDIT_UNCHANGED"
                independent = sqlite3.connect(migrated.as_uri() + "?mode=ro", uri=True)
                try:
                    if (engine.database_snapshot(independent) != report["database"] or
                            independent.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall() != schema_after):
                        raise ValueError("OFFLINE_SCHEMA_INDEPENDENT_READBACK_FAILED")
                finally:
                    independent.close()
            finally:
                offline.close()
            current = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=10)
            try:
                current.execute("PRAGMA query_only=ON")
                if engine.database_snapshot(current) != report["database"]:
                    raise ValueError("CRM_CHANGED_DURING_PREFLIGHT")
            finally:
                current.close()
            for name, expected in before.items():
                current_path = _safe(root, name)
                current_hash = _sha(_read(current_path)) if current_path.exists() else None
                if current_hash != expected:
                    raise ValueError("SOURCE_OR_HTML_CHANGED_DURING_PREFLIGHT:" + name)
            for name, expected in report["dependencies"].items():
                if _sha(_read(_safe(root, name))) != expected:
                    raise ValueError("DEPENDENCY_CHANGED_DURING_PREFLIGHT:" + name)
            if engine.system_inventory(root) != inventory:
                raise ValueError("PROTECTED_SYSTEM_CHANGED_DURING_PREFLIGHT")
            if homepage_policy:
                engine.verify_routing_sources(routing, root=root)
            report["protected_system_readback"] = "PASS"
            for name, content in sorted(candidates.items()):
                _write(_safe(output / "candidate_root", name), content)
            report["candidate_files"] = engine.candidate_manifest(candidates, {name: before[name] for name in candidates})
            report["candidate_manifest_sha256"] = _sha(_json(report["candidate_files"]))
            _write(output / "candidate_manifest.json", _json(report["candidate_files"]))
            report["candidate_verification"] = "FAIL" if failures else "PASS"
        finally:
            sys.path.remove(str(package))
        if failures:
            report["blockers"].append("INITIAL_PRICE_MIGRATION_FAILED:" + ",".join(failures))
        quota = bundle.get("quota_evidence", {})
        if not _fresh_quota(quota, datetime.now(timezone.utc).timestamp()):
            report["blockers"].append("FRESH_AUTHENTICATED_PA_QUOTA_REQUIRED")
        report["quota_evidence_sha256"] = _sha(_json(quota)) if quota else None
        report["filesystem_free_bytes"] = shutil.disk_usage(root).free
        stage2 = bundle.get("stage2_receipt", {})
        if (stage2.get("task_id") != "TASK088-GE-PRICE-CRM-STAGE2" or stage2.get("status") != "FINISHED"
                or stage2.get("stage2_status") != "PASS" or stage2.get("stage3_allowed") is not True
                or stage2.get("installed_source_sha256") != before.get("cars_ui.py")):
            report["blockers"].append("CANONICAL_STAGE2_PREREQUISITE_REQUIRED")
        report["stage2_receipt_sha256"] = _sha(_json(stage2)) if stage2 else None
        report["blockers"].append("CANONICAL_CONTROL_BRIDGE_GATE_B_AND_ACTIVATION_NOT_RUN")
    except Exception as exc:
        report["candidate_verification"] = "FAIL"
        report["blockers"].append(type(exc).__name__ + ":" + str(exc)[:260])
    report["status"] = "BLOCKED" if report["blockers"] else "PASS"
    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    _write(output / "report.json", _json(report))
    return report, output / "report.json"


def main():
    parser = argparse.ArgumentParser(description="UA ART read-only source and price preflight")
    parser.add_argument("--output-id", required=True)
    parser.add_argument("--expected-bundle-sha256", required=True)
    arguments = parser.parse_args()
    package_relative = str(Path(__file__).resolve().parent.relative_to(LIVE_ROOT))
    report, path = run(arguments.output_id, arguments.expected_bundle_sha256, package_relative=package_relative)
    print(json.dumps({"status": report["status"], "candidate_verification": report.get("candidate_verification"),
                      "report": str(path), "blockers": report["blockers"]}, ensure_ascii=False))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
