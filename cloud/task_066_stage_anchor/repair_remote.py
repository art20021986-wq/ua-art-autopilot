#!/usr/bin/env python3
"""Atomic production installer for UA-CARDS-STAGE-ANCHOR-001 V1.1.

The installer is intentionally stdlib-only.  It patches the two card
generators and the CRM keyboard, upgrades every published card/variant in
/video and /site, preserves diagnostics, and rolls the complete write set
back on any failed invariant.
"""
from __future__ import annotations

import ast
import datetime as dt
import fcntl
import glob
import hashlib
import html
import json
import os
import pathlib
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
from typing import Any


MODE = "UA_CARDS_STAGE_ANCHOR_001_V1_1_ATOMIC_INSTALL"
CONTRACT = "UA-CARDS-STAGE-ANCHOR-001-V1.1"
ROOT = "/home/Carix"
VIDEO_ROOT = ROOT + "/video"
SITE_ROOT = ROOT + "/site"
ETALON_ROOT = ROOT + "/etalon"
CRM_PATH = ROOT + "/crm.db"
STRANICA_PATH = ROOT + "/stranica.py"
YADRO_PATH = ROOT + "/yadro.py"
CARS_UI_PATH = ROOT + "/cars_ui.py"
DB_PATH = ROOT + "/db.py"
TEAM_BOT_PATH = ROOT + "/team_bot.py"
START_SAFE_PATH = ROOT + "/start_safe.py"
SAFE_ROOT = ROOT + "/autopilot_inbox/cloud/task_066_stage_anchor"
RECEIPT_PATH = SAFE_ROOT + "/install_receipt.json"
ROLLBACK_RECEIPT_PATH = SAFE_ROOT + "/rollback_receipt.json"
BACKUP_PARENT = SAFE_ROOT + "/backups"
LOCK_PATH = ROOT + "/.task066_stage_anchor.lock"
START_MARKER = "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START -->"
END_MARKER = "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:END -->"
DIAG_MARKER = "<!--ua-art-diagnostics-permanent-v1-->"
MAX_FILE_BYTES = 24 * 1024 * 1024
CARD_ID = re.compile(r"^UA-[0-9]{4,}$")

EXPECTED_SHA = {
    STRANICA_PATH: "530b345caf2534fe4c38dc0d3fc3ab69e01b4a540cf67fe012a6a7678a786453",
    YADRO_PATH: "71d981508c157dad7d683430d8d0965af8d3b5946331cbda06b2a0179a7a657c",
    CARS_UI_PATH: "a7da33f7a653a0cef697aad784e5c29bc2600639eb48b272793d61f1ac0e2af5",
    DB_PATH: "b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086",
    TEAM_BOT_PATH: "70b349cdbe72a0cf5f674a1341a493de7759b5263859ce73d86fb292db3b5ad2",
    START_SAFE_PATH: "2daefa4e6cee8054452ff61200f1cb4b89284a23289370bd24c8a8053674d007",
}

EXPECTED_FUNCTION_SHA = {
    (STRANICA_PATH, "sobrat_kartochku"): "6a1c8b834336e7369e70081babfd4d7d3c4dfea5554bd17dfe1f29f624dfd486",
    (YADRO_PATH, "blok_marshruta"): "f459488ed1dceeb6560273c065cefd8b5aa48ededf7f5bd84a5a5e116cdbbdc4",
    (CARS_UI_PATH, "card_kb"): "8fd0c67de08f7bbc55518aa941748f383a8744a1d0557be6316c0ca141123251",
    (CARS_UI_PATH, "stage_menu"): "30c655140f878647b24bcd59fca05ca1825760adc5f35e664b5aac2598747194",
    (CARS_UI_PATH, "stage_set"): "c71f05a3b314b5fe9b64d9e3d3e2146bb51a20ae710b804ebb8bdab1f97ca9aa",
}

PRESERVE_FUNCTIONS = {
    # CRM-PHOTO-FASTPATH-001 is the current production baseline.  The stage
    # anchor must retain its spool enqueue/worker path byte-for-byte.
    "catch_message": "e8d274e671f7cea58f82d463e301f784e457c5981e89a59ec1f3a25f52255e4a",
    "save_media": "6be0c1a9e8c6b94063262e330a3cb3dd4026b7d1d008b9e100dc3160249b747f",
}


class RepairBlocked(RuntimeError):
    pass


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _read(path: str, *, required: bool = True) -> bytes | None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        if required:
            raise RepairBlocked("missing_file:" + path)
        return None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RepairBlocked("unsafe_file:" + path)
    if info.st_size <= 0 or info.st_size > MAX_FILE_BYTES:
        raise RepairBlocked("invalid_file_size:" + path)
    with open(path, "rb") as handle:
        data = handle.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise RepairBlocked("file_too_large:" + path)
    return data


def _safe_parent(path: str) -> str:
    root = os.path.realpath(ROOT)
    parent = os.path.realpath(os.path.dirname(path))
    if os.path.commonpath((root, parent)) != root:
        raise RepairBlocked("path_escape:" + path)
    os.makedirs(parent, mode=0o755, exist_ok=True)
    return parent


