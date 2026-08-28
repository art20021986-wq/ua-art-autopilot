#!/usr/bin/env python3
"""Fail-closed production installer for CRM-CONTAINER-KYIV-DAYS-001 v1.0."""
from __future__ import annotations

import ast
import asyncio
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import logging
import os
import pathlib
import re
import sqlite3
import sys
import tempfile
import time


CONTRACT = "CRM-CONTAINER-KYIV-DAYS-001-V1.0"
ROOT = pathlib.Path("/home/Carix")
SOURCE = ROOT / "konteyner.py"
CARS_UI = ROOT / "cars_ui.py"
DB_MODULE = ROOT / "db.py"
DATABASE = ROOT / "crm.db"
SAFE = ROOT / "autopilot_inbox" / "cloud" / "task_069"
BACKUP_PARENT = SAFE / "backups"
SHADOW_RECEIPT = SAFE / "gate_b_shadow_receipt.json"
INSTALL_RECEIPT = SAFE / "gate_b_install_receipt.json"
ROLLBACK_RECEIPT = SAFE / "gate_b_rollback_receipt.json"
SHARED_LOCK = ROOT / ".task066_stage_anchor.lock"
TASK_LOCK = ROOT / ".task069_container.lock"

TARGET_CARD = "UA-0011"
TARGET_CONTAINER = "ONEYSELGF1046602"
MINIMUM_CARD_IDS = ["UA-%04d" % value for value in range(1, 12)]
LABEL = "⏱ Количество дней до Киева"
MAX_SOURCE = 3_000_000
MAX_DATABASE = 128_000_000


class GateBlocked(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_bytes(path: pathlib.Path, limit: int) -> bytes:
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if not data:
        raise GateBlocked("EMPTY_FILE:" + path.name)
    if len(data) > limit:
        raise GateBlocked("FILE_TOO_LARGE:" + path.name)
    return data


def fsync_dir(directory: pathlib.Path) -> None:
    descriptor = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: pathlib.Path, data: bytes, mode: int = 0o600) -> None:
    if not data:
        raise GateBlocked("REFUSE_EMPTY_WRITE:" + path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=str(path.parent), prefix="." + path.name + ".", suffix=".tmp"
    )
    temporary = pathlib.Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict) -> None:
    atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


@contextlib.contextmanager
def deployment_locks():
    handles = []
    try:
        for path in (SHARED_LOCK, TASK_LOCK):
            handle = path.open("a+")
            handles.append(handle)
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise GateBlocked("CONCURRENT_PRODUCTION_GATE:" + path.name) from exc
        yield
    finally:
        for handle in reversed(handles):
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            handle.close()


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise GateBlocked("%s_MATCH_COUNT_%d" % (label, count))
    return source.replace(old, new, 1)


def function_hashes(source: str) -> dict[str, list[str]]:
    tree = ast.parse(source)
    lines = source.splitlines()
    result: dict[str, list[str]] = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = "\n".join(lines[node.lineno - 1:node.end_lineno])
            result.setdefault(node.name, []).append(sha(body.encode("utf-8")))
    return result


def function_sources(source: str) -> dict[str, list[str]]:
    tree = ast.parse(source)
    lines = source.splitlines()
    result: dict[str, list[str]] = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result.setdefault(node.name, []).append(
                "\n".join(lines[node.lineno - 1:node.end_lineno])
            )
    return result


