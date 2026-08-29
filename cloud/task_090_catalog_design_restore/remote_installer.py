#!/usr/bin/env python3
"""Atomic production installer for CATALOG-DESIGN-STAGE-RESTORE-090."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
import uuid
from typing import Any, Iterable


CONTRACT_ID = "CATALOG-DESIGN-STAGE-RESTORE-090-V1.0"
ROOT = pathlib.Path(os.environ.get("UA_ART_ROOT", "/home/Carix")).resolve()
REMOTE = ROOT / "autopilot_inbox/cloud/task_090_catalog_design_restore"
BACKUPS = ROOT / "rezerv_publikacii" / "TASK090"
LAST_SUCCESS = REMOTE / "last_successful_install.json"
LOCK = ROOT / ".ua_art_publish_transaction.lock"
DB = ROOT / "crm.db"
VIDEO_CATALOG = ROOT / "video/katalog.html"
SITE_CATALOG = ROOT / "site/katalog.html"
MASTER = ROOT / "master_card.py"
PUBLISH_GUARD = ROOT / "publish_transaction_guard.py"
DESIGN_MODULE = ROOT / "catalog_design_guard.py"
GOLDEN = ROOT / "catalog_design_golden.html"
INBOX_MODULE = REMOTE / "catalog_design_guard.py"
RECEIPTS = {
    "install": REMOTE / "install_receipt.json",
    "postcheck": REMOTE / "postcheck_receipt.json",
    "rollback": REMOTE / "rollback_receipt.json",
}
KNOWN_GOOD_SHA256 = {
    "34fb82b9ec1bc66b76fccbbaad9b440d01ea4d60fe5c195954e88251442ecdd0",
}
EXPECTED_IDS = tuple("UA-%04d" % number for number in range(1, 14))
EXPECTED_COUNTS = {"all": 13, "kiev": 3, "georgia": 1, "sea": 7, "korea": 2}
TASK083_START = "# UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0:MASTER_CARD:START"
TASK083_END = "# UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0:MASTER_CARD:END"
MASTER_START = "# CATALOG-DESIGN-STAGE-RESTORE-090-V1.0:MASTER:START"
MASTER_END = "# CATALOG-DESIGN-STAGE-RESTORE-090-V1.0:MASTER:END"
PUBLISH_START = "# CATALOG-DESIGN-STAGE-RESTORE-090-V1.0:PUBLISH:START"
PUBLISH_END = "# CATALOG-DESIGN-STAGE-RESTORE-090-V1.0:PUBLISH:END"
MAX_FILE = 48 * 1024 * 1024
WAIT_SECONDS = 120


class InstallError(RuntimeError):
    pass


def sha(data: bytes | str) -> str:
    value = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(value).hexdigest()


def read(path: pathlib.Path) -> bytes:
    data = path.read_bytes()
    if len(data) > MAX_FILE:
        raise InstallError("FILE_TOO_LARGE:" + str(path))
    return data


def atomic(path: pathlib.Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        dir=path.parent, prefix="." + path.name + ".", suffix=".task090.tmp", delete=False
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
        directory = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    atomic(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
        0o644,
    )


@contextlib.contextmanager
def exclusive_lock():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    handle = open(LOCK, "a+")
    deadline = time.monotonic() + WAIT_SECONDS
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise InstallError("PUBLISH_LOCK_TIMEOUT")
                time.sleep(0.25)
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def load_design(path: pathlib.Path):
    if not path.is_file():
        raise InstallError("DESIGN_MODULE_MISSING:" + str(path))
    specification = importlib.util.spec_from_file_location("catalog_design_guard_task090", path)
    if specification is None or specification.loader is None:
        raise InstallError("DESIGN_MODULE_SPEC_INVALID")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    if getattr(module, "CONTRACT_ID", None) != CONTRACT_ID:
        raise InstallError("DESIGN_CONTRACT_MISMATCH")
    return module


def db_snapshot(design) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    db_data = read(DB)
    connection = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        rows = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM cars WHERE published=1 ORDER BY auto_number, id"
            ).fetchall()
        ]
    finally:
        connection.close()
    if quick != "ok":
        raise InstallError("CRM_QUICK_CHECK:" + quick)
    normalized = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode()
    identifiers = tuple(sorted(str(row.get("auto_number") or "").upper() for row in rows))
    counts = {"all": len(rows), "kiev": 0, "georgia": 0, "sea": 0, "korea": 0}
    for row in rows:
        counts[design.STAGE_KEYS[design.stage_number(row)]] += 1
    return rows, {
        "quick_check": quick,
        "file_sha256": sha(db_data),
        "rows_sha256": sha(normalized),
        "identifiers": identifiers,
        "counts": counts,
    }


def assert_current_db(snapshot: dict[str, Any]) -> None:
    if snapshot["identifiers"] != EXPECTED_IDS:
        raise InstallError("CURRENT_13_IDS_INVALID:" + ",".join(snapshot["identifiers"]))
    if snapshot["counts"] != EXPECTED_COUNTS:
        raise InstallError("CURRENT_STAGE_COUNTS_INVALID:" + json.dumps(snapshot["counts"]))


def protected_pages() -> dict[str, str]:
    result: dict[str, str] = {}
    for root in (ROOT / "video", ROOT / "site"):
        for path in sorted(root.glob("UA-*.html")):
            result[str(path)] = sha(read(path))
    return result


def main_photos(rows: Iterable[dict[str, Any]], design) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in rows:
        identifier = str(row.get("auto_number") or "").upper()
        primary = ROOT / "video" / (identifier + ".html")
        if not primary.is_file():
            raise InstallError("PRIMARY_PAGE_MISSING:" + identifier)
        source = read(primary).decode("utf-8", "replace")
        value = design.extract_main_photo(source, identifier)
        if not value:
            raise InstallError("MAIN_PHOTO_MISSING:" + identifier)
        result[identifier] = value
    return result


def _candidate_paths() -> list[pathlib.Path]:
    direct = [VIDEO_CATALOG, SITE_CATALOG, GOLDEN]
    patterns = (
        ROOT / "rezerv_publikacii/TASK083",
        ROOT / "autopilot_inbox/cloud/task_074_catalog_unify/backups",
        ROOT / "autopilot_inbox",
    )
    found: set[pathlib.Path] = set(path for path in direct if path.is_file())
    for base in patterns:
        if not base.is_dir():
            continue
        for path in base.rglob("katalog.html"):
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if ROOT not in resolved.parents or not resolved.is_file():
                continue
            if "video" not in resolved.parts:
                continue
            found.add(resolved)
            if len(found) >= 800:
                break
    return sorted(found)


def select_golden(design) -> tuple[pathlib.Path, str, dict[str, Any]]:
    candidates: list[tuple[int, float, pathlib.Path, str, dict[str, Any]]] = []
    rejected: dict[str, str] = {}
    for path in _candidate_paths():
        try:
            data = read(path)
            source = data.decode("utf-8")
            audit = design.shell_audit(source)
            if audit.get("status") != "PASS" or int(audit.get("article_cards") or 0) < 10:
                rejected[str(path)] = ",".join(audit.get("errors") or ["NOT_APPROVED"])
                continue
            digest = sha(data)
            priority = 0 if digest in KNOWN_GOOD_SHA256 else 1
            candidates.append((priority, -path.stat().st_mtime, path, source, audit))
        except Exception as exc:
            rejected[str(path)] = type(exc).__name__ + ":" + str(exc)
    if not candidates:
        raise InstallError("APPROVED_GOLDEN_BACKUP_NOT_FOUND")
    candidates.sort(key=lambda item: (item[0], item[1], str(item[2])))
    priority, _mtime, path, source, audit = candidates[0]
    evidence = {
        "path": str(path),
        "sha256": sha(source),
        "exact_known_good": priority == 0,
        "article_cards": audit["article_cards"],
        "shell_fingerprint": audit["fingerprint"],
        "valid_candidates": len(candidates),
        "rejected_candidates": len(rejected),
    }
    return path, source, evidence


def strip_marker(source: str, start: str, end: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end) + r"\s*", re.S)
    return pattern.sub("", source)


def master_wrapper() -> str:
    return r'''
# CATALOG-DESIGN-STAGE-RESTORE-090-V1.0:MASTER:START
def obrabotat_obshuyu(html):
    import pathlib as _ua090_pathlib
    import catalog_design_guard as _ua090_design

    _rows = {}
    for _kod in vse_kody():
        _row = dict(_ua068_master_row(str(_kod)) or {})
        try:
            _published = int(_row.get("published") or 0)
        except (TypeError, ValueError):
            _published = 0
        if _published != 1:
            continue
        _identifier = str(_kod).strip().upper()
        _rows[_identifier] = _row
    if not _rows:
        raise RuntimeError("TASK090_NO_PUBLISHED_ROWS")

    _photos = {}
    for _identifier in sorted(_rows):
        _primary = _ua090_pathlib.Path("/home/Carix/video") / (_identifier + ".html")
        if not _primary.is_file():
            raise RuntimeError("TASK090_PRIMARY_MISSING:" + _identifier)
        _page = _primary.read_text(encoding="utf-8", errors="replace")
        _photos[_identifier] = _ua090_design.extract_main_photo(_page, _identifier)

    _result = _ua090_design.build_from_golden_path(_rows.values(), _photos)
    _audit = _ua090_design.audit_catalog(
        _result, _rows.values(),
        _ua090_design.GOLDEN_PATH.read_text(encoding="utf-8"),
    )
    if _audit.get("status") != "PASS":
        raise RuntimeError("TASK090_CATALOG_AUDIT:" + ",".join(_audit.get("errors") or []))
    return _result
# CATALOG-DESIGN-STAGE-RESTORE-090-V1.0:MASTER:END
'''


def patch_master(source: str) -> str:
    base = strip_marker(source, MASTER_START, MASTER_END)
    base = strip_marker(base, TASK083_START, TASK083_END).rstrip() + "\n"
    required = ("def obrabotat_obshuyu", "def vse_kody", "def _ua068_master_row")
    missing = [value for value in required if value not in base]
    if missing:
        raise InstallError("MASTER_ANCHOR_MISSING:" + ",".join(missing))
    candidate = base + master_wrapper().lstrip()
    compile(candidate, str(MASTER), "exec")
    if candidate.count(MASTER_START) != 1 or candidate.count(MASTER_END) != 1:
        raise InstallError("MASTER_MARKER_COUNT")
    if TASK083_START in candidate or "_ua068_ensure_catalog(html, rows)" in master_wrapper():
        raise InstallError("BARE_GENERATOR_REMAINS_ACTIVE")
    return candidate


def publish_wrapper() -> str:
    return r'''
# CATALOG-DESIGN-STAGE-RESTORE-090-V1.0:PUBLISH:START
def _validate_catalog(source, rows):
    import catalog_design_guard as _ua090_design
    _golden = _ua090_design.GOLDEN_PATH.read_text(encoding="utf-8")
    _audit = _ua090_design.audit_catalog(source, rows.values(), _golden)
    if _audit.get("status") != "PASS":
        raise PublishError("TASK090_CATALOG_CONTRACT:" + ",".join(_audit.get("errors") or []))
    return _audit


def _install_catalog(source, target):
    import catalog_design_guard as _ua090_design
    _rows_map, _rows_digest = _row_map()
    _photos = {}
    for _identifier in sorted(_rows_map):
        _primary_path = VIDEO / (_identifier + ".html")
        if not _primary_path.is_file():
            raise PublishError("TASK090_PRIMARY_NOT_READY:" + _identifier)
        _primary = _read(_primary_path).decode("utf-8", "replace")
        _photos[_identifier] = _ua090_design.extract_main_photo(_primary, _identifier)

    _normalized = _ua090_design.build_from_golden_path(_rows_map.values(), _photos)
    _before = _validate_catalog(_normalized, _rows_map)
    _data = _normalized.encode("utf-8")
    for _root in ROOTS:
        _path = _root / "katalog.html"
        _atomic(_path, _data, _path.stat().st_mode & 0o777 if _path.exists() else 0o644)
        if _read(_path) != _data:
            raise PublishError("TASK090_CATALOG_READBACK:" + str(_path))

    _installed = {}
    for _root in ROOTS:
        _path = _root / "katalog.html"
        _text = _read(_path).decode("utf-8", "replace")
        _installed[str(_path)] = {
            "sha256": _sha(_read(_path)),
            "audit": _validate_catalog(_text, _rows_map),
        }
    return {
        "candidate": _before,
        "design_guard": _before,
        "target": target,
        "published_rows_sha256": _rows_digest,
        "installed": _installed,
    }
# CATALOG-DESIGN-STAGE-RESTORE-090-V1.0:PUBLISH:END
'''


def patch_publish_guard(source: str) -> str:
    base = strip_marker(source, PUBLISH_START, PUBLISH_END).rstrip() + "\n"
    required = ("def _validate_catalog", "def _install_catalog", "def _row_map", "def _atomic")
    missing = [value for value in required if value not in base]
    if missing:
        raise InstallError("PUBLISH_GUARD_ANCHOR_MISSING:" + ",".join(missing))
    candidate = base + publish_wrapper().lstrip()
    compile(candidate, str(PUBLISH_GUARD), "exec")
    if candidate.count(PUBLISH_START) != 1 or candidate.count(PUBLISH_END) != 1:
        raise InstallError("PUBLISH_MARKER_COUNT")
    return candidate


MANAGED = (
    VIDEO_CATALOG,
    SITE_CATALOG,
    MASTER,
    PUBLISH_GUARD,
    DESIGN_MODULE,
    GOLDEN,
    DB,
)


def create_backup() -> pathlib.Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = BACKUPS / (stamp + "-" + uuid.uuid4().hex[:12])
    manifest: dict[str, Any] = {}
    for path in MANAGED:
        exists = path.is_file()
        item: dict[str, Any] = {
            "path": str(path),
            "exists": exists,
            "restore": path != DB,
        }
        if exists:
            data = read(path)
            target = root / "files" / path.relative_to(ROOT)
            atomic(target, data, path.stat().st_mode & 0o777)
            item.update({
                "sha256": sha(data),
                "mode": path.stat().st_mode & 0o777,
                "bytes": len(data),
            })
        manifest[str(path)] = item
    atomic_json(root / "manifest.json", manifest)
    return root


def restore_backup(root: pathlib.Path) -> dict[str, Any]:
    root = root.resolve()
    if root == BACKUPS or BACKUPS not in root.parents:
        raise InstallError("BACKUP_PATH_OUTSIDE_TASK090")
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise InstallError("BACKUP_MANIFEST_MISSING")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed: list[str] = []
    for path in MANAGED:
        item = manifest.get(str(path))
        if not item:
            raise InstallError("BACKUP_ENTRY_MISSING:" + str(path))
        if not item.get("restore"):
            continue
        if item.get("exists"):
            data = read(root / "files" / path.relative_to(ROOT))
            if not path.is_file() or read(path) != data:
                atomic(path, data, int(item.get("mode") or 0o644))
                changed.append(str(path))
        elif path.exists():
            path.unlink()
            changed.append(str(path))
    mismatches = []
    for path in MANAGED:
        item = manifest[str(path)]
        if not item.get("restore"):
            continue
        if item.get("exists"):
            if not path.is_file() or sha(read(path)) != item.get("sha256"):
                mismatches.append(str(path))
        elif path.exists():
            mismatches.append(str(path))
    if mismatches:
        raise InstallError("ROLLBACK_READBACK_MISMATCH:" + ",".join(mismatches))
    return {"backup_root": str(root), "changed_paths": changed}


def shadow_tests(golden: str, rows: list[dict[str, Any]], photos: dict[str, str], design) -> dict[str, Any]:
    candidate = design.build_catalog(golden, rows, photos)
    for _ in range(10):
        repeated = design.build_catalog(candidate, rows, photos)
        if repeated != candidate:
            raise InstallError("IDEMPOTENCY_FAIL")
    current = design.assert_live_acceptance(candidate, rows, golden)

    future = [dict(row) for row in rows]
    extra = dict(rows[-1])
    extra.update({
        "auto_number": "UA-9999",
        "published": 1,
        "status": "kr_bought",
        "vin": "TASK090FUTURE9999",
    })
    future.append(extra)
    future_photos = dict(photos)
    future_photos["UA-9999"] = photos[str(rows[-1]["auto_number"]).upper()]
    future_catalog = design.build_catalog(candidate, future, future_photos)
    future_audit = design.audit_catalog(future_catalog, future, golden)
    if future_audit.get("status") != "PASS" or future_audit.get("article_cards") != 14:
        raise InstallError("FUTURE_CARD_TEST_FAIL")
    if design.shell_fingerprint(candidate) != design.shell_fingerprint(future_catalog):
        raise InstallError("FUTURE_SHELL_CHANGED")
    return {
        "status": "PASS",
        "candidate_sha256": sha(candidate),
        "current": current,
        "idempotent_runs": 10,
        "future_card": {
            "status": "PASS",
            "article_cards": future_audit["article_cards"],
            "shell_fingerprint": future_audit["shell_fingerprint"],
        },
        "candidate": candidate,
    }


def install() -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "contract_id": CONTRACT_ID,
        "status": "FAIL",
        "production_write": False,
        "crm_write": False,
        "runtime_llm_tokens": 0,
        "errors": [],
        "rollback": None,
    }
    backup_root: pathlib.Path | None = None
    try:
        design = load_design(INBOX_MODULE)
        rows, before_db = db_snapshot(design)
        assert_current_db(before_db)
        before_protected = protected_pages()
        source_path, golden_source, golden_evidence = select_golden(design)
        photos = main_photos(rows, design)
        shadow = shadow_tests(golden_source, rows, photos, design)
        candidate = shadow.pop("candidate")
        master_candidate = patch_master(MASTER.read_text(encoding="utf-8"))
        publish_candidate = patch_publish_guard(PUBLISH_GUARD.read_text(encoding="utf-8"))
        module_data = read(INBOX_MODULE)

        evidence.update({
            "db_before": before_db,
            "golden_source": golden_evidence,
            "shadow": shadow,
        })
        backup_root = create_backup()
        evidence["backup_root"] = str(backup_root)

        atomic(DESIGN_MODULE, module_data, 0o644)
        atomic(GOLDEN, golden_source.encode("utf-8"), 0o444)
        atomic(MASTER, master_candidate.encode("utf-8"), MASTER.stat().st_mode & 0o777)
        atomic(
            PUBLISH_GUARD,
            publish_candidate.encode("utf-8"),
            PUBLISH_GUARD.stat().st_mode & 0o777,
        )
        catalog_data = candidate.encode("utf-8")
        for path in (VIDEO_CATALOG, SITE_CATALOG):
            atomic(path, catalog_data, path.stat().st_mode & 0o777)

        if read(DESIGN_MODULE) != module_data:
            raise InstallError("DESIGN_MODULE_READBACK")
        if read(GOLDEN) != golden_source.encode("utf-8"):
            raise InstallError("GOLDEN_READBACK")
        if MASTER.read_text(encoding="utf-8").count(MASTER_START) != 1:
            raise InstallError("MASTER_PATCH_READBACK")
        if PUBLISH_GUARD.read_text(encoding="utf-8").count(PUBLISH_START) != 1:
            raise InstallError("PUBLISH_PATCH_READBACK")
        compile(MASTER.read_text(encoding="utf-8"), str(MASTER), "exec")
        compile(PUBLISH_GUARD.read_text(encoding="utf-8"), str(PUBLISH_GUARD), "exec")

        after_rows, after_db = db_snapshot(design)
        if before_db["file_sha256"] != after_db["file_sha256"]:
            raise InstallError("CRM_FILE_CHANGED")
        if before_db["rows_sha256"] != after_db["rows_sha256"]:
            raise InstallError("CRM_ROWS_CHANGED")
        if before_protected != protected_pages():
            raise InstallError("PROTECTED_PAGE_CHANGED")
        audits: dict[str, Any] = {}
        for path in (VIDEO_CATALOG, SITE_CATALOG):
            text = read(path).decode("utf-8")
            audits[str(path)] = design.assert_live_acceptance(text, after_rows, golden_source)
        if read(VIDEO_CATALOG) != read(SITE_CATALOG):
            raise InstallError("CATALOG_COPIES_DIFFER")

        evidence.update({
            "status": "PASS",
            "production_write": True,
            "db_after": after_db,
            "catalogs": audits,
            "catalog_sha256": sha(read(VIDEO_CATALOG)),
            "protected_pages_changed": 0,
            "source_golden_path": str(source_path),
        })
        atomic_json(LAST_SUCCESS, {
            "contract_id": CONTRACT_ID,
            "backup_root": str(backup_root),
            "installed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "catalog_sha256": evidence["catalog_sha256"],
            "golden_sha256": sha(read(GOLDEN)),
        })
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        evidence["traceback"] = traceback.format_exc(limit=8)
        if backup_root is not None:
            try:
                evidence["rollback"] = restore_backup(backup_root)
            except Exception as rollback_exc:
                evidence["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )
    return evidence


def postcheck() -> dict[str, Any]:
    result: dict[str, Any] = {
        "contract_id": CONTRACT_ID,
        "status": "FAIL",
        "read_only": True,
        "production_write": False,
        "crm_write": False,
        "runtime_llm_tokens": 0,
        "errors": [],
    }
    try:
        design = load_design(DESIGN_MODULE)
        rows, database = db_snapshot(design)
        assert_current_db(database)
        golden_source = GOLDEN.read_text(encoding="utf-8")
        audits = {}
        for path in (VIDEO_CATALOG, SITE_CATALOG):
            audits[str(path)] = design.assert_live_acceptance(
                read(path).decode("utf-8"), rows, golden_source
            )
        if read(VIDEO_CATALOG) != read(SITE_CATALOG):
            raise InstallError("CATALOG_COPIES_DIFFER")
        if MASTER.read_text(encoding="utf-8").count(MASTER_START) != 1:
            raise InstallError("MASTER_MARKER_INVALID")
        if PUBLISH_GUARD.read_text(encoding="utf-8").count(PUBLISH_START) != 1:
            raise InstallError("PUBLISH_MARKER_INVALID")
        result.update({
            "status": "PASS",
            "database": database,
            "catalogs": audits,
            "catalog_sha256": sha(read(VIDEO_CATALOG)),
            "golden_sha256": sha(read(GOLDEN)),
            "markers": {"master": 1, "publish_guard": 1},
        })
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
    return result


def rollback() -> dict[str, Any]:
    result: dict[str, Any] = {
        "contract_id": CONTRACT_ID,
        "status": "FAIL",
        "production_write": True,
        "crm_write": False,
        "errors": [],
    }
    try:
        if not LAST_SUCCESS.is_file():
            raise InstallError("LAST_SUCCESS_MISSING")
        pointer = json.loads(LAST_SUCCESS.read_text(encoding="utf-8"))
        restored = restore_backup(pathlib.Path(pointer["backup_root"]))
        result.update({"status": "PASS", "restored": restored})
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=tuple(RECEIPTS))
    arguments = parser.parse_args(argv)
    REMOTE.mkdir(parents=True, exist_ok=True)
    with exclusive_lock():
        value = {
            "install": install,
            "postcheck": postcheck,
            "rollback": rollback,
        }[arguments.mode]()
    value["completed_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    atomic_json(RECEIPTS[arguments.mode], value)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

