#!/usr/bin/env python3
"""Atomic production repair for CRM voice mileage, media opening and sea status."""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import py_compile
import shutil
import stat
import tempfile
import time


ROOT = Path("/home/Carix")
TASK_ROOT = ROOT / "autopilot_inbox" / "cloud" / "task_089_crm_voice_photo_repair"
BACKUPS = ROOT / "backups" / "task_089_crm_voice_photo_repair"
LOCK = ROOT / ".ua_art_production_writer.lock"
RECEIPT = TASK_ROOT / "install_receipt.json"
ROLLBACK_RECEIPT = TASK_ROOT / "rollback_receipt.json"
MARKER = "CRM-VOICE-PHOTO-STAGE-REPAIR-089-V1"
TARGETS = {
    "cars_ui.py": ROOT / "cars_ui.py",
    "local_ocr.py": ROOT / "local_ocr.py",
    "team_bot.py": ROOT / "team_bot.py",
    "konteyner.py": ROOT / "konteyner.py",
    "card_render.py": ROOT / "card_render.py",
}
EXPECTED = {
    "cars_ui.py": "825e1febb2193ccf47293c383624a222de57f3cf9e9bcaf5d5e6a0243dd23629",
    "local_ocr.py": "7eb4de0597fb6064c8e5f7b56c00d673e8d964630481b3fe5511bb20363770b5",
    "team_bot.py": "b640a4dd0dffcc249dbc0f7ce46fb977fca58babc6a3dd1d8c0cf10d3819f03f",
    "konteyner.py": "2d56a970fb76c782f0d5caebd65b6a7ffd44fd3ad1278a775bf641cffd39080d",
    "card_render.py": "00e288065f2c19ed633cf21e7698fcd65c1d614e403740b1bbab01752d20ab25",
}


class RepairError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_text(value: str) -> str:
    return sha_bytes(value.encode("utf-8"))


def regular(path: Path) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise RepairError("UNSAFE_TARGET:" + path.name)


def atomic_bytes(path: Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".task089-", dir=path.parent)
    try:
        if mode is not None:
            os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except Exception:
        try:
            os.close(descriptor)
        except Exception:
            pass
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def atomic_json(path: Path, value: dict) -> None:
    atomic_bytes(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        0o600,
    )


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RepairError("REPLACE_COUNT:%s:%d" % (label, count))
    return source.replace(old, new, 1)


def replace_definition(source: str, name: str, replacement: str) -> str:
    tree = ast.parse(source)
    nodes = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(nodes) != 1:
        raise RepairError("DEFINITION_COUNT:%s:%d" % (name, len(nodes)))
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [replacement.rstrip() + "\n\n"]
    return "".join(lines)


OPEN_CARD = r'''async def open_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open the card immediately; media delivery is bounded and cannot freeze CRM."""
    import asyncio as _v189_asyncio
    q = update.callback_query
    await _v168_ack(q,)
    drop_wait(context)
    staff = db.get_staff(q.from_user.id)
    cid = q.data.split(":")[-1]
    card = card_of(cid)
    if not card:
        await q.message.reply_text("Карточка не найдена.")
        raise ApplicationHandlerStop

    # CRM-VOICE-PHOTO-STAGE-REPAIR-089-V1: the card itself is always first.
    await q.message.reply_text(
        render(card, staff), parse_mode="HTML", reply_markup=card_kb(card, staff),
        disable_web_page_preview=True)
    context.user_data["car_last"] = int(cid)
    context.user_data["car_voice_active"] = int(cid)
    try:
        await _v189_asyncio.wait_for(CR.send_photos(q.message, card), timeout=9.0)
    except _v189_asyncio.TimeoutError:
        log.warning("CRM photos opening timeout card=%s", cid)
    except Exception as exc:
        log.warning("CRM photos opening failed card=%s error=%s", cid, exc)
    try:
        await _v189_asyncio.wait_for(CR.send_videos(q.message, card), timeout=6.0)
    except _v189_asyncio.TimeoutError:
        log.warning("CRM videos opening timeout card=%s", cid)
    except Exception as exc:
        log.warning("CRM videos opening failed card=%s error=%s", cid, exc)
    raise ApplicationHandlerStop'''


