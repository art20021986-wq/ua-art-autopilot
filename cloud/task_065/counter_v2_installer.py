#!/usr/bin/env python3
"""Fail-closed installer for CRM-PHOTO-COUNTER-002."""
from __future__ import annotations

import ast
import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import stat
import sys
import tempfile


BASE = pathlib.Path("/home/Carix")
CARS_UI = BASE / "cars_ui.py"
CRM_DB = BASE / "crm.db"
SAFE = BASE / "autopilot_inbox" / "cloud" / "task_065"
BACKUPS = BASE / "backups" / "task_065_counter_v2"
INSTALL_RECEIPT = SAFE / "counter_v2_install_receipt.json"
ROLLBACK_RECEIPT = SAFE / "counter_v2_rollback_receipt.json"
EXPECTED_CARS_SHA = "a7da33f7a653a0cef697aad784e5c29bc2600639eb48b272793d61f1ac0e2af5"
MARKER = "CRM-PHOTO-COUNTER-002"
VOICE_MARKER = "CRM-VOICE-FIELDS-003"
STAGE_MARKER = "UA-CARDS-STAGE-ANCHOR-001-V1.1"
EXPECTED_TARGET_SHAS = {
    "_v165_spool_drain": "7b131cf2ec1f85eed8c07c17762efaca73520d705b7ed4dad3319a838006996a",
    "_v165_status": "b161a2b91b43d1e85979a5d15e29f2fe33e2b4b95a8828a96b65aad81801d13e",
    "_v165_progress_job": "37fb964f56d51e0b7357695b2a1d60b903422d0440dd7ca2451fdd0c005b8441",
    "_v165_schedule_progress": "45a35f1c866e3897d0f16b76147468870f7b3899c01e44d4ba6d09aa5a17f52a",
    "catch_message": "e8d274e671f7cea58f82d463e301f784e457c5981e89a59ec1f3a25f52255e4a",
}
DEPLOY_LOCK = BASE / ".task066_stage_anchor.lock"


NEW_DRAIN = r'''def _v166_drain_owned(max_items=100):
    """Drain while the one global drain lock is owned."""
    _v165_rows = _v165_read_rows()[:max(1, int(max_items))]
    _v165_done = []
    _v165_error = ""
    for _v165_row in _v165_rows:
        try:
            _v165_card = card_of(_v165_row["card_id"])
            if not _v165_card:
                _v165_error = "card unavailable"
                continue
            _v165_answer = save_media(
                _v165_card,
                _v165_row["target"],
                _v165_row["file_id"],
                _v165_row["actor_id"],
                _v165_row.get("tag", ""),
            )
            if _v165_answer and any(_v165_word in str(_v165_answer).casefold()
                                    for _v165_word in ("не принят", "не проверен")):
                _v165_error = str(_v165_answer)[:160]
                continue
            _v165_done.append(_v165_row["key"])
        except Exception as _v165_exc:
            _v165_error = "%s: %s" % (type(_v165_exc).__name__, _v165_exc)
            if "locked" in str(_v165_exc).casefold() or "busy" in str(_v165_exc).casefold():
                break
    _v165_spool_remove(_v165_done)
    return {"processed": len(_v165_done),
            "remaining": len(_v165_read_rows()),
            "error": _v165_error, "busy": False}


def _v165_spool_drain(max_items=100):
    """Exactly one worker may mutate card media at a time."""
    import fcntl as _v166_fcntl
    with open(_V165_DRAIN_LOCK, "a+", encoding="utf-8") as _v166_guard:
        try:
            _v166_fcntl.flock(
                _v166_guard.fileno(), _v166_fcntl.LOCK_EX | _v166_fcntl.LOCK_NB)
        except BlockingIOError:
            return {"processed": 0, "remaining": len(_v165_read_rows()),
                    "error": "", "busy": True}
        try:
            return _v166_drain_owned(max_items)
        finally:
            _v166_fcntl.flock(_v166_guard.fileno(), _v166_fcntl.LOCK_UN)
'''


NEW_STATUS = r'''def _v165_status(card_id, target, session_ids=None):
    _v165_rows = [row for row in _v165_read_rows()
                  if row.get("card_id") == int(card_id)
                  and row.get("target") == str(target)]
    _v166_session = {str(value) for value in (session_ids or []) if value}
    try:
        _v165_saved = _v165_media_ids(card_of(card_id), target)
        _v165_saved_set = set(_v165_saved)
        _v165_saved_count = len(_v165_saved_set)
        _v165_all = set(_v165_saved_set)
        _v165_all.update(row.get("file_id") for row in _v165_rows)
        _v165_accepted = len([value for value in _v165_all if value])
        _v166_session_saved = len(_v165_saved_set & _v166_session)
    except Exception:
        _v165_saved_count = None
        _v165_accepted = len({row.get("file_id") for row in _v165_rows
                              if row.get("file_id")})
        _v166_session_saved = None
    _v166_queued_ids = {str(row.get("file_id")) for row in _v165_rows
                        if row.get("file_id")}
    return {"accepted": _v165_accepted,
            "saved": _v165_saved_count,
            "queued": len(_v165_rows),
            "limit": _v165_limit(target),
            "session_saved": _v166_session_saved,
            "session_queued": len(_v166_queued_ids & _v166_session)}
'''