def patch_source(original: str) -> str:
    candidate = original
    functions = function_sources(candidate)
    if len(functions.get("_ekran", [])) != 1:
        raise GateBlocked("CENTRAL_SCREEN_DEFINITION_COUNT")
    if LABEL not in functions["_ekran"][0]:
        candidate = replace_once(
            candidate,
            '        [InlineKeyboardButton("Дни до прибытия",\n'
            '                              callback_data="cont_days:%d" % cid)],',
            '        [InlineKeyboardButton("⏱ Количество дней до Киева",\n'
            '                              callback_data="car_setf:%d:eta_days" % cid)],',
            "CENTRAL_DAYS_BUTTON",
        )

    functions = function_sources(candidate)
    if len(functions.get("posle_statusa", [])) != 1:
        raise GateBlocked("STATUS_PROMPT_DEFINITION_COUNT")
    if LABEL not in functions["posle_statusa"][0]:
        candidate = replace_once(
            candidate,
            '                [InlineKeyboardButton("Ввести дату отправления",\n'
            '                                      callback_data="cont_date:%d" % cid)],\n'
            '                [InlineKeyboardButton("Пропустить",',
            '                [InlineKeyboardButton("Ввести дату отправления",\n'
            '                                      callback_data="cont_date:%d" % cid)],\n'
            '                [InlineKeyboardButton("⏱ Количество дней до Киева",\n'
            '                                      callback_data="car_setf:%d:eta_days" % cid)],\n'
            '                [InlineKeyboardButton("Пропустить",',
            "STATUS_PROMPT_DAYS_BUTTON",
        )

    functions = function_sources(candidate)
    if len(functions.get("prinyat", [])) != 1:
        raise GateBlocked("PRINYAT_DEFINITION_COUNT")
    handler = functions["prinyat"][0]
    if "✅ Контейнер сохранён: %s" not in handler:
        # Original UA-V172 handler: move wait cleanup behind verified read-back.
        original_write = (
            '    context.user_data.pop("cont_wait", None)\n'
            '    do = _karta(cid) or {}\n'
            '    try:\n'
            '        _pisat(cid, pole, znachenie, kto)'
        )
        original_readback = (
            '    posle = _karta(cid) or {}          # повторное чтение из базы\n'
            '    stalo = (posle.get(pole) or "").strip()\n'
            '    if pole == "sea_container":\n'
            '        podpis = "Номер контейнера сохранён: %s" % (stalo or "—")'
        )
        if original_write in candidate and original_readback in candidate:
            candidate = replace_once(
                candidate,
                original_write,
                '    do = _karta(cid) or {}\n'
                '    try:\n'
                '        _pisat(cid, pole, znachenie, kto)',
                "WAIT_CLEAR_BEFORE_WRITE",
            )
            candidate = replace_once(
                candidate,
                original_readback,
                '    posle = _karta(cid) or {}          # повторное чтение из базы\n'
                '    stalo = str(posle.get(pole) or "").strip()\n'
                '    ozhidaemoe = str(znachenie).strip()\n'
                '    if stalo != ozhidaemoe:\n'
                '        log.warning("konteyner: read-back mismatch %s expected=%r actual=%r",\n'
                '                    pole, ozhidaemoe, stalo)\n'
                '        await msg.reply_text(\n'
                '            "Не удалось подтвердить сохранение. Повторите ввод.",\n'
                '            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(\n'
                '                "Отмена", callback_data="cont_menu:%d" % cid)]]))\n'
                '        raise ApplicationHandlerStop\n'
                '    context.user_data.pop("cont_wait", None)\n'
                '    if pole == "sea_container":\n'
                '        podpis = "✅ Контейнер сохранён: %s" % stalo',
                "READ_BACK_GATE",
            )
        # CRM-ONLINE-GUARD v1.3 handler already has durable queue + read-back.
        elif (
            '        podpis = "Номер контейнера сохранён: %s" % stalo' in candidate
            and 'context.user_data["cont_wait"] = wait' in handler
            and 'result.get("queued")' in handler
        ):
            candidate = replace_once(
                candidate,
                '        podpis = "Номер контейнера сохранён: %s" % stalo',
                '        podpis = "✅ Контейнер сохранён: %s" % stalo',
                "DURABLE_HANDLER_SUCCESS_MESSAGE",
            )
        else:
            raise GateBlocked("UNRECOGNIZED_CONTAINER_HANDLER")
    return candidate


