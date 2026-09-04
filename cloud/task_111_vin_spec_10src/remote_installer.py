#!/usr/bin/env python3
"""Fail-closed production installer for UA111 ten-source VIN enrichment.

Runs only on PythonAnywhere through the CRITICAL controller.  Main crm.db is
read-only.  The only durable data write is /home/Carix/vin_specs.db; source
modules and existing published HTML are snapshotted for exact rollback.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import glob
import gzip
import hashlib
import importlib
import json
import os
import pathlib
import re
import sqlite3
import stat
import sys
import tempfile
import time
from typing import Any, Callable, Iterable

import integration_patcher
import source_policy


TASK_ID = "TASK111-VIN-SPEC-10SRC"
CONTRACT = "UA-VIN-SPEC-10SRC-V2.0"
ROOT = "/home/Carix"
REMOTE = ROOT + "/autopilot_inbox/cloud/task_068_ferry_vin"
BUNDLED = REMOTE
MAIN_DB = ROOT + "/crm.db"
SPEC_DB = ROOT + "/vin_specs.db"
TARGET_SOURCE_POLICY = ROOT + "/source_policy.py"
TARGET_PROFILE_LIBRARY = ROOT + "/profile_library.py"
TARGET_SERVICE = ROOT + "/vin_spec_service.py"
TARGET_SPEC = ROOT + "/ua_additional_spec.py"
TARGET_CRM = ROOT + "/cars_ui.py"
SOURCE_TARGETS = (TARGET_SOURCE_POLICY, TARGET_PROFILE_LIBRARY, TARGET_SERVICE, TARGET_SPEC, TARGET_CRM)
BACKUP_PARENT = REMOTE + "/task111_backups"
LATEST_BACKUP = REMOTE + "/task111_latest_backup.txt"
INSTALL_RECEIPT = REMOTE + "/task111_install_receipt.json"
VERIFY_RECEIPT = REMOTE + "/task111_verify_receipt.json"
ROLLBACK_RECEIPT = REMOTE + "/task111_rollback_receipt.json"
LOCK_PATH = ROOT + "/.task111_vin_spec.lock"
MAX_FILE_BYTES = 64 * 1024 * 1024
SPEC_START = "<!--UA099_ADD_SPEC_START-->"
SPEC_END = "<!--UA099_ADD_SPEC_END-->"
CARD_FILE_RE = re.compile(r"^UA-[0-9]{4,}\.html$", re.I)
PUBLIC_HTML_RE = re.compile(r"^UA-[0-9]{4,}(?:-diag)?\.html$", re.I)


class InstallError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_read(path: str, *, required: bool = True) -> bytes | None:
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        if required:
            raise InstallError("MISSING:" + path)
        return None
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise InstallError("UNSAFE_FILE:" + path)
    if before.st_size > MAX_FILE_BYTES:
        raise InstallError("FILE_TOO_LARGE:" + path)
    flags = os.O_RDONLY | (getattr(os, "O_NOFOLLOW", 0))
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise InstallError("FILE_IDENTITY_CHANGED:" + path)
        chunks, total = [], 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, MAX_FILE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise InstallError("FILE_TOO_LARGE:" + path)
        after = os.fstat(descriptor)
        if (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise InstallError("CONCURRENT_READ:" + path)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def fsync_dir(path: str) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: str, value: bytes, mode: int = 0o600) -> None:
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb", dir=parent, prefix="." + os.path.basename(path) + ".",
        suffix=".task111.tmp", delete=False,
    )
    temporary = handle.name
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, stat.S_IMODE(mode))
        os.replace(temporary, path)
        fsync_dir(parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path: str, value: dict[str, Any]) -> None:
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n").encode()
    current = safe_read(path, required=False)
    mode = os.lstat(path).st_mode if current is not None else 0o600
    atomic_write(path, payload, mode)


def _allowed_snapshot_path(path: str) -> bool:
    if path in SOURCE_TARGETS or path in {SPEC_DB, SPEC_DB + "-wal", SPEC_DB + "-shm"}:
        return True
    parent, name = os.path.dirname(path), os.path.basename(path)
    if parent in {ROOT + "/video", ROOT + "/site"}:
        return name in {"index.html", "katalog.html"} or bool(PUBLIC_HTML_RE.fullmatch(name))
    return False


def snapshot_paths() -> list[str]:
    paths = set(SOURCE_TARGETS)
    paths.update({SPEC_DB, SPEC_DB + "-wal", SPEC_DB + "-shm"})
    for public_root in (ROOT + "/video", ROOT + "/site"):
        paths.update({public_root + "/index.html", public_root + "/katalog.html"})
        paths.update(glob.glob(public_root + "/UA-*.html"))
    result = sorted(path for path in paths if _allowed_snapshot_path(path))
    if len([path for path in result if CARD_FILE_RE.fullmatch(os.path.basename(path))]) < 16:
        raise InstallError("PUBLISHED_CARD_INVENTORY_TOO_SMALL")
    return result


def create_backup(paths: Iterable[str]) -> str:
    os.makedirs(BACKUP_PARENT, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = os.path.join(BACKUP_PARENT, stamp)
    os.makedirs(os.path.join(backup, "files"), mode=0o700)
    manifest: list[dict[str, Any]] = []
    for index, path in enumerate(sorted(set(paths))):
        if not _allowed_snapshot_path(path):
            raise InstallError("BACKUP_PATH_FORBIDDEN:" + path)
        raw = safe_read(path, required=False)
        item: dict[str, Any] = {"path": path, "exists": raw is not None}
        if raw is not None:
            item.update({
                "sha256": sha_bytes(raw), "mode": stat.S_IMODE(os.lstat(path).st_mode),
                "stored": "files/%04d.gz" % index,
            })
            atomic_write(os.path.join(backup, item["stored"]), gzip.compress(raw, 9, mtime=0), 0o600)
        manifest.append(item)
    atomic_json(os.path.join(backup, "manifest.json"), {"task_id": TASK_ID, "files": manifest})
    atomic_write(LATEST_BACKUP, (backup + "\n").encode(), 0o600)
    return backup


def validate_backup_path(path: str) -> str:
    resolved = os.path.realpath(path)
    parent = os.path.realpath(BACKUP_PARENT)
    if os.path.dirname(resolved) != parent or not os.path.isdir(resolved):
        raise InstallError("BACKUP_PATH_FORBIDDEN")
    return resolved


def restore_backup(path: str) -> dict[str, Any]:
    backup = validate_backup_path(path)
    raw = safe_read(os.path.join(backup, "manifest.json"))
    manifest = json.loads((raw or b"").decode())
    if manifest.get("task_id") != TASK_ID or not isinstance(manifest.get("files"), list):
        raise InstallError("BACKUP_MANIFEST_INVALID")
    restored, removed = [], []
    for item in manifest["files"]:
        target = str(item.get("path") or "")
        if not _allowed_snapshot_path(target):
            raise InstallError("RESTORE_PATH_FORBIDDEN:" + target)
        current = safe_read(target, required=False)
        if item.get("exists"):
            stored = os.path.realpath(os.path.join(backup, str(item.get("stored") or "")))
            if pathlib.Path(os.path.realpath(backup)) not in pathlib.Path(stored).parents:
                raise InstallError("RESTORE_STORAGE_ESCAPE")
            packed = safe_read(stored)
            data = gzip.decompress(packed or b"")
            if sha_bytes(data) != item.get("sha256"):
                raise InstallError("RESTORE_SHA_MISMATCH:" + target)
            if current != data:
                atomic_write(target, data, int(item.get("mode") or 0o600))
                restored.append(target)
        elif current is not None:
            os.unlink(target)
            fsync_dir(os.path.dirname(target))
            removed.append(target)
    return {"status": "PASS", "backup": backup, "restored": restored, "removed": removed}


def cars_hash() -> str:
    uri = "file:" + str(pathlib.Path(MAIN_DB).resolve()) + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        columns = [str(row[1]) for row in conn.execute("PRAGMA table_info(cars)")]
        if not columns:
            raise InstallError("CARS_TABLE_MISSING")
        quoted = ",".join('"' + item.replace('"', '""') + '"' for item in columns)
        rows = [dict(row) for row in conn.execute("SELECT " + quoted + " FROM cars ORDER BY rowid")]
        if conn.total_changes:
            raise InstallError("CRM_WRITE_GUARD")
    payload = json.dumps({"columns": columns, "rows": rows}, ensure_ascii=False, sort_keys=True, default=str).encode()
    return sha_bytes(payload)


def _candidate_sources() -> dict[str, bytes]:
    bundled_policy = safe_read(BUNDLED + "/source_policy.py") or b""
    bundled_profiles = safe_read(BUNDLED + "/profile_library.py") or b""
    bundled_service = safe_read(BUNDLED + "/vin_spec_service.py") or b""
    deployed_spec = (safe_read(TARGET_SPEC) or b"").decode("utf-8")
    deployed_crm = (safe_read(TARGET_CRM) or b"").decode("utf-8")
    patched_spec = integration_patcher.patch_additional_spec(deployed_spec).encode("utf-8")
    patched_crm = integration_patcher.patch_cars_ui(deployed_crm).encode("utf-8")
    candidates = {
        TARGET_SOURCE_POLICY: bundled_policy,
        TARGET_PROFILE_LIBRARY: bundled_profiles,
        TARGET_SERVICE: bundled_service,
        TARGET_SPEC: patched_spec,
        TARGET_CRM: patched_crm,
    }
    for path, raw in candidates.items():
        compile(raw.decode("utf-8"), path, "exec")
    return candidates


def _install_sources(candidates: dict[str, bytes]) -> dict[str, str]:
    hashes = {}
    for path, raw in candidates.items():
        current = safe_read(path, required=False)
        mode = os.lstat(path).st_mode if current is not None else 0o644
        if current != raw:
            atomic_write(path, raw, mode)
        if safe_read(path) != raw:
            raise InstallError("SOURCE_READBACK:" + path)
        hashes[path] = sha_bytes(raw)
    return hashes


def _fresh_modules():
    for name in ("profile_library", "source_policy", "vin_spec_service", "ua_additional_spec", "publikaciya"):
        sys.modules.pop(name, None)
    if BUNDLED not in sys.path:
        sys.path.insert(0, BUNDLED)
    if ROOT not in sys.path:
        sys.path.insert(1, ROOT)
    os.environ["UA_ART_CRM_DB"] = MAIN_DB
    os.environ["UA_ART_SPEC_DB"] = SPEC_DB
    os.environ.setdefault("UA_ART_SPEC_HTTP_TIMEOUT", "10")
    service = importlib.import_module("vin_spec_service")
    return service


def _visible_count(uid: str) -> int:
    if not os.path.isfile(SPEC_DB):
        return 0
    with sqlite3.connect(SPEC_DB) as conn:
        row = conn.execute(
            """SELECT COUNT(*) FROM additional_specification a
               LEFT JOIN additional_specification_meta m
                 ON m.car_uid=a.car_uid AND m.field_key=a.field_key
               WHERE a.car_uid=? AND a.is_price_field=0 AND COALESCE(m.is_visible,1)=1""",
            (uid,),
        ).fetchone()
    return int(row[0] if row else 0)


def _spec_fragment(page: str) -> str:
    if page.count(SPEC_START) != 1 or page.count(SPEC_END) != 1:
        raise InstallError("PUBLIC_SPEC_MARKER_COUNT")
    start = page.index(SPEC_START)
    end = page.index(SPEC_END, start) + len(SPEC_END)
    return page[start:end]


def _local_public_current(uid: str, expected: int) -> bool:
    """Avoid a duplicate publication when process_one already updated both copies."""
    if expected < 1:
        return False
    for public_root in (ROOT + "/video", ROOT + "/site"):
        raw = safe_read(public_root + "/" + uid + ".html", required=False)
        if raw is None:
            return False
        try:
            fragment = _spec_fragment(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, InstallError):
            return False
        shown = len(re.findall(r"class=['\"]ua-addspec-row['\"]", fragment, re.I))
        if shown != expected:
            return False
    return True


def _current_job_rows(service: Any) -> list[dict[str, Any]]:
    with service.connect_spec(True) as conn:
        return [dict(row) for row in conn.execute(
            """SELECT car_uid,status,facts_count,attempts,last_error
               FROM vin_spec_jobs
               WHERE policy_version=? AND status<>'SUPERSEDED'
               ORDER BY car_uid""",
            (source_policy.POLICY_VERSION,),
        )]


def _drain_full_backfill(
    service: Any,
    expected: int,
    *,
    timeout_seconds: int = 900,
    state_reader: Callable[[], list[dict[str, Any]]] | None = None,
    sleeper: Callable[[float], Any] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Finish or observe every current VIN even with concurrent CRM workers.

    The CRM bot can legitimately claim some PENDING rows immediately after the
    full requeue.  No single process therefore has to return all 16 results;
    the durable invariant is 16 current rows in READY with at least ten facts.
    """
    if expected < 1:
        raise InstallError("BACKFILL_EXPECTED_INVALID")
    read_state = state_reader or (lambda: _current_job_rows(service))
    deadline = clock() + max(1, int(timeout_seconds))
    processed: list[dict[str, Any]] = []
    recovered = 0
    polls = 0
    while True:
        item = service.process_one()
        if item is not None:
            processed.append(item)
            continue
        rows = read_state()
        polls += 1
        ready = [
            row for row in rows
            if row.get("status") == "READY" and int(row.get("facts_count") or 0) >= 10
        ]
        if len(rows) == expected and len(ready) == expected:
            installer_ready = {
                str(item.get("car_uid")) for item in processed
                if item.get("status") == "READY"
            }
            return {
                "expected": expected,
                "completed": len(ready),
                "installer_completed": len(installer_ready),
                "concurrent_worker_completed": expected - len(installer_ready),
                "recovered_interrupted": recovered,
                "polls": polls,
                "processed": processed,
            }
        statuses: dict[str, int] = {}
        for row in rows:
            status = str(row.get("status") or "UNKNOWN")
            statuses[status] = statuses.get(status, 0) + 1
        active = sum(statuses.get(name, 0) for name in ("PENDING", "RUNNING", "PROCESSING"))
        terminal = statuses.get("FAILED", 0) + statuses.get("NEEDS_REVIEW", 0)
        problem_rows = [
            {
                "car_uid": str(row.get("car_uid") or ""),
                "status": str(row.get("status") or "UNKNOWN"),
                "facts": int(row.get("facts_count") or 0),
                "attempts": int(row.get("attempts") or 0),
                "error": str(row.get("last_error") or "")[:120],
            }
            for row in rows
            if row.get("status") != "READY" or int(row.get("facts_count") or 0) < 10
        ]
        if len(rows) != expected and active == 0:
            raise InstallError("BACKFILL_INVENTORY:%d:%d" % (len(rows), expected))
        if terminal and active == 0:
            raise InstallError("BACKFILL_TERMINAL:" + json.dumps(problem_rows, sort_keys=True))
        if len(rows) == expected and active == 0:
            raise InstallError("BACKFILL_SHALLOW:" + json.dumps(problem_rows, sort_keys=True))
        if clock() >= deadline:
            raise InstallError("BACKFILL_WAIT_TIMEOUT:" + json.dumps(statuses, sort_keys=True))
        recovered += int(service.recover_interrupted_jobs(stale_after_seconds=360))
        sleeper(2)