NEW_PROGRESS = r'''async def _v165_progress_job(context):
    import asyncio as _v165_asyncio
    _v165_data = context.job.data
    _v165_status_now = None
    for _v166_attempt in range(12):
        _v165_status_now = await _v165_asyncio.to_thread(
            _v165_status, _v165_data["card_id"], _v165_data["target"],
            _v165_data.get("session_ids") or [])
        if _v165_status_now["queued"] == 0:
            break
        await _v165_asyncio.sleep(0.35)
    if _v165_status_now["saved"] is None:
        _v165_text = "Фото принято: %d · очередь: %d." % (
            _v165_status_now["accepted"], _v165_status_now["queued"])
    else:
        _v166_added = _v165_status_now.get("session_saved")
        _v165_text = "Добавлено сейчас: %d · всего: %d/%d · очередь: %d." % (
            int(_v166_added or 0), _v165_status_now["saved"],
            _v165_status_now["limit"], _v165_status_now["queued"])
    await context.bot.send_message(
        chat_id=_v165_data["chat_id"],
        text=_v165_text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "Открыть карточку",
            callback_data="car_open:%d" % _v165_data["card_id"])]]),
    )
'''


NEW_SCHEDULE = r'''def _v165_schedule_progress(context, msg, card_id, target, session_ids):
    _v165_key_value = "%s:%s:%s" % (msg.chat_id, int(card_id), str(target))
    _v165_old = _V165_PROGRESS.get(_v165_key_value)
    if _v165_old is not None:
        try:
            _v165_old.schedule_removal()
        except Exception:
            pass
    if context.job_queue:
        _V165_PROGRESS[_v165_key_value] = context.job_queue.run_once(
            _v165_progress_job,
            when=1.2,
            data={"chat_id": msg.chat_id, "card_id": int(card_id),
                  "target": str(target), "session_ids": list(session_ids)},
            name="crm-photo-progress-" + _v165_key_value,
        )
'''


VOICE_HELPER = r'''# CRM-VOICE-FIELDS-003: deterministic explicit fields supplement AI parsing.
def _v167_voice_explicit_fields(text, allowed):
    import re as _v167_re
    _v167_text = str(text or "").casefold().replace("ё", "е")
    _v167_result = {}
    _v167_allowed = set(allowed or [])

    _v167_lpi = _v167_re.search(
        r"(?<![a-zа-я0-9])(?:l\s*p\s*i|л\s*п\s*и|эл\s*пи\s*ай)(?![a-zа-я0-9])",
        _v167_text)
    _v167_lpg = _v167_re.search(
        r"(?<![a-zа-я0-9])(?:l\s*p\s*g|л\s*п\s*г|эл\s*пи\s*джи|газ)(?![a-zа-я0-9])",
        _v167_text)
    if "fuel" in _v167_allowed:
        if _v167_lpi:
            _v167_result["fuel"] = "LPI"
        elif _v167_lpg:
            _v167_result["fuel"] = "LPG"

    _v167_engine = _v167_re.search(
        r"(?:объ?ем(?:\s+двигателя)?|двигател[ья]|мотор[а]?|engine)"
        r"\s*(?:[:=\-–—]|составляет)?\s*(\d+(?:[.,]\d+)?)",
        _v167_text)
    if _v167_engine and "engine_cc" in _v167_allowed:
        try:
            _v167_number = float(_v167_engine.group(1).replace(",", "."))
            _v167_cc = int(round(_v167_number * 1000 if _v167_number < 20 else _v167_number))
            if 400 <= _v167_cc <= 12000:
                _v167_result["engine_cc"] = _v167_cc
        except Exception:
            pass

    _v167_colors = {
        "бел": "белый", "черн": "чёрный", "сер": "серый",
        "серебр": "серебристый", "красн": "красный", "син": "синий",
        "голуб": "голубой", "зелен": "зелёный", "желт": "жёлтый",
        "беж": "бежевый", "корич": "коричневый", "white": "белый",
        "black": "чёрный", "silver": "серебристый", "gray": "серый",
        "grey": "серый",
    }
    _v167_color = _v167_re.search(
        r"(?:(?:цвет|color)\s*(?:[:=\-–—]|автомобиля|машины)?\s*([a-zа-я]+)|"
        r"([a-zа-я]+)\s+(?:цвет|color))", _v167_text)
    if _v167_color and "color" in _v167_allowed:
        _v167_word = next((value for value in _v167_color.groups() if value), "")
        for _v167_prefix, _v167_value in _v167_colors.items():
            if _v167_word.startswith(_v167_prefix):
                _v167_result["color"] = _v167_value
                break
    return _v167_result
'''