def run_handler_synthetic(candidate: str) -> dict:
    functions = function_sources(candidate)
    source = functions.get("prinyat", [])
    if len(source) != 1:
        raise GateBlocked("PRINYAT_DEFINITION_COUNT")

    class Stop(Exception):
        pass

    class Button:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class Markup:
        def __init__(self, value):
            self.value = value

    class Message:
        def __init__(self, text: str):
            self.text = text
            self.sent = []

        async def reply_text(self, text: str, **kwargs):
            self.sent.append(str(text))

    class Context:
        def __init__(self):
            self.user_data = {"cont_wait": {"card_id": 18, "field": "sea_container"}}

    class Update:
        def __init__(self, text: str):
            self.effective_message = Message(text)
            self.effective_user = type("User", (), {"id": 1})()

    namespace = {
        "re": re,
        "time": time,
        "OBRAZEC_NOMERA": re.compile(r"^[A-Z0-9]{4,20}$"),
        "InlineKeyboardButton": Button,
        "InlineKeyboardMarkup": Markup,
        "ApplicationHandlerStop": Stop,
        "log": logging.getLogger("task069-synthetic"),
        "_v_iso": lambda _value: "",
        "_krasivo": lambda value: value,
        "_peresobrat": lambda: None,
        "_ekran": lambda card: ("CARD:" + str(card.get("sea_container") or ""), None),
    }
    exec(compile("from __future__ import annotations\n" + source[0], "<task069-prinyat>", "exec"), namespace)
    handler = namespace["prinyat"]

    async def accepted_case(initial: str, write: bool) -> tuple[dict, Context, Update]:
        state = {
            "id": 18,
            "auto_number": TARGET_CARD,
            "sea_container": initial,
            "sea_date_out": "",
            "eta_manual": "",
        }
        namespace["_karta"] = lambda _cid: dict(state)

        def writer(_cid, field, value, _actor):
            if write:
                state[field] = value

        namespace["_pisat"] = writer
        context = Context()
        update = Update("oney selgf-1046602")
        try:
            await handler(update, context)
        except Stop:
            pass
        return state, context, update

    state, context, update = asyncio.run(accepted_case("", True))
    if state["sea_container"] != TARGET_CONTAINER:
        raise GateBlocked("SYNTHETIC_NORMALIZATION_FAILED")
    if "cont_wait" in context.user_data:
        raise GateBlocked("SYNTHETIC_WAIT_NOT_CLEARED")
    if not update.effective_message.sent or not update.effective_message.sent[-1].startswith(
        "✅ Контейнер сохранён: " + TARGET_CONTAINER
    ):
        raise GateBlocked("SYNTHETIC_SUCCESS_MESSAGE_FAILED")

    _state, mismatch_context, mismatch_update = asyncio.run(accepted_case("", False))
    if "cont_wait" not in mismatch_context.user_data:
        raise GateBlocked("SYNTHETIC_MISMATCH_DROPPED_WAIT")
    if not any(
        ("Не удалось подтвердить сохранение" in value or "Запись не подтверждена" in value)
        for value in mismatch_update.effective_message.sent
    ):
        raise GateBlocked("SYNTHETIC_MISMATCH_NOT_REPORTED")

    namespace["_karta"] = lambda _cid: {
        "id": 18, "auto_number": TARGET_CARD, "sea_container": "",
        "sea_date_out": "", "eta_manual": "",
    }
    namespace["_pisat"] = lambda *_args: (_ for _ in ()).throw(GateBlocked("INVALID_INPUT_WROTE"))
    invalid_context = Context()
    invalid_update = Update("???")
    try:
        asyncio.run(handler(invalid_update, invalid_context))
    except Stop:
        pass
    if "cont_wait" not in invalid_context.user_data:
        raise GateBlocked("SYNTHETIC_INVALID_DROPPED_WAIT")
    if not any("Это не похоже" in value for value in invalid_update.effective_message.sent):
        raise GateBlocked("SYNTHETIC_INVALID_NOT_REJECTED")

    idempotent_state, _, _ = asyncio.run(accepted_case(TARGET_CONTAINER, True))
    if idempotent_state["sea_container"] != TARGET_CONTAINER:
        raise GateBlocked("SYNTHETIC_IDEMPOTENCY_FAILED")
    durable_queue_preserved = True
    if 'result.get("queued")' in source[0]:
        namespace["_karta"] = lambda _cid: {
            "id": 18, "auto_number": TARGET_CARD, "sea_container": "",
            "sea_date_out": "", "eta_manual": "",
        }
        namespace["_pisat"] = lambda *_args: {"queued": True}
        queued_context = Context()
        queued_update = Update(TARGET_CONTAINER)
        try:
            asyncio.run(handler(queued_update, queued_context))
        except Stop:
            pass
        if "cont_wait" in queued_context.user_data:
            raise GateBlocked("SYNTHETIC_DURABLE_QUEUE_WAIT_NOT_CLEARED")
        if not any("надёжной очереди" in value for value in queued_update.effective_message.sent):
            raise GateBlocked("SYNTHETIC_DURABLE_QUEUE_CONFIRMATION")
    return {
        "valid_normalized": True,
        "readback_failure_keeps_wait": True,
        "invalid_rejected": True,
        "idempotent": True,
        "durable_queue_preserved": durable_queue_preserved,
        "llm_tokens": 0,
    }


