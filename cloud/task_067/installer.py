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
VOICE_RESTORE_MARKER = "CRM-VOICE-RESTORE-01-V1.3.1"
INPUT_DB_MARKER = "CRM-INPUT-DB-ROUTES-02-V1.3.2"
CONTAINER_MARKER = "CRM-CONTAINER-ROUTES-02-V1.3.2"
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
    "konteyner.py": ROOT / "konteyner.py",
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

# Exact live v1.3 definitions audited read-only on 29.08.2026 before the
# voice-restoration hotfix.  They make the incremental upgrade fail closed.
VOICE_V13_DEFS = {
    "catch_message": "2b02ec1cf0cc649618f88de40fbb3a8e37d325828b4e925c9b15dc75859a850c",
    "transcribe": "731c2b98652fb0ddecc3711d81b78c8eca5e84084327e6539b1c58d8e1d56fc4",
}

INPUT_V13_DEFS = {
    "set_field": "8f6ea6455a0f950573e4433f3bc273471c617b679d37ae96b803cfbf492440e8",
    "apply_value": "18c8dfc9f7cb6f5d4cf4e41a0fe02dbd07be9b21f142a072e90bfac602f7388b",
    "stage_set": "f5f962f3bace303d314e82cf053e95000d601e9e827e7cd181a4bd3e0a4d650e",
    "register": "eae5c22d3d823e6524b6ec2823e03d46deb2d38dbfeb80e189508aadc41cc5e3",
    "container_write": "fc1309f3d134b0730a569182fa2ef19fda15325d77dd0bd0361d412ae8f8a519",
    "container_accept": "e82be6158f5f67025b88e5e17f70e77b814e0c239acbfbb23bc4e124baa02ee7",
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
    # Never contend with the live CRM merely to deploy Python source.  SQLite
    # integrity is checked by postcheck immediately after the old process has
    # released its transaction during the bounded Always-On restart.
    info = DB_PATH.stat()
    if not DB_PATH.is_file() or info.st_size <= 0:
        raise InstallError("DB_FILE_MISSING_OR_EMPTY")
    return {
        "quick_check": "deferred_to_post_restart_postcheck",
        "mode": "metadata_only_no_sqlite_connection",
        "size_bytes": info.st_size,
        "mtime_ns": info.st_mtime_ns,
    }


DB_CONNECT = r'''def connect():
    # CRM-DB-BOUNDED-QUEUE-001: a user operation never waits 20 seconds.
    conn = sqlite3.connect(DB_FILE, timeout=2.0, factory=Soedinenie)
    conn.row_factory = sqlite3.Row
    # Journal mode is a database-level deployment setting. Reissuing it on
    # every hot-path connection may itself request a lock and stall callbacks.
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
    started = _ua_time.monotonic()
    old_value = None
    try:
        old = get_card(table, card_id)
        old_value = old.get(field) if old else None
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


SET_FIELD_RESTORE = r'''# CRM-INPUT-DB-ROUTES-02-V1.3.2: return durable-write state to callers.
def set_field(card_id, field, value, actor_id):
    """Write one non-empty field and expose whether it entered the durable queue."""
    if value in (None, "", []):
        return {"queued": False, "skipped": True}
    return db.update_card_field("cars", int(card_id), field, value, actor_id)
'''


APPLY_VALUE_RESTORE = r'''# CRM-INPUT-DB-ROUTES-02-V1.3.2: selected field accepts text or voice scalar.
def apply_value(card_id, field, raw, actor_id):
    """Normalize the selected CRM field, commit/queue it, then report truthfully."""
    value = (raw or "").strip()
    if not value:
        return False, "Пустое значение не записываю."

    if field == "eta_days":
        n = _v169_parse_number(value)
        if n is None:
            return False, "Пришлите число дней, например 45."
        if n < 0 or n > 400:
            return False, "Слишком большой срок. Пришлите число дней до 400."
        eta = _date.today() + _td(days=n)
        first = set_field(card_id, "eta_manual", eta.isoformat(), actor_id)
        second = set_field(card_id, "days_to_kyiv", n, actor_id)
        queued = any(isinstance(item, dict) and item.get("queued")
                     for item in (first, second))
        if queued:
            return True, "Принято: %d дней. Сохраняю из очереди." % n
        return True, "До прибытия %d дней · %s" % (n, eta.strftime("%d.%m.%Y"))

    if field in NUMERIC:
        num = _v169_parse_number(value)
        if num is None:
            return False, "Не разобрал число. Пришлите цифрами или словами."
        if field == "engine_cc" and int(num) < 20:
            import re as _v170_re
            liters = _v170_re.search(r"(?<!\d)(\d+(?:[.,]\d+)?)(?!\d)", value)
            if liters:
                try:
                    num = int(round(float(liters.group(1).replace(",", ".")) * 1000))
                except Exception:
                    pass
        limits = {
            "year": (1900, 2100), "engine_cc": (400, 12000),
            "mileage_km": (0, 2_000_000), "price_uah": (0, 100_000_000),
        }
        low, high = limits.get(field, (0, 1_000_000_000))
        if not low <= int(num) <= high:
            return False, "Число вне допустимого диапазона для этого поля."
        result = set_field(card_id, field, int(num), actor_id)
        if isinstance(result, dict) and result.get("queued"):
            return True, "Принято: %s. Сохраняю из очереди." % S.num(int(num))
        saved = card_of(card_id) or {}
        if str(saved.get(field) or "") != str(int(num)):
            return False, "Запись не подтверждена. Значение оставлено для повторной попытки."
        return True, "Записано: %s" % S.num(int(num))

    if field == "vin":
        vin = value.upper().replace(" ", "")
        ok, msg = S.check_vin(vin)
        if not ok:
            return False, "VIN не принят: %s" % msg
        result = set_field(card_id, field, vin, actor_id)
        if isinstance(result, dict) and result.get("queued"):
            return True, "VIN принят. Сохраняю из очереди."
        return True, "Записано: %s" % vin

    result = set_field(card_id, field, value, actor_id)
    if isinstance(result, dict) and result.get("queued"):
        return True, "Принято. Сохраняю из очереди."
    return True, "Записано."
'''


STAGE_SET_RESTORE = r'''# CRM-INPUT-DB-ROUTES-02-V1.3.2: stage writes never leak DB locks.
async def stage_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q,)
    drop_wait(context)
    _, cid, code = q.data.split(":")
    cid = int(cid)
    card_before = card_of(cid) or {}
    status_result = set_field(cid, "status", code, q.from_user.id)

    if code == "ge_waiting" and not card_before.get("ge_arrived"):
        set_field(cid, "ge_arrived", _date.today().isoformat(), q.from_user.id)
    if code == "ge_to_kyiv":
        released = card_before.get("ge_released")
        if not released:
            released = _date.today().isoformat()
            set_field(cid, "ge_released", released, q.from_user.id)
        if not card_before.get("eta_manual"):
            try:
                base = _dt.strptime(str(released)[:10], "%Y-%m-%d").date()
            except Exception:
                base = _date.today()
            eta = base + _td(days=DNEI_GRUZIA_UKRAINA)
            set_field(cid, "eta_manual", eta.isoformat(), q.from_user.id)
            set_field(cid, "days_to_kyiv", DNEI_GRUZIA_UKRAINA, q.from_user.id)

    rows = [
        [InlineKeyboardButton("🚚 Доставка и этапы", callback_data="car_stage:%d" % cid)],
        [InlineKeyboardButton("← Вернуться к карточке", callback_data="car_open:%d" % cid)],
    ]
    if isinstance(status_result, dict) and status_result.get("queued"):
        await q.message.reply_text(
            "Этап принят: %s. База занята; сохраняю из надёжной очереди."
            % _v170_ferry_label(S.status_label(code)),
            reply_markup=InlineKeyboardMarkup(rows))
        raise ApplicationHandlerStop

    card = card_of(cid) or {}
    saved = card.get("status")
    if saved != code:
        await q.message.reply_text(
            "Запись этапа не подтверждена. Сейчас: %s"
            % _v170_ferry_label(S.status_label(saved)),
            reply_markup=InlineKeyboardMarkup(rows))
        raise ApplicationHandlerStop
    lines = [card.get("auto_number") or "#%d" % cid,
             "Этап сохранён: %s" % _v170_ferry_label(S.status_label(saved))]
    left, eta = eta_of(card)
    if left is not None:
        lines.append("До выдачи в Киеве: %d дней · %s" % (
            left, eta.strftime("%d.%m.%Y")))
    await q.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))
    raise ApplicationHandlerStop