def _fsync_dir(path: str) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: str, data: bytes, mode: int = 0o644) -> None:
    parent = _safe_parent(path)
    if os.path.lexists(path) and os.path.islink(path):
        raise RepairBlocked("symlink_target:" + path)
    descriptor, temporary = tempfile.mkstemp(prefix=".task066-", dir=parent)
    try:
        os.fchmod(descriptor, stat.S_IMODE(mode))
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        _fsync_dir(parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if os.path.exists(temporary):
            os.unlink(temporary)


def _atomic_json(path: str, value: Any) -> None:
    _atomic_write(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def _mode_for(path: str) -> int:
    try:
        return stat.S_IMODE(os.lstat(path).st_mode)
    except FileNotFoundError:
        return 0o644


def _source_segment(source: str, node: ast.AST) -> str:
    lines = source.splitlines()
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def _function_nodes(source: str, name: str) -> list[ast.AST]:
    tree = ast.parse(source)
    return [
        node for node in ast.iter_child_nodes(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]


def _function_sha(source: str, name: str, *, last: bool = False) -> str:
    nodes = _function_nodes(source, name)
    if not nodes:
        raise RepairBlocked("function_missing:" + name)
    node = nodes[-1] if last else nodes[0]
    return _sha(_source_segment(source, node).encode("utf-8"))


def _replace_function(source: str, name: str, replacement: str, expected_sha: str) -> str:
    nodes = _function_nodes(source, name)
    if len(nodes) != 1:
        raise RepairBlocked("function_count_invalid:%s:%d" % (name, len(nodes)))
    node = nodes[0]
    segment = _source_segment(source, node)
    if _sha(segment.encode("utf-8")) != expected_sha:
        raise RepairBlocked("function_hash_mismatch:" + name)
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [replacement.rstrip() + "\n"]
    return "".join(lines)


# This exact helper is installed in both generators.  It contains its own CSS,
# uses only saved dates, never returns negative days, and always emits four
# immutable stage labels with one and only one current state.
STAGE_HELPER_SOURCE = r'''
# UA-CARDS-STAGE-ANCHOR-001-V1.1: permanent four-stage card contract.
import datetime as _ua_stage_dt
import html as _ua_stage_html
import json as _ua_stage_json
import os as _ua_stage_os
try:
    from zoneinfo import ZoneInfo as _UaStageZoneInfo
except Exception:
    _UaStageZoneInfo = None

_UA_STAGE_START = "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START -->"
_UA_STAGE_END = "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:END -->"
_UA_STAGE_LABELS = ("Корея", "Паром", "Грузия", "Киев")
_UA_STAGE_DETAILS = (
    "Выкуплен · стоянка в Корее",
    "Паром · Корея → Грузия",
    "Грузия · оформление",
    "Киев · выдача автомобиля",
)
_UA_STAGE_MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def _ua_stage_escape(value):
    try:
        return ekran(str(value))
    except Exception:
        return _ua_stage_html.escape(str(value), quote=True)


def _ua_stage_number(m):
    status = str(m.get("status") or "").strip().lower()
    if status.startswith("kr_"):
        return 1
    if status.startswith("sea_"):
        return 2
    if status == "ge_to_kyiv" or status.startswith("ge_"):
        return 3
    if status.startswith("ua_"):
        return 4
    try:
        saved = int(m.get("stage") or 0)
        if 1 <= saved <= 4:
            return saved
    except Exception:
        pass
    return 1


def _ua_stage_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    for pattern, width in (("%Y-%m-%d", 10), ("%d.%m.%Y", 10), ("%d/%m/%Y", 10)):
        try:
            return _ua_stage_dt.datetime.strptime(text[:width], pattern).date()
        except Exception:
            pass
    return None


def _ua_stage_today():
    if _UaStageZoneInfo is not None:
        try:
            return _ua_stage_dt.datetime.now(_UaStageZoneInfo("Europe/Kyiv")).date()
        except Exception:
            pass
    zone = _ua_stage_dt.timezone(_ua_stage_dt.timedelta(hours=3))
    return _ua_stage_dt.datetime.now(zone).date()


def _ua_stage_pretty(value):
    return "%d %s %d" % (value.day, _UA_STAGE_MONTHS[value.month - 1], value.year)


def _ua_stage_plural(value):
    value = abs(int(value))
    if value % 10 == 1 and value % 100 != 11:
        return "день"
    if value % 10 in (2, 3, 4) and value % 100 not in (12, 13, 14):
        return "дня"
    return "дней"


def _ua_stage_saved_release(m):
    for key in ("ge_released", "ge_to_kyiv_at"):
        value = _ua_stage_date(m.get(key))
        if value is not None:
            return value
    identifier = str(m.get("auto_number") or "").strip()
    if not identifier:
        return None
    for path in ("/home/Carix/.srok_gruzia.json", "/home/Carix/.sroki_gruzia.json"):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                memory = _ua_stage_json.load(handle)
            value = _ua_stage_date((memory.get(identifier) or {}).get("vyehal"))
            if value is not None:
                return value
        except Exception:
            pass
    return None


def _ua_stage_eta(m, stage):
    status = str(m.get("status") or "").strip().lower()
    if stage >= 4 or status.startswith("ua_"):
        return ("arrived", None, None)
    manual = _ua_stage_date(m.get("eta_manual"))
    if manual is not None:
        target = manual
    elif status == "ge_to_kyiv":
        released = _ua_stage_saved_release(m)
        target = released + _ua_stage_dt.timedelta(days=15) if released else None
    elif status.startswith("ge_"):
        target = None
    else:
        shipped = _ua_stage_date(m.get("sea_date_out"))
        target = shipped + _ua_stage_dt.timedelta(days=75) if shipped else None
    if target is None:
        return ("georgia" if status.startswith("ge_") else "unknown", None, None)
    days = max((target - _ua_stage_today()).days, 0)
    return ("due" if days else "soon", days, target)


def _ua_delivery_stage_anchor(m):
    stage = _ua_stage_number(m)
    progress = int(round((stage - 1) * 100.0 / 3.0))
    status = str(m.get("status") or "").strip().lower()
    details = list(_UA_STAGE_DETAILS)
    if status == "ge_to_kyiv":
        details[2] = "Грузия · отправлен в Киев"
    css = r"""<style>
.ua-delivery-v1{position:relative;margin:14px 0;padding:18px 16px 16px;overflow:hidden;border:1px solid rgba(240,166,60,.30);border-radius:18px;background:linear-gradient(145deg,rgba(19,37,59,.98),rgba(10,25,42,.98));box-shadow:0 16px 38px rgba(0,0,0,.20)}
.ua-delivery-v1:before{content:"";position:absolute;inset:-90px auto auto -80px;width:190px;height:190px;border-radius:50%;background:radial-gradient(circle,rgba(240,166,60,.12),transparent 68%);pointer-events:none}
.ua-stage-v1-head{position:relative;display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:17px}.ua-stage-v1-title{font-size:18px;font-weight:850;letter-spacing:.1px;color:#f3f6fb}.ua-stage-v1-count{flex:0 0 auto;padding:6px 9px;border:1px solid rgba(240,166,60,.35);border-radius:999px;color:#f5bf70;background:rgba(240,166,60,.08);font-size:10px;font-weight:850;letter-spacing:.65px}
.ua-stage-v1-route{position:relative;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:2px}.ua-stage-v1-track{position:absolute;z-index:0;top:19px;left:12.5%;right:12.5%;height:3px;border-radius:4px;background:rgba(154,169,189,.18);overflow:hidden}.ua-stage-v1-fill{display:block;height:100%;border-radius:4px;background:linear-gradient(90deg,#d68c2d,#ffc05a);box-shadow:0 0 13px rgba(240,166,60,.55)}
.ua-stage-v1-step{position:relative;z-index:1;min-width:0;text-align:center}.ua-stage-v1-node{display:grid;place-items:center;width:40px;height:40px;margin:0 auto 8px;border:2px solid rgba(154,169,189,.30);border-radius:50%;background:#13243a;color:#8595aa;font-size:14px;font-weight:900;box-shadow:0 0 0 4px #102238}.ua-stage-v1-step.is-done .ua-stage-v1-node{border-color:#d89435;background:#d89435;color:#101a28}.ua-stage-v1-step.is-current .ua-stage-v1-node{border-color:#ffc05a;background:#f2a63b;color:#111b29;box-shadow:0 0 0 5px rgba(240,166,60,.13),0 0 23px rgba(240,166,60,.52)}.ua-stage-v1-name{display:block;overflow:hidden;color:#8291a5;font-size:11.5px;font-weight:750;text-overflow:ellipsis;white-space:nowrap}.ua-stage-v1-step.is-done .ua-stage-v1-name,.ua-stage-v1-step.is-current .ua-stage-v1-name{color:#f1ad4e}.ua-stage-v1-now{display:inline-flex;min-height:17px;align-items:center;justify-content:center;margin-top:5px;padding:2px 6px;border-radius:999px;background:#f0a63c;color:#101a28;font-size:8px;font-weight:950;letter-spacing:.7px}.ua-stage-v1-future{display:block;height:17px;margin-top:5px}
.ua-stage-v1-current{display:flex;align-items:center;gap:10px;margin-top:16px;padding:11px 12px;border:1px solid rgba(240,166,60,.20);border-radius:13px;background:rgba(240,166,60,.065)}.ua-stage-v1-current-icon{display:grid;place-items:center;flex:0 0 auto;width:30px;height:30px;border-radius:9px;background:rgba(240,166,60,.15);font-size:16px}.ua-stage-v1-current-copy{min-width:0}.ua-stage-v1-current-copy small{display:block;margin-bottom:2px;color:#f0a63c;font-size:9px;font-weight:900;letter-spacing:.8px}.ua-stage-v1-current-copy b{display:block;color:#edf2f8;font-size:13px;line-height:1.25}
.ua-stage-v1-meta{display:flex;flex-wrap:wrap;gap:7px;margin-top:13px}.ua-stage-v1-badge{padding:7px 9px;border:1px solid rgba(142,160,183,.18);border-radius:10px;background:rgba(255,255,255,.035);color:#b9c5d4;font-size:11px}.ua-stage-v1-badge b{color:#eef3f8}.ua-stage-v1-eta{margin-top:13px;padding-top:13px;border-top:1px solid rgba(142,160,183,.14)}.ua-stage-v1-eta-row{display:flex;align-items:baseline;gap:9px}.ua-stage-v1-days{color:#f0a63c;font-size:44px;font-weight:900;line-height:.95}.ua-stage-v1-days-copy{color:#eef3f8;font-size:14px;font-weight:750;line-height:1.3}.ua-stage-v1-date{margin-top:7px;color:#aebccd;font-size:12.5px}.ua-stage-v1-date b{color:#e8eef5}.ua-stage-v1-state{color:#f2b45d;font-size:16px;font-weight:850;line-height:1.3}.ua-stage-v1-note{margin-top:4px;color:#aebccd;font-size:12.5px;line-height:1.4}.ua-stage-v1-track-link{display:inline-flex;margin-top:9px;color:#f2ba69;font-size:11px;font-weight:800;text-decoration:none}
@media(max-width:380px){.ua-delivery-v1{padding:16px 11px 14px}.ua-stage-v1-name{font-size:10.5px}.ua-stage-v1-node{width:36px;height:36px}.ua-stage-v1-track{top:17px}.ua-stage-v1-title{font-size:17px}.ua-stage-v1-count{font-size:9px}}
@media(prefers-reduced-motion:no-preference){.ua-stage-v1-step.is-current .ua-stage-v1-node{animation:uaStagePulse 2.6s ease-in-out infinite}@keyframes uaStagePulse{0%,100%{box-shadow:0 0 0 5px rgba(240,166,60,.11),0 0 17px rgba(240,166,60,.35)}50%{box-shadow:0 0 0 7px rgba(240,166,60,.18),0 0 27px rgba(240,166,60,.58)}}}
</style>"""
    out = [_UA_STAGE_START, "<!--v173-marshrut--><!--ua-art-karta-v177-->", css]
    out.append('<section class="ua-delivery-v1" data-ua-stage-current="%d" aria-label="Путь автомобиля: этап %d из 4">' % (stage, stage))
    out.append('<div class="ua-stage-v1-head"><div class="ua-stage-v1-title">Путь автомобиля</div><div class="ua-stage-v1-count">ЭТАП %d ИЗ 4</div></div>' % stage)
    out.append('<div class="ua-stage-v1-route" role="list"><div class="ua-stage-v1-track" aria-hidden="true"><span class="ua-stage-v1-fill" style="width:%d%%"></span></div>' % progress)
    for number, label in enumerate(_UA_STAGE_LABELS, 1):
        state = "is-done" if number < stage else ("is-current" if number == stage else "is-future")
        icon = "✓" if number < stage else str(number)
        current = ' aria-current="step"' if number == stage else ""
        out.append('<div class="ua-stage-v1-step %s" data-ua-stage="%d" data-ua-state="%s" role="listitem"%s><div class="ua-stage-v1-node">%s</div><span class="ua-stage-v1-name" data-ua-stage-label="%s">%s</span>%s</div>' % (
            state, number, state[3:], current, icon, label, label,
            '<span class="ua-stage-v1-now">СЕЙЧАС</span>' if number == stage else '<span class="ua-stage-v1-future"></span>',
        ))
    out.append('</div><div class="ua-stage-v1-current"><span class="ua-stage-v1-current-icon">%s</span><span class="ua-stage-v1-current-copy"><small>ТЕКУЩИЙ ЭТАП</small><b>%s</b></span></div>' % (("🇰🇷", "🚢", "📋", "📍")[stage - 1], details[stage - 1]))

    container = str(m.get("sea_container") or "").strip()
    shipped = _ua_stage_date(m.get("sea_date_out"))
    if container or shipped is not None:
        out.append('<div class="ua-stage-v1-meta">')
        if container:
            out.append('<span class="ua-stage-v1-badge">Контейнер: <b>%s</b></span>' % _ua_stage_escape(container))
        if shipped is not None:
            out.append('<span class="ua-stage-v1-badge">Отправлен: <b>%s</b></span>' % _ua_stage_pretty(shipped))
        out.append('</div>')

    kind, days, target = _ua_stage_eta(m, stage)
    out.append('<div class="ua-stage-v1-eta">')
    if kind == "arrived":
        out.append('<div class="ua-stage-v1-state">Автомобиль в Киеве — можно приехать на осмотр</div><div class="ua-stage-v1-note">Осмотр в офисе на Победы 20</div>')
    elif kind == "due":
        out.append('<div class="ua-stage-v1-eta-row"><span class="ua-stage-v1-days">%d</span><span class="ua-stage-v1-days-copy">%s до выдачи<br>в Киеве</span></div><div class="ua-stage-v1-date">Ориентировочная дата выдачи — <b>%s</b></div>' % (days, _ua_stage_plural(days), _ua_stage_pretty(target)))
    elif kind == "soon":
        out.append('<div class="ua-stage-v1-state">Прибытие в Киев ожидается со дня на день</div><div class="ua-stage-v1-date">Ориентировочная дата — <b>%s</b></div>' % _ua_stage_pretty(target))
    elif kind == "georgia":
        out.append('<div class="ua-stage-v1-state">Автомобиль в Грузии</div><div class="ua-stage-v1-note">Дата отправления в Украину уточняется</div>')
    else:
        out.append('<div class="ua-stage-v1-state">Дата прибытия уточняется</div><div class="ua-stage-v1-note">Сообщим точный срок после отправки контейнера</div>')
    if container.upper().startswith("ONEY") and len(container) > 4:
        tracking = _ua_stage_escape(container[4:])
        out.append('<a class="ua-stage-v1-track-link" href="https://ecomm.one-line.com/one-ecom/manage-shipment/cargo-tracking?trakNoParam=%s" target="_blank" rel="noopener">Отследить контейнер онлайн →</a>' % tracking)
    out.append('</div></section>')
    out.append(_UA_STAGE_END)
    return "".join(out)
'''.strip()


OLD_STRANICA_STAGE = '''    tekushchij = nomer_etapa(m)
    c.append("<div class='blok'><div class='zag'>Где машина сейчас</div>")
    for i, nazv in enumerate(("Выкуплена, стоянка в Корее", "Паром: Корея → Грузия",
                              "Поти/Батуми, оформление", "Киев: растаможка и выдача"), 1):
        klass = "tut" if i == tekushchij else ("proshel" if i < tekushchij else "")
        znak = "✓" if i < tekushchij else str(i)
        c.append("<div class='etap %s'><div class='krug'>%s</div>%s</div>" % (klass, znak, nazv))
    c.append(blok_pribytiya(m))  # UA-V115'''


NEW_CARD_KB = '''# UA-CARDS-STAGE-ANCHOR-001-V1.1 · one visible entry per semantic action.
def card_kb(card, staff):
    cid = card["id"]
    rows = [
        [InlineKeyboardButton("Редактировать данные", callback_data="car_edit:%d" % cid),
         InlineKeyboardButton("Фото и видео", callback_data="car_media:%d" % cid)],
        [InlineKeyboardButton("🚚 Доставка и этапы", callback_data="car_stage:%d" % cid)],
        [InlineKeyboardButton("Комплексная диагностика", callback_data="car_cond:%d" % cid)],
    ]
    klient = client_of(card)
    rows.append([InlineKeyboardButton(
        "Покупатель" if klient else "Оформить за клиентом",
        callback_data="car_client:%d" % cid)])
    rows.append([InlineKeyboardButton("Как видит покупатель",
                                      callback_data="car_preview:%d" % cid)])
    rows.append([InlineKeyboardButton("Разместить объявление",
                                      callback_data="car_ad:%d" % cid)])
    rows.append([
        InlineKeyboardButton(
            "Скрыть от клиентов" if card.get("published") else "Показать клиентам",
            callback_data="car_pub:%d" % cid),
        InlineKeyboardButton("Продано", callback_data="car_sold:%d" % cid),
    ])
    rows.append([InlineKeyboardButton("Удалить", callback_data="car_del:%d" % cid)])
    rows.append([InlineKeyboardButton("← Все автомобили", callback_data="cards_cars")])
    return InlineKeyboardMarkup(rows)
'''


NEW_STAGE_MENU = '''# UA-CARDS-STAGE-ANCHOR-001-V1.1 · canonical delivery submenu.
async def stage_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    drop_wait(context)
    cid = int(q.data.split(":")[-1])
    card = card_of(cid)
    stage = S.stage_of(card.get("status")) or 1
    lines = [
        "🚚 Доставка и этапы",
        card.get("auto_number") or "#%d" % cid,
        "",
        "Сейчас: %s" % S.status_label(card.get("status")),
        "Этап %d из 4: %s" % (stage, dict(S.STAGES).get(stage, "—")),
    ]
    if card.get("sea_container"):
        lines.append("Контейнер: %s" % card["sea_container"])
    if card.get("sea_date_out"):
        lines.append("Дата отправления: %s" % str(card["sea_date_out"])[:10])
    left, eta = eta_of(card)
    if stage >= 4:
        lines.append("Выдача: автомобиль в Киеве")
    elif left is not None:
        lines.append("До выдачи в Киеве: %d дней · %s" % (
            left, eta.strftime("%d.%m.%Y")))
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
    rows.append([InlineKeyboardButton("📦 Контейнер, даты и сроки",
                                      callback_data="cont_menu:%d" % cid)])
    rows.append([InlineKeyboardButton("← К карточке", callback_data="car_open:%d" % cid)])
    await q.message.reply_text("\\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))
    raise ApplicationHandlerStop
'''


NEW_STAGE_SET = '''# UA-CARDS-STAGE-ANCHOR-001-V1.1 · stage changes never force price/ETA prompts.
async def stage_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    drop_wait(context)
    _, cid, code = q.data.split(":")
    cid = int(cid)
    card_before = card_of(cid)
    set_field(cid, "status", code, q.from_user.id)

    if code == "ge_waiting" and not card_before.get("ge_arrived"):
        set_field(cid, "ge_arrived", _date.today().isoformat(), q.from_user.id)
    if code == "ge_to_kyiv":
        released = card_before.get("ge_released")
        if not released:
            released = _date.today().isoformat()
            set_field(cid, "ge_released", released, q.from_user.id)
        # A deliberate manual date is immutable here.  The 15-day default is
        # initialized only when no manual ETA has ever been saved.
        if not card_before.get("eta_manual"):
            try:
                base = _dt.strptime(str(released)[:10], "%Y-%m-%d").date()
            except Exception:
                base = _date.today()
            eta = base + _td(days=DNEI_GRUZIA_UKRAINA)
            try:
                db.update_card_field("cars", cid, "eta_manual",
                                     eta.isoformat(), q.from_user.id)
                db.update_card_field("cars", cid, "days_to_kyiv",
                                     DNEI_GRUZIA_UKRAINA, q.from_user.id)
            except Exception as exc:
                log.warning("не смог поставить срок до Украины: %s", exc)

    card = card_of(cid)
    saved = card.get("status")
    if saved != code:
        await q.message.reply_text(
            "Не удалось сохранить этап. Сейчас в карточке: %s"
            % S.status_label(saved),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
                "← Вернуться к карточке", callback_data="car_open:%d" % cid)]]))
        raise ApplicationHandlerStop

    lines = [
        card.get("auto_number") or "#%d" % cid,
        "Этап сохранён: %s" % S.status_label(saved),
    ]
    left, eta = eta_of(card)
    if left is not None:
        lines.append("До выдачи в Киеве: %d дней · %s" % (
            left, eta.strftime("%d.%m.%Y")))
    rows = [
        [InlineKeyboardButton("🚚 Доставка и этапы",
                              callback_data="car_stage:%d" % cid)],
        [InlineKeyboardButton("← Вернуться к карточке",
                              callback_data="car_open:%d" % cid)],
    ]
    await q.message.reply_text("\\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))
    raise ApplicationHandlerStop
'''


OLD_EDITABLE = '''EDITABLE = [
    ("auto_number", "Номер авто"), ("brand", "Марка"), ("model", "Модель"),
    ("year", "Год выпуска"), ("vin", "VIN"), ("fuel", "Топливо"),
    ("engine_cc", "Объём, см³"), ("gearbox", "КПП"), ("drive", "Привод"),
    ("mileage_km", "Пробег"), ("color", "Цвет"), ("condition_text", "Описание"),
    ("price_uah", "Цена продажи"), ("diag_link", "Ссылка на отчёт"),
    ("diag_text", "Описание диагностики"),
    ("eta_days", "Дней до прибытия"),
    ("sea_container", "Номер контейнера"),
]'''


NEW_EDITABLE = '''# UA-CARDS-STAGE-ANCHOR-001-V1.1 · only general vehicle data here.
EDITABLE = [
    ("auto_number", "Номер авто"), ("brand", "Марка"), ("model", "Модель"),
    ("year", "Год выпуска"), ("vin", "VIN"), ("fuel", "Топливо"),
    ("engine_cc", "Объём, см³"), ("gearbox", "КПП"), ("drive", "Привод"),
    ("mileage_km", "Пробег"), ("color", "Цвет"), ("condition_text", "Описание"),
    ("price_uah", "Цена продажи"),
]'''


def _patch_stranica(source: str, original_sha: str) -> str:
    if CONTRACT in source:
        _validate_stranica(source)
        return source
    if original_sha != EXPECTED_SHA[STRANICA_PATH]:
        raise RepairBlocked("stranica_sha_changed")
    if _function_sha(source, "sobrat_kartochku") != EXPECTED_FUNCTION_SHA[(STRANICA_PATH, "sobrat_kartochku")]:
        raise RepairBlocked("stranica_card_builder_changed")
    if source.count(OLD_STRANICA_STAGE) != 1:
        raise RepairBlocked("stranica_stage_pattern_changed")
    source = source.replace(
        OLD_STRANICA_STAGE,
        "    # %s · permanent visual anchor\n    c.append(_ua_delivery_stage_anchor(m))" % CONTRACT,
        1,
    )

    # Remove the runtime condition around the existing diagnostics CTA.  This
    # is deliberately patched in the early card builder, not as a late override.
    tree = ast.parse(source)
    card_node = next(
        node for node in ast.iter_child_nodes(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "sobrat_kartochku"
    )
    target = None
    for node in ast.walk(card_node):
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Call):
            continue
        func = node.test.func
        if isinstance(func, ast.Name) and func.id == "est_diagnostika":
            target = node
            break
    if target is None or len(target.body) != 1:
        raise RepairBlocked("stranica_diagnostics_condition_changed")
    body_source = _source_segment(source, target.body[0])
    body_lines = body_source.splitlines()
    minimum = min(len(line) - len(line.lstrip()) for line in body_lines if line.strip())
    body_source = "\n".join("    " + line[minimum:] for line in body_lines)
    replacement = (
        "    # UA-DIAG-PERMANENT-V1 · never conditional in a card\n"
        "    c.append(\"%s\")\n%s" % (DIAG_MARKER, body_source)
    )
    lines = source.splitlines(keepends=True)
    lines[target.lineno - 1:target.end_lineno] = [replacement.rstrip() + "\n"]
    source = "".join(lines)

    needle = "\ndef sobrat_kartochku(m, kadry, sredn=None):"
    if source.count(needle) != 1:
        raise RepairBlocked("stranica_helper_insertion_point_changed")
    source = source.replace(needle, "\n\n" + STAGE_HELPER_SOURCE + "\n\n" + needle.lstrip("\n"), 1)
    source = source.replace('("sea_", "в море")', '("sea_", "на пароме")', 1)

    old_guard = 'V172_OBYAZATELNO = ("v171_knopka", "Комплексная диагностика", V173_METKA_MARSHRUTA)'
    new_guard = (
        'V172_OBYAZATELNO = ("v171_knopka", "Комплексная диагностика", '
        'V173_METKA_MARSHRUTA, "UA-ART-DELIVERY-STAGES-PERMANENT-V1:START", '
        '"ua-art-diagnostics-permanent-v1")'
    )
    if source.count(old_guard) != 1:
        raise RepairBlocked("stranica_publication_guard_changed")
    source = source.replace(old_guard, new_guard, 1)
    _validate_stranica(source)
    return source


def _validate_stranica(source: str) -> None:
    compile(source, STRANICA_PATH, "exec")
    required = (
        CONTRACT, "def _ua_delivery_stage_anchor(m):", START_MARKER,
        END_MARKER, 'c.append(_ua_delivery_stage_anchor(m))', DIAG_MARKER,
        '"UA-ART-DELIVERY-STAGES-PERMANENT-V1:START"',
        '"ua-art-diagnostics-permanent-v1"', '("sea_", "на пароме")',
    )
    for value in required:
        if value not in source:
            raise RepairBlocked("stranica_contract_missing:" + value)
    nodes = _function_nodes(source, "sobrat_kartochku")
    if len(nodes) != 1:
        raise RepairBlocked("stranica_card_builder_count_invalid")
    segment = _source_segment(source, nodes[0])
    if "if est_diagnostika" in segment or "Где машина сейчас</div>" in segment:
        raise RepairBlocked("stranica_legacy_card_logic_remains")


def _patch_yadro(source: str, original_sha: str) -> str:
    if CONTRACT in source:
        _validate_yadro(source)
        return source
    if original_sha != EXPECTED_SHA[YADRO_PATH]:
        raise RepairBlocked("yadro_sha_changed")
    source = _replace_function(
        source,
        "blok_marshruta",
        '''# UA-CARDS-STAGE-ANCHOR-001-V1.1 · canonical route renderer.
def blok_marshruta(m):
    return _ua_delivery_stage_anchor(m)
''',
        EXPECTED_FUNCTION_SHA[(YADRO_PATH, "blok_marshruta")],
    )
    needle = "\ndef blok_marshruta(m):"
    if source.count(needle) != 1:
        raise RepairBlocked("yadro_helper_insertion_point_changed")
    source = source.replace(needle, "\n\n" + STAGE_HELPER_SOURCE + "\n\n" + needle.lstrip("\n"), 1)

    diag_call = '    c.append("<a class=\\"knp ram\\" href=\\"%s-diag.html\\">🩺 %s</a>"'
    if source.count(diag_call) != 1:
        raise RepairBlocked("yadro_diagnostics_link_pattern_changed")
    source = source.replace(
        diag_call,
        '    c.append("%s")\n%s' % (DIAG_MARKER, diag_call),
        1,
    )
    old_guard = '                              ("маршрут", METKA_KARTA),\n                              ("диагностика", "-diag.html"),'
    new_guard = (
        '                              ("маршрут", METKA_KARTA),\n'
        '                              ("этапы навсегда", "UA-ART-DELIVERY-STAGES-PERMANENT-V1:START"),\n'
        '                              ("диагностика навсегда", "ua-art-diagnostics-permanent-v1"),\n'
        '                              ("диагностика", "-diag.html"),'
    )
    if source.count(old_guard) != 1:
        raise RepairBlocked("yadro_publication_guard_changed")
    source = source.replace(old_guard, new_guard, 1)
    _validate_yadro(source)
    return source


def _validate_yadro(source: str) -> None:
    compile(source, YADRO_PATH, "exec")
    for value in (
        CONTRACT, "def _ua_delivery_stage_anchor(m):", START_MARKER,
        END_MARKER, "return _ua_delivery_stage_anchor(m)", DIAG_MARKER,
        '("этапы навсегда", "UA-ART-DELIVERY-STAGES-PERMANENT-V1:START")',
    ):
        if value not in source:
            raise RepairBlocked("yadro_contract_missing:" + value)


def _patch_cars_ui(source: str, original_sha: str) -> str:
    if CONTRACT in source:
        _validate_cars_ui(source)
        return source
    if original_sha != EXPECTED_SHA[CARS_UI_PATH]:
        raise RepairBlocked("cars_ui_sha_changed")
    preserved_before = {name: _function_sha(source, name) for name in PRESERVE_FUNCTIONS}
    for name, expected in PRESERVE_FUNCTIONS.items():
        if preserved_before[name] != expected:
            raise RepairBlocked("preserved_function_changed:" + name)
    source = _replace_function(
        source, "card_kb", NEW_CARD_KB,
        EXPECTED_FUNCTION_SHA[(CARS_UI_PATH, "card_kb")],
    )
    source = _replace_function(
        source, "stage_menu", NEW_STAGE_MENU,
        EXPECTED_FUNCTION_SHA[(CARS_UI_PATH, "stage_menu")],
    )
    source = _replace_function(
        source, "stage_set", NEW_STAGE_SET,
        EXPECTED_FUNCTION_SHA[(CARS_UI_PATH, "stage_set")],
    )
    if source.count(OLD_EDITABLE) != 1:
        raise RepairBlocked("cars_ui_editable_pattern_changed")
    source = source.replace(OLD_EDITABLE, NEW_EDITABLE, 1)
    for name, value in preserved_before.items():
        if _function_sha(source, name) != value:
            raise RepairBlocked("preserved_function_modified:" + name)
    _validate_cars_ui(source)
    return source


def _validate_cars_ui(source: str) -> None:
    compile(source, CARS_UI_PATH, "exec")
    required = (
        CONTRACT, '"🚚 Доставка и этапы"', '"Редактировать данные"',
        '"Комплексная диагностика"', '"📦 Контейнер, даты и сроки"',
        'pattern=r"^car_price:"', 'pattern=r"^car_keepprice:"',
        'pattern=r"^car_setf:"',
    )
    for value in required:
        if value not in source:
            raise RepairBlocked("cars_ui_contract_missing:" + value)
    card_segment = _source_segment(source, _function_nodes(source, "card_kb")[0])
    forbidden_card_labels = (
        "Сменить этап", "Срок доставки", "Цена по этапам",
        'InlineKeyboardButton("Описание"',
    )
    if any(value in card_segment for value in forbidden_card_labels):
        raise RepairBlocked("cars_ui_duplicate_main_button_remains")
    for label in (
        "Редактировать данные", "Фото и видео", "🚚 Доставка и этапы",
        "Комплексная диагностика", "Покупатель", "Как видит покупатель",
        "Разместить объявление", "Продано", "Удалить", "← Все автомобили",
    ):
        if label not in card_segment:
            raise RepairBlocked("cars_ui_main_action_missing:" + label)
    stage_segment = _source_segment(source, _function_nodes(source, "stage_set")[0])
    for forbidden in (
        "ЦЕНА НА ЭТОМ ЭТАПЕ", "Оставить прежнюю", "Изменить срок доставки",
        '"car_wait"', '"eta_manual", ""', '"days_to_kyiv", ""',
    ):
        if forbidden in stage_segment:
            raise RepairBlocked("cars_ui_stage_duplicate_remains:" + forbidden)
    assignment_match = re.search(r"(?ms)^# UA-CARDS-STAGE-ANCHOR-001-V1\.1 · only general vehicle data here\.\nEDITABLE = \[.*?^\]", source)
    if not assignment_match:
        raise RepairBlocked("cars_ui_editable_contract_missing")
    editable = assignment_match.group(0)
    for forbidden in ("diag_link", "diag_text", "eta_days", "sea_container"):
        if forbidden in editable:
            raise RepairBlocked("cars_ui_duplicate_edit_field_remains:" + forbidden)
    for name, expected in PRESERVE_FUNCTIONS.items():
        if _function_sha(source, name) != expected:
            raise RepairBlocked("preserved_function_hash_invalid:" + name)


def _db_snapshot() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    connection = sqlite3.connect("file:" + CRM_PATH + "?mode=ro", uri=True, timeout=20)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        if str(quick).lower() != "ok":
            raise RepairBlocked("crm_quick_check_failed")
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(cars)")}
        if not {"id", "auto_number", "published", "status"}.issubset(columns):
            raise RepairBlocked("crm_schema_missing")
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM cars WHERE published=1 ORDER BY id"
        )]
        total = int(connection.execute("SELECT count(*) FROM cars").fetchone()[0])
    finally:
        connection.close()
    identifiers = []
    for row in rows:
        identifier = str(row.get("auto_number") or "").strip().upper()
        if not CARD_ID.fullmatch(identifier):
            raise RepairBlocked("invalid_published_card_id:" + identifier)
        row["auto_number"] = identifier
        identifiers.append(identifier)
    if len(rows) != 10 or len(set(identifiers)) != 10 or "UA-0009" not in identifiers:
        raise RepairBlocked("published_card_contract_changed:" + ",".join(identifiers))
    canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return rows, {
        "quick_check": "ok",
        "total_cards": total,
        "published_cards": len(rows),
        "published_ids": identifiers,
        "published_rows_sha256": _sha(canonical),
        "crm_file_sha256": _sha_file(CRM_PATH),
    }


def _media_inventory(identifiers: list[str]) -> dict[str, Any]:
    allowed_suffixes = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".webm"}
    paths: set[str] = set()
    for identifier in identifiers:
        for directory in (
            os.path.join(VIDEO_ROOT, "foto", identifier),
            os.path.join(VIDEO_ROOT, "diag", identifier),
        ):
            if os.path.isdir(directory) and not os.path.islink(directory):
                for base, dirs, files in os.walk(directory, followlinks=False):
                    dirs[:] = [name for name in dirs if not os.path.islink(os.path.join(base, name))]
                    for name in files:
                        path = os.path.join(base, name)
                        if pathlib.Path(name).suffix.lower() in allowed_suffixes:
                            paths.add(path)
        for path in glob.glob(os.path.join(VIDEO_ROOT, identifier + "*")):
            if pathlib.Path(path).suffix.lower() in allowed_suffixes:
                paths.add(path)
    digest = hashlib.sha256()
    total_bytes = 0
    per_card = {identifier: {"files": 0, "bytes": 0} for identifier in identifiers}
    for path in sorted(paths):
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise RepairBlocked("unsafe_media_file:" + path)
        rel = os.path.relpath(path, ROOT)
        identifier = next((value for value in identifiers if value in rel), None)
        if identifier is None:
            raise RepairBlocked("unowned_media_file:" + rel)
        file_sha = _sha_file(path)
        digest.update((rel + "\0" + str(info.st_size) + "\0" + file_sha + "\n").encode("utf-8"))
        total_bytes += info.st_size
        per_card[identifier]["files"] += 1
        per_card[identifier]["bytes"] += info.st_size
    return {
        "files": len(paths),
        "bytes": total_bytes,
        "sha256": digest.hexdigest(),
        "per_card": per_card,
    }