def verify_local_public(cards: list[dict[str, Any]]) -> dict[str, Any]:
    checked: dict[str, Any] = {}
    pages = 0
    nonempty = 0
    minimum_specs: int | None = None
    for card in cards:
        if not card.get("published"):
            continue
        uid = str(card["car_uid"])
        expected = _visible_count(uid)
        roots = []
        for public_root in (ROOT + "/video", ROOT + "/site"):
            path = public_root + "/" + uid + ".html"
            raw = safe_read(path, required=False)
            if raw is None:
                continue
            text = raw.decode("utf-8")
            fragment = _spec_fragment(text)
            shown = len(re.findall(r"class=['\"]ua-addspec-row['\"]", fragment, re.I))
            if shown != expected:
                raise InstallError("PUBLIC_SPEC_COUNT:%s:%d:%d" % (uid, shown, expected))
            visible = re.sub(r"<[^>]+>", " ", fragment)
            if "http://" in fragment.lower() or "https://" in fragment.lower():
                raise InstallError("PUBLIC_SOURCE_URL_LEAK:" + uid)
            if source_policy.PRICE_RE.search(visible):
                raise InstallError("PUBLIC_PRICE_LEAK:" + uid)
            roots.append(public_root)
            pages += 1
        if not roots:
            raise InstallError("PUBLISHED_CARD_PAGE_MISSING:" + uid)
        nonempty += int(expected > 0)
        minimum_specs = expected if minimum_specs is None else min(minimum_specs, expected)
        checked[uid] = {"visible_specs": expected, "roots": roots}
    if len(checked) < 16 or pages < 32 or nonempty != len(checked) or (minimum_specs or 0) < 10:
        raise InstallError("PUBLIC_COVERAGE:%d:%d:%d" % (len(checked), pages, nonempty))
    return {
        "status": "PASS", "cards": checked, "card_count": len(checked),
        "page_count": pages, "nonempty_cards": nonempty,
        "minimum_specs_per_card": minimum_specs or 0,
    }


