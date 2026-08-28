#!/usr/bin/env python3
"""Fail-closed installer for CRM-PHOTO-FASTPATH-001."""
from __future__ import annotations

import ast
import datetime as dt
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
TEAM_BOT = BASE / "team_bot.py"
DB_PY = BASE / "db.py"
CRM_DB = BASE / "crm.db"
SAFE = BASE / "autopilot_inbox" / "cloud" / "task_065"
BACKUPS = BASE / "backups" / "task_065"
INSTALL_RECEIPT = SAFE / "install_receipt.json"
ROLLBACK_RECEIPT = SAFE / "rollback_receipt.json"
EXPECTED = {
    "cars_ui.py": "721e21f43787832b325c1fc806a64f332cb14a26bd63b297cb738c9fbb687563",
    "team_bot.py": "4e0ede93c744e49c2a634fa5e7f195bdda27208d7575c3cd9a0e4ce419913918",
    "db.py": "b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086",
}
MARKER = "CRM-PHOTO-FASTPATH-001"


HELPERS = r'''# CRM-PHOTO-FASTPATH-001: durable, non-blocking photo intake.
_V165_SPOOL = "/home/Carix/.crm_media_spool.jsonl"
_V165_SPOOL_LOCK = "/home/Carix/.crm_media_spool.lock"
_V165_PROGRESS = {}


def _v165_key(card_id, target, file_id):
    import hashlib as _v165_hashlib
    raw = "%s\0%s\0%s" % (int(card_id), str(target), str(file_id))
    return _v165_hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _v165_limit(target):
    return {"photos": S.PHOTO_LIMIT,
            "condition_photos": S.CONDITION_PHOTO_LIMIT}.get(target, 100)


def _v165_read_rows():
    import fcntl as _v165_fcntl
    import json as _v165_json
    import os as _v165_os
    _v165_os.makedirs(_v165_os.path.dirname(_V165_SPOOL), exist_ok=True)
    with open(_V165_SPOOL_LOCK, "a+", encoding="utf-8") as _v165_guard:
        _v165_fcntl.flock(_v165_guard.fileno(), _v165_fcntl.LOCK_EX)
        try:
            try:
                with open(_V165_SPOOL, "r", encoding="utf-8") as _v165_file:
                    _v165_lines = _v165_file.readlines()
            except FileNotFoundError:
                _v165_lines = []
        finally:
            _v165_fcntl.flock(_v165_guard.fileno(), _v165_fcntl.LOCK_UN)
    _v165_rows = []
    for _v165_line in _v165_lines:
        try:
            _v165_row = _v165_json.loads(_v165_line)
            if isinstance(_v165_row, dict) and _v165_row.get("key"):
                _v165_rows.append(_v165_row)
        except Exception:
            continue
    return _v165_rows


def _v165_spool_enqueue(card_id, target, file_id, actor_id, tag=""):
    """Durably accept first; never wait for SQLite or Telegram getFile."""
    import fcntl as _v165_fcntl
    import json as _v165_json
    import os as _v165_os
    import time as _v165_time
    _v165_os.makedirs(_v165_os.path.dirname(_V165_SPOOL), exist_ok=True)
    _v165_event = {
        "key": _v165_key(card_id, target, file_id),
        "card_id": int(card_id),
        "target": str(target),
        "file_id": str(file_id),
        "actor_id": int(actor_id),
        "tag": str(tag or ""),
        "accepted_at": int(_v165_time.time()),
    }
    with open(_V165_SPOOL_LOCK, "a+", encoding="utf-8") as _v165_guard:
        _v165_fcntl.flock(_v165_guard.fileno(), _v165_fcntl.LOCK_EX)
        try:
            try:
                with open(_V165_SPOOL, "r", encoding="utf-8") as _v165_file:
                    _v165_lines = _v165_file.readlines()
            except FileNotFoundError:
                _v165_lines = []
            _v165_keys = set()
            _v165_same = 0
            for _v165_line in _v165_lines:
                try:
                    _v165_row = _v165_json.loads(_v165_line)
                except Exception:
                    continue
                _v165_keys.add(_v165_row.get("key"))
                if (_v165_row.get("card_id") == int(card_id)
                        and _v165_row.get("target") == str(target)):
                    _v165_same += 1
            if _v165_event["key"] in _v165_keys:
                return {"state": "duplicate", "queued": _v165_same}
            if _v165_same >= _v165_limit(target):
                return {"state": "limit", "queued": _v165_same}
            _v165_payload = (_v165_json.dumps(
                _v165_event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
            _v165_fd = _v165_os.open(
                _V165_SPOOL,
                _v165_os.O_WRONLY | _v165_os.O_CREAT | _v165_os.O_APPEND,
                0o600,
            )
            try:
                _v165_os.write(_v165_fd, _v165_payload)
                _v165_os.fsync(_v165_fd)
            finally:
                _v165_os.close(_v165_fd)
            return {"state": "accepted", "queued": _v165_same + 1}
        finally:
            _v165_fcntl.flock(_v165_guard.fileno(), _v165_fcntl.LOCK_UN)


def _v165_spool_remove(keys):
    import fcntl as _v165_fcntl
    import json as _v165_json
    import os as _v165_os
    import tempfile as _v165_tempfile
    _v165_keys = set(keys)
    if not _v165_keys:
        return
    with open(_V165_SPOOL_LOCK, "a+", encoding="utf-8") as _v165_guard:
        _v165_fcntl.flock(_v165_guard.fileno(), _v165_fcntl.LOCK_EX)
        try:
            try:
                with open(_V165_SPOOL, "r", encoding="utf-8") as _v165_file:
                    _v165_lines = _v165_file.readlines()
            except FileNotFoundError:
                return
            _v165_keep = []
            for _v165_line in _v165_lines:
                try:
                    if _v165_json.loads(_v165_line).get("key") in _v165_keys:
                        continue
                except Exception:
                    pass
                _v165_keep.append(_v165_line)
            _v165_dir = _v165_os.path.dirname(_V165_SPOOL)
            _v165_fd, _v165_tmp = _v165_tempfile.mkstemp(prefix=".media-spool-", dir=_v165_dir)
            try:
                with _v165_os.fdopen(_v165_fd, "w", encoding="utf-8") as _v165_file:
                    _v165_file.writelines(_v165_keep)
                    _v165_file.flush()
                    _v165_os.fsync(_v165_file.fileno())
                _v165_os.replace(_v165_tmp, _V165_SPOOL)
            finally:
                try:
                    _v165_os.unlink(_v165_tmp)
                except FileNotFoundError:
                    pass
        finally:
            _v165_fcntl.flock(_v165_guard.fileno(), _v165_fcntl.LOCK_UN)


def _v165_spool_drain(max_items=100):
    """Drain in a worker thread; locked DB leaves every event on disk."""
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
            "error": _v165_error}


def _v165_media_ids(card, target):
    if not card:
        return []
    try:
        _v165_items = jload(card.get(target))
    except Exception:
        _v165_items = []
    _v165_result = []
    for _v165_item in _v165_items:
        _v165_value = (_v165_item.get("file_id") if isinstance(_v165_item, dict)
                       else _v165_item)
        if _v165_value and _v165_value not in _v165_result:
            _v165_result.append(_v165_value)
    return _v165_result


def _v165_status(card_id, target):
    _v165_rows = [row for row in _v165_read_rows()
                  if row.get("card_id") == int(card_id)
                  and row.get("target") == str(target)]
    try:
        _v165_saved = _v165_media_ids(card_of(card_id), target)
        _v165_saved_count = len(_v165_saved)
        _v165_all = set(_v165_saved)
        _v165_all.update(row.get("file_id") for row in _v165_rows)
        _v165_accepted = len([value for value in _v165_all if value])
    except Exception:
        _v165_saved_count = None
        _v165_accepted = len({row.get("file_id") for row in _v165_rows
                              if row.get("file_id")})
    return {"accepted": _v165_accepted,
            "saved": _v165_saved_count,
            "queued": len(_v165_rows),
            "limit": _v165_limit(target)}


async def media_spool_worker_job(context):
    import asyncio as _v165_asyncio
    await _v165_asyncio.to_thread(_v165_spool_drain, 100)


async def _v165_progress_job(context):
    import asyncio as _v165_asyncio
    _v165_data = context.job.data
    await _v165_asyncio.to_thread(_v165_spool_drain, 100)
    _v165_status_now = await _v165_asyncio.to_thread(
        _v165_status, _v165_data["card_id"], _v165_data["target"])
    if _v165_status_now["saved"] is None:
        _v165_text = "Фото принято: %d · очередь: %d." % (
            _v165_status_now["accepted"], _v165_status_now["queued"])
    else:
        _v165_text = "Фото: %d/%d · очередь: %d." % (
            _v165_status_now["saved"], _v165_status_now["limit"],
            _v165_status_now["queued"])
    await context.bot.send_message(
        chat_id=_v165_data["chat_id"],
        text=_v165_text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "Открыть карточку",
            callback_data="car_open:%d" % _v165_data["card_id"])]]),
    )


def _v165_schedule_progress(context, msg, card_id, target):
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
                  "target": str(target)},
            name="crm-photo-progress-" + _v165_key_value,
        )
'''