def validate_candidate(source_data: bytes) -> tuple[bytes, dict]:
    source_hash = sha(source_data)
    source_text = source_data.decode("utf-8")
    compile(source_text, str(SOURCE), "exec")
    candidate_text = patch_source(source_text)
    candidate_data = candidate_text.encode("utf-8")
    before = function_hashes(source_text)
    after = function_hashes(candidate_text)
    changed_functions = sorted(
        name for name in set(before) | set(after) if before.get(name) != after.get(name)
    )
    allowed = {"_ekran", "posle_statusa", "prinyat"}
    if not set(changed_functions).issubset(allowed):
        raise GateBlocked("UNEXPECTED_CHANGED_FUNCTIONS:" + ",".join(changed_functions))
    already_applied = not changed_functions
    if not candidate_data or len(candidate_data) > MAX_SOURCE:
        raise GateBlocked("CANDIDATE_SIZE_INVALID")
    candidate_text = candidate_data.decode("utf-8")
    compile(candidate_text, str(SOURCE), "exec")
    functions = function_sources(candidate_text)
    for name in ("_ekran", "posle_statusa", "prinyat"):
        if len(functions.get(name, [])) != 1:
            raise GateBlocked("EXPECTED_FUNCTION_COUNT:" + name)
    central = functions["_ekran"][0]
    prompt = functions["posle_statusa"][0]
    handler = functions["prinyat"][0]
    if central.count(LABEL) != 1 or prompt.count(LABEL) != 1:
        raise GateBlocked("BUTTON_LABEL_COUNT")
    if central.count("car_setf:%d:eta_days") != 1 or prompt.count("car_setf:%d:eta_days") != 1:
        raise GateBlocked("BUTTON_ROUTE_COUNT")
    if "cont_days:%d" in central:
        raise GateBlocked("LEGACY_DAYS_ROUTE_VISIBLE")
    direct_wait_safe = (
        'context.user_data.pop("cont_wait", None)' in handler
        and "if stalo != ozhidaemoe" in handler
        and handler.index('context.user_data.pop("cont_wait", None)')
        > handler.index("if stalo != ozhidaemoe")
    )
    durable_wait_safe = (
        'context.user_data["cont_wait"] = wait' in handler
        and 'result.get("queued")' in handler
        and "if stalo != str(znachenie)" in handler
    )
    if not (direct_wait_safe or durable_wait_safe):
        raise GateBlocked("WAIT_READBACK_CONTRACT")
    if "✅ Контейнер сохранён: %s" not in handler:
        raise GateBlocked("HANDLER_READBACK_CONTRACT")

    cars_ui_data = read_bytes(CARS_UI, MAX_SOURCE)
    db_module_data = read_bytes(DB_MODULE, MAX_SOURCE)
    cars_ui_source = cars_ui_data.decode("utf-8")
    compile(cars_ui_source, str(CARS_UI), "exec")
    ui_functions = function_sources(cars_ui_source)
    apply_value = ui_functions.get("apply_value", [""])[0]
    edit_ask = ui_functions.get("edit_ask", [""])[0]
    register = ui_functions.get("register", [""])[-1]
    eta_of = ui_functions.get("eta_of", [""])[0]
    route_checks = {
        "eta_days_branch": 'field == "eta_days"' in apply_value,
        "range_0_400": "if n > 400" in apply_value,
        "stores_eta_manual": 'set_field(card_id, "eta_manual"' in apply_value,
        "stores_days_to_kyiv": 'set_field(card_id, "days_to_kyiv"' in apply_value,
        "eta_prompt": 'field == "eta_days"' in edit_ask,
        "callback_registered": 'pattern=r"^car_setf:"' in register,
        "manual_eta_priority": 'manual = card.get("eta_manual")' in eta_of,
    }
    if not all(route_checks.values()):
        raise GateBlocked("EXISTING_DAYS_ROUTE_INVALID:" + json.dumps(route_checks, sort_keys=True))
    synthetic = run_handler_synthetic(candidate_text)
    return candidate_data, {
        "source_sha256": source_hash,
        "candidate_sha256": sha(candidate_data),
        "already_applied": already_applied,
        "changed_functions": changed_functions,
        "button_label_occurrences": 2,
        "route_checks": route_checks,
        "handler_synthetic": synthetic,
        "protected_source_sha256": {
            "cars_ui.py": sha(cars_ui_data),
            "db.py": sha(db_module_data),
        },
    }