def _renderer() -> Any:
    namespace: dict[str, Any] = {"__name__": "task066_stage_renderer"}
    exec(compile(STAGE_HELPER_SOURCE, "<task066-stage-helper>", "exec"), namespace)
    return namespace["_ua_delivery_stage_anchor"]


def _find_balanced_div(source: str, start: int) -> int:
    pattern = re.compile(r"<div\b[^>]*>|</div\s*>", re.IGNORECASE)
    depth = 0
    first = True
    for match in pattern.finditer(source, start):
        token = match.group(0).lower()
        if first:
            if match.start() != start or token.startswith("</"):
                raise RepairBlocked("stage_div_start_invalid")
            first = False
        if token.startswith("</"):
            depth -= 1
            if depth == 0:
                return match.end()
        else:
            depth += 1
    raise RepairBlocked("stage_div_unbalanced")


def _find_stage_span(source: str, identifier: str) -> tuple[int, int]:
    start_count = source.count(START_MARKER)
    end_count = source.count(END_MARKER)
    if start_count or end_count:
        if start_count != 1 or end_count != 1:
            raise RepairBlocked("stage_marker_count_invalid_before:" + identifier)
        start = source.index(START_MARKER)
        end = source.index(END_MARKER, start) + len(END_MARKER)
        return start, end
    positions = [
        position for phrase in ("Где машина сейчас", "Де машина зараз", "<!--ua-art-karta-v177-->")
        for position in [source.find(phrase)] if position >= 0
    ]
    if not positions:
        raise RepairBlocked("stage_block_missing:" + identifier)
    position = min(positions)
    candidates = list(re.finditer(r"<div\b[^>]*\bclass=[\"'][^\"']*(?:blok|krt)[^\"']*[\"'][^>]*>", source[:position], re.IGNORECASE))
    for match in reversed(candidates):
        end = _find_balanced_div(source, match.start())
        if end > position:
            return match.start(), end
    raise RepairBlocked("stage_outer_block_missing:" + identifier)


