#!/usr/bin/env python3
"""Atomic fail-closed installer for CRM-ONLINE-GUARD-001 v1.3."""
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


CONTRACT = "CRM-ONLINE-GUARD-001-V1.3"
MARKER = "CRM-ONLINE-GUARD-001-V1.3"
DB_MARKER = "CRM-DB-BOUNDED-QUEUE-001"
ROOT = pathlib.Path("/home/Carix")
STAGING = ROOT / "autopilot_inbox" / "cloud" / "task_047_ferry_discovery"
SAFE = ROOT / "autopilot_inbox" / "cloud" / "task_067"
BACKUPS = ROOT / "backups" / "task_067"
RECEIPT = SAFE / "install_receipt.json"
SHADOW_RECEIPT = SAFE / "shadow_receipt.json"
ROLLBACK_RECEIPT = SAFE / "rollback_receipt.json"
GUARD_STAGED = STAGING / "crm_online_guard.py"
DEPLOY_LOCK = ROOT / ".task066_stage_anchor.lock"
TASK_LOCK = ROOT / ".task067_guard.lock"
DB_PATH = ROOT / "crm.db"
PATHS = {
    "cars_ui.py": ROOT / "cars_ui.py",
    "ai.py": ROOT / "ai.py",
    "run_all.py": ROOT / "run_all.py",
    "client_ui.py": ROOT / "client_ui.py",
    "team_bot.py": ROOT / "team_bot.py",
    "lead_bot.py": ROOT / "lead_bot.py",
    "db.py": ROOT / "db.py",
    "crm_online_guard.py": ROOT / "crm_online_guard.py",
}
EXPECTED = {
    "cars_ui.py": "734f61a314b9f5391f999664d5267448a7f1e372245a7840057cf7fb7e599f9c",
    "ai.py": "406c625f43d966e6871d766ca2dd825e7e33c019fadb6e287cafdb7803a524ed",
    "run_all.py": "7deb18698f792b61fd734b36451296343ec528e15ccd86798d6cbc4a7a75eca5",
    "client_ui.py": "e3b3964644fc8f18e28916ee665685e42c139d47a6276d2f2bb4eaddd62891d3",
    "team_bot.py": "70b349cdbe72a0cf5f674a1341a493de7759b5263859ce73d86fb292db3b5ad2",
    "lead_bot.py": "118573df42b51db49f7c2ebd9b830f78ebd1e62b71846760f62fa2f0590ffc0c",
    "db.py": "b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086",
}
EXPECTED_DEFS = {
    "condition_screen": "cbc01d25a2cdf803bb35c168c99a7b7507e627640f83102746487f0bd6ed35c7",
    "stage_menu": "218e4f4c2284b3bbf709744c95a9918df2703871fa07ed9eca18b59e83cc2e70",
    "_v165_key": "c50994908138e7796f642ae7660210581d5ab3a89b2fbf6119db945699ef22ed",
    "_v165_spool_enqueue": "74d6d26647ece9ab8c79b395001d17c23eb2cec9cec79efc0635f224197720a2",
    "_v166_drain_owned": "6aea9b6fe780e944c0aee619f0de35b52a6e5345650983167d978d044cba0c7f",
    "_v165_status": "f3fc19ccfeaa3185bb3524fbc1615083d4d467a2e195a25f43d83364a8dcf96a",
    "_v165_progress_job": "805216c628f24d3625924eadbf7b9f2cf67701837c48235ef72154566f7cc6da",
    "_v165_schedule_progress": "a633afd16e8a1c463f5d4d0b977a81db315449d6d17e6d9209e41d2793ce0722",
    "_v167_voice_explicit_fields": "acf4cbfeb17c9bf003bec688574f06fe9521c9c802d3edc87c0382d106fb4b95",
    "catch_message": "03a26be9a856227f8a592929a3b530f2a9979294b3fc21cc92baf76048d3b9d4",
    "cars_register": "4ce2316dded963d5ac429004fe99c55921d89f7042856fab6eca50ef6f2b06ec",
    "transcribe": "68e2cbd03b89278f6e9a164c6220dbc60da3e7ae85e766964d002e58e3f45cd2",
    "client_catalog_cars": "b94a3a5cfb422920702c19a7da0baae167b406a0581ab4c5577c37bffe6f1fc7",
    "client_catalog": "daef37a3dd03a99efd47eaf20cf656ef76b2020b48d00a9fbc5c8785ebef7e80",
    "client_car_screen": "9ba521882a07dedeec59c7e0826fe942a3f1f4a90f6dbe441b866b44827e82b0",
    "client_register": "1a937b7e96cb9127941ba2db24cf1cd69b232c94da7475feae49a13e8a67b29e",
    "db_connection_class": "8f2ea10d7ef423768646706a07ec14c9b793e74d070e6cab85179e5bbc225823",
    "db_connect": "3257e05c559e7c2d6d39ba0ca1b66818f6283909a411bba695d21517b29afe15",
    "db_update_card_field": "1749f0eef8fc799ed5b08bd6a4482fad3126199d8c40207b76143b263349a1b1",
}


class InstallError(RuntimeError):
    pass


def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write(path: pathlib.Path, data: bytes, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".task067-", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        descriptor = -1
        os.replace(temporary, path)
        parent_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def atomic_json(path: pathlib.Path, value):
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(), 0o600)


def safe_read(path: pathlib.Path, required=True) -> bytes | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        if required:
            raise InstallError("MISSING:" + path.name)
        return None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise InstallError("UNSAFE_FILE:" + path.name)
    if info.st_size <= 0 or info.st_size > 8_000_000:
        raise InstallError("BAD_SIZE:" + path.name)
    return path.read_bytes()


def source_node(source: str, name: str):
    tree = ast.parse(source)
    nodes = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
             and node.name == name]
    if len(nodes) != 1:
        raise InstallError("TARGET_COUNT:%s:%d" % (name, len(nodes)))
    return nodes[0]


def segment(source: str, name: str) -> str:
    node = source_node(source, name)
    return "\n".join(source.splitlines()[node.lineno - 1:node.end_lineno])


def replace_definition(source: str, name: str, replacement: str, expected: str) -> str:
    node = source_node(source, name)
    current = segment(source, name)
    if sha(current.encode()) != expected:
        raise InstallError("TARGET_SHA:" + name)
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [replacement.rstrip() + "\n\n"]
    return "".join(lines)


def insert_before(source: str, name: str, addition: str) -> str:
    node = source_node(source, name)
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.lineno - 1] = [addition.rstrip() + "\n\n\n"]
    return "".join(lines)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise InstallError("REPLACE_COUNT:%s:%d" % (label, source.count(old)))
    return source.replace(old, new, 1)


def db_state():
    con = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True, timeout=3)
    try:
        return {
            "quick_check": con.execute("PRAGMA quick_check").fetchone()[0],
            "cars": con.execute("SELECT COUNT(*) FROM cars").fetchone()[0],
            "clients": con.execute("SELECT COUNT(*) FROM clients").fetchone()[0],
        }
    finally:
        con.close()


DB_CONNECT = r'''def connect():
    # CRM-DB-BOUNDED-QUEUE-001: a user operation never waits 20 seconds.
    conn = sqlite3.connect(DB_FILE, timeout=2.0, factory=Soedinenie)
    conn.row_factory = sqlite3.Row
    # Keep rollback-journal mode: the home directory may be on shared storage,
    # where SQLite WAL shared memory is not a safe assumption.
    try:
        sqlite3.Connection.execute(conn, "PRAGMA journal_mode=DELETE")
    except Exception:
        pass
    sqlite3.Connection.execute(conn, "PRAGMA busy_timeout=450")
    sqlite3.Connection.execute(conn, "PRAGMA foreign_keys=ON")
    return conn
'''