def json_value(value):
    if isinstance(value, bytes):
        return {"bytes_sha256": sha(value), "size": len(value)}
    return value


def row_digest(rows: list[dict]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha(payload.encode("utf-8"))


def db_snapshot() -> dict:
    connection = sqlite3.connect("file:%s?mode=ro" % DATABASE, uri=True, timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=15000")
        quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        columns = [str(row[1]) for row in connection.execute("PRAGMA table_info(cars)")]
        required = {"id", "auto_number", "sea_container", "updated_at"}
        if not required.issubset(columns):
            raise GateBlocked("CARS_SCHEMA_MISSING:" + ",".join(sorted(required - set(columns))))
        rows = [
            {key: json_value(row[key]) for key in row.keys()}
            for row in connection.execute("SELECT * FROM cars ORDER BY id")
        ]
    finally:
        connection.close()
    if quick != "ok":
        raise GateBlocked("SQLITE_QUICK_CHECK:" + quick)
    cards = [row for row in rows if re.fullmatch(r"UA-\d{4}", str(row.get("auto_number") or ""))]
    card_ids = sorted(str(row["auto_number"]) for row in cards)
    if len(card_ids) != len(set(card_ids)) or not set(MINIMUM_CARD_IDS).issubset(card_ids):
        raise GateBlocked("CARD_SET_CHANGED:" + ",".join(card_ids))
    targets = [row for row in rows if str(row.get("auto_number") or "") == TARGET_CARD]
    if len(targets) != 1:
        raise GateBlocked("TARGET_CARD_COUNT_%d" % len(targets))
    target = targets[0]
    target_id = int(target["id"])
    owners = [
        {"id": int(row["id"]), "auto_number": str(row.get("auto_number") or "")}
        for row in rows
        if str(row.get("sea_container") or "").strip().upper() == TARGET_CONTAINER
    ]
    current = str(target.get("sea_container") or "").strip().upper()
    if current not in ("", TARGET_CONTAINER):
        raise GateBlocked("TARGET_ALREADY_HAS_OTHER_CONTAINER:" + current)
    protected_rows = []
    for row in rows:
        copy = dict(row)
        if int(copy["id"]) == target_id:
            copy["sea_container"] = "<TASK069_ALLOWED>"
            copy["updated_at"] = "<TASK069_ALLOWED>"
        protected_rows.append(copy)
    return {
        "quick_check": quick,
        "row_count": len(rows),
        "card_ids": card_ids,
        "rows_sha256": row_digest(rows),
        "protected_rows_sha256": row_digest(protected_rows),
        "target": {
            "id": target_id,
            "auto_number": TARGET_CARD,
            "sea_container": current or None,
            "updated_at": target.get("updated_at"),
        },
        "container_owners": owners,
    }


def backup_database(destination: pathlib.Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect("file:%s?mode=ro" % DATABASE, uri=True, timeout=30)
    target = sqlite3.connect(str(destination), timeout=30)
    try:
        source.backup(target)
        target.commit()
        if str(target.execute("PRAGMA quick_check").fetchone()[0]) != "ok":
            raise GateBlocked("BACKUP_DB_QUICK_CHECK")
    finally:
        target.close()
        source.close()
    with destination.open("rb") as handle:
        os.fsync(handle.fileno())
    fsync_dir(destination.parent)


def restore_database(source_path: pathlib.Path) -> None:
    source = sqlite3.connect("file:%s?mode=ro" % source_path, uri=True, timeout=30)
    target = sqlite3.connect(str(DATABASE), timeout=30)
    try:
        source.backup(target)
        target.commit()
    finally:
        target.close()
        source.close()
    with DATABASE.open("rb") as handle:
        os.fsync(handle.fileno())
    fsync_dir(DATABASE.parent)


def write_target_container(target_id: int) -> bool:
    before = db_snapshot()
    if before["target"]["id"] != target_id:
        raise GateBlocked("TARGET_CHANGED_DURING_INSTALL")
    if before["target"]["sea_container"] == TARGET_CONTAINER:
        return False
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import importlib
    db_runtime = importlib.import_module("db")
    result = db_runtime.update_card_field(
        "cars", int(target_id), "sea_container", TARGET_CONTAINER, 0
    )
    deadline = time.monotonic() + (12 if isinstance(result, dict) and result.get("queued") else 3)
    last = None
    while time.monotonic() < deadline:
        last = db_snapshot()
        if last["target"]["sea_container"] == TARGET_CONTAINER:
            return True
        time.sleep(0.25)
    raise GateBlocked("TARGET_READBACK_MISMATCH_AFTER_PRODUCTION_PATH")


def create_backup(source_data: bytes, before_db: dict, candidate_data: bytes) -> tuple[pathlib.Path, dict]:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = BACKUP_PARENT / (stamp + "-" + sha(candidate_data)[:12])
    backup_root.mkdir(parents=True, mode=0o700, exist_ok=False)
    source_backup = backup_root / "konteyner.py"
    database_backup = backup_root / "crm.db"
    atomic_write(source_backup, source_data, SOURCE.stat().st_mode & 0o777)
    backup_database(database_backup)
    manifest = {
        "contract_id": CONTRACT,
        "created_at_utc": utc_now(),
        "source": {
            "path": str(SOURCE),
            "backup": str(source_backup),
            "sha256": sha(source_data),
        },
        "database": {
            "path": str(DATABASE),
            "backup": str(database_backup),
            "backup_sha256": sha(read_bytes(database_backup, MAX_DATABASE)),
            "snapshot": before_db,
        },
        "candidate_sha256": sha(candidate_data),
    }
    atomic_json(backup_root / "manifest.json", manifest)
    return backup_root, manifest


def validated_manifest(backup_root: pathlib.Path) -> dict:
    resolved_parent = BACKUP_PARENT.resolve()
    resolved = backup_root.resolve()
    if resolved.parent != resolved_parent:
        raise GateBlocked("BACKUP_PATH_OUTSIDE_ALLOWLIST")
    manifest_path = resolved / "manifest.json"
    value = json.loads(read_bytes(manifest_path, 1_000_000).decode("utf-8"))
    if value.get("contract_id") != CONTRACT:
        raise GateBlocked("BACKUP_CONTRACT_MISMATCH")
    source_backup = pathlib.Path(value["source"]["backup"])
    database_backup = pathlib.Path(value["database"]["backup"])
    if source_backup.parent.resolve() != resolved or database_backup.parent.resolve() != resolved:
        raise GateBlocked("BACKUP_FILE_OUTSIDE_ROOT")
    if sha(read_bytes(source_backup, MAX_SOURCE)) != value["source"]["sha256"]:
        raise GateBlocked("SOURCE_BACKUP_HASH_MISMATCH")
    if sha(read_bytes(database_backup, MAX_DATABASE)) != value["database"]["backup_sha256"]:
        raise GateBlocked("DATABASE_BACKUP_HASH_MISMATCH")
    return value


def rollback_backup(backup_root: pathlib.Path, *, source_write: bool, db_write: bool) -> dict:
    manifest = validated_manifest(backup_root)
    restored = []
    if source_write:
        source_backup = pathlib.Path(manifest["source"]["backup"])
        atomic_write(SOURCE, read_bytes(source_backup, MAX_SOURCE), SOURCE.stat().st_mode & 0o777)
        if sha(read_bytes(SOURCE, MAX_SOURCE)) != manifest["source"]["sha256"]:
            raise GateBlocked("SOURCE_ROLLBACK_READBACK")
        restored.append("konteyner.py")
    if db_write:
        database_backup = pathlib.Path(manifest["database"]["backup"])
        restore_database(database_backup)
        after = db_snapshot()
        expected = manifest["database"]["snapshot"]
        if after["rows_sha256"] != expected["rows_sha256"]:
            raise GateBlocked("DATABASE_ROLLBACK_ROWS_MISMATCH")
        restored.append("crm.db")
    return {"status": "PASS", "restored": restored, "backup_root": str(backup_root)}


def shadow() -> dict:
    with deployment_locks():
        source_data = read_bytes(SOURCE, MAX_SOURCE)
        candidate_data, candidate = validate_candidate(source_data)
        database = db_snapshot()
    return {
        "contract_id": CONTRACT,
        "mode": "SHADOW",
        "status": "PASS",
        "production_write": False,
        "crm_db_write": False,
        "service_reload": False,
        "candidate": candidate,
        "database": database,
        "target_container": TARGET_CONTAINER,
        "runtime_llm_tokens": 0,
    }


def install() -> dict:
    receipt = {
        "contract_id": CONTRACT,
        "mode": "PRODUCTION_GATE_B",
        "status": "BLOCKED",
        "started_at_utc": utc_now(),
        "production_write": False,
        "source_write": False,
        "crm_db_write": False,
        "backup_root": "",
        "errors": [],
        "rollback": None,
        "runtime_llm_tokens": 0,
    }
    backup_root = None
    try:
        with deployment_locks():
            source_data = read_bytes(SOURCE, MAX_SOURCE)
            candidate_data, candidate = validate_candidate(source_data)
            before_db = db_snapshot()
            backup_root, manifest = create_backup(source_data, before_db, candidate_data)
            receipt["backup_root"] = str(backup_root)
            receipt["backup_manifest_sha256"] = sha(
                read_bytes(backup_root / "manifest.json", 1_000_000)
            )
            receipt["candidate"] = candidate
            receipt["database_before"] = before_db

            # Revalidate every guarded input immediately before the first write.
            if read_bytes(SOURCE, MAX_SOURCE) != source_data:
                raise GateBlocked("CONCURRENT_SOURCE_CHANGE_BEFORE_WRITE")
            recheck_db = db_snapshot()
            if recheck_db["rows_sha256"] != before_db["rows_sha256"]:
                raise GateBlocked("CONCURRENT_DB_CHANGE_BEFORE_WRITE")
            shadow_receipt = json.loads(read_bytes(SHADOW_RECEIPT, 2_000_000).decode("utf-8"))
            if shadow_receipt.get("contract_id") != CONTRACT or shadow_receipt.get("status") != "PASS":
                raise GateBlocked("SHADOW_RECEIPT_NOT_PASS")
            shadow_candidate = shadow_receipt.get("candidate") or {}
            shadow_database = shadow_receipt.get("database") or {}
            if candidate.get("source_sha256") != shadow_candidate.get("source_sha256"):
                raise GateBlocked("SOURCE_CHANGED_AFTER_SHADOW")
            if candidate.get("candidate_sha256") != shadow_candidate.get("candidate_sha256"):
                raise GateBlocked("CANDIDATE_CHANGED_AFTER_SHADOW")
            if candidate.get("protected_source_sha256") != shadow_candidate.get("protected_source_sha256"):
                raise GateBlocked("PROTECTED_SOURCE_CHANGED_AFTER_SHADOW")
            if before_db.get("rows_sha256") != shadow_database.get("rows_sha256"):
                raise GateBlocked("DATABASE_CHANGED_AFTER_SHADOW")

            if sha(read_bytes(CARS_UI, MAX_SOURCE)) != candidate["protected_source_sha256"]["cars_ui.py"]:
                raise GateBlocked("CONCURRENT_CARS_UI_CHANGE")
            if sha(read_bytes(DB_MODULE, MAX_SOURCE)) != candidate["protected_source_sha256"]["db.py"]:
                raise GateBlocked("CONCURRENT_DB_MODULE_CHANGE")

            if source_data != candidate_data:
                atomic_write(SOURCE, candidate_data, SOURCE.stat().st_mode & 0o777)
                receipt["source_write"] = True
                receipt["production_write"] = True
                if read_bytes(SOURCE, MAX_SOURCE) != candidate_data:
                    raise GateBlocked("SOURCE_READBACK_MISMATCH")

            target_needs_write = before_db["target"]["sea_container"] != TARGET_CONTAINER
            if target_needs_write:
                # Mark before invoking the production DB path so every partial
                # or queued failure restores the full consistent backup.
                receipt["crm_db_write"] = True
                receipt["production_write"] = True
            changed = write_target_container(before_db["target"]["id"])
            if changed != target_needs_write:
                raise GateBlocked("TARGET_WRITE_STATE_MISMATCH")
            after_db = db_snapshot()
            receipt["database_after"] = after_db
            if after_db["target"]["sea_container"] != TARGET_CONTAINER:
                raise GateBlocked("TARGET_CONTAINER_NOT_PERSISTED")
            if after_db["protected_rows_sha256"] != before_db["protected_rows_sha256"]:
                raise GateBlocked("UNEXPECTED_CRM_CARD_CHANGE")
            if sha(read_bytes(SOURCE, MAX_SOURCE)) != candidate["candidate_sha256"]:
                raise GateBlocked("SOURCE_POSTWRITE_HASH")
            if sha(read_bytes(CARS_UI, MAX_SOURCE)) != candidate["protected_source_sha256"]["cars_ui.py"]:
                raise GateBlocked("CARS_UI_POSTWRITE_HASH")
            if sha(read_bytes(DB_MODULE, MAX_SOURCE)) != candidate["protected_source_sha256"]["db.py"]:
                raise GateBlocked("DB_MODULE_POSTWRITE_HASH")
            receipt["status"] = "PASS"
    except Exception as exc:
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc))
        if backup_root is not None and (receipt["source_write"] or receipt["crm_db_write"]):
            try:
                receipt["rollback"] = rollback_backup(
                    backup_root,
                    source_write=receipt["source_write"],
                    db_write=receipt["crm_db_write"],
                )
                receipt["status"] = "ROLLED_BACK"
            except Exception as rollback_exc:
                receipt["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )
                receipt["status"] = "BLOCKED"
    receipt["finished_at_utc"] = utc_now()
    return receipt


def explicit_rollback() -> dict:
    install_receipt = json.loads(read_bytes(INSTALL_RECEIPT, 2_000_000).decode("utf-8"))
    if install_receipt.get("contract_id") != CONTRACT:
        raise GateBlocked("INSTALL_RECEIPT_CONTRACT")
    backup_root = pathlib.Path(str(install_receipt.get("backup_root") or ""))
    with deployment_locks():
        result = rollback_backup(
            backup_root,
            source_write=bool(install_receipt.get("source_write")),
            db_write=bool(install_receipt.get("crm_db_write")),
        )
    return {"contract_id": CONTRACT, "mode": "ROLLBACK", **result, "runtime_llm_tokens": 0}


def main() -> int:
    SAFE.mkdir(parents=True, exist_ok=True)
    if "--shadow" in sys.argv:
        path = SHADOW_RECEIPT
        try:
            value = shadow()
        except Exception as exc:
            value = {
                "contract_id": CONTRACT,
                "mode": "SHADOW",
                "status": "BLOCKED",
                "production_write": False,
                "crm_db_write": False,
                "errors": [type(exc).__name__ + ":" + str(exc)],
                "runtime_llm_tokens": 0,
            }
    elif "--rollback" in sys.argv:
        path = ROLLBACK_RECEIPT
        try:
            value = explicit_rollback()
        except Exception as exc:
            value = {
                "contract_id": CONTRACT,
                "mode": "ROLLBACK",
                "status": "BLOCKED",
                "errors": [type(exc).__name__ + ":" + str(exc)],
                "runtime_llm_tokens": 0,
            }
    else:
        path = INSTALL_RECEIPT
        value = install()
    atomic_json(path, value)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