def run_install(invocation: str) -> dict[str, Any]:
    crm_before = cars_hash()
    audit = source_policy.audit_sources()
    detailed_pass = sum(
        1 for domain in source_policy.SOURCE_DOMAINS[1:]
        if audit["sources"].get(domain, {}).get("status") == "PASS"
    )
    if audit.get("pass_count", 0) < 2 or detailed_pass < 1:
        raise InstallError("SOURCE_AUDIT_INSUFFICIENT")
    candidates = _candidate_sources()
    backup = create_backup(snapshot_paths())
    try:
        source_hashes = _install_sources(candidates)
        service = _fresh_modules()
        migration = service.migrate_legacy_once()
        scan = service.scan_new_vins()
        if int(scan.get("valid_vins") or 0) < 16:
            raise InstallError("VALID_VIN_COVERAGE_TOO_SMALL")
        # A terminated remote run can leave current-policy rows in RUNNING.
        # Full installation must deterministically revisit every current VIN,
        # not just rows the periodic scanner considers new.
        backfill = service.requeue_all_current_vins()
        if (
            int(backfill.get("valid_vins") or 0) != int(scan["valid_vins"])
            or int(backfill.get("queued") or 0) != int(scan["valid_vins"])
        ):
            raise InstallError("FULL_REQUEUE_INCOMPLETE")
        completion = _drain_full_backfill(service, int(backfill["valid_vins"]))
        processed = completion.pop("processed")
        cards = service.read_cards()
        # process_one already refreshes published cards.  Only retry cards whose
        # two local public copies are not current; a second unconditional pass
        # can trip the publication layer's duplicate/rate guard.
        refreshes = []
        for card in cards:
            if card.get("published") and _visible_count(str(card["car_uid"])) > 0:
                uid = str(card["car_uid"])
                expected = _visible_count(uid)
                if _local_public_current(uid, expected):
                    status, detail = "PASS", "already current after VIN processing"
                else:
                    status, detail = service._refresh_published(card)
                refreshes.append({"car_uid": card["car_uid"], "status": status, "detail": detail})
                if status != "PASS":
                    raise InstallError("PUBLIC_REFRESH_FAILED:%s:%s" % (uid, detail[:240]))
        public = verify_local_public(cards)
        crm_after = cars_hash()
        if crm_after != crm_before:
            raise InstallError("MAIN_CRM_CHANGED")
        with service.connect_spec(True) as conn:
            quick = str(conn.execute("PRAGMA quick_check").fetchone()[0])
            price_rows = int(conn.execute(
                "SELECT COUNT(*) FROM additional_specification WHERE is_price_field<>0 OR lower(field_key) LIKE '%price%'"
            ).fetchone()[0])
            job_rows = [dict(row) for row in conn.execute(
                """SELECT car_uid,status,facts_count,site_sync_status FROM vin_spec_jobs
                   WHERE policy_version=? AND status<>'SUPERSEDED' ORDER BY car_uid""",
                (source_policy.POLICY_VERSION,),
            )]
        if quick != "ok" or price_rows != 0:
            raise InstallError("SIDECAR_INTEGRITY")
        if len(job_rows) != int(scan["valid_vins"]) or any(
            row["status"] != "READY" or int(row["facts_count"] or 0) < 10
            for row in job_rows
        ):
            raise InstallError("BACKFILL_INCOMPLETE")
        result = {
            "task_id": TASK_ID, "contract_id": CONTRACT, "status": "PASS",
            "invocation": invocation,
            "phase": "INSTALL", "finished_at": utc_now(), "backup": backup,
            "source_audit": audit, "source_hashes": source_hashes,
            "legacy_migration": migration, "scan": scan, "full_requeue": backfill,
            "backfill_completion": completion, "processed": processed,
            "jobs": job_rows, "refreshes": refreshes, "public": public,
            "sidecar_quick_check": quick, "price_rows": price_rows,
            "crm_write": False, "crm_unchanged": True,
            "initial_autopublication": False, "published_cards_refreshed": True,
            "source_urls_public": False, "global_automatic_mode_enabled": False,
            "vin_autostart_enabled": True,
        }
        atomic_json(INSTALL_RECEIPT, result)
        return result
    except Exception as exc:
        rollback = restore_backup(backup)
        failure = {
            "task_id": TASK_ID, "contract_id": CONTRACT, "status": "FAIL",
            "invocation": invocation,
            "phase": "INSTALL", "finished_at": utc_now(), "backup": backup,
            "error": type(exc).__name__ + ":" + str(exc), "rollback": rollback,
            "crm_write": False, "global_automatic_mode_enabled": False,
            "vin_autostart_enabled": True,
        }
        atomic_json(INSTALL_RECEIPT, failure)
        raise