MEDIA_SEND = r'''async def _otpravit(msg, albums):
    """Send bounded media batches; one stale Telegram file can never freeze a card."""
    import asyncio as _v189_asyncio
    import logging as _v189_logging
    deadline = _v189_asyncio.get_running_loop().time() + 8.0
    sent = 0
    # CRM-VOICE-PHOTO-STAGE-REPAIR-089-V1: at most 30 media items per opening.
    for album in list(albums)[:3]:
        remaining = deadline - _v189_asyncio.get_running_loop().time()
        if remaining <= 0.15:
            break
        try:
            if len(album) > 1:
                await _v189_asyncio.wait_for(
                    msg.reply_media_group(album), timeout=min(4.0, remaining))
            else:
                await _v189_asyncio.wait_for(
                    msg.reply_photo(album[0].media), timeout=min(4.0, remaining))
            sent += len(album)
        except _v189_asyncio.TimeoutError:
            _v189_logging.getLogger(__name__).warning("CRM media batch timeout")
            break
        except Exception as exc:
            _v189_logging.getLogger(__name__).warning(
                "CRM media batch skipped: %s", type(exc).__name__)
            continue
    return sent'''


CONTAINER_STATUS = r'''async def posle_statusa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save sea status before any optional prompt; never leave the button spinning."""
    import asyncio as _v189_asyncio
    q = update.callback_query
    try:
        chasti = q.data.split(":")
        cid = int(chasti[1])
        status = chasti[2]
    except Exception:
        return
    if status not in ("sea_loaded", "sea_transit"):
        return
    card = _karta(cid)
    if not card:
        return
    try:
        # CRM-VOICE-PHOTO-STAGE-REPAIR-089-V1: write before any Telegram request.
        _pisat(cid, "status", status, q.from_user.id)
        saved = _karta(cid)
        if not saved or saved.get("status") != status:
            raise RuntimeError("STATUS_READBACK_MISMATCH")
    except Exception as exc:
        log.error("konteyner: status save failed card=%s status=%s error=%s",
                  cid, status, exc)
        try:
            await _v189_asyncio.wait_for(
                q.message.reply_text("Не удалось сохранить этап. Повторите ещё раз."),
                timeout=3.0)
        except Exception:
            pass
        from telegram.ext import ApplicationHandlerStop as _V189Stop
        raise _V189Stop

    try:
        await _v189_asyncio.wait_for(q.answer("Этап сохранён"), timeout=1.2)
    except Exception:
        pass
    rows = []
    text = ("Этап сохранён: Загружено в контейнер" if status == "sea_loaded"
            else "Этап сохранён: В пути")
    if not (saved.get("sea_container") or "").strip():
        rows.append([InlineKeyboardButton("Ввести номер контейнера",
                                          callback_data="cont_num:%d" % cid)])
    if not (saved.get("sea_date_out") or "").strip():
        rows.append([InlineKeyboardButton("Ввести дату отправления",
                                          callback_data="cont_date:%d" % cid)])
    rows.append([InlineKeyboardButton("← Вернуться к карточке",
                                      callback_data="car_open:%d" % cid)])
    try:
        await _v189_asyncio.wait_for(
            q.message.reply_text(text, reply_markup=InlineKeyboardMarkup(rows)),
            timeout=4.0)
    except Exception as exc:
        log.warning("konteyner: status confirmation skipped: %s", exc)
    from telegram.ext import ApplicationHandlerStop as _V189Stop
    raise _V189Stop'''