SAVE_BASE = r'''def _save_media_bazovoe(card, target, file_id, actor_id, tag=""):  # UA-V142
    """Write one unique media id using the latest authoritative card state."""
    cid = card["id"]
    latest = card_of(cid)
    if latest:
        card = latest
    if target in ("video_h", "video_v"):
        target = "videos"
    if target == "diag_report":
        set_field(cid, target, file_id, actor_id)
        return "Отчёт диагностики сохранён."

    limit = {"photos": S.PHOTO_LIMIT,
             "videos": VIDEO_LIMIT,
             "condition_photos": S.CONDITION_PHOTO_LIMIT,
             "condition_videos": S.CONDITION_VIDEO_LIMIT}.get(target, 99)
    items = jload(card.get(target))
    norm = []
    for p in items:
        norm.append(p if isinstance(p, dict) else {"file_id": p, "tag": ""})
    if any(p.get("file_id") == file_id for p in norm):
        return None
    if len(norm) >= limit:
        return "Достигнут предел: %d." % limit
    norm.append({"file_id": file_id, "tag": tag})
    set_field(cid, target, jdump(norm), actor_id)
    return "Сохранено. Всего: %d из %d." % (len(norm), limit)
'''


SAVE_CHECK = r'''def _save_media_proverka(card, target, file_id, actor_id, tag=""):  # UA-V152
    nomer = str(card.get("auto_number") or "?")
    eto_video = target in ("videos", "video_h", "video_v", "condition_videos")
    # Telegram already validated msg.photo. A second blocking getFile request is redundant.
    if target in ("photos", "condition_photos"):
        _v140_zapis("%s · %s · принято fast-path · %s"
                    % (nomer, target, str(file_id)[:24]))
        return _v140_save_media_ishodnyy(card, target, file_id, actor_id, tag)
    otvetil, razmer, oshibka = _v140_sprosit(file_id)

    if otvetil is False:
        if "too big" in oshibka.lower():
            _v140_zapis("%s · %s · ОТКАЗ файл больше предела Telegram · %s · %s"
                        % (nomer, target, str(file_id)[:24], oshibka))
            return _V140_BOLSHOE
        _v140_zapis("%s · %s · ОТКАЗ · %s · %s"
                    % (nomer, target, str(file_id)[:24], oshibka))
        return ("Файл не принят: Telegram отвечает «%s».\n\n"
                "Пришлите файл этому боту ещё раз." % oshibka)

    if otvetil and _v159_ne_tot_tip(target, file_id):
        _v140_zapis("%s · %s · ОТКАЗ не тот тип файла" % (nomer, target))
        return ("В этот раздел нужен другой тип файла.\n\n"
                "Для видео нажмите «Добавить видео», для фотографий — «Добавить фото».")

    if otvetil and eto_video and razmer > _V140_PREDEL_VIDEO:
        _v140_zapis("%s · %s · ОТКАЗ размер %d байт · %s"
                    % (nomer, target, razmer, str(file_id)[:24]))
        return _V140_BOLSHOE

    if otvetil is None:
        _v140_zapis("%s · %s · ОТКАЗ проверка не выполнена (%s) — в карточку не записан"
                    % (nomer, target, oshibka))
        return ("Файл пока не проверен: Telegram не ответил (%s).\n\n"
                "В карточку он НЕ сохранён — пришлите его ещё раз через минуту."
                % oshibka)
    _v140_zapis("%s · %s · принято · размер %d байт" % (nomer, target, razmer))
    return _v140_save_media_ishodnyy(card, target, file_id, actor_id, tag)
'''