def _ensure_stage_anchor(source: str, identifier: str, row: dict[str, Any], render: Any) -> str:
    if identifier not in source or "</html>" not in source.lower():
        raise RepairBlocked("invalid_card_html:" + identifier)
    start, end = _find_stage_span(source, identifier)
    candidate = source[:start] + render(row) + source[end:]
    _validate_stage_html(candidate, identifier, int(render.__globals__["_ua_stage_number"](row)))
    return candidate


def _diagnostic_link_count(source: str, identifier: str) -> int:
    return len(re.findall(
        r'href=["\']' + re.escape(identifier) + r'-diag\.html(?:\?[^"\']*)?["\']',
        source,
        flags=re.IGNORECASE,
    ))


def _diagnostic_anchor(identifier: str) -> str:
    return (
        DIAG_MARKER
        + '<a class="mcf-diag-cta" href="%s-diag.html" '
          'style="display:flex;align-items:center;gap:12px;margin:14px 0;'
          'padding:15px 16px;border-radius:14px;text-decoration:none;'
          'background:linear-gradient(180deg,rgba(212,175,55,.20),'
          'rgba(212,175,55,.08));border:1px solid rgba(212,175,55,.55);'
          'color:#f4e3ae"><span style="font-size:22px;line-height:1">🔧</span>'
          '<span style="flex:1"><span style="display:block;font-weight:800;'
          'font-size:16px">Открыть комплексную диагностику →</span>'
          '<span style="display:block;font-size:13px;opacity:.85;margin-top:3px">'
          'ЛКП · OBD · ходовая · фото · видео</span></span>'
          '<span style="font-size:20px;opacity:.8">›</span></a>' % identifier
    )