MILEAGE_HELPERS = r'''# CRM-VOICE-PHOTO-STAGE-REPAIR-089-V1: natural RU/UK mileage parsing.
_V189_MILEAGE_UNITS = {
    "ноль": 0, "один": 1, "одна": 1, "два": 2, "две": 2, "три": 3,
    "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8,
    "девять": 9, "нуль": 0, "один": 1, "одна": 1, "два": 2, "дві": 2,
    "три": 3, "чотири": 4, "п'ять": 5, "пять": 5, "шість": 6,
    "сім": 7, "вісім": 8, "дев'ять": 9, "девять": 9,
}
_V189_MILEAGE_TEENS = {
    "десять": 10, "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13,
    "четырнадцать": 14, "пятнадцать": 15, "шестнадцать": 16,
    "семнадцать": 17, "восемнадцать": 18, "девятнадцать": 19,
    "десять": 10, "одинадцять": 11, "дванадцять": 12, "тринадцять": 13,
    "чотирнадцять": 14, "п'ятнадцять": 15, "пятнадцять": 15,
    "шістнадцять": 16, "сімнадцять": 17, "вісімнадцять": 18,
    "дев'ятнадцять": 19, "девятнадцять": 19,
}
_V189_MILEAGE_TENS = {
    "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
    "шестьдесят": 60, "семьдесят": 70, "восемьдесят": 80, "девяносто": 90,
    "двадцять": 20, "тридцять": 30, "сорок": 40, "п'ятдесят": 50,
    "пятдесят": 50, "шістдесят": 60, "сімдесят": 70,
    "вісімдесят": 80, "дев'яносто": 90, "девяносто": 90,
}
_V189_MILEAGE_HUNDREDS = {
    "сто": 100, "двести": 200, "триста": 300, "четыреста": 400,
    "пятьсот": 500, "шестьсот": 600, "семьсот": 700,
    "восемьсот": 800, "девятьсот": 900, "двісті": 200,
    "чотириста": 400, "п'ятсот": 500, "пятсот": 500,
    "шістсот": 600, "сімсот": 700, "вісімсот": 800,
    "дев'ятсот": 900, "девятсот": 900,
}


def _v189_number_words(text):
    tokens = re.findall(r"[a-zа-яіїєґ']+", str(text or "").casefold().replace("’", "'"))
    total = 0
    current = 0
    seen = False
    for token in tokens:
        if token in _V189_MILEAGE_UNITS:
            current += _V189_MILEAGE_UNITS[token]
            seen = True
        elif token in _V189_MILEAGE_TEENS:
            current += _V189_MILEAGE_TEENS[token]
            seen = True
        elif token in _V189_MILEAGE_TENS:
            current += _V189_MILEAGE_TENS[token]
            seen = True
        elif token in _V189_MILEAGE_HUNDREDS:
            current += _V189_MILEAGE_HUNDREDS[token]
            seen = True
        elif token.startswith(("тыс", "тис")) or token in ("k", "tuc"):
            total += max(1, current) * 1000
            current = 0
            seen = True
        elif seen:
            break
    value = total + current
    return value if seen and 0 < value <= 2_000_000 else None


def _v189_mileage_value(text):
    folded = str(text or "").casefold().replace("ё", "е").replace("’", "'")
    keyword = re.search(
        r"\b(?:пробег|пробіг|mileage|kilometr\w*)\b\s*[:=\-]?\s*([^,;\n]{1,80})",
        folded,
    )
    if keyword:
        segment = keyword.group(1)
        number = re.search(
            r"(?<!\d)(\d{1,3}(?:[ .]\d{3})+|\d{1,7})\s*"
            r"(k|к|tuc|тыс\w*|тис\w*)?",
            segment,
        )
        if number:
            value = int(re.sub(r"\D", "", number.group(1)))
            if number.group(2) and value < 10_000:
                value *= 1000
            if 0 < value <= 2_000_000:
                return value
        words = _v189_number_words(segment)
        if words:
            return words
    suffix = re.search(
        r"(?<!\d)(\d{1,3}(?:[ .]\d{3})+|\d{1,7})\s*"
        r"(tuc|тыс\w*|тис\w*)?\.?\s*(km|км)\b",
        folded,
    )
    if suffix:
        value = int(re.sub(r"\D", "", suffix.group(1)))
        if suffix.group(2) and value < 10_000:
            value *= 1000
        if 0 < value <= 2_000_000:
            return value
    return None
'''