SAVE_MEDIA = r'''def save_media(card, target, file_id, actor_id, tag=""):
    otvet = _v152_save_media(card, target, file_id, actor_id, tag)
    cel = "videos" if target in ("video_h", "video_v") else target
    vid = _V152_VID.get(cel)
    otkaz = otvet and any(word in str(otvet).casefold() for word in (
        "слишком большое", "не принят", "не проверен", "достигнут предел"))
    if vid and not otkaz:
        with db.connect() as con:
            est = con.execute("SELECT id FROM media WHERE car_id=? AND vid=? AND file_id=?",
                              (card["id"], vid, file_id)).fetchone()
            if not est:
                nomer = con.execute(
                    "SELECT COALESCE(MAX(poryadok),0)+1 FROM media WHERE car_id=? AND vid=?",
                    (card["id"], vid)).fetchone()[0]
                con.execute(
                    "INSERT INTO media (car_id, auto_number, vid, file_id, status, tag,"
                    " poryadok, kogda, kto, primechanie) VALUES (?,?,?,?,'pending',?,?,?,?,?)",
                    (card["id"], str(card.get("auto_number") or ""), vid, file_id, tag,
                     nomer, _t140.strftime("%Y-%m-%dT%H:%M:%S"), str(actor_id),
                     "принят ботом, ждёт скачивания"))
                _v140_zapis("media: заведена запись %s %s pending"
                            % (card.get("auto_number"), vid))
    return otvet
'''