DB_UPDATE_FIELD = r'''def update_card_field(table: str, card_id: int, field: str, value,
                      actor_id: int, _queue_on_busy: bool = True):
    """Commit quickly or durably queue a scalar field update.

    Media fields retain their dedicated ordered media spool.  Scalar fields are
    safe to accept into the guard queue when a foreign reader temporarily holds
    the rollback journal lock.
    """
    import time as _ua_time
    old = get_card(table, card_id)
    old_value = old.get(field) if old else None
    started = _ua_time.monotonic()
    try:
        with connect() as c:
            c.execute(f"UPDATE {table} SET {field}=?, updated_at=? WHERE id=?",
                      (value, now(), card_id))
    except sqlite3.OperationalError as exc:
        lowered = str(exc).casefold()
        busy = any(word in lowered for word in ("locked", "busy", "queue timeout"))
        media_fields = {
            "photos", "videos", "condition_photos", "condition_videos",
            "video_h", "video_v", "diag_photos", "diag_videos",
        }
        if (not busy or not _queue_on_busy or str(field) in media_fields
                or str(table) not in {"cars", "clients"}):
            raise
        import crm_online_guard as _ua_guard
        _ua_guard.enqueue_field_update(
            table, card_id, field, value, actor_id,
            expected_old=old_value, mode="set")
        _ua_guard.record_timing(
            "db_field_queued", _ua_time.monotonic() - started,
            "queued", card_id=card_id, detail=str(field))
        return {"queued": True}
    try:
        log_action(actor_id, "card_edit", table, card_id, field, old_value, value)
    except sqlite3.OperationalError as exc:
        lowered = str(exc).casefold()
        if _queue_on_busy and any(word in lowered for word in (
                "locked", "busy", "queue timeout")):
            import crm_online_guard as _ua_guard
            _ua_guard.enqueue_field_update(
                table, card_id, field, value, actor_id,
                expected_old=old_value, mode="audit")
            _ua_guard.record_timing(
                "db_audit_queued", _ua_time.monotonic() - started,
                "queued", card_id=card_id, detail=str(field))
        else:
            raise
    return {"queued": False}
'''


CARS_HELPERS = r'''# CRM-ONLINE-GUARD-001-V1.3: bounded callbacks, missing-only writes and CAS.
def _v168_empty(value):
    return value in (None, "", 0, [], {})


def _v168_is_correction(text):
    import re as _v168_re
    return bool(_v168_re.search(
        r"\b(?:измени|изменить|исправь|исправить|замени|заменить|поменяй|"
        r"скорректируй|зміни|змінити|виправ|заміни|поміняй|change|correct|"
        r"replace|update)\b", str(text or "").casefold()))


def _v168_named_fields(text, allowed):
    import re as _v168_re
    value = str(text or "").casefold().replace("ё", "е")
    patterns = {
        "fuel": r"топлив|палив|fuel|l\s*p\s*[ig]|бензин|diesel|дизел|hybrid|electric|газ",
        "engine_cc": r"объ?ем|об['’]?єм|двигател|двигун|мотор|engine",
        "color": r"цвет|колір|color|white|black|silver|gray|grey|бел|білий|черн",
        "mileage_km": r"пробег|пробіг|mileage|kilometr",
        "transmission": r"кпп|коробк|трансмис|transmission|automatic|manual|автомат|механик",
        "drive": r"привод|привід|drive|4wd|awd|fwd|rwd",
        "price_uah": r"цена|ціна|стоимост|вартіст|price",
        "description": r"описан|опис|description",
        "status": r"статус|этап|етап|stage|status",
        "brand": r"марка|бренд|brand|make",
        "model": r"модель|model",
        "year": r"год|рік|year",
        "vin": r"\bvin\b|вин[- ]?код",
    }
    permitted = set(allowed or ())
    return {field for field, pattern in patterns.items()
            if field in permitted and _v168_re.search(pattern, value)}


def _v168_cas_write(card_id, field, expected_old, new_value, actor_id,
                    correction=False, _queue_on_busy=True):
    import re as _v168_re
    if not _v168_re.fullmatch(r"[a-z_][a-z0-9_]*", str(field or "")):
        return False, "invalid"
    if _v168_empty(new_value):
        return False, "empty"
    try:
        with db.connect() as _v168_con:
            columns = {row[1] for row in _v168_con.execute("PRAGMA table_info(cars)")}
            if field not in columns:
                return False, "unknown"
            row = _v168_con.execute(
                "SELECT %s FROM cars WHERE id=?" % field, (int(card_id),)).fetchone()
            if row is None:
                return False, "missing_card"
            current = row[0]
            if str(current or "") == str(new_value):
                return False, "same"
            if correction:
                if str(current or "") != str(expected_old or ""):
                    return False, "conflict"
            elif not _v168_empty(current):
                return False, "filled"
            cursor = _v168_con.execute(
                "UPDATE cars SET %s=?,updated_at=? WHERE id=? AND %s IS ?" % (field, field),
                (new_value, db.now(), int(card_id), current))
            if cursor.rowcount != 1:
                return False, "conflict"
    except Exception as _v168_exc:
        lowered = str(_v168_exc).casefold()
        if (_queue_on_busy
                and any(word in lowered for word in ("locked", "busy", "queue timeout"))):
            try:
                import crm_online_guard as _v168_guard
                _v168_guard.enqueue_field_update(
                    "cars", card_id, field, new_value, actor_id,
                    expected_old=expected_old, correction=correction, mode="cas")
                return True, "queued"
            except Exception:
                pass
        if any(word in lowered for word in ("locked", "busy", "queue timeout")):
            return False, "busy"
        raise
    try:
        db.log_action(actor_id, "card_edit", "cars", int(card_id),
                      field, current, new_value)
    except Exception as _v168_exc:
        log.warning("CRM CAS audit failed card=%s field=%s error=%s",
                    card_id, field, _v168_exc)
    return True, "applied"


async def _v168_guard_heartbeat(context):
    try:
        import crm_online_guard as _v168_guard
        _v168_guard.heartbeat(str(context.job.data or "crm_bot"))
    except Exception:
        pass


async def _v168_ack(query, *args, **kwargs):
    try:
        import crm_online_guard as _v168_guard
        import asyncio as _v168_asyncio
        action = "crm_" + str(getattr(query, "data", "callback") or "callback").split(":", 1)[0]
        if args or kwargs:
            token, _started = _v168_guard.start_operation(action)
            try:
                await _v168_asyncio.wait_for(query.answer(*args, **kwargs), timeout=0.75)
                _v168_guard.finish_operation(token, "ack")
            except Exception as exc:
                _v168_guard.finish_operation(token, "continued", type(exc).__name__)
        else:
            token, _started = await _v168_guard.safe_callback_answer(query, action)
            _v168_guard.finish_operation(token, "ack")
    except Exception:
        try:
            await query.answer(*args, **kwargs)
        except Exception:
            pass


def _v168_start_guard(app, component="crm_bot"):
    try:
        import crm_online_guard as _v168_guard
        _v168_guard.start_supervisor()
        _v168_guard.heartbeat(component)
        if app.job_queue:
            _v168_guard_name = "crm-guard-heartbeat-" + component
            if not app.job_queue.get_jobs_by_name(_v168_guard_name):
                app.job_queue.run_repeating(
                    _v168_guard_heartbeat, interval=1.0, first=0.1,
                    data=component, name=_v168_guard_name)
    except Exception as _v168_exc:
        log.warning("CRM guard unavailable: %s", _v168_exc)
'''