def build_cars(source: str) -> str:
    if MARKER in source:
        return source
    old_allowed = '''            correction = _v168_is_correction(input_text)\n            if correction:\n                allowed = _v168_named_fields(input_text, schema_allowed)\n            else:\n                allowed = {field for field in schema_allowed if _v168_empty(card.get(field))}\n'''
    new_allowed = '''            correction = _v168_is_correction(input_text)\n            named_fields = _v168_named_fields(input_text, schema_allowed)\n            explicit_override = bool(correction or named_fields)\n            if named_fields:\n                allowed = named_fields\n            else:\n                allowed = {field for field in schema_allowed if _v168_empty(card.get(field))}\n'''
    source = replace_once(source, old_allowed, new_allowed, "voice_allowed")
    source = replace_once(
        source,
        "changes, skipped = voice_change_plan(card, data, allowed, correction)",
        "changes, skipped = voice_change_plan(card, data, allowed, explicit_override)",
        "voice_plan_override",
    )
    source = replace_once(
        source,
        'card["id"], field, old, new, user_id, correction)',
        'card["id"], field, old, new, user_id, explicit_override)',
        "voice_cas_override",
    )
    source = replace_once(
        source,
        "elif data and skipped and not override:",
        "elif data and skipped and not explicit_override:",
        "voice_undefined_override",
    )
    source = replace_once(
        source,
        "_v168_guard_heartbeat, interval=1.0, first=0.1,",
        "_v168_guard_heartbeat, interval=5.0, first=0.1,",
        "guard_interval",
    )
    source = replace_definition(source, "open_card", OPEN_CARD)
    marker = "# " + MARKER + ": bounded voice, media and background load.\n"
    source = marker + source
    return source


def build_ocr(source: str) -> str:
    if MARKER in source:
        return source
    anchor = "def fields_from_text(text: str, allowed_keys) -> dict:\n"
    if source.count(anchor) != 1:
        raise RepairError("OCR_FIELDS_ANCHOR")
    source = source.replace(anchor, MILEAGE_HELPERS.rstrip() + "\n\n\n" + anchor, 1)
    start = source.find("    mileage = re.search(\n", source.find(anchor))
    end_marker = '    if re.search(r"\\b(lpg|газ|gaz|gas|fas)\\b", folded):\n'
    end = source.find(end_marker, start)
    if start < 0 or end < 0:
        raise RepairError("OCR_MILEAGE_BLOCK")
    replacement = '''    mileage_value = _v189_mileage_value(folded)\n    if mileage_value:\n        _put(data, allowed, "mileage_km", mileage_value)\n\n'''
    return source[:start] + replacement + source[end:]


def build_team(source: str) -> str:
    if MARKER in source:
        return source
    source = replace_once(
        source,
        "cars_ui.media_spool_worker_job, interval=1.0, first=0.2",
        "cars_ui.media_spool_worker_job, interval=2.0, first=0.2",
        "media_worker_interval",
    )
    anchor = "def build_application():\n"
    if source.count(anchor) != 1:
        raise RepairError("TEAM_BUILD_ANCHOR")
    quiet = (
        "# %s: suppress one-second success spam without hiding warnings.\n" % MARKER
        + 'logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)\n\n\n'
    )
    return source.replace(anchor, quiet + anchor, 1)


def build_container(source: str) -> str:
    if MARKER in source:
        return source
    return replace_definition(source, "posle_statusa", CONTAINER_STATUS)


def build_render(source: str) -> str:
    if MARKER in source:
        return source
    return replace_definition(source, "_otpravit", MEDIA_SEND)


BUILDERS = {
    "cars_ui.py": build_cars,
    "local_ocr.py": build_ocr,
    "team_bot.py": build_team,
    "konteyner.py": build_container,
    "card_render.py": build_render,
}


def undefined_name_in_catch(source: str, name: str) -> bool:
    tree = ast.parse(source)
    node = next(item for item in tree.body
                if isinstance(item, ast.AsyncFunctionDef) and item.name == "catch_message")
    loaded = any(isinstance(item, ast.Name) and item.id == name and isinstance(item.ctx, ast.Load)
                 for item in ast.walk(node))
    stored = any(isinstance(item, ast.Name) and item.id == name and isinstance(item.ctx, ast.Store)
                 for item in ast.walk(node))
    return loaded and not stored