OLD_MEDIA_BLOCK = r'''    wait = context.user_data.get("car_media_wait")
    if wait:
        target = wait["target"]
        tag = ""
        card = card_of(wait["card_id"])
        if not card:
            context.user_data.pop("car_media_wait", None)
            return
        file_id = None
        if msg.photo:
            file_id = msg.photo[-1].file_id
        elif msg.video:
            file_id = msg.video.file_id
            if target in ("videos", "video_h", "video_v"):
                target = "videos"
                slot = _orient(msg.video)
                tag = {"video_h": "гориз", "video_v": "вертик"}.get(slot, "")
        elif msg.video_note:
            file_id = msg.video_note.file_id
        elif msg.document:
            file_id = msg.document.file_id
        if file_id:
            answer = save_media(card, target, file_id, user_id, tag)
            if answer:
                await msg.reply_text(
                    answer,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("← Вернуться к карточке",
                                              callback_data="car_open:%d" % card["id"])],
                        [InlineKeyboardButton("Фото и видео",
                                              callback_data="car_media:%d" % card["id"])]]))
            raise ApplicationHandlerStop
        if msg.text and target == "diag_report":
            pass
        return
'''


NEW_MEDIA_BLOCK = r'''    wait = context.user_data.get("car_media_wait")
    if wait:
        target = wait["target"]
        tag = ""
        file_id = None
        if msg.photo:
            file_id = msg.photo[-1].file_id
            if target in ("photos", "condition_photos"):
                _v165_spool_enqueue(wait["card_id"], target, file_id, user_id, tag)
                _v165_schedule_progress(context, msg, wait["card_id"], target)
                raise ApplicationHandlerStop
        elif msg.video:
            file_id = msg.video.file_id
            if target in ("videos", "video_h", "video_v"):
                target = "videos"
                slot = _orient(msg.video)
                tag = {"video_h": "гориз", "video_v": "вертик"}.get(slot, "")
        elif msg.video_note:
            file_id = msg.video_note.file_id
        elif msg.document:
            file_id = msg.document.file_id
        card = card_of(wait["card_id"])
        if not card:
            context.user_data.pop("car_media_wait", None)
            return
        if file_id:
            answer = await asyncio.to_thread(save_media, card, target, file_id, user_id, tag)
            if answer:
                await msg.reply_text(answer)
            raise ApplicationHandlerStop
        if msg.text and target == "diag_report":
            pass
        return
'''


class InstallError(RuntimeError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def regular(path: pathlib.Path) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise InstallError("UNSAFE_FILE:" + path.name)


def atomic_write(path: pathlib.Path, data: bytes) -> None:
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


def atomic_json(path: pathlib.Path, value) -> None:
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())


