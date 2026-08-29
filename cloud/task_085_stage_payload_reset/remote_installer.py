#!/usr/bin/env python3
"""Bounded PythonAnywhere executor for TASK 085.

Runs only through the owner-authorized GitHub production workflow.  Every
write is preceded by a read-only shadow and exact preimage backup.  A failed
apply restores only this task's row, triggers, sources and generated pages.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import fcntl
import hashlib
import importlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import sqlite3
import sys
import tempfile
import traceback
import uuid
from typing import Any


CONTRACT_ID = "UA-0011-STAGE-PAYLOAD-RESET-005-V1.0"
TARGET_CODE = "UA-0011"
PROTECTED_CODE = "UA-0009"
EXPECTED_STATUS = "kr_bought"
ACTOR_ID = 85005
ROOT = pathlib.Path("/home/Carix")
# The controller stages unique task085 files inside the already-existing,
# proven task083 inbox directory; production targets remain independently scoped.
TASK_ROOT = ROOT / "autopilot_inbox/cloud/task_083_catalog_dedup"
UPLOADED_GUARD = TASK_ROOT / "task085_stage_payload_guard.py"
LIVE_GUARD = ROOT / "stage_payload_guard.py"
STATE = TASK_ROOT / "task085_state.json"
LOCK = ROOT / ".ua_art_production_writer.lock"
DB_PATH = ROOT / "crm.db"
SOURCE_NAMES = ("db.py", "cars_ui.py", "stranica.py", "master_card.py", "cars_schema.py")
SOURCE_PATHS = tuple(ROOT / name for name in SOURCE_NAMES)
RECEIPTS = {
    "shadow": TASK_ROOT / "task085_shadow_receipt.json",
    "apply": TASK_ROOT / "task085_apply_receipt.json",
    "postcheck": TASK_ROOT / "task085_postcheck_receipt.json",
    "rollback": TASK_ROOT / "task085_rollback_receipt.json",
}
RESET_FIELDS = (
    "sea_container", "sea_date_out", "sea_port_from", "days_to_kyiv",
    "eta_manual", "ge_arrived", "ge_port", "ge_released", "ge_to_kyiv_at",
)
OLD_CONTAINER = "ONEYSELGF1046602"
OLD_ETA_VALUES = (
    "2026-12-12", "12.12.2026", "12 декабря 2026", "12 грудня 2026",
)
MARKERS = {
    "db.py": "TASK085_STAGE_PAYLOAD_DB_GUARD_V1",
    "cars_ui.py": "TASK085_STAGE_REFRESH_V1",
    "stranica.py": "TASK085_PUBLIC_PROJECTION_V1",
    "master_card.py": "TASK085_MASTER_PROJECTION_V1",
    "cars_schema.py": "TASK085_CRM_PROJECTION_V1",
}
MAX_FILE_BYTES = 16_000_000


class Task085Error(RuntimeError):
    pass


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable(value: Any) -> str:
    return sha_bytes(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8"))


def atomic_bytes(path: pathlib.Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    temp = pathlib.Path(raw)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict) -> None:
    atomic_bytes(path, (json.dumps(
        value, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n").encode("utf-8"))


def connect(read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        connection = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True, timeout=40)
    else:
        connection = sqlite3.connect(DB_PATH, timeout=40, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=40000")
    return connection


def all_rows(connection: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in connection.execute("SELECT * FROM cars ORDER BY id")]


def unique_row(rows: list[dict], code: str) -> dict:
    found = [row for row in rows if str(row.get("auto_number") or "").upper() == code]
    if len(found) != 1:
        raise Task085Error("CARD_COUNT_%s:%d" % (code, len(found)))
    return found[0]


def safe_target(row: dict) -> dict:
    keys = (
        "id", "auto_number", "status", "published", "sea_container", "sea_date_out",
        "sea_port_from", "days_to_kyiv", "eta_manual", "ge_arrived", "ge_port",
        "ge_released", "ge_to_kyiv_at", "updated_at", "vin",
    )
    return {key: row.get(key) for key in keys if key in row}


def media_digest(row: dict) -> str:
    values = {
        key: value for key, value in row.items()
        if re.search(r"photo|video|diag|media", key, re.I)
    }
    return stable(values)


def protected_rows_digest(rows: list[dict], target_id: int) -> str:
    return stable([row for row in rows if int(row["id"]) != int(target_id)])


def target_business_digest(row: dict) -> str:
    ignored = set(RESET_FIELDS) | {"status", "updated_at"}
    return stable({key: value for key, value in row.items() if key not in ignored})


def _function(source: str, name: str) -> tuple[int, int, str]:
    """Resolve the active top-level definition (Python executes the last one)."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if not matches:
        raise Task085Error("FUNCTION_MISSING_%s" % name)
    node = matches[-1]
    start, end = node.lineno - 1, getattr(node, "end_lineno", node.lineno)
    return start, end, "".join(lines[start:end])