def validate(candidates: dict[str, str]) -> dict:
    for name, source in candidates.items():
        compile(source, name + ".candidate", "exec")
    cars = candidates["cars_ui.py"]
    ocr = candidates["local_ocr.py"]
    team = candidates["team_bot.py"]
    container = candidates["konteyner.py"]
    render = candidates["card_render.py"]
    card_text_at = cars.find("reply_text(\n        render(card")
    photos_at = cars.find("CR.send_photos")
    checks = {
        "cars_marker": MARKER in cars,
        "voice_override_defined": not undefined_name_in_catch(cars, "override"),
        "voice_named_field_override": "explicit_override = bool(correction or named_fields)" in cars,
        "voice_watchdog_preserved": "crm_voice_watchdog" in cars,
        "heartbeat_five_seconds": "_v168_guard_heartbeat, interval=5.0" in cars,
        "card_first_before_photos": (
            card_text_at >= 0 and photos_at >= 0 and card_text_at < photos_at),
        "open_media_timeout": "CRM photos opening timeout" in cars,
        "ocr_natural_mileage": "_v189_mileage_value" in ocr,
        "ocr_canonical_field": '"mileage_km"' in ocr,
        "worker_two_seconds": "media_spool_worker_job, interval=2.0" in team,
        "executor_spam_suppressed": 'apscheduler.executors.default' in team,
        "sea_status_direct_write": '_pisat(cid, "status", status' in container,
        "sea_status_readback": "STATUS_READBACK_MISMATCH" in container,
        "media_total_budget": "deadline = _v189_asyncio.get_running_loop().time() + 8.0" in render,
        "media_batch_cap": "list(albums)[:3]" in render,
    }
    namespace: dict[str, object] = {}
    exec(compile(ocr, "local_ocr.py.candidate", "exec"), namespace)
    parse = namespace["fields_from_text"]
    mileage_cases = {
        "пробег 48 тысяч": 48_000,
        "пробіг 48 тисяч": 48_000,
        "пробег 48000": 48_000,
        "пробіг сорок вісім тисяч": 48_000,
        "mileage 48k": 48_000,
        "120 500 км": 120_500,
    }
    mileage_results = {
        text: (parse(text, {"mileage_km"}) or {}).get("mileage_km")
        for text in mileage_cases
    }
    checks["mileage_cases"] = mileage_results == mileage_cases
    if not all(checks.values()):
        raise RepairError("VALIDATION:" + json.dumps(checks, ensure_ascii=False, sort_keys=True))
    return {"checks": checks, "mileage_results": mileage_results}


def load_originals() -> dict[str, bytes]:
    originals = {}
    for name, path in TARGETS.items():
        regular(path)
        data = path.read_bytes()
        current = sha_bytes(data)
        if current != EXPECTED[name] and MARKER not in data.decode("utf-8", "replace"):
            raise RepairError("LIVE_PREIMAGE_DRIFT:%s:%s" % (name, current))
        originals[name] = data
    return originals


def build_all(originals: dict[str, bytes]) -> dict[str, str]:
    return {
        name: BUILDERS[name](originals[name].decode("utf-8"))
        for name in TARGETS
    }


def acquire_lock(timeout: float = 180.0):
    handle = open(LOCK, "a+", encoding="utf-8")
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except BlockingIOError:
            if time.monotonic() >= deadline:
                handle.close()
                raise RepairError("PRODUCTION_LOCK_TIMEOUT")
            time.sleep(0.5)


