#!/usr/bin/env python3
"""Bounded PythonAnywhere executor for TASK 086.

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


CONTRACT_ID = "UA-0011-FERRY-STAGE-COUNTER-SYNC-006-V1.0"
TARGET_CODE = "UA-0011"
PROTECTED_CODE = "UA-0009"
EXPECTED_STATUS = "sea_loaded"
ALLOWED_PRE_STATUSES = ("kr_bought", "sea_loaded")
ACTOR_ID = 86006
ROOT = pathlib.Path("/home/Carix")
# The controller stages unique task086 files inside the already-existing,
# proven task083 inbox directory; production targets remain independently scoped.
TASK_ROOT = ROOT / "autopilot_inbox/cloud/task_083_catalog_dedup"
UPLOADED_GUARD = TASK_ROOT / "task086_stage_counter_guard.py"
LIVE_GUARD = ROOT / "stage_counter_guard.py"
STATE = TASK_ROOT / "task086_state.json"
LOCK = ROOT / ".ua_art_production_writer.lock"
DB_PATH = ROOT / "crm.db"
SOURCE_NAMES = (
    "db.py", "cars_ui.py", "stranica.py", "cars_schema.py", "publikaciya.py",
)
SOURCE_PATHS = tuple(ROOT / name for name in SOURCE_NAMES)
RECEIPTS = {
    "shadow": TASK_ROOT / "task086_shadow_receipt.json",
    "apply": TASK_ROOT / "task086_apply_receipt.json",
    "postcheck": TASK_ROOT / "task086_postcheck_receipt.json",
    "rollback": TASK_ROOT / "task086_rollback_receipt.json",
}
SEA_FIELDS = ("sea_container", "sea_date_out", "sea_port_from")
ETA_FIELDS = ("days_to_kyiv", "eta_manual")
LATER_FIELDS = ("ge_arrived", "ge_port", "ge_released", "ge_to_kyiv_at")
STAGE_FIELDS = SEA_FIELDS + ETA_FIELDS + LATER_FIELDS
MARKERS = {
    "db.py": "TASK086_FERRY_STAGE_COUNTER_DB_GUARD_V1",
    "cars_ui.py": "TASK086_STAGE_TRANSACTION_V1",
    "stranica.py": "TASK086_PUBLIC_PROJECTION_V1",
    "cars_schema.py": "TASK086_CRM_PROJECTION_V1",
    "publikaciya.py": "TASK086_CATALOG_COUNTER_TRANSACTION_V1",
}
MAX_FILE_BYTES = 16_000_000


class Task086Error(RuntimeError):
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
        raise Task086Error("CARD_COUNT_%s:%d" % (code, len(found)))
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
    ignored = set(STAGE_FIELDS) | {"status", "updated_at"}
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
        raise Task086Error("FUNCTION_MISSING_%s" % name)
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
    # TASK086_FERRY_STAGE_COUNTER_DB_GUARD_V1
    old = get_card(table, card_id)
    old_value = old.get(field) if old else None
    if table == "cars" and field == "status":
        import stage_counter_guard as _task086_guard
        if _task086_guard.stage_number(value) is not None:
            ok, detail = _task086_guard.apply_stage_transition_live(
                int(card_id), value, actor_id
            )
            if not ok:
                raise RuntimeError(detail)
            return
    with connect() as c:
        c.execute(f"UPDATE {table} SET {field}=?, updated_at=? WHERE id=?",
                  (value, now(), card_id))
    log_action(actor_id, "card_edit", table, card_id, field, old_value, value)
'''


def patch_db(source: str) -> str:
    marker = MARKERS["db.py"]
    if marker in source:
        if source.count(marker) != 1:
            raise Task086Error("DB_MARKER_COUNT")
        return source
    return _replace_function(source, "update_card_field", DB_REPLACEMENT)


def _inject_function_line(
    source: str, function_name: str, needle: str, insertion: str, marker: str
) -> str:
    if marker in source:
        if source.count(marker) != 1:
            raise Task086Error("MARKER_COUNT:" + marker)
        return source
    start, end, block = _function(source, function_name)
    if block.count(needle) != 1:
        raise Task086Error("ANCHOR_COUNT_%s:%d" % (function_name, block.count(needle)))
    block = block.replace(needle, insertion, 1)
    lines = source.splitlines(keepends=True)
    if not block.endswith("\n"):
        block += "\n"
    return "".join(lines[:start] + [block] + lines[end:])


def _inject_function_start(
    source: str, function_name: str, statements: tuple[str, ...], marker: str
) -> str:
    if marker in source:
        if source.count(marker) != 1:
            raise Task086Error("MARKER_COUNT:" + marker)
        return source
    tree = ast.parse(source)
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if not matches or not matches[-1].body:
        raise Task086Error("FUNCTION_BODY_MISSING:" + function_name)
    node = matches[-1]
    lines = source.splitlines(keepends=True)
    index = node.body[0].lineno - 1
    indent = re.match(r"\s*", lines[index]).group(0)
    injection = "".join(indent + line + "\n" for line in statements)
    return "".join(lines[:index] + [injection] + lines[index:])


def patch_cars_ui(source: str) -> str:
    marker = MARKERS["cars_ui.py"]
    if marker in source:
        if source.count(marker) != 1:
            raise Task086Error("CARS_UI_MARKER_COUNT")
        return source
    replacement = '''async def stage_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # TASK086_STAGE_TRANSACTION_V1
    import asyncio as _task086_asyncio
    import stage_counter_guard as _task086_guard
    q = update.callback_query
    await _v168_ack(q,)
    drop_wait(context)
    _, cid, code = q.data.split(":")
    cid = int(cid)
    ok, detail = await _task086_asyncio.to_thread(
        _task086_guard.apply_stage_transition_live,
        cid, code, q.from_user.id,
    )
    card = card_of(cid)
    rows = [[InlineKeyboardButton(
        "← Вернуться к карточке", callback_data="car_open:%d" % cid)]]
    if not ok:
        await q.message.reply_text(
            detail or "Этап не изменён. Прежние данные восстановлены.",
            reply_markup=InlineKeyboardMarkup(rows))
        raise ApplicationHandlerStop
    saved = card.get("status") if card else None
    if saved != code:
        await q.message.reply_text(
            "Публикация не подтверждена. Сейчас в карточке: %s"
            % S.status_label(saved), reply_markup=InlineKeyboardMarkup(rows))
        raise ApplicationHandlerStop
    lines = [
        card.get("auto_number") or "#%d" % cid,
        "Этап сохранён: %s" % S.status_label(saved),
        "Карточка, категория и верхние счётчики пересчитаны.",
    ]
    left, eta = eta_of(card)
    if left is not None:
        lines.append("До выдачи в Киеве: %d дней · %s" % (
            left, eta.strftime("%d.%m.%Y")))
    rows.insert(0, [InlineKeyboardButton(
        "🚚 Доставка и этапы", callback_data="car_stage:%d" % cid)])
    await q.message.reply_text("\\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))
    raise ApplicationHandlerStop
'''
    source = _replace_function(source, "stage_set", replacement)
    if "async def stage_menu" in source and 'code != "sea_transit"' not in source:
        anchor = "if stage_no == number]"
        if source.count(anchor) != 1:
            raise Task086Error("STAGE_MENU_LEGACY_ANCHOR:%d" % source.count(anchor))
        source = source.replace(anchor, 'if stage_no == number and code != "sea_transit"]', 1)
    return source


def patch_stranica(source: str) -> str:
    return _inject_function_start(
        source, "sobrat_kartochku", (
            "# TASK086_PUBLIC_PROJECTION_V1",
            "from stage_counter_guard import public_projection as _task086_project",
            "m = _task086_project(m)",
        ), MARKERS["stranica.py"],
    )


def patch_cars_schema(source: str) -> str:
    return _inject_function_start(
        source, "render_card", (
            "# TASK086_CRM_PROJECTION_V1",
            "from stage_counter_guard import public_projection as _task086_project",
            "car = _task086_project(car)",
        ), MARKERS["cars_schema.py"],
    )


def patch_publikaciya(source: str) -> str:
    marker = MARKERS["publikaciya.py"]
    if marker in source:
        if source.count(marker) != 1:
            raise Task086Error("PUBLISHER_MARKER_COUNT")
        return source
    start, end, block = _function(source, "opublikovat")
    master_anchor = "        html, diag, m = _master(kod)"
    if block.count(master_anchor) != 1:
        raise Task086Error("PUBLISHER_MASTER_ANCHOR:%d" % block.count(master_anchor))
    block = block.replace(
        master_anchor,
        master_anchor
        + "\n        if not diag:\n"
        + "            from stage_counter_guard import diagnostic_placeholder_html as _task086_diag\n"
        + "            diag = _task086_diag(kod)",
        1,
    )
    anchor = "    stalo = dict((put, _sha(put)) for put in celi)"
    if block.count(anchor) != 1:
        raise Task086Error("PUBLISHER_COMPLETION_ANCHOR:%d" % block.count(anchor))
    insertion = '''    # TASK086_CATALOG_COUNTER_TRANSACTION_V1
    try:
        from stage_counter_guard import rebuild_catalogs_live as _task086_rebuild
        _task086_ok, _task086_detail = _task086_rebuild()
    except Exception as _task086_exc:
        _task086_ok, _task086_detail = False, str(_task086_exc)
    if not _task086_ok:
        _otkat(papka_rez, celi)
        return False, "Публикация отменена: каталоги и счётчики не подтверждены (%s)." % _task086_detail

'''
    block = block.replace(anchor, insertion + anchor, 1)
    lines = source.splitlines(keepends=True)
    if not block.endswith("\n"):
        block += "\n"
    return "".join(lines[:start] + [block] + lines[end:])


PATCHERS = {
    "db.py": patch_db,
    "cars_ui.py": patch_cars_ui,
    "stranica.py": patch_stranica,
    "cars_schema.py": patch_cars_schema,
    "publikaciya.py": patch_publikaciya,
}


def prepare_sources() -> dict[pathlib.Path, bytes]:
    if not UPLOADED_GUARD.is_file():
        raise Task086Error("UPLOADED_GUARD_MISSING")
    guard_data = UPLOADED_GUARD.read_bytes()
    compile(guard_data.decode("utf-8"), str(LIVE_GUARD), "exec")
    result = {LIVE_GUARD: guard_data}
    for path in SOURCE_PATHS:
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            raise Task086Error("SOURCE_INVALID:" + path.name)
        source = path.read_text(encoding="utf-8")
        candidate = PATCHERS[path.name](source)
        compile(candidate, str(path), "exec")
        marker = MARKERS[path.name]
        if candidate.count(marker) != 1:
            raise Task086Error("CANDIDATE_MARKER:" + path.name)
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
        raise Task086Error("BACKUP_OUT_OF_SCOPE")
    if not path.exists():
        return {"path": str(path), "missing": True}
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise Task086Error("BACKUP_FILE_INVALID:" + str(path))
    data = path.read_bytes()
    target = backup / "files" / ("%03d__%s" % (index, path.name))
    atomic_bytes(target, data, path.stat().st_mode & 0o777)
    return {
        "path": str(path), "missing": False, "backup": str(target),
        "sha256": sha_bytes(data), "bytes": len(data),
        "mode": path.stat().st_mode & 0o777,
    }


LEGACY_TRIGGER_NAMES = (
    "ua_stage_payload_guard_korea_update_v1",
    "ua_stage_payload_guard_korea_insert_v1",
    "ua_stage_counter_guard_korea_update_v1",
    "ua_stage_counter_guard_korea_insert_v1",
)


def trigger_sql(connection: sqlite3.Connection) -> dict[str, str]:
    names = LEGACY_TRIGGER_NAMES
    rows = connection.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND name IN (?,?,?,?)",
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
    backup = TASK_ROOT / "task086_backups" / (
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
            raise Task086Error("RESTORE_OUT_OF_SCOPE")
        if item.get("missing"):
            path.unlink(missing_ok=True)
            continue
        data = pathlib.Path(item["backup"]).read_bytes()
        if sha_bytes(data) != item["sha256"]:
            raise Task086Error("BACKUP_HASH_MISMATCH:" + path.name)
        atomic_bytes(path, data, int(item.get("mode") or 0o644))


def restore_database(state: dict) -> None:
    row = state["target_preimage"]
    connection = connect(False)
    connection.execute("BEGIN IMMEDIATE")
    try:
        columns = {item[1] for item in connection.execute("PRAGMA table_info(cars)")}
        fields = [field for field in ("status",) + STAGE_FIELDS + ("updated_at",) if field in columns]
        assignments = ", ".join('"%s"=?' % field for field in fields)
        connection.execute(
            "UPDATE cars SET %s WHERE id=?" % assignments,
            [row.get(field) for field in fields] + [int(row["id"])],
        )
        for name in LEGACY_TRIGGER_NAMES:
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
            raise Task086Error("STATE_MISSING")
        state = json.loads(STATE.read_text(encoding="utf-8"))
        if state.get("contract_id") != CONTRACT_ID:
            raise Task086Error("STATE_CONTRACT_MISMATCH")
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
            raise Task086Error("ROW_ROLLBACK_MISMATCH")
        if protected_rows_digest(rows, int(target["id"])) != state["protected_rows_sha256"]:
            raise Task086Error("PROTECTED_ROWS_ROLLBACK_MISMATCH")
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


def inspect_detail(path: pathlib.Path, target: dict) -> dict:
    if not path.is_file():
        raise Task086Error("DETAIL_MISSING:" + str(path))
    data = path.read_bytes()
    source = data.decode("utf-8", "replace")
    text = visible_text(source)
    expected_container = str(target.get("sea_container") or "").strip()
    expected_eta = str(target.get("eta_manual") or "").strip()
    eta_variants = [expected_eta]
    try:
        parsed_eta = dt.date.fromisoformat(expected_eta[:10])
        eta_variants.append(parsed_eta.strftime("%d.%m.%Y"))
        eta_variants.extend([
            "%d %s %d" % (parsed_eta.day, (
                "января", "февраля", "марта", "апреля", "мая", "июня",
                "июля", "августа", "сентября", "октября", "ноября", "декабря",
            )[parsed_eta.month - 1], parsed_eta.year),
            "%d %s %d" % (parsed_eta.day, (
                "січня", "лютого", "березня", "квітня", "травня", "червня",
                "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
            )[parsed_eta.month - 1], parsed_eta.year),
        ])
    except Exception:
        pass
    checks = {
        "code": TARGET_CODE in source,
        "vin_suffix": "4289" in source,
        "photo": bool(re.search(r"<img\b[^>]*src=", source, re.I)),
        "own_cover": bool(re.search(r"foto/UA-0011/m/001\.jpg", source, re.I)),
        "ferry_label": bool(re.search(r"На\s+(?:пароме|поромі)", text, re.I)),
        "route": bool(re.search(r"Коре[яї].{0,160}Груз[иі]", text, re.I)),
        "lower_duplicate_absent": "автомобиль на пароме" not in text.casefold(),
        "container_preserved": not expected_container or expected_container in source,
        "eta_preserved": not expected_eta or any(value and value in source for value in eta_variants),
    }
    if not all(checks.values()):
        raise Task086Error("DETAIL_CONTRACT:%s:%s" % (
            path.parent.name, ",".join(key for key, ok in checks.items() if not ok)
        ))
    return {"path": str(path), "bytes": len(data), "sha256": sha_bytes(data), "checks": checks}


def card_blocks(source: str) -> dict[str, list[str]]:
    guard = import_guard_from_upload()
    result: dict[str, list[str]] = {}
    for code, _stage, block in guard.card_entries(source):
        result.setdefault(code, []).append(block)
    return result


def catalog_semantics(path: pathlib.Path, expected_more: bool = True) -> dict:
    if not path.is_file():
        raise Task086Error("CATALOG_MISSING:" + str(path))
    data = path.read_bytes()
    source = data.decode("utf-8", "replace")
    guard = import_guard_from_upload()
    entries = guard.card_entries(source)
    blocks: dict[str, list[str]] = {}
    for code, _stage, block in entries:
        blocks.setdefault(code, []).append(block)
    target_count = len(blocks.get(TARGET_CODE, []))
    if expected_more and target_count != 1:
        raise Task086Error("UA0011_CATALOG_COUNT:%s:%d" % (
            path.parent.name, target_count
        ))
    if not expected_more and target_count < 1:
        raise Task086Error("UA0011_CATALOG_MISSING:" + path.parent.name)
    protected_catalog_count = len(blocks.get(PROTECTED_CODE, []))
    target_entries = [entry for entry in entries if entry[0] == TARGET_CODE]
    block = target_entries[0][2]
    stage_ok = target_entries[0][1] == "more"
    checks = {
        "photo": bool(re.search(r"<img\b[^>]*src=", block, re.I)),
        "own_media": "UA-0011" in block,
    }
    if expected_more:
        checks.update({
            "stage_more": stage_ok,
            "not_korea_or_kiev": target_entries[0][1] not in ("korea", "kiev"),
        })
    if expected_more and not all(checks.values()):
        raise Task086Error("CATALOG_CONTRACT:%s:%s" % (
            path.parent.name, ",".join(key for key, ok in checks.items() if not ok)
        ))
    semantic = {}
    for code, values in blocks.items():
        matching = [entry for entry in entries if entry[0] == code]
        if len(matching) == 1:
            item = values[0]
            image = re.search(r"<img\b[^>]*src=[\"']([^\"']+)", item, re.I)
            semantic[code] = {
                "stage": matching[0][1],
                "photo": image.group(1) if image else None,
            }
    issues = []
    if expected_more:
        counts = guard.verify_catalog(source, TARGET_CODE, "more")
        chips = counts
    else:
        if not all(checks.values()):
            issues.append("preexisting_target:" + ",".join(
                key for key, ok in checks.items() if not ok
            ))
        try:
            counts = guard.catalog_counts(source)
        except Exception as exc:
            counts = {}
            issues.append("cards:" + str(exc))
        try:
            chips = guard.chip_counts(source)
        except Exception as exc:
            chips = {}
            issues.append("chips:" + str(exc))
        if counts != chips:
            issues.append("preexisting_counter_drift")
    return {
        "path": str(path), "bytes": len(data), "sha256": sha_bytes(data),
        "card_count": len(blocks), "checks": checks, "semantic": semantic,
        "visible_counts": counts, "chip_counts": chips,
        "preexisting_issues": issues, "target_count": target_count,
        "protected_ua0009_catalog_count": protected_catalog_count,
    }


def source_markers() -> dict[str, int]:
    result = {}
    for path in SOURCE_PATHS:
        result[path.name] = path.read_text(encoding="utf-8").count(MARKERS[path.name])
    return result


def canary_10(guard, candidates: dict[pathlib.Path, bytes], target: dict) -> dict:
    """Ten deterministic dry-runs: source patching, cleanup and count rebuild."""
    fixture = "".join([
        "<a class='chip' data-f='all'>Все <b>4</b></a>",
        "<a class='chip' data-f='korea'>Корея <b>1</b></a>",
        "<a class='chip' data-f='more'>Паром <b>1</b></a>",
        "<a class='chip' data-f='gruzia'>Грузия <b>1</b></a>",
        "<a class='chip' data-f='kiev'>Киев <b>1</b></a>",
        "<a data-ua-card-stage='korea' href='UA-0009.html'><img src='9.jpg'></a>",
        "<a data-ua-card-stage='more' href='UA-0011.html'><img src='11.jpg'></a>",
        "<a data-ua-card-stage='gruzia' href='UA-0012.html'><img src='12.jpg'></a>",
        "<a data-ua-card-stage='kiev' href='UA-0013.html'><img src='13.jpg'></a>",
    ])
    hashes = []
    for _index in range(10):
        guard.verify_catalog(fixture, TARGET_CODE, "more")
        cleanup = guard.cleanup_fields_for_transition(
            target.get("status"), EXPECTED_STATUS, target.keys()
        )
        candidate = dict(target)
        candidate["status"] = EXPECTED_STATUS
        for field in cleanup:
            candidate[field] = None
        patched = {}
        for path, data in candidates.items():
            if path.name in PATCHERS:
                text = PATCHERS[path.name](data.decode("utf-8"))
                if text.encode("utf-8") != data:
                    raise Task086Error("CANARY_PATCH_NOT_IDEMPOTENT:" + path.name)
                patched[path.name] = sha_bytes(data)
        hashes.append(stable({
            "candidate": safe_target(candidate),
            "sources": patched,
            "counts": guard.verify_catalog(fixture, TARGET_CODE, "more"),
        }))
    if len(set(hashes)) != 1:
        raise Task086Error("CANARY_HASH_DRIFT")
    return {"runs": 10, "stable": True, "sha256": hashes[0]}


def visual_preview(target: dict, guard) -> dict:
    """Render the ferry candidate entirely in memory; no production write."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    sys.modules.pop("stranica", None)
    importlib.invalidate_caches()
    import stranica

    candidate = dict(target)
    candidate["status"] = EXPECTED_STATUS
    for field in guard.cleanup_fields_for_transition(
        target.get("status"), EXPECTED_STATUS, target.keys()
    ):
        candidate[field] = None
    candidate = guard.public_projection(candidate)
    frames = stranica.kadry_mashiny(candidate)
    # Use the existing originals as the in-memory preview set.  Calling the
    # thumbnail generator in Gate A could create media files, which is forbidden.
    html = stranica.sobrat_kartochku(candidate, frames, frames)
    visible = visible_text(html)
    current_detail = (ROOT / "video" / (TARGET_CODE + ".html")).read_text(
        encoding="utf-8", errors="replace"
    )
    manifest = []
    for item in frames:
        raw = str(item).split("?", 1)[0]
        relative = raw.lstrip("/")
        path = ROOT / relative if relative.startswith("video/") else ROOT / "video" / relative
        entry = {"path": raw, "exists": path.is_file()}
        if path.is_file() and str(path.resolve()).startswith(str(ROOT.resolve()) + os.sep):
            data = path.read_bytes()
            entry.update({"bytes": len(data), "sha256": sha_bytes(data)})
        manifest.append(entry)
    checks = {
        "mobile_viewport_390": "width=device-width" in html,
        "desktop_viewport_1440": "<style" in html,
        "ferry_label": bool(re.search(r"На\s+(?:пароме|поромі)", visible, re.I)),
        "route": bool(re.search(r"Коре[яї].{0,160}Груз[иі]", visible, re.I)),
        "vin_4289": "4289" in html,
        "own_media": bool(re.search(r"foto/UA-0011/.+001\.(?:jpg|jpeg|png|webp)", html, re.I)),
        "current_verified_cover_m001": bool(re.search(
            r"foto/UA-0011/m/001\.jpg", current_detail, re.I
        )),
        "first_photo_is_cover": bool(frames) and bool(re.search(
            r"foto/UA-0011/.+001\.(?:jpg|jpeg|png|webp)", str(frames[0]), re.I
        )),
        "photo_count": len(frames) >= 1,
        "lower_duplicate_absent": "автомобиль на пароме" not in visible.casefold(),
    }
    if not all(checks.values()):
        raise Task086Error("VISUAL_PREVIEW:%s" % ",".join(
            key for key, ok in checks.items() if not ok
        ))
    return {
        "status": "PASS", "checks": checks, "html_sha256": sha_bytes(html.encode("utf-8")),
        "photo_count": len(frames), "viewports": [390, 1440],
        "media_manifest": manifest,
        "media_manifest_sha256": stable(manifest),
        "verified_cover_from_task084_sha256_prefix": "86850437",
    }


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
        raise Task086Error("SQLITE_QUICK_CHECK:" + str(quick))
    if target.get("status") != EXPECTED_STATUS:
        raise Task086Error("UA0011_STATUS:" + str(target.get("status")))
    leaked = {
        field: target.get(field) for field in LATER_FIELDS
        if field in target and target.get(field) not in (None, "")
    }
    if leaked:
        raise Task086Error("UA0011_LATER_STAGE_PAYLOAD:" + json.dumps(leaked, ensure_ascii=False))
    if triggers:
        raise Task086Error("LEGACY_KOREA_TRIGGERS:" + ",".join(sorted(triggers)))
    preserved = {}
    if STATE.is_file():
        state = json.loads(STATE.read_text(encoding="utf-8"))
        before = state.get("target_preimage") or {}
        for field in SEA_FIELDS + ETA_FIELDS + ("published",):
            if field in target and target.get(field) != before.get(field):
                raise Task086Error("PRESERVED_FIELD_CHANGED:" + field)
            if field in target:
                preserved[field] = target.get(field)
    return {
        "quick_check": quick, "row_count": len(rows), "target": safe_target(target),
        "protected_ua0009": safe_target(protected), "legacy_triggers": sorted(triggers),
        "preserved_sea_eta": preserved,
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
            raise Task086Error("SOURCE_MARKERS:" + json.dumps(markers, sort_keys=True))
        if not LIVE_GUARD.is_file():
            raise Task086Error("LIVE_GUARD_MISSING")
        compile(LIVE_GUARD.read_text(encoding="utf-8"), str(LIVE_GUARD), "exec")
        details = {
            surface: inspect_detail(
                ROOT / surface / (TARGET_CODE + ".html"), database["target"]
            )
            for surface in ("video", "site")
        }
        catalogs = {
            surface: catalog_semantics(ROOT / surface / "katalog.html")
            for surface in ("video", "site")
        }
        if catalogs["video"]["sha256"] != catalogs["site"]["sha256"]:
            raise Task086Error("CATALOG_SURFACES_DIVERGED")
        value.update({"status": "PASS", "database": database, "markers": markers,
                      "details": details, "catalogs": catalogs})
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
    value["finished_at_utc"] = now_utc()
    if write_receipt:
        atomic_json(RECEIPTS["postcheck"], value)
    return value


def import_guard_from_upload():
    spec = importlib.util.spec_from_file_location("task086_uploaded_guard", UPLOADED_GUARD)
    if spec is None or spec.loader is None:
        raise Task086Error("GUARD_IMPORT_SPEC")
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
        if quick != "ok" or target.get("status") not in ALLOWED_PRE_STATUSES:
            raise Task086Error("SHADOW_DATABASE_OR_STATUS")
        guard = import_guard_from_upload()
        projected = dict(target)
        projected["status"] = EXPECTED_STATUS
        for field in guard.cleanup_fields_for_transition(
            target.get("status"), EXPECTED_STATUS, target.keys()
        ):
            projected[field] = None
        projected = guard.public_projection(projected)
        for field in LATER_FIELDS:
            if field in projected and projected.get(field) not in (None, ""):
                raise Task086Error("PROJECTION_LEAK:" + field)
        for field in SEA_FIELDS + ETA_FIELDS:
            if field in target and projected.get(field) != target.get(field):
                raise Task086Error("PROJECTION_DROPPED_SEA_DATA:" + field)
        current_catalogs = {
            surface: catalog_semantics(
                ROOT / surface / "katalog.html", expected_more=False
            )
            for surface in ("video", "site")
        }
        db_files = {}
        for suffix in ("", "-wal", "-shm"):
            path = pathlib.Path(str(DB_PATH) + suffix)
            if path.is_file():
                data = path.read_bytes()
                db_files[path.name] = {"bytes": len(data), "sha256": sha_bytes(data)}
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
            "source_preimages": {
                path.name: sha_bytes(path.read_bytes()) for path in SOURCE_PATHS
            },
            "catalogs_before": current_catalogs,
            "database_files": db_files,
            "projected_target": safe_target(projected),
            "canary": canary_10(guard, candidates, target),
            "visual_preview": visual_preview(target, guard),
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
            raise Task086Error("SOURCE_READBACK:" + path.name)
        hashes[path.name] = sha_bytes(data)
    return hashes


def repair_database(state: dict) -> dict:
    connection = connect(False)
    connection.execute("BEGIN IMMEDIATE")
    changed = {}
    removed_triggers = []
    try:
        rows = all_rows(connection)
        target = unique_row(rows, TARGET_CODE)
        if int(target["id"]) != int(state["target_id"]):
            raise Task086Error("TARGET_ID_DRIFT")
        if target.get("status") not in ALLOWED_PRE_STATUSES:
            raise Task086Error("TARGET_STATUS_DRIFT:" + str(target.get("status")))
        columns = {row[1] for row in connection.execute("PRAGMA table_info(cars)")}
        updates = {"status": EXPECTED_STATUS}
        for field in LATER_FIELDS:
            if field in columns:
                updates[field] = None
        for field, desired in updates.items():
            if target.get(field) != desired:
                changed[field] = {"before": target.get(field), "after": desired}
        if changed:
            assignments = ['"%s"=?' % field for field in changed]
            params = [delta["after"] for delta in changed.values()]
            if "updated_at" in columns:
                assignments.append("updated_at=?")
                params.append(now_utc())
            params.append(int(target["id"]))
            connection.execute(
                "UPDATE cars SET %s WHERE id=?" % ", ".join(assignments), params
            )
        existing = trigger_sql(connection)
        for name in existing:
            connection.execute('DROP TRIGGER IF EXISTS "%s"' % name)
            removed_triggers.append(name)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    reader = connect(True)
    try:
        after = unique_row(all_rows(reader), TARGET_CODE)
    finally:
        reader.close()
    if after.get("status") != EXPECTED_STATUS:
        raise Task086Error("DATABASE_REPAIR_STATUS_READBACK")
    for field in LATER_FIELDS:
        if field in after and after.get(field) not in (None, ""):
            raise Task086Error("DATABASE_REPAIR_LATER_FIELD:" + field)
    for field in SEA_FIELDS + ETA_FIELDS + ("published",):
        if field in after and after.get(field) != state["target_preimage"].get(field):
            raise Task086Error("DATABASE_REPAIR_PRESERVE:" + field)
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
    return {
        "changed": bool(changed or removed_triggers), "fields": changed,
        "removed_legacy_triggers": sorted(removed_triggers),
    }


def publish_target() -> dict:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    for name in (
        "publikaciya", "stranica", "master_card", "cars_schema", "db",
        "stage_counter_guard",
    ):
        sys.modules.pop(name, None)
    importlib.invalidate_caches()
    import publikaciya
    function = getattr(publikaciya, "opublikovat", None)
    if not callable(function):
        raise Task086Error("PUBLISHER_ENTRYPOINT_MISSING")
    result = function(TARGET_CODE)
    if isinstance(result, tuple):
        ok = result[0] is True
        detail = str(result[1]) if len(result) > 1 else ""
    else:
        ok = result is True
        detail = str(result)
    if not ok:
        raise Task086Error("PUBLISHER_FAILED:" + detail[:600])
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
        if quick != "ok" or target.get("status") not in ALLOWED_PRE_STATUSES:
            raise Task086Error("PREWRITE_DATABASE_OR_STATUS")
        state = create_backup(rows, target)
        value["backup_root"] = state["backup_root"]
        value["before"] = safe_target(target)
        value["catalog_semantics_before"] = {
            surface: catalog_semantics(
                ROOT / surface / "katalog.html", expected_more=False
            )["semantic"]
            for surface in ("video", "site")
        }
        value["source_sha256"] = install_sources(candidates)
        value["production_write"] = True
        value["crm_write"] = True
        value["database_repair"] = repair_database(state)
        value["publisher"] = publish_target()
        checked = postcheck(write_receipt=False)
        if checked.get("status") != "PASS":
            raise Task086Error("LOCAL_POSTCHECK:" + ";".join(checked.get("errors") or []))
        database = checked["database"]
        if database["protected_rows_sha256"] != state["protected_rows_sha256"]:
            raise Task086Error("PROTECTED_ROWS_CHANGED")
        if database["target_business_sha256"] != state["target_business_sha256"]:
            raise Task086Error("TARGET_BUSINESS_FIELDS_CHANGED")
        if database["target_media_sha256"] != state["target_media_sha256"]:
            raise Task086Error("TARGET_MEDIA_CHANGED")
        for surface in ("video", "site"):
            before = value["catalog_semantics_before"][surface]
            after = checked["catalogs"][surface]["semantic"]
            for code, semantic in before.items():
                if code != TARGET_CODE and after.get(code) != semantic:
                    raise Task086Error("CATALOG_OTHER_CARD_CHANGED:%s:%s" % (surface, code))
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