def _replace_function(source: str, name: str, replacement: str) -> str:
    start, end, _old = _function(source, name)
    lines = source.splitlines(keepends=True)
    if not replacement.endswith("\n"):
        replacement += "\n"
    return "".join(lines[:start] + [replacement] + lines[end:])


DB_REPLACEMENT = '''def update_card_field(table: str, card_id: int, field: str, value, actor_id: int):
    """Каждая правка поля попадает в журнал со старым и новым значением."""
    # TASK085_STAGE_PAYLOAD_DB_GUARD_V1
    old = get_card(table, card_id)
    old_value = old.get(field) if old else None
    if table == "cars" and field == "status":
        import stage_payload_guard as _task085_guard
        fields = ()
        if _task085_guard.stage_number(value) is not None:
            fields = _task085_guard.cleanup_fields_for_transition(
                old_value, value, (old or {}).keys()
            )
        assignments = ["status=?"] + ['"%s"=NULL' % name for name in fields]
        assignments.append("updated_at=?")
        params = [value, now(), card_id]
        with connect() as c:
            c.execute(
                "UPDATE cars SET %s WHERE id=?" % ", ".join(assignments), params
            )
    else:
        with connect() as c:
            c.execute(f"UPDATE {table} SET {field}=?, updated_at=? WHERE id=?",
                      (value, now(), card_id))
    log_action(actor_id, "card_edit", table, card_id, field, old_value, value)
'''


def patch_db(source: str) -> str:
    marker = MARKERS["db.py"]
    if marker in source:
        if source.count(marker) != 1:
            raise Task085Error("DB_MARKER_COUNT")
        return source
    return _replace_function(source, "update_card_field", DB_REPLACEMENT)


def _inject_function_line(
    source: str, function_name: str, needle: str, insertion: str, marker: str
) -> str:
    if marker in source:
        if source.count(marker) != 1:
            raise Task085Error("MARKER_COUNT:" + marker)
        return source
    start, end, block = _function(source, function_name)
    if block.count(needle) != 1:
        raise Task085Error("ANCHOR_COUNT_%s:%d" % (function_name, block.count(needle)))
    block = block.replace(needle, insertion, 1)
    lines = source.splitlines(keepends=True)
    if not block.endswith("\n"):
        block += "\n"
    return "".join(lines[:start] + [block] + lines[end:])


def patch_cars_ui(source: str) -> str:
    needle = '    set_field(cid, "status", code, q.from_user.id)\n'
    insertion = needle + (
        "    # TASK085_STAGE_REFRESH_V1\n"
        "    # Re-read the atomic destination payload before stage-specific defaults.\n"
        "    card_before = card_of(cid)\n"
    )
    return _inject_function_line(
        source, "stage_set", needle, insertion, MARKERS["cars_ui.py"]
    )