def rollback(backup: Path) -> dict:
    if not str(backup).startswith(str(BACKUPS) + os.sep) or not backup.is_dir():
        raise RepairError("ROLLBACK_SCOPE")
    restored = {}
    lock = acquire_lock()
    try:
        for name, target in TARGETS.items():
            saved = backup / name
            if not saved.is_file():
                raise RepairError("ROLLBACK_FILE_MISSING:" + name)
            mode = target.stat().st_mode & 0o777
            atomic_bytes(target, saved.read_bytes(), mode)
            py_compile.compile(str(target), doraise=True)
            restored[name] = sha_bytes(target.read_bytes())
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()
    value = {
        "task_id": "task_089",
        "contract_id": MARKER,
        "status": "PASS",
        "mode": "ROLLBACK",
        "production_write": True,
        "crm_db_write": False,
        "backup_dir": str(backup),
        "restored": restored,
        "finished_at_utc": utc_now(),
        "errors": [],
    }
    atomic_json(ROLLBACK_RECEIPT, value)
    return value


def install(dry_run: bool) -> dict:
    receipt = {
        "task_id": "task_089",
        "contract_id": MARKER,
        "status": "FAIL",
        "mode": "DRY_RUN" if dry_run else "ATOMIC_INSTALL",
        "production_write": False,
        "crm_db_write": False,
        "media_write": False,
        "bot_restarted": False,
        "started_at_utc": utc_now(),
        "errors": [],
    }
    backup = None
    changed = False
    originals = load_originals()
    candidates = build_all(originals)
    receipt.update(validate(candidates))
    receipt["before_sha256"] = {name: sha_bytes(data) for name, data in originals.items()}
    receipt["after_sha256"] = {name: sha_text(source) for name, source in candidates.items()}
    already = all(MARKER in originals[name].decode("utf-8", "replace") for name in TARGETS)
    receipt["already_applied"] = already
    if dry_run or already:
        receipt["status"] = "PASS"
        receipt["finished_at_utc"] = utc_now()
        atomic_json(RECEIPT, receipt)
        return receipt

    lock = acquire_lock()
    try:
        # Recheck every live byte only after the global production lock is held.
        for name, target in TARGETS.items():
            if target.read_bytes() != originals[name]:
                raise RepairError("LIVE_PREIMAGE_CHANGED_UNDER_LOCK:" + name)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = BACKUPS / stamp
        backup.mkdir(parents=True, exist_ok=False)
        for name, data in originals.items():
            atomic_bytes(backup / name, data, 0o600)
        atomic_json(backup / "manifest.json", {
            "contract_id": MARKER,
            "created_at_utc": utc_now(),
            "before_sha256": receipt["before_sha256"],
            "after_sha256": receipt["after_sha256"],
        })
        try:
            for name, target in TARGETS.items():
                mode = target.stat().st_mode & 0o777
                atomic_bytes(target, candidates[name].encode("utf-8"), mode)
            changed = True
            for name, target in TARGETS.items():
                py_compile.compile(str(target), doraise=True)
                if sha_bytes(target.read_bytes()) != receipt["after_sha256"][name]:
                    raise RepairError("AFTER_SHA_MISMATCH:" + name)
        except Exception:
            for name, target in TARGETS.items():
                mode = target.stat().st_mode & 0o777
                atomic_bytes(target, originals[name], mode)
                py_compile.compile(str(target), doraise=True)
            changed = False
            raise
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()
    receipt["status"] = "PASS"
    receipt["production_write"] = changed
    receipt["backup_dir"] = str(backup)
    receipt["changed_files"] = list(TARGETS)
    receipt["finished_at_utc"] = utc_now()
    atomic_json(RECEIPT, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("dry-run", "install", "rollback"))
    parser.add_argument("--backup")
    args = parser.parse_args()
    try:
        if args.mode == "rollback":
            if not args.backup:
                raise RepairError("ROLLBACK_BACKUP_REQUIRED")
            value = rollback(Path(args.backup))
        else:
            value = install(args.mode == "dry-run")
    except Exception as exc:
        value = {
            "task_id": "task_089",
            "contract_id": MARKER,
            "status": "FAIL",
            "mode": args.mode.upper(),
            "production_write": False,
            "crm_db_write": False,
            "media_write": False,
            "bot_restarted": False,
            "finished_at_utc": utc_now(),
            "errors": [type(exc).__name__ + ":" + str(exc)],
        }
        TASK_ROOT.mkdir(parents=True, exist_ok=True)
        atomic_json(RECEIPT, value)
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
