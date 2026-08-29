#!/usr/bin/env python3
"""Bounded PythonAnywhere executor for TASK 077 production Gate B.

This file runs on the PythonAnywhere host only after the owner-authorized,
manual GitHub workflow uploads it.  It performs a read-only shadow, a durable
backup, the exact SHA-anchored source install, two current-card repairs, and
read-only postchecks.  UA-0011 is deliberately protected because the owner's
newer instruction moves that card back to Korea and clears its ETA/container.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import urllib.request
import uuid


CONTRACT = "CRM-CONTAINER-STAGE-SYNC-004-V1.0"
OWNER_TOKEN = "CRM-CONTAINER-STAGE-SYNC-004-V1.0-PRODUCTION-APPROVED"
ROOT = pathlib.Path("/home/Carix")
CLOUD = ROOT / "autopilot_inbox/cloud"
TASK_ROOT = CLOUD / "task_077_container_stage_sync"
HERE = TASK_ROOT / "gate_b"
PATCHER = TASK_ROOT / "patcher"
ENGINE_ROOT = CLOUD / "task_076_eta_sync"
STATE = HERE / "gate_b_state.json"
RECEIPTS = {
    "shadow": HERE / "gate_b_shadow_receipt.json",
    "apply": HERE / "gate_b_apply_receipt.json",
    "postcheck": HERE / "gate_b_postcheck_receipt.json",
    "rollback": HERE / "gate_b_rollback_receipt.json",
}
TARGET_CODES = ("UA-0009", "UA-0010")
PROTECTED_AMENDED_CODE = "UA-0011"
ACTOR_ID = "77004"
EXPECTED_DAYS = 30
SOURCE_NAMES = (
    "db.py", "cars_ui.py", "konteyner.py", "stranica.py", "publikaciya.py",
)
INSTALLED_EXTRA_NAMES = ("eta_sync_guard.py", "eta_engine.py")
MAX_FILE_BYTES = 80_000_000


class GateBError(RuntimeError):
    pass


def utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        .isoformat().replace("+00:00", "Z")
    )


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: pathlib.Path) -> str:
    return sha_bytes(path.read_bytes())


def atomic_bytes(path: pathlib.Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    temp_path = pathlib.Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict) -> None:
    atomic_bytes(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def db_connect(read_only: bool = False) -> sqlite3.Connection:
    db_path = ROOT / "crm.db"
    if read_only:
        uri = "file:%s?mode=ro" % db_path
        conn = sqlite3.connect(uri, uri=True, timeout=30)
    else:
        conn = sqlite3.connect(db_path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def row_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def all_rows(conn: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in conn.execute("SELECT * FROM cars ORDER BY id")]


def stable_digest(rows: list[dict]) -> str:
    return sha_bytes(json.dumps(
        rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8"))


def protected_digest(rows: list[dict], target_ids: set[int]) -> str:
    return stable_digest([row for row in rows if int(row["id"]) not in target_ids])


def safe_card(row: dict) -> dict:
    keys = (
        "id", "auto_number", "status", "days_to_kyiv", "eta_manual",
        "published", "updated_at", "sea_container", "sea_date_out",
    )
    return {key: row.get(key) for key in keys if key in row}


def resolve_targets(rows: list[dict]) -> dict[str, dict]:
    result = {}
    for code in TARGET_CODES + (PROTECTED_AMENDED_CODE,):
        matches = [row for row in rows if str(row.get("auto_number") or "").upper() == code]
        if len(matches) != 1:
            raise GateBError("CARD_COUNT_%s:%d" % (code, len(matches)))
        result[code] = matches[0]
    if int(result[TARGET_CODES[0]]["id"]) == int(result[TARGET_CODES[1]]["id"]):
        raise GateBError("TARGET_ID_COLLISION")
    return result


def audit_max(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id),0) FROM audit").fetchone()
    return int(row[0])


def source_paths() -> list[pathlib.Path]:
    return [ROOT / name for name in SOURCE_NAMES + INSTALLED_EXTRA_NAMES]


def bounded_page_paths() -> list[pathlib.Path]:
    paths = []
    for surface in ("video", "site"):
        base = ROOT / surface
        for code in TARGET_CODES:
            paths.extend((base / (code + ".html"), base / (code + "-diag.html")))
        paths.append(base / "katalog.html")
    return paths


def require_no_hashed_variants() -> None:
    pattern = re.compile(r"^UA-\d{4}-[0-9a-f]{6,10}\.html$", re.I)
    found = []
    for surface in ("video", "site"):
        base = ROOT / surface
        for code in TARGET_CODES:
            for path in base.glob(code + "-*.html"):
                if pattern.fullmatch(path.name):
                    found.append(str(path))
    if found:
        raise GateBError("UNBOUNDED_HASHED_VARIANTS:" + ",".join(sorted(found)))


def load_modules():
    for path in (str(PATCHER), str(ENGINE_ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)
    import live_patcher
    return live_patcher


def verify_patch_bundle() -> dict:
    live_patcher = load_modules()
    patched = live_patcher.prepare_patch_bundle(str(ROOT))
    if len(live_patcher.PATCH_SPECS) != 8 or len(patched) != 5:
        raise GateBError("PATCH_BUNDLE_COVERAGE")
    return {
        "function_transforms": len(live_patcher.PATCH_SPECS),
        "compiled_files": {
            pathlib.Path(path).name: sha_bytes(text.encode("utf-8"))
            for path, text in sorted(patched.items())
        },
    }


def public_manifest(code: str) -> dict:
    stamp = int(time.time())
    result = {}
    for surface in ("video", "site"):
        url = "https://www.uaart.com.ua/%s/%s.html?v=%d" % (surface, code, stamp)
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                data = response.read(2_000_001)
                status = response.status
            text = data.decode("utf-8", "replace")
            result[surface] = {
                "status": status,
                "bytes": len(data),
                "code_present": code in text,
                "days_30": bool(re.search(r"\b30\s*(?:дн|дней|дня)", text, re.I)),
                "eta_2026_09_28": any(value in text for value in (
                    "2026-09-28", "28.09.2026", "28 сентября 2026", "28 вересня 2026",
                )),
                "sha256": sha_bytes(data),
            }
        except Exception as exc:
            result[surface] = {"error": type(exc).__name__}
    return result


def shadow() -> dict:
    value = {
        "contract_id": CONTRACT,
        "mode": "SHADOW_GET_ONLY",
        "status": "FAIL",
        "production_write": False,
        "crm_db_write": False,
        "runtime_llm_tokens": 0,
        "started_at_utc": utc_now(),
        "errors": [],
    }
    try:
        require_no_hashed_variants()
        patch = verify_patch_bundle()
        conn = db_connect(read_only=True)
        try:
            quick = conn.execute("PRAGMA quick_check").fetchone()[0]
            rows = all_rows(conn)
            targets = resolve_targets(rows)
            maximum = audit_max(conn)
        finally:
            conn.close()
        if quick != "ok":
            raise GateBError("SQLITE_QUICK_CHECK:" + str(quick))
        target_ids = {int(targets[code]["id"]) for code in TARGET_CODES}
        value.update({
            "database": {
                "quick_check": quick,
                "row_count": len(rows),
                "audit_max_id": maximum,
                "targets": {code: safe_card(targets[code]) for code in TARGET_CODES},
                "protected_ua0011": safe_card(targets[PROTECTED_AMENDED_CODE]),
                "protected_rows_sha256": protected_digest(rows, target_ids),
            },
            "patch_bundle": patch,
            "public_before": {code: public_manifest(code) for code in TARGET_CODES},
        })
        value["status"] = "PASS"
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
    value["finished_at_utc"] = utc_now()
    atomic_json(RECEIPTS["shadow"], value)
    return value


def copy_preimage(path: pathlib.Path, backup_root: pathlib.Path, index: int) -> dict:
    if not str(path).startswith(str(ROOT) + os.sep):
        raise GateBError("BACKUP_PATH_OUT_OF_SCOPE")
    if not path.exists():
        return {"path": str(path), "missing": True}
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise GateBError("BACKUP_FILE_INVALID:" + str(path))
    data = path.read_bytes()
    target = backup_root / "files" / ("%03d__%s" % (index, path.name))
    atomic_bytes(target, data, path.stat().st_mode & 0o777)
    return {
        "path": str(path), "backup": str(target), "missing": False,
        "sha256": sha_bytes(data), "bytes": len(data),
        "mode": path.stat().st_mode & 0o777,
    }


def create_backup(rows: list[dict], targets: dict[str, dict], audit_before: int) -> dict:
    backup_root = (
        HERE / "backups" /
        (dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:10])
    )
    backup_root.mkdir(parents=True, exist_ok=False)
    paths = source_paths() + bounded_page_paths()
    manifest = [copy_preimage(path, backup_root, index) for index, path in enumerate(paths)]
    source = db_connect(read_only=False)
    snapshot = sqlite3.connect(backup_root / "crm.db.snapshot")
    try:
        source.backup(snapshot)
    finally:
        snapshot.close()
        source.close()
    target_ids = {int(targets[code]["id"]) for code in TARGET_CODES}
    state = {
        "contract_id": CONTRACT,
        "status": "BACKED_UP",
        "created_at_utc": utc_now(),
        "backup_root": str(backup_root),
        "file_manifest": manifest,
        "database_snapshot": str(backup_root / "crm.db.snapshot"),
        "audit_max_before": audit_before,
        "actor_id": ACTOR_ID,
        "target_codes": list(TARGET_CODES),
        "target_ids": sorted(target_ids),
        "target_preimages": {code: targets[code] for code in TARGET_CODES},
        "protected_rows_sha256": protected_digest(rows, target_ids),
        "protected_ua0011": targets[PROTECTED_AMENDED_CODE],
        "audit_ids": [],
        "installed_sha256": {},
    }
    atomic_json(backup_root / "manifest.json", state)
    atomic_json(STATE, state)
    return state


def restore_files(state: dict) -> None:
    for item in state.get("file_manifest") or []:
        path = pathlib.Path(item["path"])
        if not str(path).startswith(str(ROOT) + os.sep):
            raise GateBError("RESTORE_PATH_OUT_OF_SCOPE")
        if item.get("missing"):
            path.unlink(missing_ok=True)
            continue
        backup = pathlib.Path(item["backup"])
        data = backup.read_bytes()
        if sha_bytes(data) != item["sha256"]:
            raise GateBError("BACKUP_HASH_MISMATCH:" + path.name)
        atomic_bytes(path, data, int(item.get("mode") or 0o644))
        if sha_file(path) != item["sha256"]:
            raise GateBError("RESTORE_HASH_MISMATCH:" + path.name)


def audit_ids_for_operation(conn: sqlite3.Connection, state: dict) -> list[int]:
    marks = ",".join("?" for _ in state["target_ids"])
    query = (
        "SELECT id FROM audit WHERE id>? AND CAST(actor_id AS TEXT)=? "
        "AND entity_type='cars' AND entity_id IN (%s) ORDER BY id" % marks
    )
    args = [int(state["audit_max_before"]), str(state["actor_id"])] + list(state["target_ids"])
    return [int(row[0]) for row in conn.execute(query, args)]


def restore_database(state: dict) -> None:
    conn = db_connect(read_only=False)
    conn.execute("BEGIN IMMEDIATE")
    try:
        for code in TARGET_CODES:
            row = state["target_preimages"][code]
            conn.execute(
                "UPDATE cars SET days_to_kyiv=?, eta_manual=?, status=?, published=?, "
                "condition_text=?, updated_at=? WHERE id=?",
                (row.get("days_to_kyiv"), row.get("eta_manual"), row.get("status"),
                 row.get("published"), row.get("condition_text"), row.get("updated_at"),
                 int(row["id"])),
            )
        ids = audit_ids_for_operation(conn, state)
        for audit_id in ids:
            conn.execute("DELETE FROM audit WHERE id=?", (audit_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rollback(reason: str = "manual") -> dict:
    value = {
        "contract_id": CONTRACT, "mode": "ROLLBACK", "status": "FAIL",
        "production_write": True, "runtime_llm_tokens": 0,
        "started_at_utc": utc_now(), "reason": reason, "errors": [],
    }
    try:
        if not STATE.exists():
            raise GateBError("ROLLBACK_STATE_MISSING")
        state = json.loads(STATE.read_text(encoding="utf-8"))
        if state.get("contract_id") != CONTRACT:
            raise GateBError("ROLLBACK_STATE_CONTRACT")
        restore_database(state)
        restore_files(state)
        conn = db_connect(read_only=True)
        try:
            rows = all_rows(conn)
            targets = resolve_targets(rows)
            quick = conn.execute("PRAGMA quick_check").fetchone()[0]
            audit_left = audit_ids_for_operation(conn, state)
        finally:
            conn.close()
        for code in TARGET_CODES:
            current = targets[code]
            before = state["target_preimages"][code]
            for field in (
                "days_to_kyiv", "eta_manual", "status", "published",
                "condition_text", "updated_at",
            ):
                if current.get(field) != before.get(field):
                    raise GateBError("ROLLBACK_DB_MISMATCH:%s:%s" % (code, field))
        target_ids = set(state["target_ids"])
        if protected_digest(rows, target_ids) != state["protected_rows_sha256"]:
            raise GateBError("ROLLBACK_PROTECTED_ROWS_MISMATCH")
        if quick != "ok" or audit_left:
            raise GateBError("ROLLBACK_DB_INTEGRITY")
        state["status"] = "ROLLED_BACK"
        state["rollback_at_utc"] = utc_now()
        atomic_json(STATE, state)
        value.update({"status": "PASS", "backup_root": state["backup_root"],
                      "quick_check": quick, "audit_ids_removed": True})
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
    value["finished_at_utc"] = utc_now()
    atomic_json(RECEIPTS["rollback"], value)
    return value


def apply_release() -> dict:
    value = {
        "contract_id": CONTRACT, "mode": "APPROVED_PRODUCTION_APPLY",
        "status": "FAIL", "production_write": False, "runtime_llm_tokens": 0,
        "started_at_utc": utc_now(), "errors": [], "rollback": None,
    }
    state = None
    try:
        require_no_hashed_variants()
        patch = verify_patch_bundle()
        conn = db_connect(read_only=True)
        try:
            quick = conn.execute("PRAGMA quick_check").fetchone()[0]
            rows = all_rows(conn)
            targets = resolve_targets(rows)
            maximum = audit_max(conn)
        finally:
            conn.close()
        if quick != "ok":
            raise GateBError("PREWRITE_QUICK_CHECK")
        state = create_backup(rows, targets, maximum)
        value["backup_root"] = state["backup_root"]
        value["database_before"] = {
            "quick_check": quick,
            "targets": {code: safe_card(targets[code]) for code in TARGET_CODES},
            "protected_ua0011": safe_card(targets[PROTECTED_AMENDED_CODE]),
            "protected_rows_sha256": state["protected_rows_sha256"],
        }
        live_patcher = load_modules()
        temporary_parent = pathlib.Path(tempfile.mkdtemp(prefix="task077-install-"))
        try:
            installed = live_patcher.apply_patch_bundle(
                str(ROOT), str(temporary_parent / "source-backup"),
                OWNER_TOKEN, apply=True,
            )
        finally:
            shutil.rmtree(temporary_parent, ignore_errors=True)
        state["installed_sha256"] = {
            str(pathlib.Path(path)): digest for path, digest in installed.items()
        }
        state["status"] = "SOURCES_INSTALLED"
        atomic_json(STATE, state)
        value["production_write"] = True
        value["source_install"] = {"status": "PASS", "sha256": state["installed_sha256"]}

        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import eta_sync_guard
        messages = {}
        for code in TARGET_CODES:
            ok, detail = eta_sync_guard.apply_eta_days_live(
                int(targets[code]["id"]), EXPECTED_DAYS, ACTOR_ID,
            )
            messages[code] = detail
            conn = db_connect(read_only=True)
            try:
                state["audit_ids"] = audit_ids_for_operation(conn, state)
            finally:
                conn.close()
            atomic_json(STATE, state)
            if not ok:
                raise GateBError("CARD_APPLY_%s:%s" % (code, detail))

        expected_eta = (
            dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=EXPECTED_DAYS)
        ).isoformat()
        conn = db_connect(read_only=True)
        try:
            quick_after = conn.execute("PRAGMA quick_check").fetchone()[0]
            rows_after = all_rows(conn)
            targets_after = resolve_targets(rows_after)
            state["audit_ids"] = audit_ids_for_operation(conn, state)
        finally:
            conn.close()
        for code in TARGET_CODES:
            row = targets_after[code]
            if int(row.get("days_to_kyiv")) != EXPECTED_DAYS:
                raise GateBError("DAYS_READBACK:" + code)
            if row.get("eta_manual") != expected_eta or row.get("status") != "sea_loaded":
                raise GateBError("ETA_STATUS_READBACK:" + code)
            if row.get("published") != targets[code].get("published"):
                raise GateBError("PUBLISHED_CHANGED:" + code)
            if eta_sync_guard.sanitize_stale_arrival_sentence(
                str(row.get("condition_text") or "")) != str(row.get("condition_text") or ""):
                raise GateBError("STALE_ARRIVAL_TEXT:" + code)
        target_ids = set(state["target_ids"])
        if protected_digest(rows_after, target_ids) != state["protected_rows_sha256"]:
            raise GateBError("PROTECTED_ROWS_CHANGED")
        if quick_after != "ok":
            raise GateBError("POSTWRITE_QUICK_CHECK")
        state["status"] = "APPLIED"
        state["expected_eta"] = expected_eta
        state["applied_at_utc"] = utc_now()
        atomic_json(STATE, state)
        value.update({
            "status": "PASS",
            "messages": messages,
            "database_after": {
                "quick_check": quick_after,
                "targets": {code: safe_card(targets_after[code]) for code in TARGET_CODES},
                "protected_ua0011": safe_card(targets_after[PROTECTED_AMENDED_CODE]),
                "protected_rows_sha256": protected_digest(rows_after, target_ids),
                "audit_ids": state["audit_ids"],
            },
            "patch_bundle": patch,
            "public_after": {code: public_manifest(code) for code in TARGET_CODES},
        })
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
        if state is not None:
            rb = rollback("apply_failure")
            value["rollback"] = rb
            value["status"] = "ROLLED_BACK" if rb.get("status") == "PASS" else "BLOCKED"
    value["finished_at_utc"] = utc_now()
    atomic_json(RECEIPTS["apply"], value)
    return value


def postcheck() -> dict:
    value = {
        "contract_id": CONTRACT, "mode": "POSTCHECK_GET_ONLY", "status": "FAIL",
        "production_write": False, "crm_db_write": False, "runtime_llm_tokens": 0,
        "started_at_utc": utc_now(), "errors": [],
    }
    try:
        if not STATE.exists():
            raise GateBError("STATE_MISSING")
        state = json.loads(STATE.read_text(encoding="utf-8"))
        if state.get("status") != "APPLIED":
            raise GateBError("STATE_NOT_APPLIED:" + str(state.get("status")))
        conn = db_connect(read_only=True)
        try:
            quick = conn.execute("PRAGMA quick_check").fetchone()[0]
            rows = all_rows(conn)
            targets = resolve_targets(rows)
            audits = audit_ids_for_operation(conn, state)
        finally:
            conn.close()
        for code in TARGET_CODES:
            row = targets[code]
            if (
                int(row.get("days_to_kyiv")) != EXPECTED_DAYS
                or row.get("eta_manual") != state["expected_eta"]
                or row.get("status") != "sea_loaded"
            ):
                raise GateBError("POSTCHECK_TARGET:" + code)
        target_ids = set(state["target_ids"])
        if protected_digest(rows, target_ids) != state["protected_rows_sha256"]:
            raise GateBError("POSTCHECK_PROTECTED_ROWS")
        if quick != "ok" or audits != state.get("audit_ids"):
            raise GateBError("POSTCHECK_DATABASE_INTEGRITY")
        for path, digest in state.get("installed_sha256", {}).items():
            if sha_file(pathlib.Path(path)) != digest:
                raise GateBError("POSTCHECK_SOURCE_DRIFT:" + pathlib.Path(path).name)
        public = {code: public_manifest(code) for code in TARGET_CODES}
        for code, surfaces in public.items():
            for surface in ("video", "site"):
                item = surfaces.get(surface) or {}
                if not (
                    item.get("status") == 200 and item.get("code_present")
                    and item.get("days_30") and item.get("eta_2026_09_28")
                ):
                    raise GateBError("POSTCHECK_PUBLIC:%s:%s" % (code, surface))
        value.update({
            "status": "PASS", "quick_check": quick,
            "targets": {code: safe_card(targets[code]) for code in TARGET_CODES},
            "protected_ua0011": safe_card(targets[PROTECTED_AMENDED_CODE]),
            "protected_rows_sha256": protected_digest(rows, target_ids),
            "public": public, "source_count": len(state.get("installed_sha256") or {}),
            "audit_ids": audits, "backup_root": state["backup_root"],
        })
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
    value["finished_at_utc"] = utc_now()
    atomic_json(RECEIPTS["postcheck"], value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("shadow", "apply", "postcheck", "rollback"))
    args = parser.parse_args()
    RECEIPTS[args.mode].unlink(missing_ok=True)
    if args.mode == "shadow":
        value = shadow()
    elif args.mode == "apply":
        value = apply_release()
    elif args.mode == "postcheck":
        value = postcheck()
    else:
        value = rollback("controller_request")
    print(json.dumps({"status": value["status"], "errors": value["errors"]}, ensure_ascii=False))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