def _inject_function_prologue(
    source: str,
    function_name: str,
    argument_name: str,
    statements: tuple[str, ...],
    marker: str,
) -> str:
    """Inject into the active definition without relying on a drifting body line."""
    tree = ast.parse(source)
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if not matches:
        raise Task085Error("FUNCTION_MISSING_%s" % function_name)
    node = matches[-1]
    lines = source.splitlines(keepends=True)
    active = "".join(lines[node.lineno - 1 : getattr(node, "end_lineno", node.lineno)])
    if marker in source:
        if source.count(marker) == 1 and active.count(marker) == 1:
            return source
        raise Task085Error("MARKER_NOT_ACTIVE:" + marker)

    arguments = list(getattr(node.args, "posonlyargs", ()))
    arguments.extend(node.args.args)
    arguments.extend(node.args.kwonlyargs)
    names = {item.arg for item in arguments}
    if node.args.vararg:
        names.add(node.args.vararg.arg)
    if node.args.kwarg:
        names.add(node.args.kwarg.arg)
    if argument_name not in names:
        raise Task085Error(
            "FUNCTION_ARGUMENT_%s:%s" % (function_name, argument_name)
        )
    if not node.body:
        raise Task085Error("FUNCTION_BODY_EMPTY:" + function_name)

    first = node.body[0]
    is_docstring = (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    )
    insert_at = (
        getattr(first, "end_lineno", first.lineno)
        if is_docstring else first.lineno - 1
    )
    reference = lines[first.lineno - 1]
    indent = reference[: len(reference) - len(reference.lstrip())]
    if len(indent) <= node.col_offset:
        indent = " " * (node.col_offset + 4)
    payload = "".join(indent + statement + "\n" for statement in statements)
    candidate = "".join(lines[:insert_at] + [payload] + lines[insert_at:])
    compile(candidate, function_name + ".candidate.py", "exec")
    if candidate.count(marker) != 1:
        raise Task085Error("CANDIDATE_MARKER:" + function_name)
    return candidate


def patch_stranica(source: str) -> str:
    return _inject_function_prologue(
        source,
        "sobrat_kartochku",
        "m",
        (
            "# TASK085_PUBLIC_PROJECTION_V1",
            "from stage_payload_guard import public_projection as _task085_project",
            "m = _task085_project(m)",
        ),
        MARKERS["stranica.py"],
    )


def patch_master_card(source: str) -> str:
    needle = "    m = dannye(kod)\n"
    insertion = needle + (
        "    # TASK085_MASTER_PROJECTION_V1\n"
        "    from stage_payload_guard import public_projection as _task085_project\n"
        "    m = _task085_project(m)\n"
    )
    return _inject_function_line(
        source, "obrabotat_kartochku", needle, insertion, MARKERS["master_card.py"]
    )


def patch_cars_schema(source: str) -> str:
    needle = "    L = []\n"
    insertion = (
        "    # TASK085_CRM_PROJECTION_V1\n"
        "    from stage_payload_guard import public_projection as _task085_project\n"
        "    car = _task085_project(car)\n" + needle
    )
    return _inject_function_line(
        source, "render_card", needle, insertion, MARKERS["cars_schema.py"]
    )


PATCHERS = {
    "db.py": patch_db,
    "cars_ui.py": patch_cars_ui,
    "stranica.py": patch_stranica,
    "master_card.py": patch_master_card,
    "cars_schema.py": patch_cars_schema,
}


def prepare_sources() -> dict[pathlib.Path, bytes]:
    if not UPLOADED_GUARD.is_file():
        raise Task085Error("UPLOADED_GUARD_MISSING")
    guard_data = UPLOADED_GUARD.read_bytes()
    compile(guard_data.decode("utf-8"), str(LIVE_GUARD), "exec")
    result = {LIVE_GUARD: guard_data}
    for path in SOURCE_PATHS:
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            raise Task085Error("SOURCE_INVALID:" + path.name)
        source = path.read_text(encoding="utf-8")
        candidate = PATCHERS[path.name](source)
        compile(candidate, str(path), "exec")
        marker = MARKERS[path.name]
        if candidate.count(marker) != 1:
            raise Task085Error("CANDIDATE_MARKER:" + path.name)
        result[path] = candidate.encode("utf-8")
    return result


def generated_paths() -> list[pathlib.Path]:
    result = []
    for surface in ("video", "site"):
        base = ROOT / surface
        result.append(base / "katalog.html")
        result.extend(sorted(base.glob(TARGET_CODE + "*.html")))
        for fixed in (base / (TARGET_CODE + ".html"), base / (TARGET_CODE + "-diag.html")):
            if fixed not in result:
                result.append(fixed)
    return result


def managed_paths() -> list[pathlib.Path]:
    values = list(SOURCE_PATHS) + [LIVE_GUARD] + generated_paths()
    seen, result = set(), []
    for path in values:
        key = str(path)
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def copy_preimage(path: pathlib.Path, backup: pathlib.Path, index: int) -> dict:
    if not str(path).startswith(str(ROOT) + os.sep):
        raise Task085Error("BACKUP_OUT_OF_SCOPE")
    if not path.exists():
        return {"path": str(path), "missing": True}
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise Task085Error("BACKUP_FILE_INVALID:" + str(path))
    data = path.read_bytes()
    target = backup / "files" / ("%03d__%s" % (index, path.name))
    atomic_bytes(target, data, path.stat().st_mode & 0o777)
    return {
        "path": str(path), "missing": False, "backup": str(target),
        "sha256": sha_bytes(data), "bytes": len(data),
        "mode": path.stat().st_mode & 0o777,
    }