CONDITION_SCREEN = r'''async def condition_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import asyncio as _v168_asyncio
    import crm_online_guard as _v168_guard
    q = update.callback_query
    cid = int(q.data.split(":")[-1])
    token, started = await _v168_guard.safe_callback_answer(q, "crm_condition", cid)
    try:
        drop_wait(context)
        card = card_of(cid)
        if not card:
            await q.message.reply_text("Карточка не найдена.")
            _v168_guard.finish_operation(token, "missing_card")
            raise ApplicationHandlerStop
        diag_opis = (card.get("diag_text") or "").strip()
        text = ["<b>Комплексная диагностика</b>", card.get("auto_number") or "", "",
                diag_opis or "Описание пока не заполнено.", "",
                "Фото проверки: %d из 50" % len(jload(card.get("condition_photos"))),
                "Видео проверки: %d из 10" % len(jload(card.get("condition_videos"))), "",
                "Ссылка OBD: %s" % (card.get("diag_link") or "нет")]
        rows = [
            [InlineKeyboardButton("Описание", callback_data="car_setf:%d:diag_text" % cid)],
            [InlineKeyboardButton("Показать фото проверки", callback_data="car_dgal:%d" % cid),
             InlineKeyboardButton("Показать видео проверки", callback_data="car_dvid:%d" % cid)],
            [InlineKeyboardButton("Добавить фото", callback_data="car_add:%d:condition_photos" % cid),
             InlineKeyboardButton("Добавить видео", callback_data="car_add:%d:condition_videos" % cid)],
            [InlineKeyboardButton("Ссылка OBD", callback_data="car_setf:%d:diag_link" % cid)],
            [InlineKeyboardButton("Удалить все фото проверки", callback_data="diag_ask:%d:condition_photos" % cid)],
            [InlineKeyboardButton("Удалить все видео проверки", callback_data="diag_ask:%d:condition_videos" % cid)],
            [InlineKeyboardButton("← К карточке", callback_data="car_open:%d" % cid)],
        ]
        send_task = _v168_asyncio.create_task(q.message.reply_text(
            "\n".join(text), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows),
            disable_web_page_preview=True))
        try:
            await _v168_asyncio.wait_for(
                _v168_asyncio.shield(send_task), timeout=_v168_guard.remaining(started))
            _v168_guard.finish_operation(token, "ok")
        except _v168_asyncio.TimeoutError:
            _v168_guard.finish_operation(token, "deferred", "telegram_send")
        raise ApplicationHandlerStop
    except ApplicationHandlerStop:
        raise
    except Exception as exc:
        _v168_guard.finish_operation(token, "error", type(exc).__name__)
        log.exception("condition route failed card=%s", cid)
        try:
            await q.message.reply_text("Не удалось открыть диагностику. Повторите нажатие.")
        finally:
            raise ApplicationHandlerStop
'''


STAGE_MENU = r'''async def stage_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import asyncio as _v168_asyncio
    import crm_online_guard as _v168_guard
    q = update.callback_query
    cid = int(q.data.split(":")[-1])
    token, started = await _v168_guard.safe_callback_answer(q, "crm_delivery", cid)
    try:
        drop_wait(context)
        card = card_of(cid)
        if not card:
            await q.message.reply_text("Карточка не найдена.")
            _v168_guard.finish_operation(token, "missing_card")
            raise ApplicationHandlerStop
        stage = S.stage_of(card.get("status")) or 1
        lines = ["🚚 Доставка и этапы", card.get("auto_number") or "#%d" % cid, "",
                 "Сейчас: %s" % S.status_label(card.get("status")),
                 "Этап %d из 4: %s" % (stage, dict(S.STAGES).get(stage, "—"))]
        if card.get("sea_container"):
            lines.append("Контейнер: %s" % card["sea_container"])
        if card.get("sea_date_out"):
            lines.append("Дата отправления: %s" % str(card["sea_date_out"])[:10])
        left, eta = eta_of(card)
        if stage >= 4:
            lines.append("Выдача: автомобиль в Киеве")
        elif left is not None:
            lines.append("До выдачи в Киеве: %d дней · %s" % (left, eta.strftime("%d.%m.%Y")))
        else:
            lines.append("Срок: уточняется")
        rows = []
        for number, _name in S.STAGES:
            pair = [InlineKeyboardButton(
                ("• " if card.get("status") == code else "") + label,
                callback_data="car_setstage:%d:%s" % (cid, code))
                for code, (stage_no, label) in S.STATUSES.items() if stage_no == number]
            for index in range(0, len(pair), 2):
                rows.append(pair[index:index + 2])
        rows.append([InlineKeyboardButton("📦 Контейнер, даты и сроки", callback_data="cont_menu:%d" % cid)])
        rows.append([InlineKeyboardButton("← К карточке", callback_data="car_open:%d" % cid)])
        send_task = _v168_asyncio.create_task(q.message.reply_text(
            "\n".join(lines), reply_markup=InlineKeyboardMarkup(rows)))
        try:
            await _v168_asyncio.wait_for(
                _v168_asyncio.shield(send_task), timeout=_v168_guard.remaining(started))
            _v168_guard.finish_operation(token, "ok")
        except _v168_asyncio.TimeoutError:
            _v168_guard.finish_operation(token, "deferred", "telegram_send")
        raise ApplicationHandlerStop
    except ApplicationHandlerStop:
        raise
    except Exception as exc:
        _v168_guard.finish_operation(token, "error", type(exc).__name__)
        log.exception("delivery route failed card=%s", cid)
        try:
            await q.message.reply_text("Не удалось открыть доставку. Повторите нажатие.")
        finally:
            raise ApplicationHandlerStop
'''


MEDIA_KEY = r'''def _v165_key(card_id, target, unique_id):
    try:
        import crm_online_guard as _v168_guard
        return _v168_guard.media_receipt_key(card_id, target, unique_id)
    except Exception:
        import hashlib as _v165_hashlib
        raw = "%s\0%s\0%s" % (int(card_id), str(target), str(unique_id))
        return _v165_hashlib.sha256(raw.encode("utf-8")).hexdigest()
'''