'''


CONTAINER_HELPERS = r'''# CRM-CONTAINER-ROUTES-02-V1.3.2: bounded ACK and durable writes.
async def _v170_cont_ack(q):
    import asyncio as _v170_asyncio
    try:
        await _v170_asyncio.wait_for(q.answer(), timeout=0.7)
        return True
    except Exception:
        return False
'''


CONTAINER_WRITE = r'''def _pisat(cid, pole, znachenie, kto):
    return db.update_card_field("cars", int(cid), pole, znachenie, kto)
'''


CONTAINER_ACCEPT = r'''async def prinyat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wait = context.user_data.get("cont_wait")
    if not wait:
        return
    msg = update.effective_message
    if not msg or not msg.text:
        return
    cid, pole = wait["card_id"], wait["field"]
    kto, syroe = update.effective_user.id, msg.text.strip()

    if pole == "sea_container":
        znachenie = re.sub(r"[^A-Za-z0-9]", "", syroe).upper()
        if not OBRAZEC_NOMERA.match(znachenie):
            await msg.reply_text(
                "Это не похоже на номер контейнера. Нужно 4–20 латинских букв/цифр.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                    "Отмена", callback_data="cont_menu:%d" % cid)]]))
            raise ApplicationHandlerStop
    elif pole == "sea_date_out":
        znachenie = _v_iso(syroe)
        if not znachenie:
            await msg.reply_text("Не понял дату. Нужен вид ДД.ММ.ГГГГ.")
            raise ApplicationHandlerStop
    else:
        parsed = None
        try:
            import cars_ui as _v170_cars
            parsed = _v170_cars._v169_parse_number(syroe)
        except Exception:
            pass
        if parsed is not None and 0 <= int(parsed) <= 900:
            znachenie = time.strftime(
                "%Y-%m-%d", time.localtime(time.time() + 7 * 3600 + int(parsed) * 86400))
        else:
            znachenie = _v_iso(syroe)
        if not znachenie:
            await msg.reply_text("Не понял значение. Пришлите число дней или ДД.ММ.ГГГГ.")
            raise ApplicationHandlerStop

    try:
        result = _pisat(cid, pole, znachenie, kto)
    except Exception as exc:
        log.warning("konteyner: write failed %s: %s", pole, exc)
        await msg.reply_text("Не удалось принять значение. Оно не потеряно — повторите после возврата.")
        raise ApplicationHandlerStop
    context.user_data.pop("cont_wait", None)

    rows = InlineKeyboardMarkup([[InlineKeyboardButton(
        "← К карточке", callback_data="car_open:%d" % cid)]])
    if isinstance(result, dict) and result.get("queued"):
        await msg.reply_text(
            "Принято: %s. База занята; сохраняю из надёжной очереди." % znachenie,
            reply_markup=rows)
        raise ApplicationHandlerStop

    posle = _karta(cid) or {}
    stalo = str(posle.get(pole) or "").strip()
    if stalo != str(znachenie):
        context.user_data["cont_wait"] = wait
        await msg.reply_text("Запись не подтверждена. Пришлите значение ещё раз.", reply_markup=rows)
        raise ApplicationHandlerStop
    if pole == "sea_container":
        podpis = "Номер контейнера сохранён: %s" % stalo
    elif pole == "sea_date_out":
        podpis = "Дата отправления сохранена: %s" % (_krasivo(stalo) or stalo)
    else:
        podpis = "Срок прибытия сохранён: %s" % (_krasivo(stalo) or stalo)
    _peresobrat()
    text, kb = _ekran(posle)
    await msg.reply_text(podpis + "\n\n" + text,
                         parse_mode="HTML", reply_markup=kb)
    raise ApplicationHandlerStop
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


TRANSCRIBE_RESTORE = r'''def transcribe(file_bytes: bytes, filename="voice.ogg") -> str:
    """Last-known-good short-voice STT for the Russian-speaking owner.

    English automotive terms and Ukrainian words remain in the prompt.  A
    second transcription is not hidden here: one Telegram voice means one STT
    request, so billing and idempotency stay predictable.
    """
    # CRM-VOICE-RESTORE-01-V1.3.1
    key = openai_key()
    if not key:
        return ""
    try:
        hint = ("Автомобильная CRM. Короткая русская речь владельца с возможными "
                "украинскими и английскими терминами. Точно сохраняй VIN, LPI, LPG, "
                "пробег, цену, статус, объём двигателя, цвет, привод и КПП. "
                + str(TRANSCRIBE_HINT or ""))
        result = _post_multipart(
            "https://api.openai.com/v1/audio/transcriptions",
            {"Authorization": f"Bearer {key}"},
            {"model": TRANSCRIBE_MODEL, "language": "ru", "prompt": hint},
            "file", filename, file_bytes)
        return (result.get("text") or "").strip()
    except urllib.error.HTTPError as e:
        logging.error(f"Расшифровка не удалась: {e.code} {e.read()[:200]}")
    except Exception as e:
        logging.error(f"Расшифровка не удалась: {e}")
    return ""
'''


VOICE_RESTORE_HELPERS = r'''# CRM-VOICE-RESTORE-01-V1.3.1: semantic fallback for missing fields only.
def _v169_voice_schema(fast, ai_filter):
    # condition_text is already present in ai_filter.  price_uah and status are
    # real CRM fields that the previous fast-only whitelist accidentally lost.
    return set(fast.car_fields(ai_filter)) | {"price_uah", "status"}


def _v170_ferry_label(label):
    """One CRM display vocabulary: Море/В море -> Паром/На пароме."""
    import re as _v170_re
    value = str(label or "")
    value = _v170_re.sub(r"(?i)\bв\s+море\b", "На пароме", value)
    value = _v170_re.sub(r"(?i)\bна\s+море\b", "На пароме", value)
    value = _v170_re.sub(r"(?i)\bморе\b", "Паром", value)
    return value


def _v170_anchor_ferry_terms():
    """Anchor labels once without changing persisted status codes."""
    try:
        S.STAGES = [(number, "Паром" if int(number) == 2 else _v170_ferry_label(name))
                    for number, name in S.STAGES]
        S.STATUSES = {
            code: (spec[0], _v170_ferry_label(spec[1]))
            for code, spec in S.STATUSES.items()
        }
    except Exception as exc:
        log.warning("CRM ferry vocabulary not anchored: %s", exc)


def _v169_parse_number(text):
    import re as _v169_re
    value = str(text or "").casefold().replace("ё", "е")
    digit = _v169_re.search(r"(?<!\d)(\d{1,3}(?:[ .]\d{3})+|\d+(?:[.,]\d+)?)(?!\d)", value)
    if digit:
        raw = digit.group(1).replace(" ", "")
        try:
            number = float(raw.replace(",", "."))
        except ValueError:
            number = 0
        if _v169_re.search(r"\b(?:тыс\w*|тис\w*|thousand|k)\b", value) and number < 10000:
            number *= 1000
        return int(round(number)) if number > 0 else None
    words = {
        "один": 1, "одна": 1, "одну": 1, "одна": 1, "раз": 1,
        "два": 2, "две": 2, "дві": 2, "три": 3, "четыре": 4, "чотири": 4,
        "пять": 5, "п'ять": 5, "шість": 6, "шесть": 6, "семь": 7,
        "сім": 7, "восемь": 8, "вісім": 8, "девять": 9, "дев'ять": 9,
        "десять": 10, "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13,
        "четырнадцать": 14, "пятнадцать": 15, "шестнадцать": 16,
        "семнадцать": 17, "восемнадцать": 18, "девятнадцать": 19,
        "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
        "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90,
        "сто": 100, "двести": 200, "триста": 300, "четыреста": 400,
        "пятьсот": 500, "шестьсот": 600, "семьсот": 700,
        "восемьсот": 800, "девятьсот": 900,
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    }
    total = current = 0
    seen = False
    for token in _v169_re.findall(r"[a-zа-яіїєґ'’]+", value):
        token = token.replace("’", "'")
        if token in ("hundred",):
            current = max(1, current) * 100
            seen = True
        elif token.startswith(("тысяч", "тисяч")) or token == "thousand":
            total += max(1, current) * 1000
            current = 0
            seen = True
        elif token in words:
            current += words[token]
            seen = True
    number = total + current
    return number if seen and number > 0 else None


def _v169_status_code(text):
    import re as _v169_re
    value = str(text or "").casefold().replace("ё", "е")
    for code, spec in getattr(S, "STATUSES", {}).items():
        try:
            label = str(spec[1]).casefold().replace("ё", "е")
        except Exception:
            label = ""
        if label and (label in value or value in label):
            return code
    stage = None
    if _v169_re.search(r"коре|korea", value):
        stage = 1
    elif _v169_re.search(r"паром|море|sea|ferry|ship", value):
        stage = 2
    elif _v169_re.search(r"грузи|georgia|поти|батуми", value):
        stage = 3
    elif _v169_re.search(r"киев|київ|kyiv|kiev", value):
        stage = 4
    if stage is not None:
        for code, spec in getattr(S, "STATUSES", {}).items():
            try:
                if int(spec[0]) == stage:
                    return code
            except Exception:
                pass
    return None


def _v169_extra_fields(text, allowed):
    import re as _v169_re
    permitted = set(allowed or ())
    original = str(text or "").strip()
    value = original.casefold().replace("ё", "е")
    result = {}
    if "mileage_km" in permitted:
        match = (_v169_re.search(
            r"(?:пробег(?![а-я])|пробіг(?![а-яіїєґ])|mileage\b|odometer\b)"
            r"\s*(?:[:=\-–—]|составляет|is)?\s*([^,;.]+)",
            value)
            or _v169_re.search(
                r"([^,;.]{1,90}?)\s*(?:км|километр\w*|кілометр\w*|km)?\s*"
                r"(?:пробега|пробігу|mileage|odometer)\b", value))
        if match:
            number = _v169_parse_number(match.group(1))
            if number and 0 < number <= 2_000_000:
                result["mileage_km"] = number
    if "price_uah" in permitted:
        match = (_v169_re.search(
            r"(?:цена(?:\s+продажи)?|стоимость|ціна(?:\s+продажу)?|sale\s+price|price)"
            r"\s*(?:[:=\-–—]|составляет|is)?\s*([^,;.]+)", value)
            or _v169_re.search(
                r"([^,;.]{1,80}?)\s*(?:доллар\w*|usd|\$)?\s*"
                r"(?:цена|стоимость|ціна|sale\s+price|price)\b", value))
        if match:
            number = _v169_parse_number(match.group(1))
            if number and 100 <= number <= 100_000_000:
                result["price_uah"] = number
    if "condition_text" in permitted:
        match = _v169_re.search(
            r"(?:описание|опиши|опис|тех(?:ническое)?\s+состояние|description)"
            r"\s*(?:[:=\-–—]|автомобиля|машины|car|такое)?\s*(.{3,})$", original,
            _v169_re.I)
        if match:
            result["condition_text"] = match.group(1).strip()[:3500]
    if "status" in permitted and _v169_re.search(
            r"статус|этап|етап|stage|коре|паром|море|грузи|киев|київ|ferry|sea|georgia|kyiv",
            value):
        status = _v169_status_code(value)
        if status:
            result["status"] = status
    return result


def _v169_semantic_fields(text, allowed, timeout=1.8):
    """One minimal Claude Haiku call, used only after the zero-token path is empty."""
    import json as _v169_json
    import re as _v169_re
    import assistant as _v169_assistant
    import ai_fast_schema as _v169_fast
    import ai_filter as _v169_filter
    permitted = set(allowed or ())
    if not permitted or not _v169_assistant.enabled():
        return {}
    labels = {field: LABELS_ALL.get(field, field) for field in sorted(permitted)}
    system = (
        "Ты точный парсер голоса CRM автомобиля. Верни только один JSON-объект без markdown. "
        "Ключи могут быть только из whitelist пользователя. Извлекай только сказанное, ничего "
        "не выдумывай. Числа словами преобразуй в числа. LPI не заменяй на LPG. Для status "
        "верни услышанное название этапа. Если данных нет, верни {}."
    )
    prompt = ("Whitelist недостающих полей: " +
              _v169_json.dumps(labels, ensure_ascii=False, sort_keys=True) +
              "\nРаспознанная речь: " + str(text or "")[:1200])
    answer = _v169_assistant.ask(
        prompt, card=None, timeout=max(0.4, float(timeout)), web=False,
        system=system, max_tokens=260)
    if not answer:
        return {}
    cleaned = _v169_re.sub(r"^```(?:json)?|```$", "", answer.strip(), flags=_v169_re.M).strip()
    match = _v169_re.search(r"\{.*\}", cleaned, _v169_re.S)
    if not match:
        return {}
    try:
        raw = _v169_json.loads(match.group(0))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    raw = {str(key): value for key, value in raw.items()
           if str(key) in permitted and value not in (None, "", [], {})}
    standard = set(_v169_fast.car_fields(_v169_filter)) & permitted
    normalized = {}
    if standard:
        value = _v169_fast.clean_car(
            _v169_fast.parsed_from_data({key: raw[key] for key in standard if key in raw}),
            _v169_filter, str(text or ""))
        normalized.update({key: item for key, item in value.items()
                           if key in standard and item not in (None, "", [])})
    if "price_uah" in permitted and "price_uah" in raw:
        number = _v169_parse_number(raw["price_uah"])
        if number and 100 <= number <= 100_000_000:
            normalized["price_uah"] = number
    if "condition_text" in permitted and "condition_text" in raw:
        value = str(raw["condition_text"]).strip()
        if value:
            normalized["condition_text"] = value[:3500]
    if "status" in permitted and "status" in raw:
        status = _v169_status_code(raw["status"])
        if status:
            normalized["status"] = status
    return normalized
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


def upgrade_v13_voice(source: str) -> str:
    """Incrementally restore semantic voice parsing on the live v1.3 source."""
    if VOICE_RESTORE_MARKER in source:
        return source
    if MARKER not in source:
        raise InstallError("VOICE_UPGRADE_REQUIRES_V13")
    current_catch = segment(source, "catch_message")
    if sha(current_catch.encode()) != VOICE_V13_DEFS["catch_message"]:
        raise InstallError("VOICE_V13_SHA:catch_message")

    # Correct field aliases in the explicit-correction router.
    source = replace_once(
        source,
        '        "transmission": r"кпп|коробк|трансмис|transmission|automatic|manual|автомат|механик",',
        '        "gearbox": r"кпп|коробк|трансмис|transmission|automatic|manual|автомат|механик",',
        "voice_gearbox_schema")
    source = replace_once(
        source,
        '        "description": r"описан|опис|description",',
        '        "condition_text": r"описан|опис|состояни|description",',
        "voice_description_schema")
    source = insert_before(source, "voice_change_plan", VOICE_RESTORE_HELPERS)

    catch = current_catch
    old_parse = """            schema_allowed = set(fast.car_fields(ai_filter))
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
    new_parse = """            schema_allowed = _v169_voice_schema(fast, ai_filter)
            card = card_of(card["id"]) or card
            correction = _v168_is_correction(input_text)
            if correction:
                allowed = _v168_named_fields(input_text, schema_allowed)
            else:
                allowed = {field for field in schema_allowed if _v168_empty(card.get(field))}

            # Parse against the complete safe schema first, so a repeated value
            # is reported as already filled instead of falsely "not recognized".
            data_all = {}
            if schema_allowed:
                data_all.update(local_ocr.fields_from_text(input_text, schema_allowed))
                data_all.update(fast.fast_text_data(input_text, ai_filter))
                if data_all:
                    data_all = fast.clean_car(
                        fast.parsed_from_data(data_all), ai_filter, input_text)
                data_all = {key: value for key, value in (data_all or {}).items()
                            if key in schema_allowed and value not in (None, "", [])}
                data_all.update(_v167_voice_explicit_fields(input_text, schema_allowed))
                data_all.update(_v169_extra_fields(input_text, schema_allowed))
            data = {key: value for key, value in data_all.items() if key in allowed}
            already = [key for key in data_all
                       if key not in allowed and not _v168_empty(card.get(key))]
            semantic_used = False

            # Restore the original meaningful AI behavior only when the fast,
            # zero-token path found nothing.  The AI sees the transcript and
            # missing-field whitelist, never the full card or media.
            if not data and not already and allowed:
                try:
                    import crm_online_guard as _v169_guard
                    semantic_allowed = _v169_guard.circuit_allows("voice_semantic")
                except Exception:
                    semantic_allowed = True
                remaining = hard_deadline - time.monotonic() - 0.25
                if semantic_allowed and remaining >= 0.55:
                    semantic_used = True
                    semantic_started = time.monotonic()
                    semantic_error = False
                    try:
                        semantic = await asyncio.wait_for(
                            asyncio.to_thread(
                                _v169_semantic_fields, input_text, allowed,
                                min(1.8, remaining)),
                            timeout=remaining)
                    except Exception:
                        semantic = {}
                        semantic_error = True
                    data.update({key: value for key, value in (semantic or {}).items()
                                 if key in allowed and value not in (None, "", [])})
                    try:
                        _v169_guard.circuit_result("voice_semantic", not semantic_error)
                        _v169_guard.record_timing(
                            "crm_voice_semantic", time.monotonic() - semantic_started,
                            "ok" if data else "empty", card_id=card["id"])
                    except Exception:
                        pass
            voice_elapsed = time.monotonic() - started
            voice_note = ("1 смысловой AI-вызов" if semantic_used
                          else "0 LLM-вызовов")
            try:
                import crm_online_guard as _v169_quality_guard
                _v169_quality_guard.record_timing(
                    "crm_voice_total", voice_elapsed,
                    "ok" if (data or already) else "unrecognized",
                    card_id=card["id"], detail=("semantic" if semantic_used else "fast"))
            except Exception:
                pass
            changes, skipped = voice_change_plan(card, data, allowed, correction)"""
    catch = replace_once(catch, old_parse, new_parse, "voice_semantic_restore")
    catch = replace_once(
        catch,
        '                    "✅ %s дополнена:\\n%s\\n\\n⏱ %.1f с · 1 расшифровка · 0 LLM-токенов"\n'
        '                    % (number, "\\n".join(lines), voice_elapsed or 0.0),',
        '                    "✅ %s дополнена:\\n%s\\n\\n⏱ %.1f с · 1 расшифровка · %s"\n'
        '                    % (number, "\\n".join(lines), voice_elapsed or 0.0, voice_note),',
        "voice_cost_truth")
    catch = replace_once(
        catch, "            elif data and skipped and not override:",
        "            elif (skipped or already) and not correction:",
        "voice_undefined_override")
    catch = replace_once(
        catch,
        '''                await thinking.edit_text(
                    "Не распознал поле CRM. Назовите поле и значение, например: "
                    "«привод передний». Карточка не изменена."
                )''',
        '''                missing_names = ", ".join(
                    LABELS_ALL.get(field, field) for field in sorted(allowed))
                heard = str(input_text or "").replace("\\n", " ").strip()[:220]
                await thinking.edit_text(
                    "Я услышал: «%s». Из доступных незаполненных полей не удалось "
                    "уверенно извлечь значение. Ещё нужны: %s. Карточка не изменена."
                    % (heard or "—", missing_names or "—")
                )''',
        "voice_diagnostic_reply")
    source = replace_definition(
        source, "catch_message", catch, VOICE_V13_DEFS["catch_message"])
    return source


def upgrade_v13_ai(source: str) -> str:
    if VOICE_RESTORE_MARKER in source:
        return source
    return replace_definition(
        source, "transcribe", TRANSCRIBE_RESTORE, VOICE_V13_DEFS["transcribe"])


def upgrade_v13_input(source: str) -> str:
    """Repair selected-field values, stage writes and CRM ferry vocabulary."""
    if INPUT_DB_MARKER in source:
        return source
    if VOICE_RESTORE_MARKER not in source:
        raise InstallError("INPUT_UPGRADE_REQUIRES_VOICE_RESTORE")
    source = replace_definition(
        source, "set_field", SET_FIELD_RESTORE, INPUT_V13_DEFS["set_field"])
    source = replace_definition(
        source, "apply_value", APPLY_VALUE_RESTORE, INPUT_V13_DEFS["apply_value"])
    source = replace_definition(
        source, "stage_set", STAGE_SET_RESTORE, INPUT_V13_DEFS["stage_set"])
    register = segment(source, "register")
    register = replace_once(
        register,
        '    _v168_start_guard(app, "crm_bot")',
        '    _v168_start_guard(app, "crm_bot")\n    _v170_anchor_ferry_terms()',
        "ferry_vocabulary_startup")
    source = replace_definition(
        source, "register", register, INPUT_V13_DEFS["register"])
    return source


def build_container(source: str) -> str:
    """Make all container callbacks bounded and all writes queue-aware."""
    if CONTAINER_MARKER in source:
        return source
    source = insert_before(source, "_pisat", CONTAINER_HELPERS)
    source = replace_definition(
        source, "_pisat", CONTAINER_WRITE, INPUT_V13_DEFS["container_write"])
    source = replace_definition(
        source, "prinyat", CONTAINER_ACCEPT, INPUT_V13_DEFS["container_accept"])
    if source.count("await q.answer()") < 5:
        raise InstallError("CONTAINER_ACK_BASELINE")
    source = source.replace("await q.answer()", "await _v170_cont_ack(q)")
    if "await q.answer()" in source:
        raise InstallError("CONTAINER_UNSAFE_ACK")
    return source


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
        VOICE_RESTORE_MARKER, "_v169_semantic_fields",
        'schema_allowed = _v169_voice_schema(fast, ai_filter)',
        INPUT_DB_MARKER, "_v170_anchor_ferry_terms",
        "Сохраняю из очереди", "_v169_parse_number(value)",
    )
    if any(value not in cars for value in required):
        raise InstallError("CARS_CONTRACT_MISSING")
    if ("override = bool(voice_object)" in cars
            or "not override" in segment(cars, "catch_message")
            or "до 15 секунд" in segment(cars, "catch_message")):
        raise InstallError("OLD_VOICE_CONTRACT_PRESENT")
    if "await q.answer(" in cars:
        raise InstallError("UNSAFE_CRM_ACK_PRESENT")
    container = candidates["konteyner.py"]
    if any(value not in container for value in (
            CONTAINER_MARKER, "_v170_cont_ack", "return db.update_card_field",
            "База занята; сохраняю из надёжной очереди")):
        raise InstallError("CONTAINER_CONTRACT_MISSING")
    if "await q.answer()" in container:
        raise InstallError("UNSAFE_CONTAINER_ACK_PRESENT")
    client = candidates["client_ui.py"]
    if any(value not in client for value in (
            MARKER, "_v168_client_ack", "mode=ro", "media_tail", "client_catalog")):
        raise InstallError("CLIENT_CONTRACT_MISSING")
    if "await q.answer(" in client:
        raise InstallError("UNSAFE_CLIENT_ACK_PRESENT")
    if (VOICE_RESTORE_MARKER not in candidates["ai.py"]
            or '"language": "ru"' not in candidates["ai.py"]):
        raise InstallError("LAST_KNOWN_GOOD_STT_MISSING")
    db_source = candidates["db.py"]
    if any(value not in db_source for value in (
            DB_MARKER, "ZAMOK_OZHIDANIE = 2.0", "PRAGMA busy_timeout=450",
            "_queue_on_busy", "enqueue_field_update")):
        raise InstallError("DB_BOUNDED_QUEUE_CONTRACT")
    if "PRAGMA journal_mode" in segment(db_source, "connect"):
        raise InstallError("DB_HOT_JOURNAL_SWITCH_PRESENT")
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
        candidates["cars_ui.py"] = upgrade_v13_voice(candidates["cars_ui.py"])
        candidates["ai.py"] = upgrade_v13_ai(candidates["ai.py"])
    else:
        for name, expected in EXPECTED.items():
            if sha(original[name]) != expected:
                raise InstallError("SOURCE_SHA:" + name)
        candidates = dict(sources)
        candidates["cars_ui.py"] = build_cars(sources["cars_ui.py"])
        candidates["ai.py"] = replace_definition(
            sources["ai.py"], "transcribe", TRANSCRIBE, EXPECTED_DEFS["transcribe"])
        candidates["cars_ui.py"] = upgrade_v13_voice(candidates["cars_ui.py"])
        candidates["ai.py"] = upgrade_v13_ai(candidates["ai.py"])
        candidates["client_ui.py"] = build_client(sources["client_ui.py"])
        for name in ("run_all.py", "team_bot.py", "lead_bot.py"):
            if "drop_pending_updates=True" not in candidates[name]:
                raise InstallError("DROP_PENDING_BASELINE:" + name)
            candidates[name] = candidates[name].replace(
                "drop_pending_updates=True", "drop_pending_updates=False")
    candidates["cars_ui.py"] = upgrade_v13_input(candidates["cars_ui.py"])
    candidates["konteyner.py"] = build_container(candidates["konteyner.py"])
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
            if (before.get("size_bytes", 0) <= 0
                    or after.get("size_bytes", 0) <= 0):
                raise InstallError("DB_METADATA_GATE")
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
                             "konteyner.py", "run_all.py", "team_bot.py", "lead_bot.py"):
                    atomic_write(PATHS[name], candidates[name].encode("utf-8"), 0o644)
                installed = True
            after_db = db_state()
            if (before_db.get("size_bytes", 0) <= 0
                    or after_db.get("size_bytes", 0) <= 0):
                raise InstallError("DB_METADATA_GATE")
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
