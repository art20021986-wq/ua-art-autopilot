#!/usr/bin/env python3
"""Atomic PythonAnywhere installer for TASK117 CRM stage-button removal."""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import os
import pathlib
import shutil
import stat
import tempfile
from typing import Any


TASK_ID = "TASK117-REMOVE-CRM-STAGE-BUTTONS"
CONTRACT = "UA-ART-CRM-STAGE-BUTTONS-REMOVE-001-V1.0"
ROOT = pathlib.Path("/home/Carix")
REMOTE_DIR = ROOT / "autopilot_inbox/cloud/task_068_ferry_vin"
RECEIPT = REMOTE_DIR / "task117_receipt.json"
STATE = REMOTE_DIR / "task117_state.json"
BACKUP_ROOT = REMOTE_DIR / "task117_backups"
TARGETS = (ROOT / "cars_ui.py", ROOT / "konteyner.py")
SCHEMA = ROOT / "cars_schema.py"
START_SAFE = ROOT / "start_safe.py"
HIDDEN = ("kr_bought", "sea_loaded", "sea_transit", "ua_handed")
HIDDEN_SET = frozenset(HIDDEN)
HIDDEN_LITERAL = "{'kr_bought', 'sea_loaded', 'sea_transit', 'ua_handed'}"
MARKER = "UA-ART-CRM-STAGE-BUTTONS-REMOVE-001-V1.0"
MAX_BYTES = 4 * 1024 * 1024
EXPECTED_BEFORE = {
    str(ROOT / "cars_ui.py"): "bb9b4d278df8ecffdc6a33160d1d32f6ef53bb03cb35c75cda255a3cbcaa8e0f",
    str(ROOT / "konteyner.py"): "56b8595de37fb46a7aad7ad10c494630ac31a3a84e2920a4a1d4bc495e971afa",
}
EXPECTED_AFTER = {
    str(ROOT / "cars_ui.py"): "2b1ef0bcfa700b7c87ccfb164b69b8ca173d460481936225e41344096c92062f",
    str(ROOT / "konteyner.py"): "72c03a1b8ab14279b2a2adbc681e112594d88c766d2aae7cc40e08b8aa004230",
}


class InstallError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def read_regular(path: pathlib.Path) -> tuple[bytes, int]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_nlink != 1:
        raise InstallError("UNSAFE_FILE:" + str(path))
    if info.st_size < 1 or info.st_size > MAX_BYTES:
        raise InstallError("FILE_SIZE:" + str(path))
    value = path.read_bytes()
    if len(value) != info.st_size:
        raise InstallError("FILE_RACE:" + str(path))
    return value, stat.S_IMODE(info.st_mode)