MEDIA_ENQUEUE = r'''def _v165_spool_enqueue(card_id, target, file_id, actor_id, tag="", unique_id=None, message_id=None):
    """Durable, idempotent acceptance; no SQLite write and no getFile wait."""
    import fcntl as _v165_fcntl
    import hashlib as _v165_hashlib
    import json as _v165_json
    import os as _v165_os
    import time as _v165_time
    identity = str(unique_id or file_id)
    event_key = _v165_key(card_id, target, identity)
    try:
        import crm_online_guard as _v168_guard
        if _v168_guard.media_seen(event_key):
            return {"state": "duplicate_saved", "queued": 0}
    except Exception:
        pass
    try:
        if str(file_id) in set(_v165_media_ids(card_of(card_id), target)):
            return {"state": "duplicate_saved", "queued": 0}
    except Exception:
        pass
    _v165_os.makedirs(_v165_os.path.dirname(_V165_SPOOL), exist_ok=True)
    event = {
        "key": event_key, "card_id": int(card_id), "target": str(target),
        "file_id": str(file_id), "actor_id": int(actor_id), "tag": str(tag or ""),
        "unique_id_sha256": _v165_hashlib.sha256(identity.encode()).hexdigest(),
        "message_id": int(message_id) if message_id is not None else None,
        "accepted_at": int(_v165_time.time()),
    }
    with open(_V165_SPOOL_LOCK, "a+", encoding="utf-8") as guard:
        _v165_fcntl.flock(guard.fileno(), _v165_fcntl.LOCK_EX)
        try:
            try:
                lines = open(_V165_SPOOL, "r", encoding="utf-8").readlines()
            except FileNotFoundError:
                lines = []
            keys, same = set(), 0
            for line in lines:
                try:
                    row = _v165_json.loads(line)
                except Exception:
                    continue
                keys.add(row.get("key"))
                if row.get("card_id") == int(card_id) and row.get("target") == str(target):
                    same += 1
            if event_key in keys:
                return {"state": "duplicate_queued", "queued": same}
            try:
                saved_count = len(set(_v165_media_ids(card_of(card_id), target)))
            except Exception:
                saved_count = 0
            if saved_count + same >= _v165_limit(target):
                return {"state": "limit", "queued": same}
            payload = (_v165_json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
            descriptor = _v165_os.open(_V165_SPOOL, _v165_os.O_WRONLY | _v165_os.O_CREAT | _v165_os.O_APPEND, 0o600)
            try:
                _v165_os.write(descriptor, payload)
                _v165_os.fsync(descriptor)
            finally:
                _v165_os.close(descriptor)
            return {"state": "accepted", "queued": same + 1, "key": event_key}
        finally:
            _v165_fcntl.flock(guard.fileno(), _v165_fcntl.LOCK_UN)
'''


MEDIA_DRAIN = r'''def _v166_drain_owned(max_items=100):
    """Drain once; mark a durable receipt only after successful CRM save."""
    rows = _v165_read_rows()[:max(1, int(max_items))]
    done, error = [], ""
    for row in rows:
        try:
            card = card_of(row["card_id"])
            if not card:
                error = "card unavailable"
                continue
            answer = save_media(card, row["target"], row["file_id"],
                                row["actor_id"], row.get("tag", ""))
            if answer and any(word in str(answer).casefold() for word in ("не принят", "не проверен")):
                error = str(answer)[:160]
                continue
            done.append(row["key"])
            try:
                import crm_online_guard as _v168_guard
                _v168_guard.media_mark(row["key"], row["card_id"], row["target"])
            except Exception:
                pass
        except Exception as exc:
            error = "%s: %s" % (type(exc).__name__, exc)
            if "locked" in str(exc).casefold() or "busy" in str(exc).casefold():
                break
    _v165_spool_remove(done)
    return {"processed": len(done), "remaining": len(_v165_read_rows()),
            "error": error, "busy": False}
'''


MEDIA_STATUS = r'''def _v165_status(card_id, target, session_ids=None):
    rows = [row for row in _v165_read_rows()
            if row.get("card_id") == int(card_id) and row.get("target") == str(target)]
    session = {str(value) for value in (session_ids or []) if value}
    try:
        saved_set = set(_v165_media_ids(card_of(card_id), target))
        saved_count = len(saved_set)
        session_saved = len(saved_set & session)
    except Exception:
        saved_set, saved_count, session_saved = set(), None, None
    queued_ids = {str(row.get("file_id")) for row in rows if row.get("file_id")}
    return {"accepted": len(session), "saved": saved_count, "queued": len(rows),
            "limit": _v165_limit(target), "session_saved": session_saved,
            "session_queued": len(queued_ids & session)}
'''


MEDIA_PROGRESS = r'''async def _v165_progress_job(context):
    import asyncio as _v165_asyncio
    data = context.job.data
    status = None
    for _attempt in range(10):
        status = await _v165_asyncio.to_thread(
            _v165_status, data["card_id"], data["target"], data.get("session_ids") or [])
        if status["queued"] == 0:
            break
        await _v165_asyncio.sleep(0.25)
    duplicates = int(data.get("duplicates") or 0)
    rejected = int(data.get("rejected") or 0)
    if status["saved"] is None:
        text = "Принято сейчас: %d · очередь: %d · дубли: %d." % (
            status["accepted"], status["queued"], duplicates)
    else:
        text = ("Принято сейчас: %d · сохранено сейчас: %d · всего в карточке: "
                "%d/%d · очередь: %d · отклонено как дубль: %d") % (
            status["accepted"], int(status.get("session_saved") or 0),
            status["saved"], status["limit"], status["queued"], duplicates)
        if rejected:
            text += " · лимит: %d" % rejected
    await context.bot.send_message(
        chat_id=data["chat_id"], text=text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "Открыть карточку", callback_data="car_open:%d" % data["card_id"])]]))
'''


MEDIA_SCHEDULE = r'''def _v165_schedule_progress(context, msg, card_id, target, session_ids, duplicates=0, rejected=0):
    key = "%s:%s:%s" % (msg.chat_id, int(card_id), str(target))
    old = _V165_PROGRESS.get(key)
    if old is not None:
        try:
            old.schedule_removal()
        except Exception:
            pass
    if context.job_queue:
        _V165_PROGRESS[key] = context.job_queue.run_once(
            _v165_progress_job, when=0.35,
            data={"chat_id": msg.chat_id, "card_id": int(card_id), "target": str(target),
                  "session_ids": list(session_ids), "duplicates": int(duplicates),
                  "rejected": int(rejected)},
            name="crm-photo-progress-" + key)
'''


VOICE_FIELDS = r'''def _v167_voice_explicit_fields(text, allowed):
    """Deterministic RU/UA/EN automotive fields; ambiguous input writes nothing."""
    import re as _v167_re
    value = str(text or "").casefold().replace("ё", "е")
    for words in ("две тысячи", "дві тисячі", "дві тисячі", "two thousand"):
        value = value.replace(words, "2000")
    result, permitted = {}, set(allowed or ())
    if "fuel" in permitted:
        fuel = None
        if _v167_re.search(r"(?<![a-zа-яіїєґ0-9])(?:l\s*p\s*i|л\s*п\s*и|[еэ]л\s*пи\s*ай)(?![a-zа-яіїєґ0-9])", value):
            fuel = "LPI"
        elif _v167_re.search(r"(?<![a-zа-яіїєґ0-9])(?:l\s*p\s*g|л\s*п\s*г|[еэ]л\s*пи\s*джи)(?![a-zа-яіїєґ0-9])", value):
            fuel = "LPG"
        elif _v167_re.search(r"\b(?:дизел[ьяь]?|дизельне|diesel)\b", value):
            fuel = "diesel"
        elif _v167_re.search(r"\b(?:бензин|бензинов|gasoline|petrol)\b", value):
            fuel = "gasoline"
        elif _v167_re.search(r"\b(?:гибрид|гібрид|hybrid)\b", value):
            fuel = "hybrid"
        elif _v167_re.search(r"\b(?:электро|електро|electric)\b", value):
            fuel = "electric"
        elif _v167_re.search(r"(?:топлив|палив|fuel)\s*(?:[:=\-–—]|тип)?\s*газ\b", value):
            fuel = "LPG"
        if fuel:
            result["fuel"] = fuel
    if "engine_cc" in permitted:
        label = r"(?:объ?ем(?:\s+двигателя)?|об['’]?єм(?:\s+двигуна)?|двигател[ья]|двигун[ау]?|мотор[ау]?|engine(?:\s+volume)?)"
        match = (_v167_re.search(label + r"\s*(?:[:=\-–—]|составляет|становить|is)?\s*(\d+(?:[.,]\d+)?)", value)
                 or _v167_re.search(r"(\d+(?:[.,]\d+)?)\s*(?:см3|см³|cc|куб(?:ов)?)?\s*" + label, value))
        if match:
            try:
                number = float(match.group(1).replace(",", "."))
                cc = int(round(number * 1000 if number < 20 else number))
                if 400 <= cc <= 12000:
                    result["engine_cc"] = cc
            except Exception:
                pass
    if "color" in permitted:
        colors = {
            "бел": "белый", "білий": "белый", "біла": "белый", "white": "белый",
            "черн": "чёрный", "чорн": "чёрный", "black": "чёрный",
            "серебр": "серебристый", "сріб": "серебристый", "silver": "серебристый",
            "сер": "серый", "сір": "серый", "gray": "серый", "grey": "серый",
            "красн": "красный", "червон": "красный", "red": "красный",
            "син": "синий", "blue": "синий", "зелен": "зелёный", "green": "зелёный",
            "желт": "жёлтый", "жовт": "жёлтый", "yellow": "жёлтый",
            "беж": "бежевый", "beige": "бежевый", "корич": "коричневый", "brown": "коричневый",
        }
        match = _v167_re.search(
            r"(?:(?:цвет|колір|color)\s*(?:[:=\-–—]|автомобиля|авто|машины|car)?\s*([a-zа-яіїєґ]+)|"
            r"([a-zа-яіїєґ]+)\s+(?:цвет|колір|color))", value)
        if match:
            word = next((item for item in match.groups() if item), "")
            for prefix, normalized in colors.items():
                if word.startswith(prefix):
                    result["color"] = normalized
                    break
    return result
'''


