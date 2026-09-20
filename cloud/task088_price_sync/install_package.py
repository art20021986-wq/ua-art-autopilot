"""Reviewed Stage 3 install engine candidate; never runs on import or restarts CRM.

Production calls require a fresh hash-bound canonical evidence bundle, a bound
bootstrap module, exact current file/database snapshots and a reviewed schema
installer. This engine does not manufacture Gate B, request or transaction IDs.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import fcntl
import hashlib
import inspect
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import tempfile


CONTRACT = "UA-ART-GE-PRICE-STAGE3-INSTALL-5"
LIVE_ROOT = Path("/home/Carix")
MAX_FILE = 8 * 1024 * 1024
MODULES = frozenset({"uaart_market_prices.py", "uaart_price_sync_outbox.py",
    "uaart_price_sync_runtime.py", "uaart_price_sync_binding.py", "owner_policy.py",
    "price_publication.py", "uaart_price_sync_confirmation.py", "uaart_price_control_reader.py",
    "publication_fence.py", "mutation_recovery.py", "visibility_lifecycle.py"})
SOURCES = frozenset({"cars_ui.py", "yadro.py", "stranica.py", "catalog_design_guard.py",
                     "publish_transaction_guard.py", "ua_stage_catalog_sync.py", "ua_spec_permanent.py", "ua_site_counters.py", "publikaciya.py"})
DEPENDENCIES = frozenset({"db.py", "cars_schema.py", "start_safe.py",
                         "master_card.py", "team_bot.py",
                         "catalog_design_golden.html", "lock4_zhurnal.py",
                         "ua_additional_spec.py", "vin_spec_service.py"})
EVIDENCE_NAMES = ("request", "claim", "transaction", "gate_b", "stage2", "quota", "writers", "manifest", "owner_approval", "preview_gate")
PREVIEW_CHECKS = frozenset({"all_published_cars", "homepage", "catalog", "full_cards",
    "ru", "ua", "ge", "language_switching", "ua_price", "ge_price", "missing_ge",
    "desktop", "mobile", "links", "buttons", "vin", "photos", "specifications",
    "additional_specification", "stages", "counters", "no_unrelated_diff",
    "source_generation", "independent_db_readback"})
SCHEMA_TABLES = frozenset({"uaart_price_publication_outbox_v1",
    "uaart_price_publication_recovery_v1", "uaart_price_sync_notices_v1",
    "uaart_price_operations_v5", "uaart_price_audit_v5", "uaart_price_notices_v5",
    "uaart_price_confirmation_v5"})


class InstallError(RuntimeError):
    pass


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def _instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.timestamp()
    except (TypeError, AttributeError, ValueError) as exc:
        raise InstallError("AWARE_TIMESTAMP_REQUIRED") from exc


def _fresh(value, now, seconds=1800):
    if not 0 <= now - _instant(value) <= seconds:
        raise InstallError("FRESH_OBSERVATION_REQUIRED")


def _hash(value):
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise InstallError("SHA256_REQUIRED")


def _path(root, relative):
    if type(relative) is not str:
        raise InstallError("RELATIVE_PATH_REQUIRED")
    parts = PurePosixPath(relative)
    if (parts.is_absolute() or not parts.parts or relative != parts.as_posix()
            or any(p in (".", "..") for p in parts.parts)):
        raise InstallError("PATH_OUTSIDE_BOUND_ROOT")
    path = root.joinpath(*parts.parts)
    for parent in (path, *path.parents):
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise InstallError("SYMLINK_PATH_FORBIDDEN")
    return path


def _read(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE:
        raise InstallError("REGULAR_BOUNDED_FILE_REQUIRED")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read(MAX_FILE + 1)
        if len(data) > MAX_FILE:
            raise InstallError("FILE_LIMIT_EXCEEDED")
        return data
    finally:
        os.close(fd)


def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic(path, data, mode=0o600):
    fd, temporary_name = tempfile.mkstemp(prefix=".task088-stage3-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_dir(path.parent)
        if _read(path) != data:
            raise InstallError("FILE_WRITE_READBACK_MISMATCH")
    finally:
        temporary.unlink(missing_ok=True)



def _stream_entry(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise InstallError("REGULAR_INVENTORY_FILE_REQUIRED")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    digest = hashlib.sha256()
    total = 0
    try:
        with os.fdopen(fd, "rb", closefd=False) as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                total += len(chunk)
        after = os.fstat(fd)
        if (info.st_size != total or (info.st_ino, info.st_size, info.st_mtime_ns) !=
                (after.st_ino, after.st_size, after.st_mtime_ns)):
            raise InstallError("INVENTORY_FILE_CHANGED_DURING_READ")
    finally:
        os.close(fd)
    return {"sha256": digest.hexdigest(), "bytes": total, "mode": stat.S_IMODE(info.st_mode)}


def system_inventory(root):
    """Hash complete public trees plus every root Python source; reject symlinks."""
    root = Path(root)
    names = {path.name for pattern in ("*.py", "*.html", "*.css", "*.js") for path in root.glob(pattern)}
    for folder in ("video", "site"):
        base = _path(root, folder)
        if not base.is_dir():
            raise InstallError("COMPLETE_PUBLIC_TREE_REQUIRED:" + folder)
        def walk_error(exc):
            raise InstallError("COMPLETE_PUBLIC_TREE_UNREADABLE:" + folder) from exc
        for directory, dirs, files in os.walk(base, followlinks=False, onerror=walk_error):
            for name in dirs:
                _path(root, str((Path(directory) / name).relative_to(root)))
            names.update(str((Path(directory) / name).relative_to(root)) for name in files)
    return {name: _stream_entry(_path(root, name)) for name in sorted(names)}


def _backup_file(source, destination, expected):
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    target_fd = None
    try:
        target_fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(source_fd, "rb", closefd=False) as src, os.fdopen(target_fd, "wb", closefd=False) as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(target_fd)
    finally:
        os.close(source_fd)
        if target_fd is not None:
            os.close(target_fd)
    _fsync_dir(destination.parent)
    observed = _stream_entry(destination)
    if observed["sha256"] != expected["sha256"] or observed["bytes"] != expected["bytes"]:
        raise InstallError("FULL_BACKUP_READBACK_MISMATCH")


def validate_schema_change(before, after):
    if any(row not in after for row in before):
        raise InstallError("EXISTING_SCHEMA_CHANGED")
    if any(row[2] not in SCHEMA_TABLES or row[0] not in ("table", "index", "trigger")
           for row in after if row not in before):
        raise InstallError("UNAPPROVED_SCHEMA_OBJECT")


def database_snapshot(conn):
    """No values are returned in receipts; retain only reproducible digests."""
    if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise InstallError("CRM_INTEGRITY_FAILED")
    def table(name):
        cursor = conn.execute("SELECT * FROM " + name + " ORDER BY rowid")
        names = [column[0] for column in cursor.description]
        rows = [dict(zip(names, row)) for row in cursor]
        return rows, sha(encoded(rows))
    cars, cars_hash = table("cars")
    _, audit_hash = table("audit")
    published = [row for row in cars if row.get("published") == 1]
    identity = [{key: row.get(key) for key in ("id", "auto_number", "published", "status", "price_uah", "price_georgia")}
                for row in published]
    codes = [row.get("auto_number") for row in published]
    if (len(codes) != len(set(codes)) or any(type(code) is not str or not re.fullmatch(r"UA-[0-9]{4}", code)
                                           for code in codes)):
        raise InstallError("PUBLISHED_IDENTITIES_INVALID")
    if any(row.get("price_uah") in (None, "", 0) for row in published):
        raise InstallError("LEGACY_UKRAINE_FALLBACK_REQUIRES_REVIEW")
    return {"cars_sha256": cars_hash, "audit_sha256": audit_hash,
            "published_sha256": sha(encoded(identity)), "published_codes": sorted(codes)}


def candidate_manifest(files, before):
    if set(files) != set(before):
        raise InstallError("EXACT_FILE_SET_REQUIRED")
    return {name: {"before_sha256": before[name], "after_sha256": sha(data), "bytes": len(data)}
            for name, data in sorted(files.items())}



def validate_routing(routing):
    expected_paths = {"observed_wsgi_config.py": "/var/www/www_uaart_com_ua_wsgi.py",
        "analitika_wsgi.py": "/home/Carix/analitika_wsgi.py", "uaart_bridge_wsgi.py": "/home/Carix/uaart_bridge_wsgi.py",
        "video/index.html": "/home/Carix/video/index.html", "site/index.html": "/home/Carix/site/index.html"}
    if (not isinstance(routing, dict) or routing.get("report_kind") != "READ_ONLY_OBSERVED_ROUTING"
            or routing.get("source_server_paths") != expected_paths
            or routing.get("static_mappings") != [{"url": "/video/", "directory": "/home/Carix/video/"}]
            or routing.get("conclusion", {}).get("served_home") != "video/index.html"
            or routing.get("conclusion", {}).get("site/index.html") != "UNSERVED_LEGACY_PRESERVE_EXACT_BYTES"):
        raise InstallError("EXACT_OBSERVED_HOME_ROUTING_REQUIRED")
    if set(routing.get("source_sha256", {})) != set(expected_paths):
        raise InstallError("FULL_ROUTING_SOURCE_PINS_REQUIRED")
    for value in routing["source_sha256"].values():
        _hash(value)
    return expected_paths


def verify_routing_sources(routing, *, root=LIVE_ROOT):
    for key, original in validate_routing(routing).items():
        path = Path(original)
        if root != LIVE_ROOT:
            path = root / (path.relative_to(LIVE_ROOT) if path.is_relative_to(LIVE_ROOT)
                           else Path("routing_external") / path.name)
        if path.is_symlink() or sha(_read(path)) != routing["source_sha256"][key]:
            raise InstallError("OBSERVED_ROUTING_SOURCE_DRIFT:" + key)


def migrate_home_candidate(name, source, rows, policy, routing):
    from initial_html_prices import migrate_home
    if policy.get(name) != "PROTECTED_LEGACY_NOT_SERVED":
        return migrate_home(source, rows)
    validate_routing(routing)
    if name != "site/index.html" or sha(source.encode("utf-8")) != routing["source_sha256"][name]:
        raise InstallError("PROTECTED_LEGACY_HOME_PREIMAGE_DRIFT")
    return source, {"surface": "PROTECTED_LEGACY_HOME", "price_regions_changed": 0,
        "outside_price_unchanged": True, "all_bytes_unchanged": True,
        "before_sha256": sha(source.encode("utf-8")), "after_sha256": sha(source.encode("utf-8")),
        "public_serving": "NOT_SERVED_BY_VERIFIED_CONFIGURATION"}


def build_source_candidates(source_files, dependency_files):
    """Compose pinned price patches and writer protection, without live imports.

    All private bytes are supplied explicitly. The public composition helper
    independently checks the exact price after-images and specification inputs.
    No existing integrated source or arbitrary local file is used as a fallback.
    """
    from patch_cars_ui import patch_source
    from patch_yadro import patch_yadro
    from patch_stranica import patch_stranica
    from patch_catalog_design_guard import patch_catalog_design_guard
    from patch_stage_catalog_sync import patch_stage_catalog_sync
    from patch_guard import patch_source as patch_guard
    from patch_site_counters import patch_source as patch_site_counters
    from patch_publikaciya import patch_publikaciya
    from integrate_private_sources import compose_price_candidate
    if set(source_files) != SOURCES or set(dependency_files) != DEPENDENCIES:
        raise InstallError("EXACT_REVIEWED_SOURCE_DEPENDENCY_SET_REQUIRED")
    if any(type(value) is not bytes for value in (*source_files.values(), *dependency_files.values())):
        raise InstallError("EXACT_SOURCE_DEPENDENCY_BYTES_REQUIRED")
    result = {"cars_ui.py": patch_source(source_files["cars_ui.py"].decode()).encode()}
    result["publish_transaction_guard.py"] = patch_guard(source_files["publish_transaction_guard.py"].decode()).encode()
    result["ua_site_counters.py"] = patch_site_counters(source_files["ua_site_counters.py"].decode()).encode()
    result["publikaciya.py"] = patch_publikaciya(source_files["publikaciya.py"])[0]
    for name, patcher in (("yadro.py", patch_yadro), ("stranica.py", patch_stranica),
                          ("catalog_design_guard.py", patch_catalog_design_guard),
                          ("ua_stage_catalog_sync.py", patch_stage_catalog_sync)):
        result[name] = patcher(source_files[name])[0]
    composed = compose_price_candidate(
        {name: result[name] for name in ("cars_ui.py", "publish_transaction_guard.py", "stranica.py")},
        {"ua_spec_permanent.py": source_files["ua_spec_permanent.py"],
         **{name: dependency_files[name] for name in
            ("lock4_zhurnal.py", "ua_additional_spec.py", "vin_spec_service.py")}})
    if set(composed) != {"cars_ui.py", "publish_transaction_guard.py", "stranica.py", "ua_spec_permanent.py"}:
        raise InstallError("EXACT_COMPOSED_WRITER_SOURCE_SET_REQUIRED")
    result.update(composed)
    for name in SOURCES:
        if type(result[name]) is not bytes:
            raise InstallError("COMPOSED_SOURCE_BYTES_REQUIRED")
        ast.parse(result[name].decode("utf-8"))
    return result


def build_candidates(source_files, html_files, rows, modules, *, dependency_files,
                     homepage_policy=None, routing=None):
    """Pure complete candidate construction, including the reviewed writer closure."""
    from initial_html_prices import migrate_card, migrate_catalog, migrate_home
    if set(modules) != MODULES:
        raise InstallError("EXACT_REVIEWED_SOURCE_MODULE_SET_REQUIRED")
    result = build_source_candidates(source_files, dependency_files)
    result.update(modules)
    by_code = {row["auto_number"]: row for row in rows if row["published"] == 1}
    expected = {f"{root}/{code}.html" for root in ("video", "site") for code in by_code}
    expected |= {"video/katalog.html", "site/katalog.html", "video/index.html", "site/index.html"}
    if set(html_files) != expected:
        raise InstallError("EXACT_PUBLISHED_HTML_MIRRORS_REQUIRED")
    for name, original in html_files.items():
        text = original.decode("utf-8")
        code = Path(name).stem
        if code == "index":
            value, _ = migrate_home_candidate(name, text, list(by_code.values()), homepage_policy or {}, routing)
        elif code == "katalog":
            value, _ = migrate_catalog(text, list(by_code.values()))
        else:
            value, _ = migrate_card(text, by_code[code])
        value, _ = migrate_counter_client_candidate(name, value,
            source_files["ua_site_counters.py"], result["ua_site_counters.py"], homepage_policy or {})
        result[name] = value.encode("utf-8") if isinstance(value, str) else value
    for name in SOURCES | MODULES:
        ast.parse(result[name].decode("utf-8"))
    return result


def migrate_counter_client_candidate(name, source, before_counter, after_counter, homepage_policy):
    """Update the known counter script while preserving the unserved legacy home."""
    if homepage_policy.get(name) == "PROTECTED_LEGACY_NOT_SERVED":
        if name != "site/index.html":
            raise InstallError("EXACT_PROTECTED_LEGACY_HOME_REQUIRED")
        source_hash = sha(source.encode("utf-8"))
        return source, {"status": "PROTECTED_LEGACY_UNCHANGED", "before_sha256": source_hash,
                        "after_sha256": source_hash, "unrelated_markup_preserved": True}
    from patch_site_counters import patch_html_client
    return patch_html_client(source, before_counter.decode("utf-8"), after_counter.decode("utf-8"))


def _validate(plan, files, evidence, now, root, *, testing, phase="OPEN"):
    if phase not in ("PREPARING", "OPEN", "ROLLING_BACK"):
        raise InstallError("EXACT_CANONICAL_TRANSACTION_PHASE_REQUIRED")
    recovering = phase == "ROLLING_BACK"
    if plan.get("contract") != CONTRACT or plan.get("environment") != ("TEST" if testing else "PRODUCTION"):
        raise InstallError("EXACT_INSTALL_CONTRACT_REQUIRED")
    if plan.get("root") != str(root):
        raise InstallError("ROOT_BINDING_MISMATCH")
    if not recovering:
        _fresh(plan.get("observed_at"), now)
    task_id = plan.get("task_id", "")
    if not re.fullmatch(r"TASK088-GE-PRICE-SITE-STAGE3-[A-Za-z0-9-]+", task_id):
        raise InstallError("FRESH_STAGE3_TASK_ID_REQUIRED")
    if not re.fullmatch(r"tx-[A-Za-z0-9-]{8,100}", plan.get("transaction_id", "")):
        raise InstallError("REAL_TRANSACTION_ID_REQUIRED")
    manifest = candidate_manifest(files, {name: item["before_sha256"] for name, item in plan["files"].items()})
    if manifest != plan["files"] or sha(encoded(manifest)) != plan.get("manifest_sha256"):
        raise InstallError("CANDIDATE_MANIFEST_MISMATCH")
    codes = plan.get("database", {}).get("published_codes")
    if (type(codes) is not list or any(type(code) is not str or not re.fullmatch(r"UA-[0-9]{4}", code) for code in codes)
            or codes != sorted(set(codes)) or len(codes) != plan.get("published_count")):
        raise InstallError("APPROVED_PUBLISHED_CAR_COUNT_REQUIRED")
    expected_html = {f"{directory}/{code}.html" for directory in ("video", "site") for code in codes}
    expected_html |= {"video/katalog.html", "site/katalog.html", "video/index.html", "site/index.html"}
    if set(files) != SOURCES | MODULES | expected_html:
        raise InstallError("EXACT_BOUNDED_INSTALL_FILE_SET_REQUIRED")
    if set(plan.get("dependencies_sha256", {})) != DEPENDENCIES:
        raise InstallError("COMPLETE_CURRENT_DEPENDENCY_HASHES_REQUIRED")
    expected_evidence = set(EVIDENCE_NAMES)
    if plan.get("homepage_policy"):
        if plan["homepage_policy"] != {"site/index.html": "PROTECTED_LEGACY_NOT_SERVED"}:
            raise InstallError("EXACT_HOME_POLICY_REQUIRED")
        expected_evidence.add("routing")
    if set(evidence) != expected_evidence or set(plan.get("evidence_sha256", {})) != expected_evidence:
        raise InstallError("COMPLETE_CANONICAL_EVIDENCE_REQUIRED")
    records = {}
    for name, content in evidence.items():
        _hash(plan["evidence_sha256"][name])
        if sha(content) != plan["evidence_sha256"][name]:
            raise InstallError("CANONICAL_EVIDENCE_HASH_MISMATCH:" + name)
        records[name] = json.loads(content)
    request, claim, transaction, gate, stage2, quota, writers, approved_manifest, owner, preview = (records[name] for name in EVIDENCE_NAMES)
    if plan.get("homepage_policy"):
        validate_routing(records["routing"])
        if (approved_manifest.get("deployment_plan", {}).get("routing_evidence_sha256") != sha(evidence["routing"])
                or plan.get("routing_evidence_sha256") != sha(evidence["routing"])
                or plan["files"]["site/index.html"]["before_sha256"] != records["routing"]["source_sha256"]["site/index.html"]
                or plan["files"]["site/index.html"]["after_sha256"] != records["routing"]["source_sha256"]["site/index.html"]):
            raise InstallError("BOUND_PROTECTED_LEGACY_HOME_EVIDENCE_REQUIRED")
    request_hash = sha(evidence["request"])
    critical = request.get("critical", {})
    manifest_hash = sha(evidence["manifest"])
    if (request.get("task_id") != task_id or critical.get("manifest_sha256") != manifest_hash
            or approved_manifest.get("install_files_sha256") != plan["manifest_sha256"]
            or request.get("requested_min_class") != "CRITICAL" or request.get("production_required") is not True
            or critical.get("gate_a_sha256") != sha(evidence["gate_b"])
            or critical.get("owner_approval_sha256") != sha(evidence["owner_approval"])):
        raise InstallError("REQUEST_PACKAGE_BINDING_MISMATCH")
    identity = claim.get("identity", {})
    if (transaction.get("task_id") != task_id or transaction.get("request_sha256") != request_hash
            or identity.get("task_id") != task_id or identity.get("task_sha256") != request_hash):
        raise InstallError("CANONICAL_REQUEST_BINDING_MISMATCH")
    if (claim.get("task_execution_status") != "RUNNING" or claim.get("production_transaction_id") != plan["transaction_id"]
            or claim.get("production_transaction_status") != phase
            or transaction.get("status") != phase or transaction.get("transaction_id") != plan["transaction_id"]
            or transaction.get("run_id") != identity.get("run_id") or not str(identity.get("run_id", "")).isdigit()
            or (not recovering and _instant(transaction.get("expires_at")) <= now)):
        raise InstallError("ACTIVE_CANONICAL_CLAIM_TRANSACTION_REQUIRED")
    if (gate.get("task_id") != task_id or gate.get("status") != "PASS" or gate.get("manifest_sha256") != manifest_hash
            or gate.get("tests") != "PASS" or gate.get("unexpected_changes") != 0
            or gate.get("backup_plan_ready") is not True or gate.get("rollback_plan_ready") is not True
            or gate.get("writer_fence_report_sha256") != sha(evidence["writers"])):
        raise InstallError("BOUND_GATE_B_EVIDENCE_REQUIRED")
    if not recovering:
        _fresh(gate.get("evaluated_at"), now)
    if (preview.get("contract") != "TASK088-FINAL-V5-PREVIEW-GATE-1"
            or preview.get("task_id") != task_id or preview.get("status") != "PASS"
            or preview.get("candidate_manifest_sha256") != plan["manifest_sha256"]
            or preview.get("database") != plan["database"]
            or preview.get("schema_sha256") != plan["schema_sha256"]
            or preview.get("system_inventory_sha256") != sha(encoded(plan.get("system_inventory")))
            or preview.get("published_codes") != plan["database"]["published_codes"]
            or set(preview.get("checks", {})) != PREVIEW_CHECKS
            or any(result != "PASS" for result in preview["checks"].values())
            or gate.get("preview_gate_sha256") != sha(evidence["preview_gate"])):
        raise InstallError("FULL_BOUND_PREVIEW_GATE_REQUIRED")
    if not recovering:
        _fresh(preview.get("evaluated_at"), now)
    subject = json.loads(evidence["request"])
    subject["critical"]["owner_approval_sha256"] = "0" * 64
    subject_hash = sha((json.dumps(subject, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())
    if (owner.get("schema_version") != "UA-ART-PRODUCTION-AUTHORIZATION-1"
            or owner.get("task_id") != task_id or owner.get("owner_authorized") is not True
            or owner.get("production_allowed") is not True or owner.get("authorized_environment") != "production"
            or owner.get("owner") != "Артём Бровинский / UA ART COMPANY LLC"
            or owner.get("manifest_sha256") != manifest_hash or owner.get("gate_a_sha256") != sha(evidence["gate_b"])
            or owner.get("request_subject_sha256") != subject_hash or (not recovering and _instant(owner.get("expires_at")) <= now)
            or not re.fullmatch(r"prod-auth-[A-Za-z0-9._-]{16,100}", owner.get("authorization_id", ""))
            or owner.get("mode_epoch") != claim.get("mode_epoch") or owner.get("mode_epoch") != transaction.get("mode_epoch")):
        raise InstallError("EXACT_CANONICAL_OWNER_AUTHORIZATION_REQUIRED")
    if (stage2.get("task_id") != "TASK088-GE-PRICE-CRM-STAGE2" or stage2.get("status") != "FINISHED"
            or stage2.get("stage2_status") != "PASS" or stage2.get("stage3_allowed") is not True
            or stage2.get("stage1_prerequisite") != "PASS"
            or stage2.get("independent_price_fields") != "PASS" or stage2.get("original_values_restored") is not True
            or stage2.get("installed_source_sha256") != plan["files"]["cars_ui.py"]["before_sha256"]):
        raise InstallError("CANONICAL_STAGE2_ACCEPTANCE_REQUIRED")
    if not recovering:
        _fresh(quota.get("observed_at"), now)
    if quota.get("source") != "PYTHONANYWHERE_AUTHENTICATED_ACCOUNT" or quota.get("account") != "Carix":
        raise InstallError("AUTHENTICATED_ACCOUNT_QUOTA_REQUIRED")
    if (writers.get("task_id") != task_id or writers.get("install_files_sha256") != plan["manifest_sha256"]
            or writers.get("publication_lock") != str(root / ".ua_art_publish_transaction.lock")
            or not writers.get("writers") or any(writer.get("fence") != "VERIFIED" for writer in writers["writers"])
            or writers.get("uncovered_writers") != []):
        raise InstallError("ALL_EXISTING_WRITERS_MUST_BE_FENCED")
    if not recovering:
        _fresh(writers.get("observed_at"), now, 300)
    return records


def install(plan, files, evidence, *, expected_plan_sha256, schema_installer, test_root=None, now=None):
    """Apply only a reviewed exact plan. Tests explicitly use TEST + temp root.

    Canonical evidence must come from the trusted execution adapter, not from
    user-editable unchecked booleans. This engine binds its bytes and identities;
    upstream authenticates the canonical repository/authorization provenance.
    """
    _hash(expected_plan_sha256)
    if sha(encoded(plan)) != expected_plan_sha256:
        raise InstallError("IMMUTABLE_PLAN_HASH_MISMATCH")
    testing = test_root is not None
    root = Path(test_root) if testing else LIVE_ROOT
    if not root.is_absolute() or root.is_symlink() or not root.is_dir() or (testing and root == LIVE_ROOT):
        raise InstallError("EXPLICIT_SAFE_ROOT_REQUIRED")
    if not testing and now is not None:
        raise InstallError("PRODUCTION_CLOCK_OVERRIDE_FORBIDDEN")
    now = datetime.now(timezone.utc).timestamp() if now is None else now
    records = _validate(plan, files, evidence, now, root, testing=testing)
    if plan.get("homepage_policy"):
        verify_routing_sources(records["routing"], root=root)
    codes = plan["database"]["published_codes"]
    html = {f"{directory}/{code}.html" for directory in ("video", "site") for code in codes}
    html |= {"video/katalog.html", "site/katalog.html", "video/index.html", "site/index.html"}
    if set(files) != SOURCES | MODULES | html:
        raise InstallError("EXACT_BOUNDED_INSTALL_FILE_SET_REQUIRED")
    if (codes != sorted(set(codes)) or any(not re.fullmatch(r"UA-[0-9]{4}", code) for code in codes)
            or len(codes) != plan.get("published_count")):
        raise InstallError("APPROVED_PUBLISHED_CAR_COUNT_REQUIRED")
    for name in SOURCES | MODULES:
        try:
            ast.parse(files[name].decode("utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            raise InstallError("CANDIDATE_PYTHON_SYNTAX_FAILED:" + name) from exc
    if not callable(schema_installer):
        raise InstallError("REVIEWED_SCHEMA_INSTALLER_REQUIRED")
    if not testing:
        module = inspect.getmodule(schema_installer)
        if (schema_installer.__name__ != "install" or module is None
                or sha(_read(Path(module.__file__))) != sha(files["uaart_price_sync_runtime.py"])):
            raise InstallError("SCHEMA_INSTALLER_SOURCE_BINDING_MISMATCH")
    paths = {name: _path(root, name) for name in files}
    if set(plan.get("dependencies_sha256", {})) != DEPENDENCIES:
        raise InstallError("COMPLETE_CURRENT_DEPENDENCY_HASHES_REQUIRED")
    for name in plan.get("dependencies_sha256", {}):
        if name in files or sha(_read(_path(root, name))) != plan["dependencies_sha256"][name]:
            raise InstallError("DEPENDENCY_HASH_MISMATCH")
    db_path = _path(root, "crm.db")
    if not stat.S_ISREG(db_path.lstat().st_mode):
        raise InstallError("REGULAR_DATABASE_REQUIRED")
    lock_path = _path(root, ".ua_art_publish_transaction.lock")
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    conn = sqlite3.connect(db_path, timeout=0)
    if plan.get("runtime_journal_relative") != ".uaart_price_sync_journal":
        raise InstallError("EXPLICIT_PRIVATE_RUNTIME_JOURNAL_REQUIRED")
    runtime_directory = _path(root, plan["runtime_journal_relative"])
    changed, backup, committed, runtime_directory_created = [], None, False, False
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        conn.execute("BEGIN IMMEDIATE")
        initial = database_snapshot(conn)
        if initial != plan["database"]:
            raise InstallError("CRM_SNAPSHOT_DRIFT")
        observed_inventory = system_inventory(root)
        if observed_inventory != plan.get("system_inventory"):
            raise InstallError("FULL_SYSTEM_INVENTORY_DRIFT")
        before_schema = conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        if sha(encoded(before_schema)) != plan.get("schema_sha256"):
            raise InstallError("DATABASE_SCHEMA_SNAPSHOT_DRIFT")
        dependencies = {name: _read(_path(root, name)) for name in DEPENDENCIES}
        if any(sha(content) != plan["dependencies_sha256"][name] for name, content in dependencies.items()):
            raise InstallError("LOCKED_DEPENDENCY_HASH_DRIFT")
        originals, modes = {}, {}
        for name, path in paths.items():
            expected = plan["files"][name]["before_sha256"]
            value = _read(path) if path.exists() else None
            if (sha(value) if value is not None else None) != expected:
                raise InstallError("FILE_PREIMAGE_DRIFT:" + name)
            originals[name] = value
            modes[name] = stat.S_IMODE(path.stat().st_mode) if value is not None else (0o644 if name.endswith(".html") else 0o600)
        db_bytes = db_path.stat().st_size + sum(path.stat().st_size for path in (Path(str(db_path) + "-wal"),)
                                               if path.exists())
        required = 3 * (db_bytes + sum(len(value or b"") + len(files[name]) for name, value in originals.items())
                        + sum(len(value) for value in dependencies.values())
                        + sum(item["bytes"] for item in observed_inventory.values())) + 1024 * 1024
        quota = records["quota"]
        used, limit = quota.get("used_bytes"), quota.get("limit_bytes")
        if (type(used) is not int or type(limit) is not int or not 0 <= used < limit
                or used + required > limit * 0.8 or shutil.disk_usage(root).free < required):
            raise InstallError("BACKUP_ROLLBACK_QUOTA_INSUFFICIENT")
        parent = _path(root, "rezerv_publikacii/TASK088_STAGE3")
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        new_backup = _path(root, "rezerv_publikacii/TASK088_STAGE3/" + plan["transaction_id"])
        new_backup.mkdir(mode=0o700)  # Existing transaction directory must never be reused.
        backup = new_backup  # Error reporting may only touch this invocation's newly created directory.
        _fsync_dir(parent)
        _atomic(backup / "plan.json", encoded(plan))
        _atomic(backup / "evidence-hashes.json", encoded(plan["evidence_sha256"]))
        for index, (name, value) in enumerate(sorted(originals.items())):
            if value is not None:
                _atomic(backup / (str(index) + ".before"), value)
        for index, (name, value) in enumerate(sorted(dependencies.items())):
            _atomic(backup / (str(index) + ".dependency"), value)
        # Full scoped website and root Python source backup, including untouched
        # assets/specification pages. Large media is streamed, not size-capped.
        for name, entry in sorted(observed_inventory.items()):
            _backup_file(_path(root, name), _path(backup / "full", name), entry)
        _atomic(backup / "full-system-manifest.json", encoded(observed_inventory))
        if system_inventory(root) != observed_inventory:
            raise InstallError("SYSTEM_CHANGED_DURING_FULL_BACKUP")
        backup_db = backup / "crm.sqlite"
        reader = sqlite3.connect("file:" + str(db_path) + "?mode=ro", uri=True, timeout=0)
        destination = sqlite3.connect(backup_db)
        try:
            reader.backup(destination)
            if database_snapshot(destination) != initial:
                raise InstallError("ONLINE_BACKUP_READBACK_MISMATCH")
        finally:
            reader.close()
            destination.close()
        os.chmod(backup_db, 0o600)
        fd = os.open(backup_db, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        _fsync_dir(backup)
        digest = hashlib.sha256()
        with backup_db.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        backup_hash = digest.hexdigest()
        journal = {"status": "BACKUP_VERIFIED", "plan_sha256": expected_plan_sha256,
                   "backup_database_sha256": backup_hash, "files": plan["files"], "changed": [],
                   "dependencies_sha256": plan["dependencies_sha256"],
                   "runtime_journal_relative": plan["runtime_journal_relative"]}
        _atomic(backup / "journal.json", encoded(journal))
        # A full website backup can take time: do not cross expired approval,
        # writer-fence, or transaction boundaries before the first mutation.
        if not testing:
            _validate(plan, files, evidence, datetime.now(timezone.utc).timestamp(), root, testing=False)
            if plan.get("homepage_policy"):
                verify_routing_sources(records["routing"], root=root)
        if runtime_directory.exists():
            if not runtime_directory.is_dir() or stat.S_IMODE(runtime_directory.stat().st_mode) != 0o700:
                raise InstallError("PRIVATE_RUNTIME_JOURNAL_DIRECTORY_REQUIRED")
        else:
            runtime_directory.mkdir(mode=0o700)
            runtime_directory_created = True
            _fsync_dir(root)
        schema_installer(conn)
        if not conn.in_transaction or database_snapshot(conn) != initial:
            raise InstallError("SCHEMA_INSTALLER_CHANGED_CRM_OR_COMMITTED")
        after_schema = conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        if any(row not in after_schema for row in before_schema):
            raise InstallError("EXISTING_SCHEMA_CHANGED")
        validate_schema_change(before_schema, after_schema)
        if sha(encoded(after_schema)) != plan.get("candidate_schema_sha256"):
            raise InstallError("CANDIDATE_SCHEMA_HASH_MISMATCH")
        for name in sorted(files, key=lambda name: (name.endswith(".html"), name)):
            path, content = paths[name], files[name]
            value = _read(path) if path.exists() else None
            if value != originals[name]:
                raise InstallError("PRE_SWITCH_CAS_FAILED:" + name)
            # Intent recorded before replace; recovery also examines exact hashes.
            changed.append(name)
            journal.update(status="APPLYING", changed=list(changed))
            _atomic(backup / "journal.json", encoded(journal))
            _atomic(path, content, modes[name])
        expected_inventory = dict(observed_inventory)
        for name, content in files.items():
            expected_inventory[name] = {"sha256": sha(content), "bytes": len(content), "mode": modes[name]}
        if system_inventory(root) != expected_inventory:
            raise InstallError("PROTECTED_SYSTEM_CONTENT_CHANGED")
        if (database_snapshot(conn) != initial or any(_read(paths[name]) != content for name, content in files.items())
                or any(_read(_path(root, name)) != content for name, content in dependencies.items())):
            raise InstallError("PRE_COMMIT_VERIFICATION_FAILED")
        journal["status"] = "READY_TO_COMMIT"
        _atomic(backup / "journal.json", encoded(journal))
        conn.commit()
        committed = True
        # A new connection must observe the committed schema and unchanged CRM.
        independent = sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=0)
        try:
            independent.execute("PRAGMA query_only=ON")
            committed_schema = independent.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
            if (database_snapshot(independent) != initial or committed_schema != after_schema
                    or system_inventory(root) != expected_inventory):
                raise InstallError("INDEPENDENT_POSTCOMMIT_READBACK_FAILED")
        finally:
            independent.close()
        journal["status"] = "INSTALLED_PENDING_LIVE_ACCEPTANCE"
        _atomic(backup / "journal.json", encoded(journal))
        receipt = {"status": journal["status"], "task_id": plan["task_id"], "transaction_id": plan["transaction_id"],
                "plan_sha256": expected_plan_sha256, "backup_database_sha256": backup_hash,
                "cars_audit_unchanged": True, "files_installed": len(files), "bot_restarted": False,
                "independent_db_readback": "PASS", "protected_system_verification": "PASS",
                "full_backup_manifest_sha256": sha(encoded(observed_inventory)),
                "installed_system_inventory_sha256": sha(encoded(expected_inventory)),
                "preview_gate_sha256": sha(evidence["preview_gate"]),
                "request_sha256": sha(evidence["request"]), "manifest_sha256": sha(evidence["manifest"]),
                "gate_b_sha256": sha(evidence["gate_b"]), "stage2_receipt_sha256": sha(evidence["stage2"]),
                "installed_files_sha256": {name: sha(value) for name, value in files.items()},
                "installed_schema_sha256": sha(encoded(after_schema)), "database": initial,
                "runtime_journal": str(runtime_directory),
                "live_public_acceptance": "NOT_RUN", "stage3_complete": False,
                "journal": str(backup / "journal.json")}
        _atomic(backup / "install_receipt.json", encoded(receipt))
        return dict(receipt, receipt_path=str(backup / "install_receipt.json"), receipt_sha256=sha(encoded(receipt)))
    except Exception as exc:
        if committed or (changed and not conn.in_transaction):
            raise InstallError("INSTALL_COMMIT_OR_RECEIPT_UNCERTAIN_RECONCILIATION_REQUIRED") from exc
        conn.rollback()
        conflicts = []
        rollback_errors = []
        for name in reversed(changed):
            try:
                path = _path(root, name)
                current = _read(path) if path.exists() else None
                if current == originals[name]:
                    continue
                if current != files[name]:
                    conflicts.append(name)
                    continue
                if originals[name] is None:
                    path.unlink()
                    _fsync_dir(path.parent)
                else:
                    _atomic(path, originals[name], modes[name])
            except Exception as rollback_exc:
                rollback_errors.append({"path": name, "error_type": type(rollback_exc).__name__})
        if runtime_directory_created:
            try:
                runtime_directory.rmdir()  # Do not remove data written by any other process.
                _fsync_dir(root)
            except OSError as rollback_exc:
                rollback_errors.append({"path": plan["runtime_journal_relative"],
                                        "error_type": type(rollback_exc).__name__})
        if backup is not None:
            _atomic(backup / "result.json", encoded({"status": "ROLLBACK_INCOMPLETE" if rollback_errors else
                "ROLLBACK_CONFLICT" if conflicts else "ROLLED_BACK", "rollback_errors": rollback_errors,
                "conflicts": conflicts, "error_type": type(exc).__name__, "plan_sha256": expected_plan_sha256}))
        if rollback_errors:
            raise InstallError("ROLLBACK_INCOMPLETE_RECONCILIATION_REQUIRED") from exc
        if conflicts:
            raise InstallError("ROLLBACK_FOREIGN_WRITE_CONFLICT:" + ",".join(conflicts)) from exc
        raise
    finally:
        conn.close()
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