def fsync_dir(path: pathlib.Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: pathlib.Path, value: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=path.parent, delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        fsync_dir(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_receipt(value: dict[str, Any]) -> None:
    atomic_write(RECEIPT, canonical(value), 0o600)


def active_function(source: str, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(source)
    matches = [node for node in tree.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name == name]
    if not matches:
        raise InstallError("FUNCTION_MISSING:" + name)
    return max(matches, key=lambda node: node.lineno)


def function_text(source: str, name: str) -> str:
    node = active_function(source, name)
    lines = source.splitlines(keepends=True)
    return "".join(lines[node.lineno - 1:node.end_lineno])


def replace_in_active_function(source: str, name: str,
                               variants: tuple[tuple[str, str], ...], code: str) -> str:
    node = active_function(source, name)
    lines = source.splitlines(keepends=True)
    segment = "".join(lines[node.lineno - 1:node.end_lineno])
    matches = [(old, new) for old, new in variants if segment.count(old) == 1]
    if len(matches) != 1:
        raise InstallError(code + ":" + str(len(matches)))
    old, new = matches[0]
    segment = segment.replace(old, new, 1)
    lines[node.lineno - 1:node.end_lineno] = [segment]
    return "".join(lines)


def schema_statuses(source: str) -> dict[str, tuple[int, str]]:
    tree = ast.parse(source)
    values = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "STATUSES"
                for target in node.targets):
            values.append(ast.literal_eval(node.value))
    if len(values) != 1 or not isinstance(values[0], dict):
        raise InstallError("STATUSES_SHAPE")
    statuses = values[0]
    expected = {
        "kr_bought": "Выкуплено, на нашей парковке",
        "sea_loaded": "Загружено в контейнер",
        "sea_transit": "В пути",
        "ua_handed": "Передано клиенту",
    }
    for code, label in expected.items():
        item = statuses.get(code)
        if not isinstance(item, tuple) or len(item) != 2 or item[1] != label:
            raise InstallError("STATUS_HISTORY_MISSING:" + code)
    return statuses


def desired_cars_ui(source: str) -> bool:
    try:
        menu = function_text(source, "stage_menu")
        setter = function_text(source, "stage_set")
    except Exception:
        return False
    filtered = (
        "code not in _UA117_HIDDEN_STATUS_CODES" in menu
        or "code not in _UA116_HIDDEN_STATUS_CODES" in menu
        or all(code in menu for code in HIDDEN)
    )
    guarded = (
        "if code in _UA117_HIDDEN_STATUS_CODES:" in setter
        or "if code in _UA116_HIDDEN_STATUS_CODES:" in setter
    )
    blocker = (
        r"^car_setstage:\d+:(?:kr_bought|sea_loaded|sea_transit|ua_handed)$"
        in source and ("group=-100" in source or "group=-10" in source)
    )
    return filtered and guarded and blocker


def desired_konteyner(source: str) -> bool:
    try:
        menu = function_text(source, "gde_mashina")
    except Exception:
        return False
    return (
        "code not in _UA117_HIDDEN_STATUS_CODES" in menu
        or "code not in _UA116_HIDDEN_STATUS_CODES" in menu
        or all(code in menu for code in HIDDEN)
    )


def patch_cars_ui(source: str) -> str:
    compile(source, "cars_ui.py", "exec")
    if desired_cars_ui(source):
        return source
    if MARKER in source or "_UA117_HIDDEN_STATUS_CODES" in source:
        raise InstallError("CARS_UI_PARTIAL_PATCH")

    loop_variants = (
        (
            "for code, (stage_no, label) in S.STATUSES.items() if stage_no == number]",
            "for code, (stage_no, label) in S.STATUSES.items() if stage_no == number "
            "and code not in _UA117_HIDDEN_STATUS_CODES]",
        ),
        (
            "for code, (stage_no, label) in S.STATUSES.items()\n"
            "                if stage_no == number]",
            "for code, (stage_no, label) in S.STATUSES.items()\n"
            "                if stage_no == number and code not in _UA117_HIDDEN_STATUS_CODES]",
        ),
        (
            "for code, (stage_no, label) in S.STATUSES.items() if stage_no == number "
            "and code not in (\"sea_loaded\", \"sea_transit\")]",
            "for code, (stage_no, label) in S.STATUSES.items() if stage_no == number "
            "and code not in _UA117_HIDDEN_STATUS_CODES]",
        ),
    )
    source = replace_in_active_function(
        source, "stage_menu", loop_variants, "CARS_UI_STAGE_MENU_SHAPE")

    anchor = '    _, cid, code = q.data.split(":")\n    cid = int(cid)\n'
    guard = (
        anchor
        + "    if code in _UA117_HIDDEN_STATUS_CODES:\n"
        + "        await q.message.reply_text(\n"
        + "            \"Эта старая кнопка удалена. Данные не изменены.\",\n"
        + "            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(\n"
        + "                \"← К карточке\", callback_data=\"car_open:%d\" % cid)]]))\n"
        + "        raise ApplicationHandlerStop\n"
        + "    if code not in S.STATUSES:\n"
        + "        await q.message.reply_text(\"Неизвестный этап. Данные не изменены.\")\n"
        + "        raise ApplicationHandlerStop\n"
    )
    source = replace_in_active_function(
        source, "stage_set", ((anchor, guard),), "CARS_UI_STAGE_SET_SHAPE")
    if "group=-100" in source:
        raise InstallError("CARS_UI_GROUP_COLLISION")
    support = f'''\n\n# {MARKER}: cars_ui
_UA117_HIDDEN_STATUS_CODES = frozenset({HIDDEN_LITERAL})
_UA117_BASE_REGISTER = register

async def _ua117_block_removed_stage(update, context):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    await q.message.reply_text(
        "Эта старая кнопка удалена. Данные не изменены.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "← К карточке", callback_data="car_open:%s" % q.data.split(":")[1])]]))
    raise ApplicationHandlerStop

def register(app):
    _UA117_BASE_REGISTER(app)
    app.add_handler(CallbackQueryHandler(
        _ua117_block_removed_stage,
        pattern=r"^car_setstage:\\d+:(?:kr_bought|sea_loaded|sea_transit|ua_handed)$"),
        group=-100)
'''
    result = source.rstrip() + support
    compile(result, "cars_ui.py", "exec")
    if not desired_cars_ui(result):
        raise InstallError("CARS_UI_POSTCONDITION")
    return result


def patch_konteyner(source: str) -> str:
    compile(source, "konteyner.py", "exec")
    if desired_konteyner(source):
        return source
    if MARKER in source or "_UA117_HIDDEN_STATUS_CODES" in source:
        raise InstallError("KONTEYNER_PARTIAL_PATCH")
    variants = (
        (
            "if stage_no == nomer_etapa]",
            "if stage_no == nomer_etapa and code not in _UA117_HIDDEN_STATUS_CODES]",
        ),
        (
            "if stage_no == number]",
            "if stage_no == number and code not in _UA117_HIDDEN_STATUS_CODES]",
        ),
        (
            "if stage_no == nomer_etapa and code not in (\"sea_loaded\", \"sea_transit\")]",
            "if stage_no == nomer_etapa and code not in _UA117_HIDDEN_STATUS_CODES]",
        ),
    )
    source = replace_in_active_function(
        source, "gde_mashina", variants, "KONTEYNER_STAGE_MENU_SHAPE")
    result = (source.rstrip() + f"\n\n# {MARKER}: konteyner\n"
              + f"_UA117_HIDDEN_STATUS_CODES = frozenset({HIDDEN_LITERAL})\n")
    compile(result, "konteyner.py", "exec")
    if not desired_konteyner(result):
        raise InstallError("KONTEYNER_POSTCONDITION")
    return result


def verify_sources(cars: bytes, container: bytes, schema: bytes) -> dict[str, Any]:
    cars_text = cars.decode("utf-8")
    container_text = container.decode("utf-8")
    schema_text = schema.decode("utf-8")
    compile(cars_text, "cars_ui.py", "exec")
    compile(container_text, "konteyner.py", "exec")
    statuses = schema_statuses(schema_text)
    if not desired_cars_ui(cars_text) or not desired_konteyner(container_text):
        raise InstallError("MENU_POSTCONDITION")
    visible = [code for code in statuses if code not in HIDDEN_SET]
    if any(code in visible for code in HIDDEN) or len(visible) != len(statuses) - 4:
        raise InstallError("VISIBLE_STATUS_SET")
    return {
        "hidden_codes": list(HIDDEN),
        "visible_codes": visible,
        "schema_status_count": len(statuses),
        "old_callbacks": "BLOCKED_NO_WRITE",
        "primary_menu": "PASS",
        "fallback_menu": "PASS",
    }


def snapshot() -> dict[str, Any]:
    files = {}
    for path in TARGETS + (SCHEMA, START_SAFE):
        value, mode = read_regular(path)
        files[str(path)] = {"sha256": sha(value), "bytes": len(value), "mode": mode}
    return files


def load_state(expected_sha: str | None = None) -> dict[str, Any]:
    value, _ = read_regular(STATE)
    state_value = json.loads(value.decode("utf-8"))
    if state_value.get("task_id") != TASK_ID:
        raise InstallError("STATE_IDENTITY")
    if expected_sha and state_value.get("backup_manifest_sha256") != expected_sha:
        raise InstallError("BACKUP_IDENTITY")
    return state_value


def backup() -> dict[str, Any]:
    before = snapshot()
    for path, expected in EXPECTED_BEFORE.items():
        if before[path]["sha256"] != expected:
            raise InstallError("LIVE_PREIMAGE_MISMATCH:" + pathlib.Path(path).name)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = BACKUP_ROOT / stamp
    backup_dir.mkdir(parents=True, exist_ok=False)
    for path in TARGETS:
        value, mode = read_regular(path)
        target = backup_dir / path.name
        atomic_write(target, value, mode)
        copied, copied_mode = read_regular(target)
        expected = before[str(path)]
        if sha(copied) != expected["sha256"] or copied_mode != expected["mode"]:
            raise InstallError("BACKUP_READBACK:" + path.name)
    manifest = {
        "schema_version": "UA-ART-TASK117-BACKUP-1",
        "task_id": TASK_ID,
        "created_at": now(),
        "backup_dir": str(backup_dir),
        "files": before,
    }
    manifest_bytes = canonical(manifest)
    manifest_sha = sha(manifest_bytes)
    atomic_write(backup_dir / "manifest.json", manifest_bytes, 0o600)
    state_value = {
        "task_id": TASK_ID,
        "backup_dir": str(backup_dir),
        "backup_manifest_sha256": manifest_sha,
        "before": before,
        "status": "BACKED_UP",
    }
    atomic_write(STATE, canonical(state_value), 0o600)
    return {
        "task_id": TASK_ID, "contract_id": CONTRACT, "status": "PASS",
        "mode": "BACKUP", "backup": str(backup_dir),
        "backup_manifest_sha256": manifest_sha, "crm_write": False,
        "media_write": False, "site_write": False, "files": before,
        "unexpected_changes": 0,
    }


def _restore(state_value: dict[str, Any]) -> dict[str, str]:
    backup_dir = pathlib.Path(state_value["backup_dir"])
    restored = {}
    for path in TARGETS:
        meta = state_value["before"][str(path)]
        value, _ = read_regular(backup_dir / path.name)
        if sha(value) != meta["sha256"]:
            raise InstallError("BACKUP_CORRUPT:" + path.name)
        atomic_write(path, value, int(meta["mode"]))
        check, _ = read_regular(path)
        if sha(check) != meta["sha256"]:
            raise InstallError("RESTORE_READBACK:" + path.name)
        restored[str(path)] = sha(check)
    return restored


def install(expected_sha: str) -> dict[str, Any]:
    state_value = load_state(expected_sha)
    before_now = snapshot()
    if before_now != state_value["before"]:
        raise InstallError("LIVE_DRIFT_AFTER_BACKUP")
    cars, cars_mode = read_regular(TARGETS[0])
    container, container_mode = read_regular(TARGETS[1])
    schema, _ = read_regular(SCHEMA)
    patched_cars = patch_cars_ui(cars.decode("utf-8")).encode("utf-8")
    patched_container = patch_konteyner(container.decode("utf-8")).encode("utf-8")
    generated = {
        str(TARGETS[0]): sha(patched_cars),
        str(TARGETS[1]): sha(patched_container),
    }
    if generated != EXPECTED_AFTER:
        raise InstallError("CANDIDATE_HASH_MISMATCH")
    verify = verify_sources(patched_cars, patched_container, schema)
    try:
        atomic_write(TARGETS[0], patched_cars, cars_mode)
        atomic_write(TARGETS[1], patched_container, container_mode)
        current_cars, _ = read_regular(TARGETS[0])
        current_container, _ = read_regular(TARGETS[1])
        if current_cars != patched_cars or current_container != patched_container:
            raise InstallError("INSTALL_READBACK")
    except Exception:
        _restore(state_value)
        raise
    after = snapshot()
    for path, expected in EXPECTED_AFTER.items():
        if after[path]["sha256"] != expected:
            _restore(state_value)
            raise InstallError("INSTALLED_HASH_MISMATCH:" + pathlib.Path(path).name)
    protected = (SCHEMA, START_SAFE)
    for path in protected:
        if after[str(path)] != state_value["before"][str(path)]:
            _restore(state_value)
            raise InstallError("PROTECTED_FILE_CHANGED:" + path.name)
    state_value.update({
        "status": "INSTALLED", "after": after, "verify": verify,
    })
    atomic_write(STATE, canonical(state_value), 0o600)
    return {
        "task_id": TASK_ID, "contract_id": CONTRACT, "status": "PASS",
        "mode": "INSTALL", "backup": state_value["backup_dir"],
        "backup_manifest_sha256": expected_sha, "before": state_value["before"],
        "after": after, "verify": verify, "crm_write": False,
        "media_write": False, "site_write": False, "unexpected_changes": 0,
    }


def verify() -> dict[str, Any]:
    state_value = load_state()
    cars, _ = read_regular(TARGETS[0])
    container, _ = read_regular(TARGETS[1])
    schema, _ = read_regular(SCHEMA)
    proof = verify_sources(cars, container, schema)
    current = snapshot()
    expected = state_value.get("after")
    if state_value.get("status") != "INSTALLED" or current != expected:
        raise InstallError("POST_RESTART_DRIFT")
    for path, expected_sha in EXPECTED_AFTER.items():
        if current[path]["sha256"] != expected_sha:
            raise InstallError("POST_RESTART_HASH_MISMATCH:" + pathlib.Path(path).name)
    return {
        "task_id": TASK_ID, "contract_id": CONTRACT, "status": "PASS",
        "mode": "VERIFY", "backup_manifest_sha256":
            state_value["backup_manifest_sha256"],
        "files": current, "verify": proof, "crm_write": False,
        "media_write": False, "site_write": False, "unexpected_changes": 0,
    }


def rollback(expected_sha: str) -> dict[str, Any]:
    state_value = load_state(expected_sha)
    restored = _restore(state_value)
    current = snapshot()
    if current != state_value["before"]:
        raise InstallError("ROLLBACK_OR_PROTECTED_DRIFT")
    state_value.update({"status": "ROLLED_BACK", "restored": restored})
    atomic_write(STATE, canonical(state_value), 0o600)
    return {
        "task_id": TASK_ID, "contract_id": CONTRACT, "status": "PASS",
        "mode": "ROLLBACK", "backup_manifest_sha256": expected_sha,
        "restored_exact": True, "restored_sha256": restored,
        "protected_schema_matches_backup": True,
        "protected_start_safe_matches_backup": True,
        "crm_write": False, "media_write": False, "site_write": False,
        "unexpected_changes": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("backup", "install", "verify", "rollback"), required=True)
    parser.add_argument("--backup-manifest-sha256")
    args = parser.parse_args()
    value: dict[str, Any]
    try:
        if args.mode in ("install", "rollback"):
            if not args.backup_manifest_sha256 or len(args.backup_manifest_sha256) != 64:
                raise InstallError("BACKUP_SHA_REQUIRED")
        if args.mode == "backup":
            value = backup()
        elif args.mode == "install":
            value = install(args.backup_manifest_sha256)
        elif args.mode == "verify":
            value = verify()
        else:
            value = rollback(args.backup_manifest_sha256)
    except Exception as exc:
        value = {
            "task_id": TASK_ID, "contract_id": CONTRACT, "status": "FAIL",
            "mode": args.mode.upper(), "error": type(exc).__name__ + ":" + str(exc),
            "crm_write": False, "media_write": False, "site_write": False,
        }
    write_receipt(value)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