TRANSCRIBE = r'''def transcribe(file_bytes: bytes, filename="voice.ogg") -> str:
    """Single multilingual STT call; language is auto-detected."""
    key = openai_key()
    if not key:
        return ""
    try:
        hint = ("Automotive CRM. Russian, Ukrainian and English mixed speech. "
                "Preserve VIN, LPI, LPG, engine volume, mileage, colors and prices. "
                + str(TRANSCRIBE_HINT or ""))
        result = _post_multipart(
            "https://api.openai.com/v1/audio/transcriptions",
            {"Authorization": f"Bearer {key}"},
            {"model": TRANSCRIBE_MODEL, "prompt": hint},
            "file", filename, file_bytes)
        return (result.get("text") or "").strip()
    except urllib.error.HTTPError as e:
        logging.error(f"Расшифровка не удалась: {e.code} {e.read()[:200]}")
    except Exception as e:
        logging.error(f"Расшифровка не удалась: {e}")
    return ""
'''


CLIENT_HELPERS = r'''# CRM-ONLINE-GUARD-001-V1.3: fast client callbacks and cached read-only catalog.
_V168_CATALOG_CACHE = []
_V168_CATALOG_AT = 0.0


async def _v168_client_ack(query, *args, **kwargs):
    try:
        import crm_online_guard as _v168_guard
        import asyncio as _v168_asyncio
        action = "client_" + str(getattr(query, "data", "callback") or "callback").split(":", 1)[0]
        if args or kwargs:
            token, _started = _v168_guard.start_operation(action)
            try:
                await _v168_asyncio.wait_for(query.answer(*args, **kwargs), timeout=0.75)
                _v168_guard.finish_operation(token, "ack")
            except Exception as exc:
                _v168_guard.finish_operation(token, "continued", type(exc).__name__)
        else:
            token, _started = await _v168_guard.safe_callback_answer(query, action)
            _v168_guard.finish_operation(token, "ack")
    except Exception:
        try:
            await query.answer(*args, **kwargs)
        except Exception:
            pass


async def _v168_client_heartbeat(context):
    try:
        import crm_online_guard as _v168_guard
        _v168_guard.heartbeat("client_bot")
    except Exception:
        pass


def _v168_client_guard_start(app):
    try:
        import crm_online_guard as _v168_guard
        _v168_guard.start_supervisor()
        _v168_guard.heartbeat("client_bot")
        if app.job_queue and not app.job_queue.get_jobs_by_name("crm-guard-heartbeat-client"):
            app.job_queue.run_repeating(
                _v168_client_heartbeat, interval=1.0, first=0.1,
                name="crm-guard-heartbeat-client")
    except Exception as exc:
        log.warning("Client guard unavailable: %s", exc)
'''


CLIENT_CATALOG_CARS = r'''def catalog_cars():
    """Fast bounded read-only catalog with last-good in-process fallback."""
    import sqlite3 as _v168_sqlite3
    import time as _v168_time
    global _V168_CATALOG_CACHE, _V168_CATALOG_AT
    started = _v168_time.monotonic()
    try:
        con = _v168_sqlite3.connect(
            "file:/home/Carix/crm.db?mode=ro", uri=True, timeout=0.45)
        con.row_factory = _v168_sqlite3.Row
        try:
            rows = con.execute(
                "SELECT * FROM cars WHERE published=1 ORDER BY id DESC LIMIT 50").fetchall()
        finally:
            con.close()
        result = [dict(row) for row in rows]
        _V168_CATALOG_CACHE = result
        _V168_CATALOG_AT = _v168_time.time()
        try:
            import crm_online_guard as _v168_guard
            _v168_guard.record_timing("client_catalog_db", _v168_time.monotonic() - started)
        except Exception:
            pass
        return result
    except Exception as exc:
        log.warning("Каталог bounded read: %s", exc)
        try:
            import crm_online_guard as _v168_guard
            _v168_guard.record_timing(
                "client_catalog_db", _v168_time.monotonic() - started,
                "cache", detail=type(exc).__name__)
        except Exception:
            pass
        return list(_V168_CATALOG_CACHE)
'''


CLIENT_CATALOG = r'''async def catalog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import asyncio as _v168_asyncio
    import time as _v168_time
    started = _v168_time.monotonic()
    q = update.callback_query
    if q:
        await _v168_client_ack(q)
        msg = q.message
    else:
        msg = update.effective_message
    cars = await _v168_asyncio.to_thread(catalog_cars)
    if not cars:
        await ST.send(
            msg, "<b>Сейчас машины в подборе</b>\n\n"
            "Все свободные автомобили уже закреплены за клиентами.\n"
            "Напишите, что ищете — покажем варианты с аукциона и зафиксируем цену до покупки.",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Подобрать авто", callback_data="c_order")],
                [InlineKeyboardButton("Написать в WhatsApp", url=WHATSAPP)],
                [InlineKeyboardButton("← Назад", callback_data="c_menu")]]))
    else:
        S, U = _schema(), _cars_ui()
        try:
            import card_render as CR
        except Exception:
            CR = None
        cards = [U.card_of(item["id"]) or item for item in cars[:12]]
        rows = []
        for card in cards:
            price = S.money(U._int(card.get("price_uah")))
            rows.append([InlineKeyboardButton(
                "%s — %s" % (podpis(card)[:26], price),
                callback_data="c_car:%d" % card["id"])])
        rows.append([InlineKeyboardButton("Не нашли подходящую?", callback_data="c_order")])
        rows.append([InlineKeyboardButton("← Назад", callback_data="c_menu")])
        await ST.send(msg, tablica_mashin(cars, S, U, CR), parse_mode="HTML",
                      reply_markup=InlineKeyboardMarkup(rows))
    try:
        import crm_online_guard as _v168_guard
        _v168_guard.record_timing("client_catalog", _v168_time.monotonic() - started)
    except Exception:
        pass
    raise ApplicationHandlerStop
'''