def trigger_sql(connection: sqlite3.Connection) -> dict[str, str]:
    names = ("ua_stage_payload_guard_korea_update_v1", "ua_stage_payload_guard_korea_insert_v1")
    rows = connection.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND name IN (?,?)",
        names,
    ).fetchall()
    return {str(row["name"]): str(row["sql"]) for row in rows}


def audit_max(connection: sqlite3.Connection) -> int:
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    if "audit" not in tables:
        return 0
    return int(connection.execute("SELECT COALESCE(MAX(id),0) FROM audit").fetchone()[0])


def create_backup(rows: list[dict], target: dict) -> dict:
    backup = TASK_ROOT / "task085_backups" / (
        dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:10]
    )
    backup.mkdir(parents=True, exist_ok=False)
    manifest = [
        copy_preimage(path, backup, index) for index, path in enumerate(managed_paths())
    ]
    source = connect(False)
    snapshot = sqlite3.connect(backup / "crm.db.snapshot")
    try:
        source.backup(snapshot)
    finally:
        snapshot.close()
        source.close()
    reader = connect(True)
    try:
        old_triggers = trigger_sql(reader)
        maximum = audit_max(reader)
    finally:
        reader.close()
    value = {
        "contract_id": CONTRACT_ID, "status": "BACKED_UP", "backup_root": str(backup),
        "created_at_utc": now_utc(), "file_manifest": manifest,
        "database_snapshot": str(backup / "crm.db.snapshot"),
        "target_preimage": target, "target_id": int(target["id"]),
        "protected_rows_sha256": protected_rows_digest(rows, int(target["id"])),
        "target_business_sha256": target_business_digest(target),
        "target_media_sha256": media_digest(target),
        "trigger_preimages": old_triggers, "audit_max_before": maximum,
        "audit_actor_id": ACTOR_ID,
    }
    atomic_json(backup / "manifest.json", value)
    atomic_json(STATE, value)
    return value


def restore_files(state: dict) -> None:
    recorded = {item["path"] for item in state.get("file_manifest") or []}
    for path in generated_paths() + list(SOURCE_PATHS) + [LIVE_GUARD]:
        if str(path) not in recorded and path.exists():
            if str(path).startswith(str(ROOT) + os.sep):
                path.unlink()
    for item in state.get("file_manifest") or []:
        path = pathlib.Path(item["path"])
        if not str(path).startswith(str(ROOT) + os.sep):
            raise Task085Error("RESTORE_OUT_OF_SCOPE")
        if item.get("missing"):
            path.unlink(missing_ok=True)
            continue
        data = pathlib.Path(item["backup"]).read_bytes()
        if sha_bytes(data) != item["sha256"]:
            raise Task085Error("BACKUP_HASH_MISMATCH:" + path.name)
        atomic_bytes(path, data, int(item.get("mode") or 0o644))