def run_verify(invocation: str) -> dict[str, Any]:
    service = _fresh_modules()
    cards = service.read_cards()
    public = verify_local_public(cards)
    with service.connect_spec(True) as conn:
        quick = str(conn.execute("PRAGMA quick_check").fetchone()[0])
        jobs = [dict(row) for row in conn.execute(
            """SELECT car_uid,status,facts_count,site_sync_status FROM vin_spec_jobs
               WHERE policy_version=? AND status<>'SUPERSEDED' ORDER BY car_uid""",
            (source_policy.POLICY_VERSION,),
        )]
    if quick != "ok" or len(jobs) != len(cards) or len(jobs) < 16 or any(
        row["status"] != "READY" or int(row["facts_count"] or 0) < 10 for row in jobs
    ):
        raise InstallError("VERIFY_SIDECAR")
    result = {
        "task_id": TASK_ID, "contract_id": CONTRACT, "status": "PASS", "phase": "VERIFY",
        "invocation": invocation,
        "finished_at": utc_now(), "public": public, "jobs": jobs,
        "sidecar_quick_check": quick, "crm_write": False,
        "vin_autostart_enabled": True,
    }
    atomic_json(VERIFY_RECEIPT, result)
    return result


def run_rollback(backup: str | None, invocation: str) -> dict[str, Any]:
    if not backup:
        raw = safe_read(LATEST_BACKUP)
        backup = (raw or b"").decode().strip()
    result = restore_backup(str(backup))
    result.update({
        "task_id": TASK_ID, "contract_id": CONTRACT, "phase": "ROLLBACK",
        "invocation": invocation, "finished_at": utc_now(),
    })
    atomic_json(ROLLBACK_RECEIPT, result)
    return result