CLIENT_CAR_SCREEN = r'''async def car_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import asyncio as _v168_asyncio
    import time as _v168_time
    started = _v168_time.monotonic()
    q = update.callback_query
    await _v168_client_ack(q)
    cid = int(q.data.split(":")[-1])
    U, S = _cars_ui(), _schema()
    card = U.card_of(cid)
    if not card or not card.get("published"):
        await ST.send(q.message, "Эта машина уже недоступна.",
                      reply_markup=InlineKeyboardMarkup([[
                          InlineKeyboardButton("← В каталог", callback_data="c_cars")]]))
        raise ApplicationHandlerStop
    etap = S.stage_of(card.get("status"))
    try:
        import card_render as CR
        sold = CR.prodano(card)
    except Exception:
        sold = False
    rows = []
    page_button = knopka_stranicy(card)
    if page_button:
        rows.append([page_button])
    if sold:
        rows.append([InlineKeyboardButton("Хочу такую же под заказ", callback_data="c_order")])
    elif etap >= 3:
        rows.append([InlineKeyboardButton("Забронировать за %s" % BRON,
                                          callback_data="c_bron:%d" % cid)])
    elif card.get("sea_container"):
        rows.append([InlineKeyboardButton("Отследить контейнер",
                                          url="https://www.searates.com/container/tracking/")])
    rows.append([InlineKeyboardButton("Задать вопрос по этой машине",
                                      callback_data="c_vopros:%d" % cid)])
    if card.get("vin"):
        rows.append([InlineKeyboardButton(
            "Проверить VIN", url="https://www.vindecoderz.com/EN/check-lookup/" + str(card["vin"]))])
    rows.append([InlineKeyboardButton("← Все машины", callback_data="c_cars")])
    # The operational screen is sent first. Media is a non-blocking tail.
    await ST.send(q.message, U.client_view(card), parse_mode="HTML",
                  disable_web_page_preview=True,
                  reply_markup=InlineKeyboardMarkup(rows))
    try:
        import crm_online_guard as _v168_guard
        _v168_guard.record_timing("client_car_screen", _v168_time.monotonic() - started, card_id=cid)
    except Exception:
        pass

    async def media_tail():
        try:
            await otmetit_prosmotr(context, q.from_user, card)
        except Exception as exc:
            log.warning("View analytics: %s", exc)
        try:
            import card_render
            await card_render.send_photos(q.message, card)
            await card_render.send_videos(q.message, card)
        except Exception as exc:
            log.warning("Client media tail: %s", exc)
    try:
        context.application.create_task(media_tail(), update=update)
    except Exception:
        _v168_asyncio.create_task(media_tail())
    raise ApplicationHandlerStop
'''


def build_cars(source: str) -> str:
    if MARKER in source:
        return source
    source = insert_before(source, "voice_change_plan", CARS_HELPERS)
    source = replace_definition(source, "condition_screen", CONDITION_SCREEN, EXPECTED_DEFS["condition_screen"])
    source = replace_definition(source, "stage_menu", STAGE_MENU, EXPECTED_DEFS["stage_menu"])
    source = replace_definition(source, "_v165_key", MEDIA_KEY, EXPECTED_DEFS["_v165_key"])
    source = replace_definition(source, "_v165_spool_enqueue", MEDIA_ENQUEUE, EXPECTED_DEFS["_v165_spool_enqueue"])
    source = replace_definition(source, "_v166_drain_owned", MEDIA_DRAIN, EXPECTED_DEFS["_v166_drain_owned"])
    source = replace_definition(source, "_v165_status", MEDIA_STATUS, EXPECTED_DEFS["_v165_status"])
    source = replace_definition(source, "_v165_progress_job", MEDIA_PROGRESS, EXPECTED_DEFS["_v165_progress_job"])
    source = replace_definition(source, "_v165_schedule_progress", MEDIA_SCHEDULE, EXPECTED_DEFS["_v165_schedule_progress"])
    source = replace_definition(source, "_v167_voice_explicit_fields", VOICE_FIELDS,
                                EXPECTED_DEFS["_v167_voice_explicit_fields"])

    catch = segment(source, "catch_message")
    if sha(catch.encode()) != EXPECTED_DEFS["catch_message"]:
        raise InstallError("TARGET_SHA:catch_message")
    catch = replace_once(catch, "hard_deadline = started + 15.0", "hard_deadline = started + 4.65", "voice_deadline")
    catch = replace_once(catch, 'thinking = await msg.reply_text("🎤 Распознаю, до 15 секунд...")',
                         'thinking = await msg.reply_text("🎤 Распознаю, до 5 секунд...")', "voice_ack")
    catch = replace_once(
        catch,
        """        if not ai.voice_enabled():
            if marker in seen:
                seen.remove(marker)
            await thinking.edit_text("Расшифровка голоса не настроена. Карточка не изменена.")
            raise ApplicationHandlerStop

        if msg.voice:""",
        """        if not ai.voice_enabled():
            if marker in seen:
                seen.remove(marker)
            await thinking.edit_text("Расшифровка голоса не настроена. Карточка не изменена.")
            raise ApplicationHandlerStop
        try:
            import crm_online_guard as _v168_guard
            if not _v168_guard.circuit_allows("stt"):
                if marker in seen:
                    seen.remove(marker)
                await thinking.edit_text(
                    "Сервис распознавания восстанавливается. Карточка не изменена; повторите через 15 секунд.")
                raise ApplicationHandlerStop
        except ApplicationHandlerStop:
            raise
        except Exception:
            pass

        if msg.voice:""", "voice_circuit")
    catch = replace_once(catch, "timeout=min(3.0, remaining)", "timeout=min(1.1, remaining)", "voice_download")
    catch = replace_once(catch, '"Голос не распознан за 15 секунд. Карточка не изменена; повторите короче."',
                         '"Голос не распознан за 5 секунд. Карточка не изменена; повторите короче."', "voice_timeout_text")
    catch = replace_once(
        catch,
        """        voice_elapsed = time.monotonic() - started
        if not input_text:""",
        """        voice_elapsed = time.monotonic() - started
        try:
            import crm_online_guard as _v168_guard
            _v168_guard.circuit_result("stt", bool(input_text))
            _v168_guard.record_timing(
                "crm_voice", voice_elapsed, "ok" if input_text else "empty",
                card_id=active_id)
        except Exception:
            pass
        if not input_text:""", "voice_telemetry")
    old_parse = """            allowed = fast.car_fields(ai_filter)
            data = {}
            data.update(local_ocr.fields_from_text(input_text, allowed))
            data.update(fast.fast_text_data(input_text, ai_filter))
            if data:
                data = fast.clean_car(fast.parsed_from_data(data), ai_filter, "")
            data = {key: value for key, value in (data or {}).items()
                    if key in allowed and value not in (None, "", [])}
            folded = input_text.casefold()
            explicit_data = _v167_voice_explicit_fields(input_text, allowed)
            data.update(explicit_data)
            # CRM-VOICE-FIELDS-003: voice is an explicit command for the open card.
            # Text keeps the conservative keyword rule; voice may replace named values.
            override = bool(voice_object) or any(word in folded for word in (
                "измени", "исправь", "замени", "поменяй", "скорректируй"))
            changes, skipped = voice_change_plan(card, data, allowed, override)"""
    new_parse = """            schema_allowed = set(fast.car_fields(ai_filter))
            card = card_of(card["id"]) or card
            correction = _v168_is_correction(input_text)
            if correction:
                allowed = _v168_named_fields(input_text, schema_allowed)
            else:
                allowed = {field for field in schema_allowed if _v168_empty(card.get(field))}
            data = {}
            if allowed:
                data.update(local_ocr.fields_from_text(input_text, allowed))
                data.update(fast.fast_text_data(input_text, ai_filter))
                if data:
                    data = fast.clean_car(fast.parsed_from_data(data), ai_filter, "")
                data = {key: value for key, value in (data or {}).items()
                        if key in allowed and value not in (None, "", [])}
                data.update(_v167_voice_explicit_fields(input_text, allowed))
            changes, skipped = voice_change_plan(card, data, allowed, correction)"""
    catch = replace_once(catch, old_parse, new_parse, "missing_only_parse")
    old_write = """                    db.update_card_field("cars", card["id"], field, new, user_id)
                    applied.append((field, old, new))"""
    new_write = """                    ok, reason = _v168_cas_write(
                        card["id"], field, old, new, user_id, correction)
                    if ok:
                        applied.append((field, old, new))
                    elif reason in ("filled", "conflict"):
                        skipped.append(field)"""
    catch = replace_once(catch, old_write, new_write, "voice_cas")
    old_photo = """                _v166_result = _v165_spool_enqueue(
                    wait["card_id"], target, file_id, user_id, tag)
                _v166_session_ids = wait.setdefault("_fast_session_ids", [])
                if (_v166_result.get("state") != "limit"
                        and file_id not in _v166_session_ids):
                    _v166_session_ids.append(file_id)
                _v165_schedule_progress(
                    context, msg, wait["card_id"], target, _v166_session_ids)"""
    new_photo = """                unique_id = getattr(msg.photo[-1], "file_unique_id", None) or file_id
                _v166_result = _v165_spool_enqueue(
                    wait["card_id"], target, file_id, user_id, tag,
                    unique_id=unique_id, message_id=msg.message_id)
                _v166_session_ids = wait.setdefault("_fast_session_ids", [])
                state = _v166_result.get("state")
                if state == "accepted" and file_id not in _v166_session_ids:
                    _v166_session_ids.append(file_id)
                elif str(state).startswith("duplicate"):
                    wait["_fast_session_duplicates"] = int(
                        wait.get("_fast_session_duplicates") or 0) + 1
                elif state == "limit":
                    wait["_fast_session_rejected"] = int(
                        wait.get("_fast_session_rejected") or 0) + 1
                _v165_schedule_progress(
                    context, msg, wait["card_id"], target, _v166_session_ids,
                    wait.get("_fast_session_duplicates", 0),
                    wait.get("_fast_session_rejected", 0))"""
    catch = replace_once(catch, old_photo, new_photo, "photo_idempotency")
    source = replace_definition(source, "catch_message", catch, EXPECTED_DEFS["catch_message"])
    register = segment(source, "register")
    if sha(register.encode()) != EXPECTED_DEFS["cars_register"]:
        raise InstallError("TARGET_SHA:cars_register")
    register = replace_once(register, "def register(app):\n    ensure_columns()",
                            "def register(app):\n    ensure_columns()\n    _v168_start_guard(app, \"crm_bot\")", "cars_guard_start")
    source = replace_definition(source, "register", register, EXPECTED_DEFS["cars_register"])
    ack_count = source.count("await q.answer(")
    if ack_count < 10:
        raise InstallError("CRM_ACK_COUNT:%d" % ack_count)
    source = source.replace("await q.answer(", "await _v168_ack(q,")
    return source