OLD_CATCH_PHOTO = r'''        if msg.photo:
            file_id = msg.photo[-1].file_id
            if target in ("photos", "condition_photos"):
                _v165_spool_enqueue(wait["card_id"], target, file_id, user_id, tag)
                _v165_schedule_progress(context, msg, wait["card_id"], target)
                raise ApplicationHandlerStop
'''


NEW_CATCH_PHOTO = r'''        if msg.photo:
            file_id = msg.photo[-1].file_id
            if target in ("photos", "condition_photos"):
                _v166_result = _v165_spool_enqueue(
                    wait["card_id"], target, file_id, user_id, tag)
                _v166_session_ids = wait.setdefault("_fast_session_ids", [])
                if (_v166_result.get("state") != "limit"
                        and file_id not in _v166_session_ids):
                    _v166_session_ids.append(file_id)
                _v165_schedule_progress(
                    context, msg, wait["card_id"], target, _v166_session_ids)
                raise ApplicationHandlerStop
'''


OLD_VOICE_OVERRIDE = r'''            folded = input_text.casefold()
            override = any(word in folded for word in (
                "измени", "исправь", "замени", "поменяй", "скорректируй"))
            changes, skipped = voice_change_plan(card, data, allowed, override)
'''


NEW_VOICE_OVERRIDE = r'''            folded = input_text.casefold()
            explicit_data = _v167_voice_explicit_fields(input_text, allowed)
            data.update(explicit_data)
            # CRM-VOICE-FIELDS-003: voice is an explicit command for the open card.
            # Text keeps the conservative keyword rule; voice may replace named values.
            override = bool(voice_object) or any(word in folded for word in (
                "измени", "исправь", "замени", "поменяй", "скорректируй"))
            changes, skipped = voice_change_plan(card, data, allowed, override)
'''