def _ensure_diag_anchor(source: str, identifier: str) -> str:
    pattern = re.compile(
        r'<a\b(?=[^>]*(?:\bclass=["\'][^"\']*\bmcf-diag-cta\b[^"\']*["\']'
        r'|\bhref=["\']' + re.escape(identifier)
        + r'-diag\.html(?:\?[^"\']*)?["\']))[^>]*>.*?</a>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = pattern.sub("", source).replace(DIAG_MARKER, "")
    purchase = re.search(
        r'<a\b(?=[^>]*\bclass=["\'][^"\']*(?:kn_kupit|dejstvie|knp\s+zol)'
        r'[^"\']*["\'])[^>]*>',
        cleaned,
        flags=re.IGNORECASE,
    )
    if purchase is None:
        purchase = re.search(
            r'<a\b[^>]*href=["\']katalog\.html(?:\?[^"\']*)?["\'][^>]*>',
            cleaned,
            flags=re.IGNORECASE,
        )
    if purchase is None:
        raise RepairBlocked("diagnostics_anchor_point_missing:" + identifier)
    candidate = cleaned[:purchase.start()] + _diagnostic_anchor(identifier) + cleaned[purchase.start():]
    if _diagnostic_link_count(candidate, identifier) != 1 or candidate.count(DIAG_MARKER) != 1:
        raise RepairBlocked("diagnostics_anchor_invalid:" + identifier)
    return candidate


def _validate_stage_html(source: str, identifier: str, expected_stage: int | None = None) -> None:
    if source.count(START_MARKER) != 1 or source.count(END_MARKER) != 1:
        raise RepairBlocked("stage_anchor_count_invalid:" + identifier)
    region = source[source.index(START_MARKER):source.index(END_MARKER) + len(END_MARKER)]
    nodes = re.findall(r'data-ua-stage="([1-4])"', region)
    if nodes != ["1", "2", "3", "4"]:
        raise RepairBlocked("stage_node_order_invalid:" + identifier)
    if region.count('data-ua-state="current"') != 1 or region.count("СЕЙЧАС") != 1:
        raise RepairBlocked("stage_current_state_invalid:" + identifier)
    for label in ("Корея", "Паром", "Грузия", "Киев"):
        if region.count('data-ua-stage-label="%s"' % label) != 1:
            raise RepairBlocked("stage_label_invalid:%s:%s" % (identifier, label))
    if expected_stage is not None:
        match = re.search(r'data-ua-stage-current="([1-4])"', region)
        if not match or int(match.group(1)) != expected_stage:
            raise RepairBlocked("stage_number_invalid:" + identifier)


def _valid_diag_page(source: str, identifier: str) -> bool:
    lowered = source.lower()
    return (
        "</html>" in lowered
        and identifier.lower() in lowered
        and ("диагност" in lowered or "diagnostic" in lowered)
        and bool(re.search(
            r'href=["\']' + re.escape(identifier) + r'\.html(?:\?[^"\']*)?["\']',
            source,
            flags=re.IGNORECASE,
        ))
    )


def _collect_candidates(rows: list[dict[str, Any]], patched: dict[str, bytes]) -> dict[str, bytes]:
    candidates = dict(patched)
    render = _renderer()
    for row in rows:
        identifier = str(row["auto_number"])
        found_primary = set()
        for root in (VIDEO_ROOT, SITE_ROOT):
            paths = {os.path.join(root, identifier + ".html")}
            paths.update(glob.glob(os.path.join(root, identifier + "-*.html")))
            for path in sorted(paths):
                name = os.path.basename(path)
                if name.startswith(identifier + "-diag"):
                    continue
                data = _read(path, required=False)
                if data is None:
                    if name == identifier + ".html":
                        raise RepairBlocked("primary_card_missing:" + path)
                    continue
                source = data.decode("utf-8")
                source = _ensure_stage_anchor(source, identifier, row, render)
                source = _ensure_diag_anchor(source, identifier)
                candidates[path] = source.encode("utf-8")
                if name == identifier + ".html":
                    found_primary.add(root)
            diag_path = os.path.join(root, identifier + "-diag.html")
            diag_data = _read(diag_path)
            assert diag_data is not None
            if not _valid_diag_page(diag_data.decode("utf-8"), identifier):
                raise RepairBlocked("diagnostics_page_invalid:" + diag_path)
        if found_primary != {VIDEO_ROOT, SITE_ROOT}:
            raise RepairBlocked("card_roots_incomplete:" + identifier)

        if os.path.isdir(ETALON_ROOT) and not os.path.islink(ETALON_ROOT):
            for path in glob.glob(os.path.join(ETALON_ROOT, "**", identifier + "*.html"), recursive=True):
                if "otklonennye" in pathlib.PurePath(path).parts:
                    continue
                if os.path.basename(path).startswith(identifier + "-diag"):
                    continue
                data = _read(path)
                assert data is not None
                source = _ensure_stage_anchor(data.decode("utf-8"), identifier, row, render)
                source = _ensure_diag_anchor(source, identifier)
                candidates[path] = source.encode("utf-8")
    return candidates


def _validate_cards(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    render = _renderer()
    results = []
    for row in rows:
        identifier = str(row["auto_number"])
        expected_stage = int(render.__globals__["_ua_stage_number"](row))
        item = {"id": identifier, "stage": expected_stage, "roots": {}}
        for root in (VIDEO_ROOT, SITE_ROOT):
            path = os.path.join(root, identifier + ".html")
            data = _read(path)
            assert data is not None
            source = data.decode("utf-8")
            _validate_stage_html(source, identifier, expected_stage)
            if _diagnostic_link_count(source, identifier) != 1 or source.count(DIAG_MARKER) != 1:
                raise RepairBlocked("diagnostics_card_contract_invalid:" + path)
            diag_data = _read(os.path.join(root, identifier + "-diag.html"))
            assert diag_data is not None
            if not _valid_diag_page(diag_data.decode("utf-8"), identifier):
                raise RepairBlocked("diagnostics_page_contract_invalid:" + path)
            item["roots"][os.path.basename(root)] = {
                "sha256": _sha(data),
                "stage_anchor_count": 1,
                "stage_nodes": 4,
                "current_nodes": 1,
                "diagnostics_links": 1,
            }
        results.append(item)
    return results


def _fixture_contract() -> dict[str, int]:
    render = _renderer()
    fixtures = {
        "korea": {"auto_number": "UA-9001", "status": "kr_bought"},
        "ferry": {"auto_number": "UA-9002", "status": "sea_loaded"},
        "georgia": {"auto_number": "UA-9003", "status": "ge_waiting"},
        "kyiv": {"auto_number": "UA-9004", "status": "ua_ready"},
    }
    result = {}
    for name, row in fixtures.items():
        page = "<html><body>" + render(row) + "</body></html>"
        expected = {"korea": 1, "ferry": 2, "georgia": 3, "kyiv": 4}[name]
        _validate_stage_html(page, str(row["auto_number"]), expected)
        result[name] = expected
    return result


def _validate_untouched() -> dict[str, str]:
    values = {}
    for path in (DB_PATH, TEAM_BOT_PATH, START_SAFE_PATH):
        data = _read(path)
        assert data is not None
        digest = _sha(data)
        if digest != EXPECTED_SHA[path]:
            raise RepairBlocked("protected_hotfix_file_changed:" + os.path.basename(path))
        compile(data.decode("utf-8"), path, "exec")
        values[os.path.basename(path)] = digest
    return values


def _build_sources() -> tuple[dict[str, bytes], dict[str, str]]:
    candidates = {}
    before_hashes = {}
    for path, patcher in (
        (STRANICA_PATH, _patch_stranica),
        (YADRO_PATH, _patch_yadro),
        (CARS_UI_PATH, _patch_cars_ui),
    ):
        data = _read(path)
        assert data is not None
        digest = _sha(data)
        before_hashes[os.path.basename(path)] = digest
        candidate = patcher(data.decode("utf-8"), digest).encode("utf-8")
        compile(candidate.decode("utf-8"), path, "exec")
        candidates[path] = candidate
    return candidates, before_hashes


def run_install() -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "mode": MODE,
        "contract_id": CONTRACT,
        "status": "BLOCKED",
        "generated_at_utc": _utc_now(),
        "production_write": False,
        "production_files_changed": 0,
        "crm_write": False,
        "db_write": False,
        "media_write": False,
        "bot_reload_required": True,
        "rollback_attempted": False,
        "rollback_completed": False,
        "backup_root": "",
        "source_sha256_before": {},
        "source_sha256_after": {},
        "protected_files": {},
        "db_before": {},
        "db_after": {},
        "media_before": {},
        "media_after": {},
        "card_ids": [],
        "cards": [],
        "fixtures": {},
        "changed_paths": [],
        "errors": [],
        "llm_tokens": 0,
    }
    before: dict[str, bytes | None] = {}
    changed: list[str] = []
    try:
        receipt["protected_files"] = _validate_untouched()
        rows, db_before = _db_snapshot()
        identifiers = [str(row["auto_number"]) for row in rows]
        receipt["card_ids"] = identifiers
        receipt["db_before"] = db_before
        media_before = _media_inventory(identifiers)
        receipt["media_before"] = media_before

        source_candidates, before_hashes = _build_sources()
        receipt["source_sha256_before"] = before_hashes
        candidates = _collect_candidates(rows, source_candidates)
        receipt["fixtures"] = _fixture_contract()

        for path, data in candidates.items():
            if not data or len(data) > MAX_FILE_BYTES:
                raise RepairBlocked("candidate_size_invalid:" + path)
            if path.endswith(".py"):
                compile(data.decode("utf-8"), path, "exec")
            elif "</html>" not in data[-1200:].decode("utf-8", "ignore").lower():
                raise RepairBlocked("candidate_html_truncated:" + path)
            before[path] = _read(path, required=False)

        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bundle_hash = _sha(b"".join(candidates[path] for path in sorted(candidates)))[:12]
        backup_root = os.path.join(BACKUP_PARENT, stamp + "-" + bundle_hash)
        os.makedirs(backup_root, mode=0o700, exist_ok=False)
        receipt["backup_root"] = backup_root
        manifest = []
        for path in sorted(candidates):
            old = before[path]
            rel = os.path.relpath(path, ROOT)
            if old is not None:
                backup_path = os.path.join(backup_root, rel)
                _atomic_write(backup_path, old, _mode_for(path))
            manifest.append({
                "path": rel,
                "existed": old is not None,
                "before_sha256": _sha(old) if old is not None else None,
                "candidate_sha256": _sha(candidates[path]),
            })
        _atomic_write(
            os.path.join(backup_root, "manifest.json"),
            (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )

        # Fail closed on concurrent page/source or CRM changes before write one.
        _, db_check = _db_snapshot()
        if db_check["published_rows_sha256"] != db_before["published_rows_sha256"]:
            raise RepairBlocked("crm_rows_changed_before_install")
        for path in sorted(candidates):
            if _read(path, required=False) != before[path]:
                raise RepairBlocked("concurrent_file_change:" + path)

        for path in sorted(candidates):
            old = before[path]
            candidate = candidates[path]
            if old == candidate:
                continue
            _atomic_write(path, candidate, _mode_for(path))
            changed.append(path)
            receipt["production_write"] = True
            receipt["production_files_changed"] = len(changed)
            if _read(path) != candidate:
                raise RepairBlocked("readback_mismatch:" + path)

        _validate_stranica(_read(STRANICA_PATH).decode("utf-8"))
        _validate_yadro(_read(YADRO_PATH).decode("utf-8"))
        _validate_cars_ui(_read(CARS_UI_PATH).decode("utf-8"))
        receipt["cards"] = _validate_cards(rows)
        rows_after, db_after = _db_snapshot()
        receipt["db_after"] = db_after
        media_after = _media_inventory(identifiers)
        receipt["media_after"] = media_after
        if [row["auto_number"] for row in rows_after] != identifiers:
            raise RepairBlocked("published_ids_changed_during_install")
        if db_after["published_rows_sha256"] != db_before["published_rows_sha256"]:
            raise RepairBlocked("crm_rows_changed_during_install")
        if media_after != media_before:
            raise RepairBlocked("media_inventory_changed_during_install")
        receipt["source_sha256_after"] = {
            os.path.basename(path): _sha(_read(path))
            for path in (STRANICA_PATH, YADRO_PATH, CARS_UI_PATH)
        }
        receipt["changed_paths"] = [os.path.relpath(path, ROOT) for path in changed]
        receipt["status"] = "PASS"
    except Exception as exc:
        receipt["errors"].append(str(exc) if isinstance(exc, RepairBlocked) else type(exc).__name__ + ":" + str(exc))
        if changed:
            receipt["rollback_attempted"] = True
            rollback_errors = []
            for path in reversed(changed):
                try:
                    old = before[path]
                    if old is None:
                        if os.path.exists(path):
                            os.unlink(path)
                            _fsync_dir(os.path.dirname(path))
                    else:
                        _atomic_write(path, old, _mode_for(path))
                    if _read(path, required=False) != old:
                        raise RepairBlocked("rollback_readback_mismatch")
                except Exception:
                    rollback_errors.append("rollback_failed:" + path)
            receipt["rollback_completed"] = not rollback_errors
            receipt["errors"].extend(rollback_errors)
            receipt["status"] = "ROLLED_BACK" if not rollback_errors else "BLOCKED"
    return receipt


def rollback_from_receipt() -> dict[str, Any]:
    result = {"contract_id": CONTRACT, "status": "BLOCKED", "restored": [], "errors": []}
    try:
        receipt = json.loads(_read(RECEIPT_PATH).decode("utf-8"))
        backup_root = str(receipt.get("backup_root") or "")
        if os.path.commonpath((os.path.realpath(BACKUP_PARENT), os.path.realpath(backup_root))) != os.path.realpath(BACKUP_PARENT):
            raise RepairBlocked("rollback_backup_path_invalid")
        manifest = json.loads(_read(os.path.join(backup_root, "manifest.json")).decode("utf-8"))
        changed = set(receipt.get("changed_paths") or [])
        by_path = {str(item["path"]): item for item in manifest}
        if not changed or not changed.issubset(by_path):
            raise RepairBlocked("rollback_manifest_invalid")
        for rel in reversed(receipt["changed_paths"]):
            target = os.path.join(ROOT, rel)
            item = by_path[rel]
            if item["existed"]:
                backup = os.path.join(backup_root, rel)
                data = _read(backup)
                assert data is not None
                if _sha(data) != item["before_sha256"]:
                    raise RepairBlocked("rollback_backup_hash_invalid:" + rel)
                _atomic_write(target, data, _mode_for(target))
            elif os.path.exists(target):
                os.unlink(target)
                _fsync_dir(os.path.dirname(target))
            result["restored"].append(rel)
        for rel in changed:
            item = by_path[rel]
            current = _read(os.path.join(ROOT, rel), required=False)
            if (current is not None) != bool(item["existed"]):
                raise RepairBlocked("rollback_existence_invalid:" + rel)
            if current is not None and _sha(current) != item["before_sha256"]:
                raise RepairBlocked("rollback_readback_invalid:" + rel)
        result["status"] = "PASS"
    except Exception as exc:
        result["errors"].append(str(exc) if isinstance(exc, RepairBlocked) else type(exc).__name__ + ":" + str(exc))
    return result


def self_test() -> int:
    fixtures = _fixture_contract()
    if fixtures != {"korea": 1, "ferry": 2, "georgia": 3, "kyiv": 4}:
        raise SystemExit("TASK066_FIXTURE_CONTRACT_FAIL")
    render = _renderer()
    row = {
        "auto_number": "UA-9999", "status": "sea_loaded",
        "sea_container": "<script>", "sea_date_out": "2026-08-01",
        "eta_manual": "2099-01-01",
    }
    anchor = render(row)
    if "<script>" in anchor or "&lt;script&gt;" not in anchor:
        raise SystemExit("TASK066_ESCAPE_FAIL")
    old = (
        "<html><body><div>UA-9999</div>"
        "<div class='blok'><div class='zag'>Где машина сейчас</div>"
        "<div class='etap tut'><div class='krug'>2</div>Море</div></div>"
        "<a class='dejstvie kn_kupit' href='#'>Купить</a></body></html>"
    )
    upgraded = _ensure_stage_anchor(old, "UA-9999", row, render)
    upgraded = _ensure_diag_anchor(upgraded, "UA-9999")
    upgraded_twice = _ensure_stage_anchor(upgraded, "UA-9999", row, render)
    upgraded_twice = _ensure_diag_anchor(upgraded_twice, "UA-9999")
    if upgraded != upgraded_twice:
        raise SystemExit("TASK066_IDEMPOTENCY_FAIL")
    _validate_stage_html(upgraded, "UA-9999", 2)
    if _diagnostic_link_count(upgraded, "UA-9999") != 1:
        raise SystemExit("TASK066_DIAGNOSTICS_FAIL")
    for value in (NEW_CARD_KB, NEW_STAGE_MENU, NEW_STAGE_SET):
        compile(value, "<task066-crm-fragment>", "exec")
    print("TASK066_SELF_TEST_PASS")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    descriptor = os.open(LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            result = {
                "mode": MODE, "contract_id": CONTRACT, "status": "BLOCKED",
                "errors": ["concurrent_repair_run"], "llm_tokens": 0,
            }
        else:
            result = rollback_from_receipt() if "--rollback" in sys.argv else run_install()
    finally:
        os.close(descriptor)
    path = ROLLBACK_RECEIPT_PATH if "--rollback" in sys.argv else RECEIPT_PATH
    _atomic_json(path, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