def build_client(source: str) -> str:
    if MARKER in source:
        return source
    source = insert_before(source, "catalog_cars", CLIENT_HELPERS)
    source = replace_definition(source, "catalog_cars", CLIENT_CATALOG_CARS,
                                EXPECTED_DEFS["client_catalog_cars"])
    source = replace_definition(source, "catalog", CLIENT_CATALOG,
                                EXPECTED_DEFS["client_catalog"])
    source = replace_definition(source, "car_screen", CLIENT_CAR_SCREEN,
                                EXPECTED_DEFS["client_car_screen"])
    register = segment(source, "register")
    if sha(register.encode()) != EXPECTED_DEFS["client_register"]:
        raise InstallError("TARGET_SHA:client_register")
    register = replace_once(
        register, "    VLADELEC = vladelec\n    g = -1",
        "    VLADELEC = vladelec\n    _v168_client_guard_start(app)\n    g = -1", "client_guard_start")
    source = replace_definition(source, "register", register,
                                EXPECTED_DEFS["client_register"])
    count = source.count("await q.answer(")
    if count < 4:
        raise InstallError("CLIENT_ACK_COUNT:%d" % count)
    source = source.replace("await q.answer(", "await _v168_client_ack(q,")
    return source


def build_db(source: str) -> str:
    if DB_MARKER in source:
        return source
    if sha(source.encode()) != EXPECTED["db.py"]:
        raise InstallError("SOURCE_SHA:db.py")
    source = replace_once(
        source, "ZAMOK_OZHIDANIE = 20",
        "ZAMOK_OZHIDANIE = 2.0  # CRM-DB-BOUNDED-QUEUE-001",
        "db_queue_deadline")
    connection = segment(source, "Soedinenie")
    if sha(connection.encode()) != EXPECTED_DEFS["db_connection_class"]:
        raise InstallError("TARGET_SHA:Soedinenie")
    connection = replace_once(
        connection, "for attempt in range(5):", "for attempt in range(4):",
        "db_commit_attempts")
    connection = replace_once(
        connection, "if attempt == 4:", "if attempt == 3:",
        "db_commit_last_attempt")
    connection = replace_once(
        connection, "_ua_time.sleep(0.15 * (2 ** attempt))",
        "_ua_time.sleep(0.08 * (2 ** attempt))", "db_commit_backoff")
    source = replace_definition(
        source, "Soedinenie", connection, EXPECTED_DEFS["db_connection_class"])
    source = replace_definition(
        source, "connect", DB_CONNECT, EXPECTED_DEFS["db_connect"])
    source = replace_definition(
        source, "update_card_field", DB_UPDATE_FIELD,
        EXPECTED_DEFS["db_update_card_field"])
    return source


def validate_candidates(candidates):
    cars = candidates["cars_ui.py"]
    required = (
        MARKER, "_v168_cas_write", "hard_deadline = started + 4.65",
        "correction = _v168_is_correction", "state == \"accepted\"",
        "media_mark", "Принято сейчас", "safe_callback_answer",
    )
    if any(value not in cars for value in required):
        raise InstallError("CARS_CONTRACT_MISSING")
    if "override = bool(voice_object)" in cars or "до 15 секунд" in segment(cars, "catch_message"):
        raise InstallError("OLD_VOICE_CONTRACT_PRESENT")
    if "await q.answer(" in cars:
        raise InstallError("UNSAFE_CRM_ACK_PRESENT")
    client = candidates["client_ui.py"]
    if any(value not in client for value in (
            MARKER, "_v168_client_ack", "mode=ro", "media_tail", "client_catalog")):
        raise InstallError("CLIENT_CONTRACT_MISSING")
    if "await q.answer(" in client:
        raise InstallError("UNSAFE_CLIENT_ACK_PRESENT")
    if '"language": "ru"' in candidates["ai.py"]:
        raise InstallError("HARDCODED_STT_LANGUAGE")
    db_source = candidates["db.py"]
    if any(value not in db_source for value in (
            DB_MARKER, "ZAMOK_OZHIDANIE = 2.0", "PRAGMA busy_timeout=450",
            "_queue_on_busy", "enqueue_field_update")):
        raise InstallError("DB_BOUNDED_QUEUE_CONTRACT")
    guard_source = candidates["crm_online_guard.py"]
    if any(value not in guard_source for value in (
            "enqueue_field_update", "field_spool", "FIELD_SPOOL_PATH")):
        raise InstallError("FIELD_SPOOL_CONTRACT")
    for name in ("run_all.py", "team_bot.py", "lead_bot.py"):
        if "drop_pending_updates=True" in candidates[name]:
            raise InstallError("DROP_PENDING_PRESENT:" + name)
    for name, source in candidates.items():
        compile(source, str(PATHS[name]), "exec")
    compile(candidates["crm_online_guard.py"], str(PATHS["crm_online_guard.py"]), "exec")