def restore_database(state: dict) -> None:
    row = state["target_preimage"]
    connection = connect(False)
    connection.execute("BEGIN IMMEDIATE")
    try:
        columns = {item[1] for item in connection.execute("PRAGMA table_info(cars)")}
        fields = [field for field in ("status",) + RESET_FIELDS + ("updated_at",) if field in columns]
        assignments = ", ".join('"%s"=?' % field for field in fields)
        connection.execute(
            "UPDATE cars SET %s WHERE id=?" % assignments,
            [row.get(field) for field in fields] + [int(row["id"])],
        )
        for name in ("ua_stage_payload_guard_korea_update_v1", "ua_stage_payload_guard_korea_insert_v1"):
            connection.execute('DROP TRIGGER IF EXISTS "%s"' % name)
        for sql in (state.get("trigger_preimages") or {}).values():
            connection.execute(sql)
        tables = {item[0] for item in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "audit" in tables:
            connection.execute(
                "DELETE FROM audit WHERE id>? AND CAST(actor_id AS TEXT)=? "
                "AND entity_type='cars' AND entity_id=?",
                (int(state["audit_max_before"]), str(state["audit_actor_id"]), int(row["id"])),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def rollback(reason: str = "manual") -> dict:
    value = {
        "contract_id": CONTRACT_ID, "mode": "ROLLBACK", "status": "FAIL",
        "production_write": True, "runtime_llm_tokens": 0,
        "started_at_utc": now_utc(), "reason": reason, "errors": [],
    }
    try:
        if not STATE.is_file():
            raise Task085Error("STATE_MISSING")
        state = json.loads(STATE.read_text(encoding="utf-8"))
        if state.get("contract_id") != CONTRACT_ID:
            raise Task085Error("STATE_CONTRACT_MISMATCH")
        restore_database(state)
        restore_files(state)
        reader = connect(True)
        try:
            rows = all_rows(reader)
            target = unique_row(rows, TARGET_CODE)
            quick = reader.execute("PRAGMA quick_check").fetchone()[0]
        finally:
            reader.close()
        if safe_target(target) != safe_target(state["target_preimage"]):
            raise Task085Error("ROW_ROLLBACK_MISMATCH")
        if protected_rows_digest(rows, int(target["id"])) != state["protected_rows_sha256"]:
            raise Task085Error("PROTECTED_ROWS_ROLLBACK_MISMATCH")
        value.update({"status": "PASS", "quick_check": quick,
                      "backup_root": state["backup_root"], "target": safe_target(target)})
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
    value["finished_at_utc"] = now_utc()
    atomic_json(RECEIPTS["rollback"], value)
    return value


def visible_text(source: str) -> str:
    source = re.sub(r"<(?:script|style)\b[^>]*>.*?</(?:script|style)\s*>", " ", source,
                    flags=re.I | re.S)
    source = re.sub(r"<[^>]+>", " ", source)
    return re.sub(r"\s+", " ", source).strip()


def inspect_detail(path: pathlib.Path) -> dict:
    if not path.is_file():
        raise Task085Error("DETAIL_MISSING:" + str(path))
    data = path.read_bytes()
    source = data.decode("utf-8", "replace")
    text = visible_text(source)
    bad_eta = any(value.casefold() in text.casefold() for value in OLD_ETA_VALUES)
    countdown = bool(re.search(
        r"\b\d{1,3}\s*(?:дн|дней|дня|дні|днів).*?(?:Киев|Київ|выдач|видач|прибыт|прибут)",
        text, re.I,
    ))
    checks = {
        "code": TARGET_CODE in source,
        "vin_suffix": "4289" in source,
        "photo": bool(re.search(r"<img\b[^>]*src=", source, re.I)),
        "korea": bool(re.search(r"Коре[яеиї]|Korea", text, re.I)),
        "container_absent": OLD_CONTAINER not in source and not re.search(
            r"Контейнер\s*:\s*[A-Z0-9]{6,}", text, re.I
        ),
        "eta_absent": not bad_eta and not countdown,
        "tracker_absent": "Отследить контейнер онлайн" not in text,
    }
    if not all(checks.values()):
        raise Task085Error("DETAIL_CONTRACT:%s:%s" % (
            path.parent.name, ",".join(key for key, ok in checks.items() if not ok)
        ))
    return {"path": str(path), "bytes": len(data), "sha256": sha_bytes(data), "checks": checks}


def card_blocks(source: str) -> dict[str, list[str]]:
    pattern = re.compile(
        r"<a\b(?=[^>]*href=[\"'][^\"']*(UA-[0-9]{4,})\.html(?:\?[^\"']*)?[\"'])"
        r"[^>]*>.*?</a\s*>", re.I | re.S,
    )
    result: dict[str, list[str]] = {}
    for match in pattern.finditer(source):
        result.setdefault(match.group(1).upper(), []).append(match.group(0))
    return result


def catalog_semantics(path: pathlib.Path) -> dict:
    if not path.is_file():
        raise Task085Error("CATALOG_MISSING:" + str(path))
    data = path.read_bytes()
    source = data.decode("utf-8", "replace")
    blocks = card_blocks(source)
    if len(blocks.get(TARGET_CODE, [])) != 1:
        raise Task085Error("UA0011_CATALOG_COUNT:%s:%d" % (
            path.parent.name, len(blocks.get(TARGET_CODE, []))
        ))
    if len(blocks.get(PROTECTED_CODE, [])) != 1:
        raise Task085Error("UA0009_CATALOG_COUNT:" + path.parent.name)
    block = blocks[TARGET_CODE][0]
    opening = re.match(r"<a\b[^>]*>", block, re.I | re.S).group(0)
    stage_ok = any(token in opening for token in (
        'data-ua-card-stage="korea"', "data-ua-card-stage='korea'",
        'data-stage="korea"', "data-stage='korea'",
        'data-ua-stage="1"', "data-ua-stage='1'",
    ))
    checks = {
        "stage_korea": stage_ok,
        "photo": bool(re.search(r"<img\b[^>]*src=", block, re.I)),
        "container_absent": OLD_CONTAINER not in block,
        "eta_absent": not any(value in block for value in OLD_ETA_VALUES),
    }
    if not all(checks.values()):
        raise Task085Error("CATALOG_CONTRACT:%s:%s" % (
            path.parent.name, ",".join(key for key, ok in checks.items() if not ok)
        ))
    semantic = {}
    for code, values in blocks.items():
        if len(values) == 1:
            item = values[0]
            opening_item = re.match(r"<a\b[^>]*>", item, re.I | re.S).group(0)
            image = re.search(r"<img\b[^>]*src=[\"']([^\"']+)", item, re.I)
            stage = re.search(r"data-(?:ua-card-stage|stage)=[\"']([^\"']+)", opening_item, re.I)
            semantic[code] = {
                "stage": stage.group(1) if stage else None,
                "photo": image.group(1) if image else None,
            }
    return {
        "path": str(path), "bytes": len(data), "sha256": sha_bytes(data),
        "card_count": len(blocks), "checks": checks, "semantic": semantic,
    }


def source_markers() -> dict[str, int]:
    result = {}
    for path in SOURCE_PATHS:
        result[path.name] = path.read_text(encoding="utf-8").count(MARKERS[path.name])
    return result


def database_check() -> dict:
    reader = connect(True)
    try:
        quick = reader.execute("PRAGMA quick_check").fetchone()[0]
        rows = all_rows(reader)
        target = unique_row(rows, TARGET_CODE)
        protected = unique_row(rows, PROTECTED_CODE)
        triggers = trigger_sql(reader)
    finally:
        reader.close()
    if quick != "ok":
        raise Task085Error("SQLITE_QUICK_CHECK:" + str(quick))
    if target.get("status") != EXPECTED_STATUS:
        raise Task085Error("UA0011_STATUS:" + str(target.get("status")))
    leaked = {
        field: target.get(field) for field in RESET_FIELDS
        if field in target and target.get(field) not in (None, "")
    }
    if leaked:
        raise Task085Error("UA0011_STAGE_PAYLOAD:" + json.dumps(leaked, ensure_ascii=False))
    if len(triggers) != 2:
        raise Task085Error("TRIGGER_COUNT:%d" % len(triggers))
    return {
        "quick_check": quick, "row_count": len(rows), "target": safe_target(target),
        "protected_ua0009": safe_target(protected), "triggers": sorted(triggers),
        "protected_rows_sha256": protected_rows_digest(rows, int(target["id"])),
        "target_business_sha256": target_business_digest(target),
        "target_media_sha256": media_digest(target),
    }


def postcheck(write_receipt: bool = True) -> dict:
    value = {
        "contract_id": CONTRACT_ID, "mode": "POSTCHECK", "status": "FAIL",
        "production_write": False, "crm_write": False, "media_write": False,
        "runtime_llm_tokens": 0, "started_at_utc": now_utc(), "errors": [],
    }
    try:
        database = database_check()
        markers = source_markers()
        if markers != {name: 1 for name in SOURCE_NAMES}:
            raise Task085Error("SOURCE_MARKERS:" + json.dumps(markers, sort_keys=True))
        if not LIVE_GUARD.is_file():
            raise Task085Error("LIVE_GUARD_MISSING")
        compile(LIVE_GUARD.read_text(encoding="utf-8"), str(LIVE_GUARD), "exec")
        details = {
            surface: inspect_detail(ROOT / surface / (TARGET_CODE + ".html"))
            for surface in ("video", "site")
        }
        catalogs = {
            surface: catalog_semantics(ROOT / surface / "katalog.html")
            for surface in ("video", "site")
        }
        value.update({"status": "PASS", "database": database, "markers": markers,
                      "details": details, "catalogs": catalogs})
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
    value["finished_at_utc"] = now_utc()
    if write_receipt:
        atomic_json(RECEIPTS["postcheck"], value)
    return value


def import_guard_from_upload():
    spec = importlib.util.spec_from_file_location("task085_uploaded_guard", UPLOADED_GUARD)
    if spec is None or spec.loader is None:
        raise Task085Error("GUARD_IMPORT_SPEC")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def shadow() -> dict:
    value = {
        "contract_id": CONTRACT_ID, "mode": "SHADOW", "status": "FAIL",
        "production_write": False, "crm_write": False, "media_write": False,
        "runtime_llm_tokens": 0, "started_at_utc": now_utc(), "errors": [],
    }
    try:
        candidates = prepare_sources()
        reader = connect(True)
        try:
            quick = reader.execute("PRAGMA quick_check").fetchone()[0]
            rows = all_rows(reader)
            target = unique_row(rows, TARGET_CODE)
            protected = unique_row(rows, PROTECTED_CODE)
            columns = [row[1] for row in reader.execute("PRAGMA table_info(cars)")]
        finally:
            reader.close()
        if quick != "ok" or target.get("status") != EXPECTED_STATUS:
            raise Task085Error("SHADOW_DATABASE_OR_STATUS")
        guard = import_guard_from_upload()
        projected = guard.public_projection(target)
        for field in RESET_FIELDS:
            if field in projected and projected.get(field) not in (None, ""):
                raise Task085Error("PROJECTION_LEAK:" + field)
        current_catalogs = {
            surface: catalog_semantics(ROOT / surface / "katalog.html")
            for surface in ("video", "site")
        }
        value.update({
            "status": "PASS",
            "database": {
                "quick_check": quick, "row_count": len(rows), "target": safe_target(target),
                "protected_ua0009": safe_target(protected), "columns": columns,
                "protected_rows_sha256": protected_rows_digest(rows, int(target["id"])),
                "target_business_sha256": target_business_digest(target),
                "target_media_sha256": media_digest(target),
            },
            "candidate_sources": {
                path.name: sha_bytes(data) for path, data in candidates.items()
            },
            "catalogs_before": current_catalogs,
            "projected_target": safe_target(projected),
        })
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
    value["finished_at_utc"] = now_utc()
    atomic_json(RECEIPTS["shadow"], value)
    return value


def install_sources(candidates: dict[pathlib.Path, bytes]) -> dict[str, str]:
    hashes = {}
    for path, data in candidates.items():
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
        if not path.exists() or path.read_bytes() != data:
            atomic_bytes(path, data, mode)
        if path.read_bytes() != data:
            raise Task085Error("SOURCE_READBACK:" + path.name)
        hashes[path.name] = sha_bytes(data)
    return hashes


def repair_database(state: dict) -> dict:
    guard = import_guard_from_upload()
    connection = connect(False)
    connection.execute("BEGIN IMMEDIATE")
    changed = {}
    try:
        rows = all_rows(connection)
        target = unique_row(rows, TARGET_CODE)
        if int(target["id"]) != int(state["target_id"]):
            raise Task085Error("TARGET_ID_DRIFT")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(cars)")}
        guard.install_korea_triggers(connection, columns)
        updates = {"status": EXPECTED_STATUS}
        for field in RESET_FIELDS:
            if field in columns:
                updates[field] = None
        for field, desired in updates.items():
            if target.get(field) != desired:
                changed[field] = {"before": target.get(field), "after": desired}
        if changed:
            assignments = ["status=?"] + [
                '"%s"=NULL' % field for field in RESET_FIELDS if field in columns
            ]
            if "updated_at" in columns:
                assignments.append("updated_at=?")
                params = [EXPECTED_STATUS, now_utc(), int(target["id"])]
            else:
                params = [EXPECTED_STATUS, int(target["id"])]
            connection.execute(
                "UPDATE cars SET %s WHERE id=?" % ", ".join(assignments), params
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    if changed:
        for name in ("db",):
            sys.modules.pop(name, None)
        importlib.invalidate_caches()
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import db
        for field, delta in changed.items():
            db.log_action(
                ACTOR_ID, "card_edit", "cars", int(state["target_id"]),
                field, delta["before"], delta["after"],
            )
    return {"changed": bool(changed), "fields": changed}


def publish_target() -> dict:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    for name in ("publikaciya", "stranica", "master_card", "cars_schema", "db"):
        sys.modules.pop(name, None)
    importlib.invalidate_caches()
    import publikaciya
    function = getattr(publikaciya, "opublikovat", None)
    if not callable(function):
        raise Task085Error("PUBLISHER_ENTRYPOINT_MISSING")
    result = function(TARGET_CODE)
    if isinstance(result, tuple):
        ok = result[0] is True
        detail = str(result[1]) if len(result) > 1 else ""
    else:
        ok = result is True
        detail = str(result)
    if not ok:
        raise Task085Error("PUBLISHER_FAILED:" + detail[:600])
    return {"status": "PASS", "detail": detail[:1000]}


def apply_release() -> dict:
    value = {
        "contract_id": CONTRACT_ID, "mode": "APPROVED_PRODUCTION_APPLY",
        "status": "FAIL", "production_write": False, "crm_write": False,
        "media_write": False, "runtime_llm_tokens": 0,
        "started_at_utc": now_utc(), "errors": [], "rollback": None,
    }
    state = None
    try:
        candidates = prepare_sources()
        reader = connect(True)
        try:
            quick = reader.execute("PRAGMA quick_check").fetchone()[0]
            rows = all_rows(reader)
            target = unique_row(rows, TARGET_CODE)
        finally:
            reader.close()
        if quick != "ok" or target.get("status") != EXPECTED_STATUS:
            raise Task085Error("PREWRITE_DATABASE_OR_STATUS")
        state = create_backup(rows, target)
        value["backup_root"] = state["backup_root"]
        value["before"] = safe_target(target)
        value["catalog_semantics_before"] = {
            surface: catalog_semantics(ROOT / surface / "katalog.html")["semantic"]
            for surface in ("video", "site")
        }
        value["source_sha256"] = install_sources(candidates)
        value["production_write"] = True
        value["crm_write"] = True
        value["database_repair"] = repair_database(state)
        value["publisher"] = publish_target()
        checked = postcheck(write_receipt=False)
        if checked.get("status") != "PASS":
            raise Task085Error("LOCAL_POSTCHECK:" + ";".join(checked.get("errors") or []))
        database = checked["database"]
        if database["protected_rows_sha256"] != state["protected_rows_sha256"]:
            raise Task085Error("PROTECTED_ROWS_CHANGED")
        if database["target_business_sha256"] != state["target_business_sha256"]:
            raise Task085Error("TARGET_BUSINESS_FIELDS_CHANGED")
        if database["target_media_sha256"] != state["target_media_sha256"]:
            raise Task085Error("TARGET_MEDIA_CHANGED")
        for surface in ("video", "site"):
            before = value["catalog_semantics_before"][surface]
            after = checked["catalogs"][surface]["semantic"]
            for code, semantic in before.items():
                if code != TARGET_CODE and after.get(code) != semantic:
                    raise Task085Error("CATALOG_OTHER_CARD_CHANGED:%s:%s" % (surface, code))
        value.update({"status": "PASS", "after": database["target"],
                      "postcheck": checked, "crm_write": bool(value["database_repair"]["changed"])})
        state["status"] = "PASS"
        state["finished_at_utc"] = now_utc()
        atomic_json(STATE, state)
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
        if state is not None:
            rolled = rollback("automatic_apply_failure")
            value["rollback"] = rolled
            value["status"] = "ROLLED_BACK" if rolled.get("status") == "PASS" else "BLOCKED"
    value["finished_at_utc"] = now_utc()
    atomic_json(RECEIPTS["apply"], value)
    return value


def run_mode(mode: str) -> dict:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        if mode == "shadow":
            return shadow()
        if mode == "apply":
            return apply_release()
        if mode == "postcheck":
            return postcheck()
        return rollback()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=sorted(RECEIPTS))
    args = parser.parse_args()
    try:
        value = run_mode(args.mode)
    except Exception as exc:
        value = {
            "contract_id": CONTRACT_ID, "mode": args.mode.upper(), "status": "FAIL",
            "runtime_llm_tokens": 0,
            "errors": [type(exc).__name__ + ":" + str(exc)],
            "traceback_tail": traceback.format_exc()[-5000:], "finished_at_utc": now_utc(),
        }
        atomic_json(RECEIPTS[args.mode], value)
    print(json.dumps({"mode": args.mode, "status": value.get("status"),
                      "errors": value.get("errors")}, ensure_ascii=False))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