def db_snapshot():
    con = sqlite3.connect("file:%s?mode=ro" % CRM_DB, uri=True, timeout=20)
    con.row_factory = sqlite3.Row
    try:
        quick = con.execute("PRAGMA quick_check").fetchone()[0]
        count = con.execute("SELECT COUNT(*) FROM cars").fetchone()[0]
        rows = [dict(row) for row in con.execute(
            "SELECT * FROM cars WHERE auto_number=? ORDER BY id", ("UA-0009",)).fetchall()]
    finally:
        con.close()
    return {"quick_check": quick, "cars_count": count,
            "ua0009_rows": len(rows),
            "ua0009_sha256": hashlib.sha256(
                json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()}


def replace_definition(source: str, name: str, replacement: str) -> str:
    tree = ast.parse(source)
    nodes = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(nodes) != 1:
        raise InstallError("TARGET_INVALID:" + name)
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [replacement.rstrip() + "\n\n"]
    return "".join(lines)


def build_cars(source: str) -> str:
    if MARKER in source:
        validate_cars(source)
        return source
    if sha(source.encode()) != EXPECTED["cars_ui.py"]:
        raise InstallError("SOURCE_HASH_MISMATCH:cars_ui.py")
    if source.count(OLD_MEDIA_BLOCK) != 1:
        raise InstallError("MEDIA_BLOCK_MISMATCH")
    source = replace_definition(source, "_save_media_bazovoe", SAVE_BASE)
    source = replace_definition(source, "_save_media_proverka", SAVE_CHECK)
    source = replace_definition(source, "save_media", SAVE_MEDIA)
    source = source.replace(OLD_MEDIA_BLOCK, NEW_MEDIA_BLOCK, 1)
    tree = ast.parse(source)
    catch = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
             and node.name == "catch_message"]
    if len(catch) != 1:
        raise InstallError("CATCH_MESSAGE_MISSING")
    lines = source.splitlines(keepends=True)
    lines[catch[0].lineno - 1:catch[0].lineno - 1] = [HELPERS.rstrip() + "\n\n\n"]
    candidate = "".join(lines)
    validate_cars(candidate)
    return candidate


def validate_cars(source: str) -> None:
    required = (MARKER, "_v165_spool_enqueue", "_v165_spool_drain",
                "media_spool_worker_job", "await asyncio.to_thread(save_media",
                "with db.connect() as con", "fast-path")
    if any(value not in source for value in required):
        raise InstallError("CARS_CONTRACT_MISSING")
    if '_s152.connect("/home/Carix/crm.db"' in source:
        raise InstallError("RAW_MEDIA_CONNECTION_REMAINS")
    tree = ast.parse(source)
    catch = next(node for node in tree.body
                 if isinstance(node, ast.AsyncFunctionDef) and node.name == "catch_message")
    text = ast.get_source_segment(source, catch) or ""
    media_part = text.split('voice_object =', 1)[0]
    if "reply_markup=InlineKeyboardMarkup([" in media_part:
        raise InstallError("REPEATED_MEDIA_MENU_REMAINS")
    compile(source, "cars_ui.py.candidate", "exec")


def build_team(source: str) -> str:
    if MARKER in source:
        validate_team(source)
        return source
    if sha(source.encode()) != EXPECTED["team_bot.py"]:
        raise InstallError("SOURCE_HASH_MISMATCH:team_bot.py")
    old = "    if app.job_queue:\n        app.job_queue.run_repeating(\n            backup_job"
    new = ("    if app.job_queue:\n"
           "        # CRM-PHOTO-FASTPATH-001: DB drain is independent of update handling.\n"
           "        app.job_queue.run_repeating(\n"
           "            cars_ui.media_spool_worker_job, interval=1.0, first=0.2\n"
           "        )\n"
           "        app.job_queue.run_repeating(\n"
           "            backup_job")
    if source.count(old) != 1:
        raise InstallError("TEAM_JOB_BLOCK_MISMATCH")
    candidate = source.replace(old, new, 1)
    validate_team(candidate)
    return candidate


def validate_team(source: str) -> None:
    if MARKER not in source or "cars_ui.media_spool_worker_job" not in source:
        raise InstallError("TEAM_CONTRACT_MISSING")
    compile(source, "team_bot.py.candidate", "exec")