def build_all(original):
    sources = {name: data.decode("utf-8") for name, data in original.items()
               if name != "crm_online_guard.py"}
    if MARKER in sources["cars_ui.py"]:
        candidates = dict(sources)
    else:
        for name, expected in EXPECTED.items():
            if sha(original[name]) != expected:
                raise InstallError("SOURCE_SHA:" + name)
        candidates = dict(sources)
        candidates["cars_ui.py"] = build_cars(sources["cars_ui.py"])
        candidates["ai.py"] = replace_definition(
            sources["ai.py"], "transcribe", TRANSCRIBE, EXPECTED_DEFS["transcribe"])
        candidates["client_ui.py"] = build_client(sources["client_ui.py"])
        for name in ("run_all.py", "team_bot.py", "lead_bot.py"):
            if "drop_pending_updates=True" not in candidates[name]:
                raise InstallError("DROP_PENDING_BASELINE:" + name)
            candidates[name] = candidates[name].replace(
                "drop_pending_updates=True", "drop_pending_updates=False")
    if DB_MARKER not in candidates["db.py"]:
        candidates["db.py"] = build_db(sources["db.py"])
    guard = safe_read(GUARD_STAGED).decode("utf-8")
    if MARKER not in guard:
        raise InstallError("GUARD_MARKER_MISSING")
    candidates["crm_online_guard.py"] = guard
    validate_candidates(candidates)
    return candidates


def rollback(directory: pathlib.Path | None = None):
    if directory is None:
        options = sorted(path for path in BACKUPS.glob("*") if path.is_dir())
        if not options:
            raise InstallError("BACKUP_MISSING")
        directory = options[-1]
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for name, info in manifest["files"].items():
        target = PATHS[name]
        if info["existed"]:
            data = (directory / name).read_bytes()
            if sha(data) != info["sha256"]:
                raise InstallError("BACKUP_SHA:" + name)
            atomic_write(target, data, info.get("mode", 0o644))
        elif target.exists():
            target.unlink()
    value = {"task_id": "task_067", "contract_id": CONTRACT,
             "status": "PASS", "mode": "ROLLBACK",
             "backup_dir": str(directory), "finished_at_utc": utc_now()}
    atomic_json(ROLLBACK_RECEIPT, value)
    return value


def shadow_main():
    value = {"task_id": "task_067", "contract_id": CONTRACT,
             "status": "FAIL", "mode": "SHADOW_COMPILE_NO_PRODUCTION_WRITE",
             "llm_tokens": 0, "crm_db_write": False, "site_write": False,
             "media_write": False, "errors": [], "started_at_utc": utc_now()}
    try:
        with open(DEPLOY_LOCK, "a+", encoding="utf-8") as outer, open(TASK_LOCK, "a+", encoding="utf-8") as inner:
            fcntl.flock(outer.fileno(), fcntl.LOCK_EX)
            fcntl.flock(inner.fileno(), fcntl.LOCK_EX)
            before = db_state()
            original = {name: safe_read(path, required=(name != "crm_online_guard.py"))
                        for name, path in PATHS.items()}
            candidates = build_all(original)
            after = db_state()
            if before.get("quick_check") != "ok" or after.get("quick_check") != "ok":
                raise InstallError("DB_QUICK_CHECK")
            value.update({"status": "PASS", "db_before": before, "db_after": after,
                          "candidate_sha256": {
                              name: sha(source.encode()) for name, source in candidates.items()}})
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
    value["finished_at_utc"] = utc_now()
    atomic_json(SHADOW_RECEIPT, value)
    return 0 if value["status"] == "PASS" else 1


def main():
    if "--shadow" in sys.argv:
        return shadow_main()
    if "--rollback" in sys.argv:
        with open(DEPLOY_LOCK, "a+", encoding="utf-8") as outer, open(TASK_LOCK, "a+", encoding="utf-8") as inner:
            fcntl.flock(outer.fileno(), fcntl.LOCK_EX)
            fcntl.flock(inner.fileno(), fcntl.LOCK_EX)
            rollback()
        return 0
    receipt = {"task_id": "task_067", "contract_id": CONTRACT,
               "status": "FAIL", "mode": "ATOMIC_PRODUCTION_INSTALL",
               "llm_tokens": 0, "crm_db_write": False, "site_write": False,
               "media_write": False, "errors": [], "started_at_utc": utc_now()}
    backup_dir = None
    installed = False
    try:
        with open(DEPLOY_LOCK, "a+", encoding="utf-8") as outer, open(TASK_LOCK, "a+", encoding="utf-8") as inner:
            fcntl.flock(outer.fileno(), fcntl.LOCK_EX)
            fcntl.flock(inner.fileno(), fcntl.LOCK_EX)
            before_db = db_state()
            original = {name: safe_read(path, required=(name != "crm_online_guard.py"))
                        for name, path in PATHS.items()}
            candidates = build_all(original)
            changed = [name for name, source in candidates.items()
                       if original.get(name) != source.encode("utf-8")]
            already = not changed
            receipt["already_applied"] = already
            receipt["changed_files"] = changed
            if not already:
                stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                backup_dir = BACKUPS / stamp
                backup_dir.mkdir(parents=True, exist_ok=False)
                manifest = {"contract_id": CONTRACT, "created_at_utc": utc_now(), "files": {}}
                for name, data in original.items():
                    path = PATHS[name]
                    existed = data is not None
                    mode = stat.S_IMODE(path.lstat().st_mode) if existed else 0o644
                    manifest["files"][name] = {
                        "existed": existed, "sha256": sha(data) if existed else None, "mode": mode}
                    if existed:
                        atomic_write(backup_dir / name, data, mode)
                atomic_json(backup_dir / "manifest.json", manifest)
                for name in ("crm_online_guard.py", "db.py", "ai.py", "client_ui.py", "cars_ui.py",
                             "run_all.py", "team_bot.py", "lead_bot.py"):
                    atomic_write(PATHS[name], candidates[name].encode("utf-8"), 0o644)
                installed = True
            after_db = db_state()
            if before_db.get("quick_check") != "ok" or after_db.get("quick_check") != "ok":
                raise InstallError("DB_QUICK_CHECK")
            receipt.update({
                "status": "PASS", "backup_dir": str(backup_dir) if backup_dir else None,
                "db_before": before_db, "db_after": after_db,
                "files_after": {name: sha(safe_read(path)) for name, path in PATHS.items()},
            })
    except Exception as exc:
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc))
        if installed and backup_dir:
            try:
                receipt["rollback"] = rollback(backup_dir)
            except Exception as rollback_exc:
                receipt["errors"].append("ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc))
    receipt["finished_at_utc"] = utc_now()
    atomic_json(RECEIPT, receipt)
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