def selftest() -> None:
    global ROOT
    assert len(source_policy.SOURCE_DOMAINS) == 10
    assert integration_patcher.patch_additional_spec(
        integration_patcher.patch_additional_spec(
            "import os,pathlib,sqlite3\nfrom typing import Any\nDB_PATH=pathlib.Path('/x')\n"
            "def connect(readonly=True): pass\ndef fetch_specs(value,include_hidden=False): return []\n"
            "def crm_summary(value): return ''\ndef _car_vin(uid): return ''\ndef _car_status(uid): return ''\n"
        )
    ).count(integration_patcher.SPEC_START) == 1
    original_root = ROOT
    try:
        with tempfile.TemporaryDirectory(prefix="ua111-current-pages-") as folder:
            ROOT = folder
            for name in ("video", "site"):
                pathlib.Path(folder, name).mkdir()
                pathlib.Path(folder, name, "UA-0005.html").write_text(
                    SPEC_START + '<div class="ua-addspec-row"></div>' * 2 + SPEC_END,
                    encoding="utf-8",
                )
            assert _local_public_current("UA-0005", 2) is True
            assert _local_public_current("UA-0005", 3) is False
        states = [
            [
                {"car_uid": "UA-%04d" % index,
                 "status": "READY" if index <= 11 else "RUNNING",
                 "facts_count": 20 if index <= 11 else 0}
                for index in range(1, 17)
            ],
            [
                {"car_uid": "UA-%04d" % index, "status": "READY", "facts_count": 20}
                for index in range(1, 17)
            ],
        ]
        fake = type("FakeService", (), {
            "process_one": staticmethod(lambda: None),
            "recover_interrupted_jobs": staticmethod(lambda **_kwargs: 0),
        })()
        completion = _drain_full_backfill(
            fake, 16, state_reader=lambda: states.pop(0),
            sleeper=lambda _seconds: None, clock=lambda: 0,
        )
        assert completion["completed"] == 16 and completion["polls"] == 2
    finally:
        ROOT = original_root
    print("UA111_REMOTE_INSTALLER_SELFTEST_PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--backup")
    parser.add_argument("--invocation", default="")
    args = parser.parse_args()
    if not (args.install or args.verify or args.rollback):
        selftest()
        return 0
    if not re.fullmatch(r"[A-Za-z0-9._-]{8,160}", args.invocation):
        raise InstallError("INVOCATION_REQUIRED")
    with open(LOCK_PATH, "a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if args.install:
            result = run_install(args.invocation)
        elif args.verify:
            result = run_verify(args.invocation)
        else:
            result = run_rollback(args.backup, args.invocation)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