def build_db(source: str) -> str:
    if MARKER in source:
        validate_db(source)
        return source
    if sha(source.encode()) != EXPECTED["db.py"]:
        raise InstallError("SOURCE_HASH_MISMATCH:db.py")
    old = '        sqlite3.Connection.execute(conn, "PRAGMA journal_mode=DELETE")'
    new = ('        # CRM-PHOTO-FASTPATH-001: readers (site) cannot block CRM writes.\n'
           '        sqlite3.Connection.execute(conn, "PRAGMA journal_mode=WAL")\n'
           '        sqlite3.Connection.execute(conn, "PRAGMA synchronous=NORMAL")')
    if source.count(old) != 1:
        raise InstallError("DB_JOURNAL_BLOCK_MISMATCH")
    candidate = source.replace(old, new, 1)
    validate_db(candidate)
    return candidate


def validate_db(source: str) -> None:
    if MARKER not in source or "PRAGMA journal_mode=WAL" not in source:
        raise InstallError("DB_WAL_CONTRACT_MISSING")
    if "PRAGMA journal_mode=DELETE" in source:
        raise InstallError("DELETE_JOURNAL_REMAINS")
    compile(source, "db.py.candidate", "exec")


def rollback(backup_dir: pathlib.Path | None = None):
    if backup_dir is None:
        backups = sorted(path for path in BACKUPS.glob("*") if path.is_dir())
        if not backups:
            raise InstallError("ROLLBACK_BACKUP_MISSING")
        backup_dir = backups[-1]
    restored = {}
    for path in (CARS_UI, TEAM_BOT, DB_PY):
        source = backup_dir / path.name
        if not source.exists():
            raise InstallError("ROLLBACK_FILE_MISSING:" + path.name)
        atomic_write(path, source.read_bytes())
        restored[path.name] = sha(path.read_bytes())
    value = {"task_id": "task_065", "contract_id": MARKER, "status": "PASS",
             "mode": "ROLLBACK", "backup_path": str(backup_dir), "restored": restored,
             "finished_at_utc": utc_now()}
    atomic_json(ROLLBACK_RECEIPT, value)
    return value


def main() -> int:
    if "--rollback" in sys.argv:
        rollback()
        return 0
    receipt = {"task_id": "task_065", "contract_id": MARKER, "status": "FAIL",
               "mode": "ATOMIC_PHOTO_FASTPATH", "llm_tokens": 0,
               "crm_db_write": False, "site_write": False, "errors": [],
               "started_at_utc": utc_now()}
    backup_dir = None
    installed = False
    try:
        before_db = db_snapshot()
        receipt["readonly_before"] = before_db
        originals = {}
        paths = (CARS_UI, TEAM_BOT, DB_PY)
        for path in paths:
            regular(path)
            originals[path.name] = path.read_bytes()
        candidates = {
            "cars_ui.py": build_cars(originals["cars_ui.py"].decode("utf-8")),
            "team_bot.py": build_team(originals["team_bot.py"].decode("utf-8")),
            "db.py": build_db(originals["db.py"].decode("utf-8")),
        }
        already = all(MARKER in originals[name].decode("utf-8") for name in candidates)
        receipt["already_applied"] = already
        if not already:
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_dir = BACKUPS / stamp
            backup_dir.mkdir(parents=True, exist_ok=False)
            for name, data in originals.items():
                atomic_write(backup_dir / name, data)
            for path in paths:
                atomic_write(path, candidates[path.name].encode("utf-8"))
            installed = True
        for path in paths:
            source = path.read_text(encoding="utf-8")
            if path == CARS_UI:
                validate_cars(source)
            elif path == TEAM_BOT:
                validate_team(source)
            else:
                validate_db(source)
        after_db = db_snapshot()
        receipt["readonly_after"] = after_db
        if before_db != after_db or after_db["quick_check"] != "ok":
            raise InstallError("LIVE_DB_CHANGED")
        receipt["files_sha256_after"] = {path.name: sha(path.read_bytes()) for path in paths}
        receipt["backup_path"] = str(backup_dir) if backup_dir else None
        receipt["status"] = "PASS"
    except Exception as exc:
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc))
        if installed and backup_dir:
            try:
                receipt["rollback"] = rollback(backup_dir)
            except Exception as rollback_exc:
                receipt["errors"].append("ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc))
    receipt["finished_at_utc"] = utc_now()
    atomic_json(INSTALL_RECEIPT, receipt)
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