class InstallError(RuntimeError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: pathlib.Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=path.parent, delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value):
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def db_snapshot():
    con = sqlite3.connect("file:%s?mode=ro" % CRM_DB, uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        quick = con.execute("PRAGMA quick_check").fetchone()[0]
        count = con.execute("SELECT COUNT(*) FROM cars").fetchone()[0]
        rows = [dict(row) for row in con.execute(
            "SELECT * FROM cars WHERE auto_number IN ('UA-0009','UA-0011') ORDER BY auto_number,id")]
    finally:
        con.close()
    return {"quick_check": quick, "cars_count": count,
            "protected_sha256": sha(json.dumps(
                rows, ensure_ascii=False, sort_keys=True, default=str).encode())}


def replace_definition(source: str, name: str, replacement: str) -> str:
    tree = ast.parse(source)
    nodes = [node for node in tree.body if isinstance(
        node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(nodes) != 1:
        raise InstallError("TARGET_INVALID:" + name)
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [replacement.rstrip() + "\n\n"]
    return "".join(lines)


def insert_before_definition(source: str, name: str, addition: str) -> str:
    node, _ = find_definition(source, name)
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.lineno - 1] = [addition.rstrip() + "\n\n\n"]
    return "".join(lines)


def validate(source: str):
    required = (MARKER, VOICE_MARKER, "_V165_DRAIN_LOCK", "LOCK_NB", "_v166_drain_owned",
                "_v167_voice_explicit_fields",
                "session_saved", "Добавлено сейчас", 'wait.setdefault("_fast_session_ids"')
    if any(value not in source for value in required):
        raise InstallError("COUNTER_V2_CONTRACT_MISSING")
    _, drain = find_definition(source, "_v165_spool_drain")
    _, progress = find_definition(source, "_v165_progress_job")
    _, catch = find_definition(source, "catch_message")
    if ("LOCK_NB" not in drain or "_v165_spool_drain" in progress
            or "override = bool(voice_object)" not in catch
            or "explicit_data = _v167_voice_explicit_fields" not in catch):
        raise InstallError("SINGLE_DRAIN_CONTRACT_INVALID")
    compile(source, "cars_ui.counter-v2", "exec")


def find_definition(source: str, name: str):
    tree = ast.parse(source)
    nodes = [node for node in tree.body if isinstance(
        node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(nodes) != 1:
        raise InstallError("TARGET_INVALID:" + name)
    return nodes[0], ast.get_source_segment(source, nodes[0]) or ""


def validate_input_baseline(source: str):
    current_sha = sha(source.encode())
    if current_sha != EXPECTED_CARS_SHA and STAGE_MARKER not in source:
        raise InstallError("CARS_SOURCE_HASH_MISMATCH")
    for name, expected in EXPECTED_TARGET_SHAS.items():
        _, segment = find_definition(source, name)
        if sha(segment.encode()) != expected:
            raise InstallError("TARGET_HASH_MISMATCH:" + name)
    if source.count(OLD_CATCH_PHOTO) != 1 or source.count(OLD_VOICE_OVERRIDE) != 1:
        raise InstallError("CATCH_INPUT_CONTRACT_MISMATCH")


def build(source: str):
    if MARKER in source:
        validate(source)
        return source
    validate_input_baseline(source)
    assignment = '_V165_SPOOL_LOCK = "/home/Carix/.crm_media_spool.lock"\n'
    addition = (assignment
                + '_V165_DRAIN_LOCK = "/home/Carix/.crm_media_drain.lock"\n'
                + '# CRM-PHOTO-COUNTER-002: one drain and session/total counters.\n')
    if source.count(assignment) != 1:
        raise InstallError("SPOOL_ASSIGNMENT_MISMATCH")
    source = source.replace(assignment, addition, 1)
    source = replace_definition(source, "_v165_spool_drain", NEW_DRAIN)
    source = replace_definition(source, "_v165_status", NEW_STATUS)
    source = replace_definition(source, "_v165_progress_job", NEW_PROGRESS)
    source = replace_definition(source, "_v165_schedule_progress", NEW_SCHEDULE)
    if source.count(OLD_CATCH_PHOTO) != 1:
        raise InstallError("CATCH_PHOTO_BLOCK_MISMATCH")
    source = source.replace(OLD_CATCH_PHOTO, NEW_CATCH_PHOTO, 1)
    if source.count(OLD_VOICE_OVERRIDE) != 1:
        raise InstallError("VOICE_OVERRIDE_BLOCK_MISMATCH")
    source = source.replace(OLD_VOICE_OVERRIDE, NEW_VOICE_OVERRIDE, 1)
    source = insert_before_definition(source, "catch_message", VOICE_HELPER)
    validate(source)
    return source


def rollback(backup=None):
    if backup is None:
        options = sorted(BACKUPS.glob("*/cars_ui.py"))
        if not options:
            raise InstallError("ROLLBACK_BACKUP_MISSING")
        backup = options[-1]
    atomic_write(CARS_UI, pathlib.Path(backup).read_bytes())
    value = {"task_id": "task_065", "contract_id": MARKER,
             "contract_ids": [MARKER, VOICE_MARKER], "status": "PASS",
             "mode": "ROLLBACK", "restored_sha256": sha(CARS_UI.read_bytes()),
             "finished_at_utc": utc_now()}
    atomic_json(ROLLBACK_RECEIPT, value)
    return value


def main():
    if "--rollback" in sys.argv:
        rollback()
        return 0
    receipt = {"task_id": "task_065", "contract_id": MARKER,
               "contract_ids": [MARKER, VOICE_MARKER], "status": "FAIL",
               "llm_tokens": 0, "crm_db_write": False, "site_write": False,
               "errors": [], "started_at_utc": utc_now()}
    backup = None
    installed = False
    deploy_guard = None
    try:
        deploy_guard = open(DEPLOY_LOCK, "a+", encoding="utf-8")
        fcntl.flock(deploy_guard.fileno(), fcntl.LOCK_EX)
        info = CARS_UI.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise InstallError("UNSAFE_CARS_UI")
        before_db = db_snapshot()
        original = CARS_UI.read_bytes()
        candidate = build(original.decode("utf-8"))
        already = MARKER in original.decode("utf-8")
        receipt["already_applied"] = already
        if not already:
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            directory = BACKUPS / stamp
            directory.mkdir(parents=True, exist_ok=False)
            backup = directory / "cars_ui.py"
            atomic_write(backup, original)
            atomic_write(CARS_UI, candidate.encode("utf-8"))
            installed = True
        validate(CARS_UI.read_text(encoding="utf-8"))
        after_db = db_snapshot()
        if before_db != after_db:
            raise InstallError("PROTECTED_DB_CHANGED")
        receipt.update({"readonly_before": before_db, "readonly_after": after_db,
                        "cars_ui_sha256_after": sha(CARS_UI.read_bytes()),
                        "backup_path": str(backup) if backup else None,
                        "status": "PASS"})
    except Exception as exc:
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc))
        if installed and backup:
            try:
                receipt["rollback"] = rollback(backup)
            except Exception as rollback_exc:
                receipt["errors"].append("ROLLBACK_" + str(rollback_exc))
    receipt["finished_at_utc"] = utc_now()
    if deploy_guard is not None:
        try:
            fcntl.flock(deploy_guard.fileno(), fcntl.LOCK_UN)
            deploy_guard.close()
        except Exception:
            pass
    atomic_json(INSTALL_RECEIPT, receipt)
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
