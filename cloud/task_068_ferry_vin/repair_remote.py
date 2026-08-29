#!/usr/bin/env python3
"""Atomic production installer for UA-CARDS-FERRY-VIN-001 V1.1.

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
import time
from typing import Any


MODE = "UA_CARDS_FERRY_VIN_001_V1_1_ATOMIC_INSTALL"
CONTRACT = "UA-CARDS-FERRY-VIN-001-V1.1"
UNIFIED_CONTRACT = "UA-CARDS-UNIFIED-SHELL-001-V1.1"
CARHISTORY_URL = "https://www.carhistory.kr/search/carhistory/search.car?lang=ru"
ROOT = "/home/Carix"
VIDEO_ROOT = ROOT + "/video"
SITE_ROOT = ROOT + "/site"
ETALON_ROOT = ROOT + "/etalon"
CRM_PATH = ROOT + "/crm.db"
STRANICA_PATH = ROOT + "/stranica.py"
YADRO_PATH = ROOT + "/yadro.py"
CARS_UI_PATH = ROOT + "/cars_ui.py"
MASTER_CARD_PATH = ROOT + "/master_card.py"
DB_PATH = ROOT + "/db.py"
TEAM_BOT_PATH = ROOT + "/team_bot.py"
START_SAFE_PATH = ROOT + "/start_safe.py"
SAFE_ROOT = ROOT + "/autopilot_inbox/cloud/task_068_ferry_vin"
RECEIPT_PATH = SAFE_ROOT + "/install_receipt.json"
SOURCE_RECEIPT_PATH = SAFE_ROOT + "/source_install_receipt.json"
ROLLBACK_RECEIPT_PATH = SAFE_ROOT + "/rollback_receipt.json"
BACKUP_PARENT = SAFE_ROOT + "/backups"
LOCK_PATH = ROOT + "/.task068_ferry_vin.lock"
START_MARKER = "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START -->"
END_MARKER = "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:END -->"
DIAG_MARKER = "<!--ua-art-diagnostics-permanent-v1-->"
MASTER_FINAL_SOURCE_MARKER = "# UA-CARDS-STAGE-ANCHOR-001-V1.1-MASTER-FINAL"
FERRY_VIN_SOURCE_MARKER = "# UA-CARDS-FERRY-VIN-001-V1.1-PERMANENT"
SEO_REHAB_SOURCE_MARKER = "# SEO-REHAB-GUARD-068-PRODUCTION-V1"
VIN_START_MARKER = "<!-- UA-ART-VIN-GUARD-LITE-V1:START -->"
VIN_END_MARKER = "<!-- UA-ART-VIN-GUARD-LITE-V1:END -->"
CATALOG_VIN_START = "<!-- UA-ART-CATALOG-VIN-V1:START -->"
CATALOG_VIN_END = "<!-- UA-ART-CATALOG-VIN-V1:END -->"
MAX_FILE_BYTES = 24 * 1024 * 1024
CARD_ID = re.compile(r"^UA-[0-9]{4,}$")

EXPECTED_SHA = {
    STRANICA_PATH: "6f70721a18e1df9158906690689d3aa90c95d82dc8f4745ba34567d52651b33f",
    YADRO_PATH: "05942c2e2060463d00fa7e641c72c864010bfd9e152047f3e7153413003f182e",
    CARS_UI_PATH: "862baea2ca0794f5e0d83bc04169f6d2fdec401f86f384ef4376e373c02a776b",
    MASTER_CARD_PATH: "7d31282a3c28e99fbe7e0278618205c23a6655a0461ca2b277f139ce3d60b06a",
    DB_PATH: "b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086",
    TEAM_BOT_PATH: "bbd644eaf2c25802984df930459da6a36f137ef2b1519642b3d006ab57388a48",
    START_SAFE_PATH: "2daefa4e6cee8054452ff61200f1cb4b89284a23289370bd24c8a8053674d007",
}

# Hashes produced by the first source-only phase of this same approved
# contract.  They are accepted only for the bounded v1.1 in-place upgrade
# that adds mixed/legacy catalog support; unknown source edits still block.
TASK068_INITIAL_SOURCE_SHA = {
    STRANICA_PATH: "001620f8f582c3ecbd638d0a1a557de085d019ea85fe17f5e4948f74c114931a",
    YADRO_PATH: "c95b0ef03d1d52423e48b127aefb75d22f00d17f531c0402daf178523707bb79",
    MASTER_CARD_PATH: "438559b3caf31ee66a4774e865ee52796c7e06a3f3e0785b54f96d4064e5b270",
}

# Exact source layer produced by approved SEO-REHAB-GUARD-068 production run
# 33216597557.  The rebasing path is allowed only for these three byte hashes;
# it preserves the SEO layer and moves this contract to the final boundary.
SEO_LAYERED_SOURCE_SHA = {
    STRANICA_PATH: "14d3f2f4a53468f9e82aaea3299bd6276b75485fd7dd65b289f3acd3ebc6a8bf",
    YADRO_PATH: "59fcce35b34bde3ab38603a5812310eb7157374289a951b91fc437d299b56f12",
    MASTER_CARD_PATH: "0b7cb65313bb116e85646d3e82966ea21e84bb910c133f208796fa3dc2000079",
}

# Exact hashes after the first SEO-preserving rebase (run 33217822333).  They
# permit the one bounded upgrade that relocates the canonical stage block.
SEO_FINAL_V1_SOURCE_SHA = {
    STRANICA_PATH: "b8fb7f418baa6a6a1ea586c8ef20a4d8e7e82ae1a41b5ee0f419f45882f80e49",
    YADRO_PATH: "3a44ae496ed65b769fa704cc3689add6f52c1ef1efc0f24be16fe20aa8b706f1",
    MASTER_CARD_PATH: "fe1bc2c317e303b799e4e50690c51e2ff4dd5a29612129b2cb5932b1c71def94",
}

# Exact production hashes from the successful permanent-anchor deployment.
# They allow one bounded replacement of the final task068 layer with the
# approved unified CTA + official Korean CarHistory extension.
UNIFIED_BASE_SOURCE_SHA = {
    STRANICA_PATH: "4bb4c26eee5948e1dc37b336c4c32689f51baf0fef1a2eceac86a50fe6434959",
    YADRO_PATH: "45bc957a8f2b9cbc509e5e140badbb2117bedc6857e111607c50adb2058cdc30",
    MASTER_CARD_PATH: "96bb7e99b15d6e5d8de7e825e427406945cf866b5cda300710950ab2ac803e81",
}

# Exact hashes produced by the first unified CarHistory/CTA source phase.  A
# follow-up design-only upgrade may remove the redundant Kyiv secondary line.
UNIFIED_CARHISTORY_SOURCE_SHA = {
    STRANICA_PATH: "c70402e495753c140d4ea0da4306c2e64b2a8c91d77a93a41ba8b9b02b6066a4",
    YADRO_PATH: "b5192a7f2a3c69fbb5b7df0eedc6d302c2cf4ca2bfc0a1a6b1aa4b22cf8deda3",
    MASTER_CARD_PATH: "8c48eab7589b1ebb3ef3ef107e88b313d1ff5e3d60357971585bdd10d53599ae",
}

EXPECTED_FUNCTION_SHA = {
    (STRANICA_PATH, "sobrat_kartochku"): "3d36b990a831078386477131afcaa74a40bccaa15e524c1ea2db2139673a13a8",
    (STRANICA_PATH, "sobrat_katalog"): "10d9505d2c65ec58ef5d83f928da123dcddd92d86080cfc14bedb96e262a4eea",
    (YADRO_PATH, "karta_html"): "ef758f9ceac41ce7137336e3714277ea82f3389dd608a7b4488412eb335aa833",
    (YADRO_PATH, "katalog_html"): "3c8d5b80b633e659dae0a83e2770cab7053de722f665097b29c90ae2702ff0cb",
    (MASTER_CARD_PATH, "obrabotat_kartochku:last"): "9c58f03474e99ef779bebaa0be8e4398b488f8f49e3da9f3e6bc3969acabb5a4",
    (MASTER_CARD_PATH, "proverit:last"): "8dd467b69467f5488bcc0322b7aa3b117e707bb099cb9849e194d833105a4adf",
    (MASTER_CARD_PATH, "obrabotat_obshuyu:last"): "a8f4ab89caae7cf99101f8c4d3c0b5b09487e46d1bdadedfe400a1fc89909c22",
}

PRESERVE_FUNCTIONS = {
    # CRM-PHOTO-FASTPATH-001 is the current production baseline.  The stage
    # anchor must retain its spool enqueue/worker path byte-for-byte.
    "catch_message": "2b02ec1cf0cc649618f88de40fbb3a8e37d325828b4e925c9b15dc75859a850c",
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


# Installed at the absolute end of master_card.py.  That module is the last
# filter used by the CRM/background writer, so this wrapper is the canonical
# persistence boundary: legacy filters may run first, but they cannot be the
# final HTML returned to a writer.
MASTER_CARD_FINAL_SOURCE = r'''
# UA-CARDS-STAGE-ANCHOR-001-V1.1-MASTER-FINAL
_UA_MASTER_DIAG_MARKER = "<!--ua-art-diagnostics-permanent-v1-->"


def _ua_master_balanced_div_end(source, start):
    pattern = re.compile(r"<div\b[^>]*>|</div\s*>", re.IGNORECASE)
    depth = 0
    first = True
    for match in pattern.finditer(source, start):
        token = match.group(0).lower()
        if first:
            if match.start() != start or token.startswith("</"):
                raise RuntimeError("UA_STAGE_DIV_START_INVALID")
            first = False
        if token.startswith("</"):
            depth -= 1
            if depth == 0:
                return match.end()
        else:
            depth += 1
    raise RuntimeError("UA_STAGE_DIV_UNBALANCED")


def _ua_master_remove_class_divs(source, class_names):
    terms = "|".join(re.escape(value) for value in class_names)
    pattern = re.compile(
        r'<div\b[^>]*\bclass=["\'][^"\']*\b(?:' + terms
        + r')\b[^"\']*["\'][^>]*>',
        re.IGNORECASE,
    )
    while True:
        match = pattern.search(source)
        if match is None:
            return source
        end = _ua_master_balanced_div_end(source, match.start())
        source = source[:match.start()] + source[end:]


def _ua_master_stage_span(source):
    start_count = source.count(_UA_STAGE_START)
    end_count = source.count(_UA_STAGE_END)
    if start_count or end_count:
        if start_count != 1 or end_count != 1:
            raise RuntimeError("UA_STAGE_MARKER_COUNT_INVALID")
        start = source.index(_UA_STAGE_START)
        end = source.index(_UA_STAGE_END, start) + len(_UA_STAGE_END)
        return start, end

    positions = []
    for phrase in ("Где машина сейчас", "Де машина зараз", "<!--ua-art-karta-v177-->"):
        position = source.find(phrase)
        if position >= 0:
            positions.append(position)
    if not positions:
        return None
    position = min(positions)
    candidates = list(re.finditer(
        r'<div\b[^>]*\bclass=["\'][^"\']*(?:blok|krt)[^"\']*["\'][^>]*>',
        source[:position],
        re.IGNORECASE,
    ))
    for match in reversed(candidates):
        end = _ua_master_balanced_div_end(source, match.start())
        if end > position:
            return match.start(), end
    return None


def _ua_master_stage_errors(source, row):
    errors = []
    if source.count(_UA_STAGE_START) != 1 or source.count(_UA_STAGE_END) != 1:
        return ["постоянных блоков этапов не ровно один"]
    start = source.index(_UA_STAGE_START)
    end = source.index(_UA_STAGE_END, start) + len(_UA_STAGE_END)
    region = source[start:end]
    if re.findall(r'data-ua-stage="([1-4])"', region) != ["1", "2", "3", "4"]:
        errors.append("этапы Корея/Паром/Грузия/Киев повреждены")
    if region.count('data-ua-state="current"') != 1 or region.count("СЕЙЧАС") != 1:
        errors.append("текущий этап не единственный")
    expected = _ua_stage_number(row)
    current = re.search(r'data-ua-stage-current="([1-4])"', region)
    if current is None or int(current.group(1)) != expected:
        errors.append("текущий этап не совпадает с CRM")
    for label in _UA_STAGE_LABELS:
        if region.count('data-ua-stage-label="%s"' % label) != 1:
            errors.append("пропала метка этапа %s" % label)
    if re.search(r'class=["\'][^"\']*\bmcf-etap\b', source, re.IGNORECASE):
        errors.append("остался дублирующий старый блок этапа")
    if re.search(r'class=["\'][^"\']*\bmcf-track\b', source, re.IGNORECASE):
        errors.append("осталась дублирующая старая кнопка контейнера")
    if "Автомобиль в море: Корея → Грузия" in source:
        errors.append("осталась старая формулировка «в море»")
    return errors


def _ua_master_ensure_stage(source, kod, row):
    if not source or "</html>" not in source.lower():
        raise RuntimeError("UA_STAGE_INVALID_CARD:%s" % kod)
    source = _ua_master_remove_class_divs(source, ("mcf-etap", "mcf-track"))
    span = _ua_master_stage_span(source)
    block = _ua_delivery_stage_anchor(row)
    if span is not None:
        source = source[:span[0]] + block + source[span[1]:]
    else:
        position = -1
        for needle in (_UA_MASTER_DIAG_MARKER, "Комплексная диагностика", "Купить авто"):
            position = source.find(needle)
            if position >= 0:
                tag = source.rfind("<", 0, position)
                if tag >= 0:
                    position = tag
                break
        if position < 0:
            position = source.lower().rfind("</body>")
        if position < 0:
            raise RuntimeError("UA_STAGE_INSERTION_POINT_MISSING:%s" % kod)
        source = source[:position] + block + source[position:]
    errors = _ua_master_stage_errors(source, row)
    if errors:
        raise RuntimeError("UA_STAGE_FINAL_INVALID:%s:%s" % (kod, ";".join(errors)))
    return source


def _ua_master_diag_anchor(kod):
    return (
        _UA_MASTER_DIAG_MARKER
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
          '<span style="font-size:20px;opacity:.8">›</span></a>' % kod
    )


def _ua_master_diag_errors(source, kod):
    errors = []
    if source.count(_UA_MASTER_DIAG_MARKER) != 1:
        errors.append("постоянных меток диагностики не ровно одна")
    links = re.findall(
        r'href=["\']' + re.escape(kod) + r'-diag\.html(?:\?[^"\']*)?["\']',
        source,
        re.IGNORECASE,
    )
    if len(links) != 1:
        errors.append("ссылок комплексной диагностики не ровно одна")
    if re.search(r'class=["\'][^"\']*\bmcf-diag-off\b', source, re.IGNORECASE):
        errors.append("диагностика ошибочно зависит от наличия материалов")
    return errors


def _ua_master_ensure_diag(source, kod):
    anchor_pattern = re.compile(
        r'<a\b(?=[^>]*(?:\bclass=["\'][^"\']*\bmcf-diag-cta\b[^"\']*["\']'
        r'|\bhref=["\'](?:[^"\']*/)?' + re.escape(kod)
        + r'-diag\.html(?:\?[^"\']*)?["\']))[^>]*>.*?</a\s*>',
        re.IGNORECASE | re.DOTALL,
    )
    source = anchor_pattern.sub("", source).replace(_UA_MASTER_DIAG_MARKER, "")
    source = _ua_master_remove_class_divs(source, ("mcf-diag-cta",))
    purchase = re.search(
        r'<a\b(?=[^>]*\bclass=["\'][^"\']*(?:kn_kupit|dejstvie|knp\s+zol)'
        r'[^"\']*["\'])[^>]*>',
        source,
        re.IGNORECASE,
    )
    if purchase is None:
        purchase = re.search(
            r'<a\b[^>]*href=["\']katalog\.html(?:\?[^"\']*)?["\'][^>]*>',
            source,
            re.IGNORECASE,
        )
    position = purchase.start() if purchase is not None else source.lower().rfind("</body>")
    if position < 0:
        raise RuntimeError("UA_DIAGNOSTICS_INSERTION_POINT_MISSING:%s" % kod)
    source = source[:position] + _ua_master_diag_anchor(kod) + source[position:]
    errors = _ua_master_diag_errors(source, kod)
    if errors:
        raise RuntimeError("UA_DIAGNOSTICS_FINAL_INVALID:%s:%s" % (kod, ";".join(errors)))
    return source


# Even direct callers of the old helper can no longer receive a disabled CTA.
def cta_diagnostiki(kod, m=None):
    return _ua_master_diag_anchor(kod)


_ua_master_original_card = obrabotat_kartochku


def obrabotat_kartochku(html, kod):
    html = _ua_master_original_card(html, kod)
    if not html:
        return html
    kod = "%s" % kod
    row = dict(dannye(kod) or {})
    row.setdefault("auto_number", kod)
    html = _ua_master_ensure_stage(html, kod, row)
    html = _ua_master_ensure_diag(html, kod)
    errors = _ua_master_stage_errors(html, row) + _ua_master_diag_errors(html, kod)
    if errors:
        raise RuntimeError("UA_MASTER_FINAL_CONTRACT:%s:%s" % (kod, ";".join(errors)))
    return html


_ua_master_original_validate = proverit


def proverit(html, kod=""):
    errors = list(_ua_master_original_validate(html, kod) or [])
    if kod:
        row = dict(dannye(kod) or {})
        row.setdefault("auto_number", kod)
        errors.extend(_ua_master_stage_errors(html, row))
        errors.extend(_ua_master_diag_errors(html, kod))
    result = []
    for error in errors:
        if error not in result:
            result.append(error)
    return result
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
        [InlineKeyboardButton("🇰🇷 Проверить VIN · CarHistory",
                              url="https://www.carhistory.kr/search/carhistory/search.car?lang=ru")],
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


def _patch_master_card(source: str, original_sha: str) -> str:
    if MASTER_FINAL_SOURCE_MARKER in source:
        _validate_master_card(source)
        return source
    if original_sha != EXPECTED_SHA[MASTER_CARD_PATH]:
        raise RepairBlocked("master_card_sha_changed")
    if _function_sha(source, "obrabotat_kartochku", last=True) != EXPECTED_FUNCTION_SHA[
        (MASTER_CARD_PATH, "obrabotat_kartochku:last")
    ]:
        raise RepairBlocked("master_card_final_writer_changed")
    if _function_sha(source, "proverit", last=True) != EXPECTED_FUNCTION_SHA[
        (MASTER_CARD_PATH, "proverit:last")
    ]:
        raise RepairBlocked("master_card_final_validator_changed")
    source = source.rstrip() + "\n\n" + STAGE_HELPER_SOURCE + "\n\n" + MASTER_CARD_FINAL_SOURCE + "\n"
    _validate_master_card(source)
    return source


def _validate_master_card(source: str) -> None:
    compile(source, MASTER_CARD_PATH, "exec")
    required = (
        MASTER_FINAL_SOURCE_MARKER,
        "def _ua_delivery_stage_anchor(m):",
        "def _ua_master_ensure_stage(source, kod, row):",
        "def _ua_master_ensure_diag(source, kod):",
        "def cta_diagnostiki(kod, m=None):",
        "html = _ua_master_ensure_stage(html, kod, row)",
        "html = _ua_master_ensure_diag(html, kod)",
        START_MARKER,
        END_MARKER,
        DIAG_MARKER,
    )
    for value in required:
        if value not in source:
            raise RepairBlocked("master_card_contract_missing:" + value)
    if source.count(MASTER_FINAL_SOURCE_MARKER) != 1:
        raise RepairBlocked("master_card_final_marker_count_invalid")
    card_nodes = _function_nodes(source, "obrabotat_kartochku")
    validate_nodes = _function_nodes(source, "proverit")
    if len(card_nodes) < 3 or len(validate_nodes) < 3:
        raise RepairBlocked("master_card_final_wrapper_missing")
    final_card = _source_segment(source, card_nodes[-1])
    final_validate = _source_segment(source, validate_nodes[-1])
    if "_ua_master_original_card" not in final_card or "_ua_master_ensure_stage" not in final_card:
        raise RepairBlocked("master_card_final_writer_not_last")
    if "_ua_master_stage_errors" not in final_validate or "_ua_master_diag_errors" not in final_validate:
        raise RepairBlocked("master_card_final_validator_not_last")


def _patch_cars_ui(source: str, original_sha: str) -> str:
    if "🇰🇷 Проверить VIN · CarHistory" in source:
        _validate_cars_ui(source)
        return source
    # Production already contains the approved stage-anchor CRM menu.  For
    # this additive contract replace only its exact current card_kb function;
    # stage handlers, media fast path and all other functions stay untouched.
    if (original_sha == EXPECTED_SHA[CARS_UI_PATH]
            and "UA-CARDS-STAGE-ANCHOR-001-V1.1" in source):
        preserved_before = {name: _function_sha(source, name) for name in PRESERVE_FUNCTIONS}
        source = _replace_function(
            source, "card_kb", NEW_CARD_KB,
            "fda0d3e7644e3cae77a176305d06ee1cb5f88ad210f5e99a515a4b0d77e8b608",
        )
        for name, value in preserved_before.items():
            if _function_sha(source, name) != value:
                raise RepairBlocked("preserved_function_modified:" + name)
        _validate_cars_ui(source)
        return source
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
        '"🚚 Доставка и этапы"', '"Редактировать данные"',
        '"Комплексная диагностика"', '"📦 Контейнер, даты и сроки"',
        'pattern=r"^car_price:"', 'pattern=r"^car_keepprice:"',
        'pattern=r"^car_setf:"',
        '"🇰🇷 Проверить VIN · CarHistory"',
        'https://www.carhistory.kr/search/carhistory/search.car?lang=ru',
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
        "Комплексная диагностика", "🇰🇷 Проверить VIN · CarHistory",
        "Покупатель", "Как видит покупатель",
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
    if (len(rows) < 10 or len(set(identifiers)) != len(rows)
            or not {"UA-0009", "UA-0010"}.issubset(identifiers)):
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


def _remove_class_divs(source: str, class_names: tuple[str, ...]) -> str:
    terms = "|".join(re.escape(value) for value in class_names)
    pattern = re.compile(
        r'<div\b[^>]*\bclass=["\'][^"\']*\b(?:' + terms
        + r')\b[^"\']*["\'][^>]*>',
        re.IGNORECASE,
    )
    while True:
        match = pattern.search(source)
        if match is None:
            return source
        end = _find_balanced_div(source, match.start())
        source = source[:match.start()] + source[end:]


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
    source = _remove_class_divs(source, ("mcf-etap", "mcf-track"))
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
    cleaned = _remove_class_divs(cleaned, ("mcf-diag-cta",))
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
    if (_diagnostic_link_count(candidate, identifier) != 1
            or candidate.count(DIAG_MARKER) != 1
            or "mcf-diag-off" in candidate):
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
    if re.search(r'class=["\'][^"\']*\b(?:mcf-etap|mcf-track)\b', source, re.IGNORECASE):
        raise RepairBlocked("legacy_stage_duplicate_remains:" + identifier)
    if "Автомобиль в море: Корея → Грузия" in source:
        raise RepairBlocked("legacy_sea_wording_remains:" + identifier)


def _valid_diag_page(source: str, identifier: str) -> bool:
    # The diagnostics CTA is permanent even while a report is empty or uses a
    # legacy template. Validate only that its target is a complete HTML page;
    # optional report copy and backlinks must not control card publication.
    lowered = source.lower()
    return (
        "<html" in lowered
        and "<body" in lowered
        and "</html>" in lowered
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
                # Background writers may briefly leave a zero-byte hashed
                # variant before atomic replacement. It is not the canonical
                # card and must not block the full contract; primary pages
                # remain strict and zero-byte variants are never published by
                # this installer.
                if name != identifier + ".html":
                    try:
                        if os.path.getsize(path) == 0:
                            continue
                    except OSError:
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
            if (_diagnostic_link_count(source, identifier) != 1
                    or source.count(DIAG_MARKER) != 1
                    or "mcf-diag-off" in source):
                raise RepairBlocked("diagnostics_card_contract_invalid:" + path)
            item["roots"][os.path.basename(root)] = {
                "sha256": _sha(data),
                "stage_anchor_count": 1,
                "stage_nodes": 4,
                "current_nodes": 1,
                "diagnostics_links": 1,
                "diagnostics_target": identifier + "-diag.html",
                "diagnostics_content_required": False,
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


def _master_final_fixture_contract() -> dict[str, int]:
    state: dict[str, Any] = {"row": {}}
    namespace: dict[str, Any] = {
        "__name__": "task066_master_final_fixture",
        "re": re,
        "dannye": lambda _kod: dict(state["row"]),
        "obrabotat_kartochku": lambda source, _kod: source,
        "proverit": lambda _source, _kod="": [],
    }
    installed = STAGE_HELPER_SOURCE + "\n\n" + MASTER_CARD_FINAL_SOURCE
    exec(compile(installed, "<task066-master-final-fixture>", "exec"), namespace)
    fixtures = {
        "korea": {"auto_number": "UA-9101", "status": "kr_bought"},
        "ferry": {"auto_number": "UA-9102", "status": "sea_loaded"},
        "georgia": {"auto_number": "UA-9103", "status": "ge_waiting"},
        "kyiv": {"auto_number": "UA-9104", "status": "ua_ready"},
    }
    expected_by_name = {"korea": 1, "ferry": 2, "georgia": 3, "kyiv": 4}
    result: dict[str, int] = {}
    for name, row in fixtures.items():
        state["row"] = row
        identifier = str(row["auto_number"])
        old = (
            "<html><body><header>UA ART</header><div>%s</div>"
            "<div class='blok'><div class='zag'>Где машина сейчас</div>"
            "<div class='etap tut'><div class='krug'>2</div>Море</div></div>"
            "<div class='mcf-etap mcf-sea'><div>Автомобиль в море: Корея → Грузия</div></div>"
            "<h2>Комплексная диагностика</h2>"
            "<div class='mcf-diag-cta mcf-diag-off'><span>Диагностика готовится</span></div>"
            "<a class='dejstvie kn_kupit' href='#'>Купить авто</a></body></html>"
        ) % identifier
        upgraded = namespace["obrabotat_kartochku"](old, identifier)
        upgraded_twice = namespace["obrabotat_kartochku"](upgraded, identifier)
        if upgraded != upgraded_twice:
            raise RepairBlocked("master_card_final_not_idempotent:" + identifier)
        expected = expected_by_name[name]
        _validate_stage_html(upgraded, identifier, expected)
        if _diagnostic_link_count(upgraded, identifier) != 1 or upgraded.count(DIAG_MARKER) != 1:
            raise RepairBlocked("master_card_final_diagnostics_invalid:" + identifier)
        if "mcf-diag-off" in upgraded or "mcf-etap" in upgraded or "Автомобиль в море:" in upgraded:
            raise RepairBlocked("master_card_final_legacy_content_remains:" + identifier)
        if namespace["proverit"](upgraded, identifier):
            raise RepairBlocked("master_card_final_validator_rejected:" + identifier)
        direct_cta = namespace["cta_diagnostiki"](identifier, {})
        if DIAG_MARKER not in direct_cta or (identifier + "-diag.html") not in direct_cta:
            raise RepairBlocked("master_card_direct_diagnostics_not_permanent:" + identifier)
        result[name] = expected
    return result


FERRY_VIN_COMMON_SOURCE = r'''
# UA-CARDS-FERRY-VIN-001-V1.1-PERMANENT
import datetime as _ua068_dt
import html as _ua068_html
import os as _ua068_os
import re as _ua068_re
import tempfile as _ua068_tempfile

_UA068_VIN_START = "<!-- UA-ART-VIN-GUARD-LITE-V1:START -->"
_UA068_VIN_END = "<!-- UA-ART-VIN-GUARD-LITE-V1:END -->"
_UA068_CAT_START = "<!-- UA-ART-CATALOG-VIN-V1:START -->"
_UA068_CAT_END = "<!-- UA-ART-CATALOG-VIN-V1:END -->"
_UA068_FALLBACK_START = "<!-- UA-ART-CATALOG-CARD-FALLBACK-V1:START -->"
_UA068_FALLBACK_END = "<!-- UA-ART-CATALOG-CARD-FALLBACK-V1:END -->"
_UA068_STAGE_START = "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START -->"
_UA068_STAGE_END = "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:END -->"
_UA068_DIAG = "<!--ua-art-diagnostics-permanent-v1-->"
_UA068_VERSION = "ua06811"
_UA068_CARHISTORY_URL = "https://www.carhistory.kr/search/carhistory/search.car?lang=ru"


def _ua068_e(value):
    return _ua068_html.escape(str(value or ""), quote=True)


def _ua068_terms(source):
    """Remove only user-facing sea wording; internal ASCII status aliases stay intact."""
    if not source:
        return source
    rules = (
        (r"(?i)(?<![А-Яа-яЁёІіЇїЄє])в\s+море(?![А-Яа-яЁёІіЇїЄє])", "на пароме", "На пароме"),
        (r"(?i)(?<![А-Яа-яЁёІіЇїЄє])на\s+море(?![А-Яа-яЁёІіЇїЄє])", "на пароме", "На пароме"),
        (r"(?i)(?<![А-Яа-яЁёІіЇїЄє])у\s+мор[іi](?![А-Яа-яЁёІіЇїЄє])", "на поромі", "На поромі"),
        (r"(?i)(?<![А-Яа-яЁёІіЇїЄє])в\s+мор[іi](?![А-Яа-яЁёІіЇїЄє])", "на поромі", "На поромі"),
        (r"(?i)(?<![А-Яа-яЁёІіЇїЄє])морем(?![А-Яа-яЁёІіЇїЄє])", "паромом", "Паромом"),
        (r"(?i)(?<![А-Яа-яЁёІіЇїЄє])морской(?![А-Яа-яЁёІіЇїЄє])", "паромный", "Паромный"),
        (r"(?i)(?<![А-Яа-яЁёІіЇїЄє])морская(?![А-Яа-яЁёІіЇїЄє])", "паромная", "Паромная"),
        (r"(?i)(?<![А-Яа-яЁёІіЇїЄє])морское(?![А-Яа-яЁёІіЇїЄє])", "паромное", "Паромное"),
        (r"(?i)(?<![А-Яа-яЁёІіЇїЄє])морские(?![А-Яа-яЁёІіЇїЄє])", "паромные", "Паромные"),
        (r"(?i)(?<![А-Яа-яЁёІіЇїЄє])море(?![А-Яа-яЁёІіЇїЄє])", "паром", "Паром"),
        (r"(?i)(?<![А-Яа-яЁёІіЇїЄє])мор[іi](?![А-Яа-яЁёІіЇїЄє])", "поромі", "Поромі"),
    )
    for pattern, lower, upper in rules:
        source = _ua068_re.sub(
            pattern,
            lambda match, lo=lower, up=upper: up if match.group(0)[:1].isupper() else lo,
            source,
        )
    return source


def _ua068_forbidden_count(source):
    patterns = (
        r"(?i)(?<![А-Яа-яЁёІіЇїЄє])в\s+море(?![А-Яа-яЁёІіЇїЄє])",
        r"(?i)(?<![А-Яа-яЁёІіЇїЄє])на\s+море(?![А-Яа-яЁёІіЇїЄє])",
        r"(?i)(?<![А-Яа-яЁёІіЇїЄє])у\s+мор[іi](?![А-Яа-яЁёІіЇїЄє])",
        r"(?i)(?<![А-Яа-яЁёІіЇїЄє])в\s+мор[іi](?![А-Яа-яЁёІіЇїЄє])",
        r"(?i)(?<![А-Яа-яЁёІіЇїЄє])мор(?:е|ем|ской|ская|ское|ские)(?![А-Яа-яЁёІіЇїЄє])",
    )
    return sum(len(_ua068_re.findall(pattern, source or "")) for pattern in patterns)


def _ua068_date(value):
    if isinstance(value, _ua068_dt.datetime):
        return value.date()
    if isinstance(value, _ua068_dt.date):
        return value
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return _ua068_dt.datetime.strptime(text, "%Y-%m-%d").date()
    except Exception:
        return None


def _ua068_pretty(value):
    value = _ua068_date(value)
    if value is None:
        return ""
    months_ru = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря")
    months_uk = ("січня", "лютого", "березня", "квітня", "травня", "червня", "липня", "серпня", "вересня", "жовтня", "листопада", "грудня")
    return ("%d %s %d" % (value.day, months_ru[value.month - 1], value.year),
            "%d %s %d" % (value.day, months_uk[value.month - 1], value.year))


def _ua068_stage(row):
    status = str((row or {}).get("status") or (row or {}).get("stage") or "").lower()
    if status.startswith("kr_") or status in ("korea", "1"):
        return 1
    if status.startswith("sea_") or status.startswith("ferry_") or status in ("sea", "ferry", "2"):
        return 2
    if status.startswith("ge_") or status in ("georgia", "3"):
        return 3
    return 4


def _ua068_primary_action(source, kod, row):
    """Enforce one stage-aware commercial CTA on cards and diagnostics."""
    stage = _ua068_stage(row)
    action = "kupit" if stage == 4 else "bron"
    label = "Купить" if stage == 4 else "Задаток 500 $"
    href = "https://t.me/UA_artcompany_LLC_bot?start=%s_%s" % (action, kod)
    canonical = ('<a class="dejstvie kn_kupit ua-primary-action-v1" '
                 'data-ua-stage-action="%d" href="%s">%s</a>'
                 % (stage, _ua068_e(href), label))

    purchase = _ua068_re.compile(
        r'<a\b(?=[^>]*href=["\'][^"\']*start=(?:kupit|bron)_' +
        _ua068_re.escape(str(kod)) + r'(?:&[^"\']*)?["\'])[^>]*>.*?</a\s*>',
        _ua068_re.I | _ua068_re.S)
    matches = list(purchase.finditer(source))
    if matches:
        source = purchase.sub(lambda match: canonical if match.start() == matches[0].start() else "", source)
    else:
        fallback = _ua068_re.compile(
            r'<a\b(?=[^>]*class=["\'][^"\']*\b(?:kn_kupit|dejstvie)\b[^"\']*["\'])'
            r'(?=[^>]*href=)[^>]*>.*?</a\s*>', _ua068_re.I | _ua068_re.S)
        source, count = fallback.subn(canonical, source, count=1)
        if count != 1:
            text_fallback = _ua068_re.compile(
                r'<a\b(?=[^>]*href=)[^>]*>\s*(?:Купить(?:\s+авто)?|Задаток\s+500\s*\$|Забронировать\s+авто\s+за\s+500\s*\$)\s*</a\s*>',
                _ua068_re.I | _ua068_re.S)
            source, count = text_fallback.subn(canonical, source, count=1)
        if count != 1:
            raise RuntimeError("UA068_PRIMARY_ACTION_MISSING:%s" % kod)
    # A Kyiv purchase is immediate: no explanatory deposit note may remain
    # next to the primary CTA. Delivery-stage copy elsewhere is stage-aware.
    if stage == 4:
        source = _ua068_re.sub(
            r'<(?:div|p)\b[^>]*class=["\'][^"\']*\bcta-note\b[^"\']*["\'][^>]*>.*?</(?:div|p)\s*>',
            "", source, flags=_ua068_re.I | _ua068_re.S)
    return source


def _ua068_primary_action_errors(source, kod, row):
    stage = _ua068_stage(row)
    nodes = _ua068_re.findall(
        r'<a\b[^>]*class=["\'][^"\']*\bua-primary-action-v1\b[^"\']*["\'][^>]*>.*?</a\s*>',
        source, _ua068_re.I | _ua068_re.S)
    if len(nodes) != 1:
        return ["primary actions != 1"]
    node = nodes[0]
    expected_action = "kupit" if stage == 4 else "bron"
    expected_label = "Купить" if stage == 4 else "Задаток 500 $"
    errors = []
    if ("start=%s_%s" % (expected_action, kod)) not in node:
        errors.append("primary action target mismatch")
    text = _ua068_re.sub(r"<[^>]+>", "", node).strip()
    if text != expected_label:
        errors.append("primary action label mismatch")
    return errors


def _ua068_eta(row, stage):
    row = row or {}
    today = _ua068_dt.datetime.now(_ua068_dt.timezone.utc).date()
    if stage == 1:
        return (
            "После внесения предоплаты 500 $ автомобиль будет отправлен ближайшим паромом.",
            "Після внесення передоплати 500 $ автомобіль буде відправлено найближчим поромом.",
            "Дата прибытия будет рассчитана после погрузки на паром.",
            "Дату прибуття буде розраховано після завантаження на пором.",
        )
    if stage == 2:
        target = _ua068_date(row.get("eta_manual"))
        if target is None:
            shipped = _ua068_date(row.get("sea_date_out"))
            if shipped is not None:
                target = shipped + _ua068_dt.timedelta(days=75)
        if target is not None:
            days = max(0, (target - today).days)
            ru_date, uk_date = _ua068_pretty(target)
            return (
                "%d дн. до Киева · ориентировочно %s." % (days, ru_date),
                "%d дн. до Києва · орієнтовно %s." % (days, uk_date),
                "Автомобиль на пароме: Корея → Грузия.",
                "Автомобіль на поромі: Корея → Грузія.",
            )
        return (
            "Автомобиль на пароме · количество дней до Киева уточняется.",
            "Автомобіль на поромі · кількість днів до Києва уточнюється.",
            "Дата прибытия будет рассчитана после подтверждения маршрута.",
            "Дату прибуття буде розраховано після підтвердження маршруту.",
        )
    if stage == 3:
        deposit = _ua068_date(row.get("ge_to_kyiv_at"))
        if deposit is not None:
            target = deposit + _ua068_dt.timedelta(days=15)
            ru_date, uk_date = _ua068_pretty(target)
            extra_ru = "Расчётная дата прибытия — %s." % ru_date
            extra_uk = "Розрахункова дата прибуття — %s." % uk_date
        else:
            extra_ru = "Точная дата появится после внесения предоплаты."
            extra_uk = "Точна дата з’явиться після внесення передоплати."
        return (
            "После внесения предоплаты 500 $ автомобиль прибудет в Киев в течение 15 календарных дней.",
            "Після внесення передоплати 500 $ автомобіль прибуде до Києва протягом 15 календарних днів.",
            extra_ru,
            extra_uk,
        )
    arrived = (_ua068_date(row.get("ua_delivered")) or _ua068_date(row.get("ua_handed"))
               or _ua068_date(row.get("eta_manual")))
    if arrived is not None:
        ru_date, uk_date = _ua068_pretty(arrived)
        extra_ru = "Дата прибытия в Киев — %s." % ru_date
        extra_uk = "Дата прибуття до Києва — %s." % uk_date
    else:
        extra_ru = "Автомобиль в Киеве и готов к осмотру."
        extra_uk = "Автомобіль у Києві та готовий до огляду."
    return (extra_ru, extra_uk, "", "")


def _ua068_vin_result(row):
    row = row or {}
    vin = str(row.get("vin") or "").strip().upper()
    brand = str(row.get("brand") or "").strip().lower()
    duplicate_count = int(row.get("_ua068_vin_duplicates") or 1)
    if not _ua068_re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin):
        return vin, "ОШИБКА VIN", "error", "VIN должен содержать 17 допустимых символов без I, O и Q."
    wmi_ok = True
    if "kia" in brand or "киа" in brand:
        wmi_ok = vin.startswith(("KN", "KNA", "KND", "KNE"))
    elif "mercedes" in brand or "мерседес" in brand:
        wmi_ok = vin.startswith(("WDB", "WDD", "WDC", "W1"))
    if duplicate_count > 1:
        return vin, "ТРЕБУЕТ УТОЧНЕНИЯ", "warn", "VIN повторяется в опубликованных карточках."
    if not wmi_ok:
        return vin, "ТРЕБУЕТ УТОЧНЕНИЯ", "warn", "WMI не совпадает с маркой в карточке."
    return vin, "VIN ПРОВЕРЕН", "ok", "Формат, запрещённые символы, WMI и уникальность в опубликованных карточках проверены."


def _ua068_engine(row):
    value = str((row or {}).get("engine_cc") or "").strip()
    try:
        return ("{:,}".format(int(float(value))).replace(",", " "))
    except Exception:
        return value


def _ua068_video_count_from_html(source):
    paths = set()
    for value in _ua068_re.findall(r'(?:src|href)=["\']([^"\']+\.mp4(?:\?[^"\']*)?)["\']',
                                   source or "", _ua068_re.I):
        clean = value.split("?", 1)[0]
        if ".novoe." in clean or clean.endswith(".novoe.mp4") or "/diag/" in clean:
            continue
        paths.add(clean)
    if paths:
        return len(paths)
    return len(_ua068_re.findall(r"<video\b", source or "", _ua068_re.I))


def _ua068_video_count(kod, row=None, source=None):
    row = row or {}
    if source is not None:
        return _ua068_video_count_from_html(source)
    if "_ua068_video_count" in row:
        try:
            return max(0, int(row.get("_ua068_video_count") or 0))
        except Exception:
            pass
    path = "/home/Carix/video/%s.html" % str(kod)
    try:
        if _ua068_os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as handle:
                return _ua068_video_count_from_html(handle.read())
    except Exception:
        pass
    return 0


def _ua068_video_word(count):
    count = int(count)
    if count % 10 == 1 and count % 100 != 11:
        return "видео"
    return "видео"


def _ua068_cache_meta(source):
    if 'name="ua-art-contract" content="UA-CARDS-FERRY-VIN-001-V1.1"' not in source:
        meta = ('<meta name="ua-art-contract" content="UA-CARDS-FERRY-VIN-001-V1.1">'
                '<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">'
                '<meta http-equiv="Pragma" content="no-cache"><meta http-equiv="Expires" content="0">')
        head = _ua068_re.search(r"<head\b[^>]*>", source, _ua068_re.I)
        if head:
            source = source[:head.end()] + meta + source[head.end():]
    if 'name="ua-art-unified-contract" content="UA-CARDS-UNIFIED-SHELL-001-V1.1"' not in source:
        meta = '<meta name="ua-art-unified-contract" content="UA-CARDS-UNIFIED-SHELL-001-V1.1">'
        head = _ua068_re.search(r"<head\b[^>]*>", source, _ua068_re.I)
        if head:
            source = source[:head.end()] + meta + source[head.end():]
    return source


def _ua068_replace_marked(source, start, end):
    return _ua068_re.sub(_ua068_re.escape(start) + r".*?" + _ua068_re.escape(end), "", source,
                         flags=_ua068_re.I | _ua068_re.S)


def _ua068_diag_anchor(kod):
    return (_UA068_DIAG
            + '<a class="mcf-diag-cta" href="%s-diag.html" style="display:flex;align-items:center;gap:12px;margin:14px 0;padding:15px 16px;border-radius:14px;text-decoration:none;background:linear-gradient(180deg,rgba(212,175,55,.20),rgba(212,175,55,.08));border:1px solid rgba(212,175,55,.55);color:#f4e3ae"><span style="font-size:22px">🔧</span><span style="flex:1"><b>Открыть комплексную диагностику →</b><small style="display:block;margin-top:3px;opacity:.82">ЛКП · OBD · ходовая · фото · видео</small></span><span>›</span></a>' % _ua068_e(kod))


def _ua068_diag_placeholder(kod, row):
    title = "%s %s %s" % (str((row or {}).get("brand") or "").strip(),
                           str((row or {}).get("model") or "").strip(),
                           str((row or {}).get("year") or "").strip())
    source = ("<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta name='ua-art-contract' content='UA-CARDS-FERRY-VIN-001-V1.1'>"
            "<meta name='ua-art-unified-contract' content='UA-CARDS-UNIFIED-SHELL-001-V1.1'>"
            "<title>Комплексная диагностика %s — UA ART</title>"
            "<style>body{margin:0;background:#0b1726;color:#e8eef6;font:16px/1.55 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif}.w{max-width:720px;margin:auto;padding:24px}.c{margin-top:18px;padding:22px;border-radius:20px;background:#16263a;border:1px solid rgba(240,166,60,.46)}h1{font-size:25px;margin:0 0 9px}.s{display:inline-block;padding:7px 10px;border-radius:999px;color:#ffd283;border:1px solid rgba(240,166,60,.48);font-size:12px;font-weight:800}.p{color:#aebed0}.b,.dejstvie{display:block;margin-top:20px;padding:14px;text-align:center;border-radius:13px;background:#f0a63c;color:#102034;text-decoration:none;font-weight:900}</style></head><body><main class='w'><div>UA ART COMPANY · %s</div><section class='c'><span class='s'>ДИАГНОСТИКА ОЖИДАЕТ ДАННЫХ</span><h1>Комплексная диагностика</h1><p>%s</p><p class='p'>Страница закреплена постоянно. Здесь появятся ЛКП, OBD, ходовая, фото и видео сразу после загрузки материалов.</p><a class='dejstvie' href='https://t.me/UA_artcompany_LLC_bot?start=kupit_%s'>Купить</a><a class='b' href='%s.html'>← Вернуться к автомобилю</a></section></main></body></html>"
            % (_ua068_e(kod), _ua068_e(kod), _ua068_e(title), _ua068_e(kod), _ua068_e(kod)))
    return _ua068_primary_action(source, kod, row)


def _ua068_ensure_diag_files(kod, row):
    """Future-card failsafe: create only missing targets; never overwrite reports."""
    payload = _ua068_diag_placeholder(kod, row).encode("utf-8")
    for root in ("/home/Carix/video", "/home/Carix/site"):
        path = _ua068_os.path.join(root, "%s-diag.html" % kod)
        if _ua068_os.path.exists(path):
            continue
        try:
            _ua068_os.makedirs(root, exist_ok=True)
            handle = _ua068_tempfile.NamedTemporaryFile(prefix=".ua068-diag-", suffix=".tmp", dir=root, delete=False)
            temp_path = handle.name
            with handle:
                handle.write(payload)
                handle.flush()
                _ua068_os.fsync(handle.fileno())
            if not _ua068_os.path.exists(path):
                _ua068_os.replace(temp_path, path)
            elif _ua068_os.path.exists(temp_path):
                _ua068_os.unlink(temp_path)
        except Exception:
            try:
                if 'temp_path' in locals() and _ua068_os.path.exists(temp_path):
                    _ua068_os.unlink(temp_path)
            except Exception:
                pass


def _ua068_balanced_div_end(source, start):
    pattern = _ua068_re.compile(r"<div\b[^>]*>|</div\s*>", _ua068_re.I)
    depth = 0
    first = True
    for match in pattern.finditer(source, start):
        token = match.group(0).lower()
        if first:
            if match.start() != start or token.startswith("</"):
                raise RuntimeError("UA068_LEGACY_DIV_START_INVALID")
            first = False
        if token.startswith("</"):
            depth -= 1
            if depth == 0:
                return match.end()
        else:
            depth += 1
    raise RuntimeError("UA068_LEGACY_DIV_UNBALANCED")


def _ua068_strip_legacy_blocks(source):
    """Remove superseded stage/diagnostics UI at every final generator boundary."""
    legacy = r"(?:mcf-etap|mcf-track|mcf-diag-off)"
    div_pattern = _ua068_re.compile(
        r'<div\b(?=[^>]*\bclass=["\'][^"\']*\b' + legacy
        + r'\b[^"\']*["\'])[^>]*>',
        _ua068_re.I,
    )
    for _attempt in range(64):
        match = div_pattern.search(source)
        if match is None:
            break
        end = _ua068_balanced_div_end(source, match.start())
        source = source[:match.start()] + source[end:]
    else:
        raise RuntimeError("UA068_LEGACY_DIV_LIMIT")

    container_pattern = _ua068_re.compile(
        r'<(?P<tag>a|button|section|aside)\b(?=[^>]*\bclass=["\'][^"\']*\b'
        + legacy + r'\b[^"\']*["\'])[^>]*>.*?</(?P=tag)\s*>',
        _ua068_re.I | _ua068_re.S,
    )
    previous = None
    while previous != source:
        previous = source
        source = container_pattern.sub("", source)
    if _ua068_re.search(
        r'class=["\'][^"\']*\b' + legacy + r'\b[^"\']*["\']',
        source,
        _ua068_re.I,
    ):
        raise RuntimeError("UA068_LEGACY_UI_REMAINS")
    return source


def _ua068_native_stage_span(source):
    heading = _ua068_re.search(
        r'<div\b(?=[^>]*\bclass=["\'][^"\']*\bzag\b[^"\']*["\'])[^>]*>\s*'
        r'(?:Где\s+(?:машина|автомобиль)\s+сейчас|'
        r'Де\s+(?:машина|автомобіль|авто)\s+зараз)\s*</div\s*>',
        source,
        _ua068_re.I,
    )
    if heading is None:
        return None
    candidates = list(_ua068_re.finditer(
        r'<div\b(?=[^>]*\bclass=["\'][^"\']*\b(?:blok|krt)\b[^"\']*["\'])[^>]*>',
        source[:heading.start()],
        _ua068_re.I,
    ))
    for match in reversed(candidates):
        end = _ua068_balanced_div_end(source, match.start())
        if end >= heading.end():
            return match.start(), end
    return None


def _ua068_reposition_stage(source, row):
    """Replace the old route block in-place; never append a second route."""
    slot = "<!-- UA-ART-DELIVERY-STAGE-SLOT-V1 -->"
    if slot in source:
        raise RuntimeError("UA068_STAGE_SLOT_ALREADY_PRESENT")
    native = _ua068_native_stage_span(source)
    if native is not None:
        source = source[:native[0]] + slot + source[native[1]:]
        source = _ua068_replace_marked(source, _UA068_STAGE_START, _UA068_STAGE_END)
    elif source.count(_UA068_STAGE_START) == 1 and source.count(_UA068_STAGE_END) == 1:
        start = source.index(_UA068_STAGE_START)
        end = source.index(_UA068_STAGE_END, start) + len(_UA068_STAGE_END)
        source = source[:start] + slot + source[end:]
    else:
        source = _ua068_replace_marked(source, _UA068_STAGE_START, _UA068_STAGE_END)
        position = source.find(_UA068_DIAG)
        if position < 0:
            purchase = _ua068_re.search(
                r'<a\b(?=[^>]*\bclass=["\'][^"\']*(?:kn_kupit|dejstvie|knp\s+zol)'
                r'[^"\']*["\'])[^>]*>',
                source,
                _ua068_re.I,
            )
            position = purchase.start() if purchase is not None else source.lower().rfind("</body>")
        if position < 0:
            raise RuntimeError("UA068_STAGE_INSERTION_POINT_MISSING")
        source = source[:position] + slot + source[position:]
    if source.count(slot) != 1:
        raise RuntimeError("UA068_STAGE_SLOT_COUNT_INVALID")
    renderer = globals().get("_ua_delivery_stage_anchor")
    if not callable(renderer):
        raise RuntimeError("UA068_STAGE_RENDERER_MISSING")
    return source.replace(slot, renderer(row), 1)


def _ua068_ensure_stage_diag(source, kod, row):
    source = _ua068_strip_legacy_blocks(source)
    source = _ua068_reposition_stage(source, row)
    master_stage = globals().get("_ua_master_ensure_stage")
    master_diag = globals().get("_ua_master_ensure_diag")
    if callable(master_stage):
        source = master_stage(source, kod, row)
    elif source.count(_UA068_STAGE_START) != 1 or source.count(_UA068_STAGE_END) != 1:
        source = _ua068_replace_marked(source, _UA068_STAGE_START, _UA068_STAGE_END)
        renderer = globals().get("_ua_delivery_stage_anchor")
        if not callable(renderer):
            raise RuntimeError("UA068_STAGE_RENDERER_MISSING:%s" % kod)
        position = source.find(_UA068_DIAG)
        if position < 0:
            position = source.lower().rfind("</body>")
        source = source[:position] + renderer(row) + source[position:]
    if callable(master_diag):
        source = master_diag(source, kod)
    else:
        source = source.replace(_UA068_DIAG, "")
        source = _ua068_re.sub(
            r'<a\b(?=[^>]*href=["\'](?:[^"\']*/)?' + _ua068_re.escape(kod)
            + r'-diag\.html(?:\?[^"\']*)?["\'])[^>]*>.*?</a\s*>',
            "", source, flags=_ua068_re.I | _ua068_re.S)
        position = source.find(_UA068_STAGE_END)
        if position >= 0:
            position += len(_UA068_STAGE_END)
        else:
            position = source.lower().rfind("</body>")
        source = source[:position] + _ua068_diag_anchor(kod) + source[position:]
    return _ua068_strip_legacy_blocks(source)


def _ua068_vin_block(kod, row):
    vin, status, kind, reason = _ua068_vin_result(row)
    stage = _ua068_stage(row)
    ru, uk, ru2, uk2 = _ua068_eta(row, stage)
    engine = _ua068_engine(row)
    video_count = _ua068_video_count(kod, row)
    container = str((row or {}).get("sea_container") or "").strip()
    extra = ""
    if container and stage == 2:
        extra = '<div class="ua-vin-v1-meta">Контейнер: <b>%s</b></div>' % _ua068_e(container)
    css = """<style>
.ua-vin-v1{margin:18px 0;padding:18px;border-radius:20px;background:linear-gradient(145deg,#192a3e,#122033);border:1px solid rgba(240,166,60,.48);box-shadow:0 14px 38px rgba(0,0,0,.24);color:#edf3fb}.ua-vin-v1 *{box-sizing:border-box}.ua-vin-v1-head{display:flex;gap:12px;align-items:center}.ua-vin-v1-shield{width:42px;height:42px;display:grid;place-items:center;border-radius:13px;background:rgba(240,166,60,.16);font-size:22px}.ua-vin-v1-title{font-size:17px;font-weight:850}.ua-vin-v1-sub{font-size:12px;color:#9fb0c5;margin-top:2px}.ua-vin-v1-status{margin-left:auto;padding:7px 9px;border-radius:999px;font-size:10px;font-weight:900;letter-spacing:.08em}.ua-vin-v1-status.ok{color:#79e3a9;background:rgba(56,190,120,.13);border:1px solid rgba(56,190,120,.4)}.ua-vin-v1-status.warn{color:#ffd480;background:rgba(240,166,60,.13);border:1px solid rgba(240,166,60,.45)}.ua-vin-v1-status.error{color:#ff9696;background:rgba(235,80,80,.12);border:1px solid rgba(235,80,80,.4)}.ua-vin-v1-code{margin:15px 0 10px;padding:12px 13px;border-radius:12px;background:#0c1827;border:1px solid #2b3f57;font:800 16px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.05em;overflow-wrap:anywhere}.ua-vin-v1-route{font-size:14px;line-height:1.5;color:#d7e1ec}.ua-vin-v1-route small{display:block;color:#98abc0;margin-top:4px;font-size:12px}.ua-vin-v1-meta{font-size:12px;color:#aebed0;margin-top:8px}.ua-vin-v1-button{display:block;width:100%;margin-top:14px;padding:14px 16px;border:1px solid #f0a63c;border-radius:14px;background:linear-gradient(180deg,#f5b452,#e99a2a);color:#102034;font:900 15px/1.2 inherit;cursor:pointer;text-align:center;text-decoration:none;box-shadow:0 8px 20px rgba(240,166,60,.2)}.ua-vin-v1-panel{margin-top:10px;padding:13px;border-radius:12px;background:#0e1b2b;border:1px solid #293e55;color:#b9c8d8;font-size:13px;line-height:1.5}.ua-vin-v1-panel b{color:#edf3fb}.ua068-uk{display:none}html:lang(uk) .ua068-ru{display:none}html:lang(uk) .ua068-uk{display:inline}@media(max-width:520px){.ua-vin-v1{padding:15px;border-radius:17px}.ua-vin-v1-head{align-items:flex-start}.ua-vin-v1-status{font-size:9px}.ua-vin-v1-code{font-size:14px}}
</style>"""
    return (_UA068_VIN_START + css
            + '<section class="ua-vin-v1" data-ua-contract="UA-CARDS-UNIFIED-SHELL-001-V1.1" data-ua-card="%s" data-ua-stage="%d" data-ua-video-count="%d">' % (_ua068_e(kod), stage, video_count)
            + '<div class="ua-vin-v1-head"><span class="ua-vin-v1-shield">🇰🇷</span><span><span class="ua-vin-v1-title">Korea CarHistory</span><span class="ua-vin-v1-sub">Официальная страховая история Кореи · 2 200 KRW</span></span><span class="ua-vin-v1-status %s">ФОРМАТ VIN ПРОВЕРЕН</span></div>' % kind
            + '<div class="ua-vin-v1-code">%s</div>' % (_ua068_e(vin) or "VIN НЕ УКАЗАН")
            + '<div class="ua-vin-v1-route"><span class="ua068-ru">%s</span><span class="ua068-uk">%s</span><small><span class="ua068-ru">%s</span><span class="ua068-uk">%s</span></small></div>' % (_ua068_e(ru), _ua068_e(uk), _ua068_e(ru2), _ua068_e(uk2))
            + extra + '<div class="ua-vin-v1-meta">Видео в карточке: <b>%d</b></div>' % video_count
            + '<a class="ua-vin-v1-button" href="%s" target="_blank" rel="noopener noreferrer" data-ua-vin="%s" onclick="try{navigator.clipboard.writeText(this.dataset.uaVin||\'\')}catch(e){}">🇰🇷 Проверить VIN в CarHistory →</a>' % (_ua068_e(_UA068_CARHISTORY_URL), _ua068_e(vin))
            + '<div class="ua-vin-v1-panel"><b>%s</b><br>%s<br>Двигатель: <b>%s см³</b>.<br>VIN копируется локально: вставьте его на официальном сайте и подтвердите поиск. Отчёт может содержать страховые ДТП, стоимость ремонта, полную гибель, угон и затопление. События без страхового обращения могут отсутствовать.</div>' % (_ua068_e(status), _ua068_e(reason), _ua068_e(engine))
            + '</section>' + _UA068_VIN_END)


def _ua068_ensure_engine(source, row):
    engine = _ua068_engine(row)
    if engine:
        source = _ua068_re.sub(r"(?<![0-9])(?:[0-9][0-9 \u00a0]{2,})\s*(?=см³)", engine + " ", source)
    return source


def _ua068_strip_vin_actions(source):
    source = _ua068_replace_marked(source, _UA068_VIN_START, _UA068_VIN_END)
    return _ua068_re.sub(
        r'<(?:a|button)\b[^>]*>\s*(?:🛡\s*)?Проверить\s+VIN(?:\s*→)?\s*</(?:a|button)\s*>',
        "", source, flags=_ua068_re.I | _ua068_re.S)


def _ua068_ensure_card(source, kod, row):
    if not source or "</html>" not in source.lower():
        raise RuntimeError("UA068_INVALID_CARD:%s" % kod)
    row = dict(row or {})
    row.setdefault("auto_number", kod)
    row["_ua068_video_count"] = _ua068_video_count(kod, row, source)
    source = _ua068_terms(source)
    source = _ua068_cache_meta(source)
    source = _ua068_ensure_engine(source, row)
    source = _ua068_ensure_stage_diag(source, kod, row)
    source = _ua068_strip_vin_actions(source)
    block = _ua068_vin_block(kod, row)
    position = source.find(_UA068_STAGE_END)
    if position >= 0:
        position += len(_UA068_STAGE_END)
    else:
        position = source.find(_UA068_DIAG)
    if position < 0:
        position = source.lower().rfind("</body>")
    source = source[:position] + block + source[position:]
    source = _ua068_primary_action(source, kod, row)
    source = _ua068_terms(source)
    source = _ua068_strip_legacy_blocks(source)
    return source


def _ua068_catalog_block(kod, row):
    vin, status, kind, _reason = _ua068_vin_result(row)
    stage = _ua068_stage(row)
    ru, uk, ru2, uk2 = _ua068_eta(row, stage)
    video_count = _ua068_video_count(kod, row)
    return (_UA068_CAT_START
            + '<div class="ua-cat-vin-v1" data-ua-card="%s" data-ua-stage="%d" data-ua-video-count="%d"><div class="ua-cat-vin-v1-top"><span>VIN <b>%s</b></span><i class="%s">%s</i></div><div class="ua-cat-vin-v1-spec">Двигатель: <b>%s см³</b> · Видео: <b>%d</b></div><div class="ua-cat-vin-v1-copy"><span class="ua068-ru">%s %s</span><span class="ua068-uk">%s %s</span></div></div>' % (_ua068_e(kod), stage, video_count, _ua068_e(vin) or "НЕ УКАЗАН", kind, _ua068_e(status), _ua068_e(_ua068_engine(row)), video_count, _ua068_e(ru), _ua068_e(ru2), _ua068_e(uk), _ua068_e(uk2))
            + _UA068_CAT_END)


def _ua068_catalog_fallback(kod, row):
    stage = _ua068_stage(row)
    title = " ".join(str((row or {}).get(key) or "").strip()
                     for key in ("brand", "model", "year")).strip()
    labels_ru = {
        1: "В Корее · подготовка к ближайшему парому",
        2: "На пароме · Корея → Грузия",
        3: "В Грузии · 15 дней до Киева после предоплаты",
        4: "В Киеве · можно посмотреть",
    }
    labels_uk = {
        1: "У Кореї · підготовка до найближчого порома",
        2: "На поромі · Корея → Грузія",
        3: "У Грузії · 15 днів до Києва після передоплати",
        4: "У Києві · можна оглянути",
    }
    return (_UA068_FALLBACK_START
            + '<a class="ua-cat-fallback-v1" href="%s.html?v=%s" data-ua-fallback-card="%s" data-ua-stage-tile="%d">' % (_ua068_e(kod), _UA068_VERSION, _ua068_e(kod), stage)
            + '<span class="ua-cat-fallback-v1-kicker">%s · ЕТАП %d ИЗ 4</span>' % (_ua068_e(kod), stage)
            + '<strong class="ua-cat-fallback-v1-title">%s</strong>' % (_ua068_e(title) or _ua068_e(kod))
            + '<span class="ua-cat-fallback-v1-stage"><span class="ua068-ru">%s</span><span class="ua068-uk">%s</span></span>' % (_ua068_e(labels_ru[stage]), _ua068_e(labels_uk[stage]))
            + _ua068_catalog_block(kod, row)
            + '<span class="ua-cat-fallback-v1-open"><span class="ua068-ru">Открыть карточку →</span><span class="ua068-uk">Відкрити картку →</span></span></a>'
            + _UA068_FALLBACK_END)


def _ua068_catalog_item(block, rows):
    match = _ua068_re.search(r"UA-[0-9]{4,}", block, _ua068_re.I)
    if not match:
        return _ua068_terms(block)
    kod = match.group(0).upper()
    row = rows.get(kod)
    if not row:
        return _ua068_terms(block)
    block = _ua068_ensure_engine(_ua068_terms(block), row)
    video_count = _ua068_video_count(kod, row)
    block = _ua068_re.sub(r"\b[0-9]+\s+видео\b", "%d видео" % video_count,
                          block, flags=_ua068_re.I)
    block = _ua068_re.sub(r"·\s*видео\b", "· %d видео" % video_count,
                          block, flags=_ua068_re.I)
    if _UA068_CAT_START in block:
        return block
    close = list(_ua068_re.finditer(r"</(?:article|a)\s*>", block, _ua068_re.I))
    if not close:
        return block
    position = close[-1].start()
    return block[:position] + _ua068_catalog_block(kod, row) + block[position:]


def _ua068_ensure_catalog(source, rows):
    if not source:
        return source
    rows = {str(k).upper(): dict(v or {}) for k, v in (rows or {}).items()}
    source = _ua068_terms(source)
    source = _ua068_cache_meta(source)
    source = _ua068_replace_marked(source, _UA068_FALLBACK_START, _UA068_FALLBACK_END)
    source = _ua068_replace_marked(source, _UA068_CAT_START, _UA068_CAT_END)
    # Catalogs currently exist in two layouts: modern <article> cards and
    # legacy standalone <a> tiles.  A page may also contain both layouts
    # (or a second link to one car).  Insert exactly one canonical block per
    # identifier instead of choosing one page-wide parser branch.
    seen = set()

    def render_once(match):
        block = match.group(0)
        found = _ua068_re.search(r"UA-[0-9]{4,}", block, _ua068_re.I)
        if not found:
            return _ua068_terms(block)
        identifier = found.group(0).upper()
        if identifier not in rows or identifier in seen:
            return _ua068_terms(block)
        rendered = _ua068_catalog_item(block, rows)
        if 'data-ua-card="%s"' % identifier in rendered:
            seen.add(identifier)
        return rendered

    article = _ua068_re.compile(
        r'<article\b[^>]*>.*?</article\s*>', _ua068_re.I | _ua068_re.S)
    source = article.sub(render_once, source)
    anchor = _ua068_re.compile(
        r'<a\b(?=[^>]*href=["\'][^"\']*UA-[0-9]{4,}\.html(?:\?[^"\']*)?["\'])[^>]*>.*?</a\s*>',
        _ua068_re.I | _ua068_re.S)
    source = anchor.sub(render_once, source)

    missing = [identifier for identifier in rows if identifier not in seen]
    if missing:
        fallback = "".join(_ua068_catalog_fallback(identifier, rows[identifier])
                           for identifier in missing)
        position = -1
        modern = _ua068_re.search(r'<div\b[^>]*class=["\'][^"\']*\bempty-assist\b',
                                  source, _ua068_re.I)
        if modern:
            position = modern.start()
        if position < 0:
            legacy = _ua068_re.search(
                r'<a\b(?=[^>]*class=["\'][^"\']*\bvtoraya\b)(?=[^>]*href=["\'][^"\']*podbor\.html)',
                source, _ua068_re.I)
            if legacy:
                position = legacy.start()
        if position < 0:
            position = source.lower().rfind("</main>")
        if position < 0:
            position = source.lower().rfind("</body>")
        if position < 0:
            raise RuntimeError("UA068_CATALOG_INSERTION_POINT_MISSING")
        source = source[:position] + fallback + source[position:]
        seen.update(missing)

    total = len(rows)
    source = _ua068_re.sub(
        r'(<div\b[^>]*class=["\']schet["\'][^>]*>)\s*\d+\s+в подборке',
        lambda match: match.group(1) + str(total) + " в подборке", source,
        flags=_ua068_re.I)
    counts = {stage: sum(1 for row in rows.values() if _ua068_stage(row) == stage)
              for stage in (1, 2, 3, 4)}
    count_labels = (
        (r"Все\s*·\s*\d+", "Все · %d" % total),
        (r"Усі\s*·\s*\d+", "Усі · %d" % total),
        (r"В Киеве\s*·\s*\d+", "В Киеве · %d" % counts[4]),
        (r"У Києві\s*·\s*\d+", "У Києві · %d" % counts[4]),
        (r"В Грузии\s*·\s*\d+", "В Грузии · %d" % counts[3]),
        (r"У Грузії\s*·\s*\d+", "У Грузії · %d" % counts[3]),
        (r"На пароме\s*·\s*\d+", "На пароме · %d" % counts[2]),
        (r"На поромі\s*·\s*\d+", "На поромі · %d" % counts[2]),
        (r"В Корее\s*·\s*\d+", "В Корее · %d" % counts[1]),
        (r"У Кореї\s*·\s*\d+", "У Кореї · %d" % counts[1]),
        (r"Показано:\s*\d+", "Показано: %d" % total),
    )
    for pattern, replacement in count_labels:
        source = _ua068_re.sub(pattern, replacement, source, flags=_ua068_re.I)
    source = _ua068_re.sub(
        r'href=(["\'])([^"\']*UA-[0-9]{4,}\.html)(?:\?[^"\']*)?\1',
        lambda match: 'href=%s%s?v=%s%s' % (match.group(1), match.group(2), _UA068_VERSION, match.group(1)),
        source, flags=_ua068_re.I)
    css = """<style id="ua-cat-vin-v1-style">.ua-cat-vin-v1{margin:12px 0 2px;padding:11px 12px;border-radius:13px;background:linear-gradient(145deg,rgba(240,166,60,.10),rgba(20,36,55,.72));border:1px solid rgba(240,166,60,.32);color:#cbd8e6;font-size:12px;line-height:1.42}.ua-cat-vin-v1-top{display:flex;align-items:center;gap:8px}.ua-cat-vin-v1-top span{min-width:0;overflow-wrap:anywhere}.ua-cat-vin-v1-top b{font:800 11px/1.2 ui-monospace,SFMono-Regular,Menlo,monospace;color:#f3f6fa;letter-spacing:.03em}.ua-cat-vin-v1-top i{margin-left:auto;font-style:normal;font-size:8px;font-weight:900;letter-spacing:.06em;padding:4px 6px;border-radius:999px;white-space:nowrap}.ua-cat-vin-v1-top i.ok{color:#72dfa5;border:1px solid rgba(64,190,125,.42)}.ua-cat-vin-v1-top i.warn{color:#ffd180;border:1px solid rgba(240,166,60,.45)}.ua-cat-vin-v1-top i.error{color:#ff9898;border:1px solid rgba(235,80,80,.4)}.ua-cat-vin-v1-spec{margin-top:5px;color:#aabbd0}.ua-cat-vin-v1-copy{margin-top:5px;color:#aabbd0}.ua-cat-fallback-v1{display:block;margin:14px 0;padding:17px;border:1px solid rgba(240,166,60,.46);border-radius:18px;background:linear-gradient(145deg,#172a40,#102033);color:#edf3fb;text-decoration:none;box-shadow:0 12px 30px rgba(0,0,0,.2)}.ua-cat-fallback-v1-kicker{display:block;color:#f0a63c;font-size:10px;font-weight:900;letter-spacing:.11em}.ua-cat-fallback-v1-title{display:block;margin-top:7px;font-size:20px;line-height:1.25}.ua-cat-fallback-v1-stage{display:block;margin-top:7px;color:#aebed0;font-size:13px}.ua-cat-fallback-v1-open{display:block;margin-top:11px;color:#f4b65c;font-size:13px;font-weight:850}.ua068-uk{display:none}html:lang(uk) .ua068-ru{display:none}html:lang(uk) .ua068-uk{display:inline}</style>"""
    source = _ua068_re.sub(r'<style\b[^>]*id=["\']ua-cat-vin-v1-style["\'][^>]*>.*?</style\s*>', "", source,
                           flags=_ua068_re.I | _ua068_re.S)
    head_end = source.lower().find("</head>")
    if head_end >= 0:
        source = source[:head_end] + css + source[head_end:]
    return _ua068_terms(source)


def _ua068_card_errors(source, kod, row):
    errors = []
    if source.count(_UA068_VIN_START) != 1 or source.count(_UA068_VIN_END) != 1:
        errors.append("VIN Guard blocks != 1")
    if len(_ua068_re.findall(r'class=["\'][^"\']*\bua-vin-v1-button\b', source, _ua068_re.I)) != 1:
        errors.append("VIN buttons != 1")
    if source.count(_UA068_CARHISTORY_URL) != 1:
        errors.append("CarHistory target != 1")
    if "navigator.clipboard.writeText" not in source:
        errors.append("VIN copy helper missing")
    errors.extend(_ua068_primary_action_errors(source, kod, row))
    if source.count(_UA068_STAGE_START) != 1 or source.count(_UA068_STAGE_END) != 1:
        errors.append("stage anchors != 1")
    if source.count(_UA068_DIAG) != 1:
        errors.append("diagnostics anchors != 1")
    diag_links = _ua068_re.findall(
        r'href=["\'](?:[^"\']*/)?' + _ua068_re.escape(str(kod)) + r'-diag\.html(?:\?[^"\']*)?["\']',
        source, _ua068_re.I)
    if len(diag_links) != 1:
        errors.append("diagnostics links != 1")
    if _ua068_forbidden_count(source):
        errors.append("forbidden sea wording remains")
    if _ua068_re.search(
            r'class=["\'][^"\']*\b(?:mcf-etap|mcf-track|mcf-diag-off)\b[^"\']*["\']',
            source, _ua068_re.I):
        errors.append("legacy duplicate UI remains")
    if _ua068_native_stage_span(source) is not None:
        errors.append("native stage duplicate remains")
    vin = str((row or {}).get("vin") or "").strip().upper()
    if not vin or vin not in source:
        errors.append("VIN missing")
    engine = _ua068_engine(row)
    if engine and not _ua068_re.search(_ua068_re.escape(engine) + r"\s*см³", source):
        errors.append("engine mismatch")
    stage = _ua068_stage(row)
    if 'data-ua-stage="%d"' % stage not in source:
        errors.append("stage copy mismatch")
    if stage == 4 and ("Выдача и осмотр — Киев" in source or "Видача та огляд — Київ" in source):
        errors.append("redundant Kyiv issue/inspection copy remains")
    expected_videos = _ua068_video_count(kod, row, source)
    if 'data-ua-video-count="%d"' % expected_videos not in source:
        errors.append("video count mismatch")
    return errors
'''.strip()


MASTER_FERRY_VIN_WRAPPER = r'''
_ua068_master_card_original = obrabotat_kartochku
_ua068_master_validate_original = proverit
_ua068_master_common_original = obrabotat_obshuyu


def _ua068_master_row(kod):
    row = dict(dannye(kod) or {})
    row.setdefault("auto_number", kod)
    vin = str(row.get("vin") or "").strip().upper()
    duplicate_count = 0
    try:
        for other_kod in vse_kody():
            other = dict(dannye(other_kod) or {})
            if str(other.get("vin") or "").strip().upper() == vin:
                duplicate_count += 1
    except Exception:
        duplicate_count = 1
    row["_ua068_vin_duplicates"] = max(1, duplicate_count)
    return row


def obrabotat_kartochku(html, kod):
    html = _ua068_master_card_original(html, kod)
    if not html:
        return html
    kod = str(kod)
    row = _ua068_master_row(kod)
    html = _ua068_ensure_card(html, kod, row)
    _ua068_ensure_diag_files(kod, row)
    errors = _ua068_card_errors(html, kod, row)
    if errors:
        raise RuntimeError("UA068_MASTER_FINAL:%s:%s" % (kod, ";".join(errors)))
    return html


def proverit(html, kod=""):
    errors = list(_ua068_master_validate_original(html, kod) or [])
    if kod:
        errors.extend(_ua068_card_errors(html, str(kod), _ua068_master_row(str(kod))))
    return list(dict.fromkeys(errors))


def obrabotat_obshuyu(html):
    html = _ua068_master_common_original(html)
    rows = {}
    try:
        for kod in vse_kody():
            row = _ua068_master_row(str(kod))
            rows[str(kod).upper()] = row
    except Exception:
        pass
    return _ua068_ensure_catalog(html, rows)
'''.strip()


STRANICA_FERRY_VIN_WRAPPER = r'''
_ua068_stranica_card_original = sobrat_kartochku
_ua068_stranica_catalog_original = sobrat_katalog


def sobrat_kartochku(m, kadry, sredn=None):
    html = _ua068_stranica_card_original(m, kadry, sredn)
    kod = str(nomer(m))
    row = dict(m or {})
    row["_ua068_vin_duplicates"] = 1
    return _ua068_ensure_card(html, kod, row)


def sobrat_katalog(spisok, kadry_po_nomeru, legkie_po_nomeru=None):
    html = _ua068_stranica_catalog_original(spisok, kadry_po_nomeru, legkie_po_nomeru)
    counts = {}
    for row in spisok:
        vin = str(row.get("vin") or "").strip().upper()
        counts[vin] = counts.get(vin, 0) + 1
    rows = {}
    for item in spisok:
        row = dict(item or {})
        row["_ua068_vin_duplicates"] = counts.get(str(row.get("vin") or "").strip().upper(), 1)
        rows[str(nomer(row)).upper()] = row
    return _ua068_ensure_catalog(html, rows)
'''.strip()


YADRO_FERRY_VIN_WRAPPER = r'''
_ua068_yadro_card_original = karta_html
_ua068_yadro_catalog_original = katalog_html


def karta_html(m, foto, bron=True):
    html = _ua068_yadro_card_original(m, foto, bron)
    kod = str(nomer(m))
    row = dict(m or {})
    row["_ua068_vin_duplicates"] = 1
    return _ua068_ensure_card(html, kod, row)


def katalog_html(spisok, foto_po_nomeru, video_po_nomeru=None):
    html = _ua068_yadro_catalog_original(spisok, foto_po_nomeru, video_po_nomeru)
    counts = {}
    for row in spisok:
        vin = str(row.get("vin") or "").strip().upper()
        counts[vin] = counts.get(vin, 0) + 1
    rows = {}
    for item in spisok:
        row = dict(item or {})
        row["_ua068_vin_duplicates"] = counts.get(str(row.get("vin") or "").strip().upper(), 1)
        rows[str(nomer(row)).upper()] = row
    return _ua068_ensure_catalog(html, rows)
'''.strip()


def _inject_task068(base: str, wrapper: str) -> str:
    payload = FERRY_VIN_COMMON_SOURCE + "\n\n" + wrapper
    guards = list(re.finditer(
        r'(?m)^if\s+__name__\s*==\s*["\']__main__["\']\s*:', base
    ))
    if not guards:
        return base.rstrip() + "\n\n" + payload + "\n"
    position = guards[-1].start()
    return (base[:position].rstrip() + "\n\n" + payload + "\n\n"
            + base[position:].lstrip())


def _detach_main_guard(source: str) -> tuple[str, str]:
    """Remove the single top-level script guard so wrappers can precede it."""
    lines = source.splitlines(keepends=True)
    guards = []
    for node in ast.parse(source).body:
        if not isinstance(node, ast.If):
            continue
        first = lines[node.lineno - 1] if 0 < node.lineno <= len(lines) else ""
        if re.search(r'^\s*if\s+__name__\s*==\s*["\']__main__["\']\s*:', first):
            guards.append(node)
    if not guards:
        return source.rstrip(), ""
    if len(guards) != 1:
        raise RepairBlocked("task068_main_guard_count_invalid")
    node = guards[0]
    guard = "".join(lines[node.lineno - 1:node.end_lineno]).strip()
    del lines[node.lineno - 1:node.end_lineno]
    return "".join(lines).rstrip(), guard


def _rebase_task068_after_seo(source: str, original_sha: str,
                              path: str, wrapper: str) -> str:
    """Preserve the approved SEO layer and restore task068 as final filter."""
    name = os.path.basename(path)
    if original_sha != SEO_LAYERED_SOURCE_SHA[path]:
        raise RepairBlocked("task068_seo_layer_hash_changed:" + name)
    if source.count(FERRY_VIN_SOURCE_MARKER) != 1:
        raise RepairBlocked("task068_seo_task_marker_count_invalid:" + name)
    if source.count(SEO_REHAB_SOURCE_MARKER) != 1:
        raise RepairBlocked("task068_seo_marker_count_invalid:" + name)

    body, guard = _detach_main_guard(source)
    task_position = body.find(FERRY_VIN_SOURCE_MARKER)
    seo_position = body.find(SEO_REHAB_SOURCE_MARKER)
    if not 0 < task_position < seo_position:
        raise RepairBlocked("task068_seo_layer_order_invalid:" + name)
    old_task_layer = body[task_position:seo_position]
    required_binding = {
        STRANICA_PATH: "_ua068_stranica_card_original",
        YADRO_PATH: "_ua068_yadro_card_original",
        MASTER_CARD_PATH: "_ua068_master_card_original",
    }[path]
    if required_binding not in old_task_layer:
        raise RepairBlocked("task068_seo_old_layer_invalid:" + name)

    base = body[:task_position].rstrip()
    seo_layer = body[seo_position:].strip()
    candidate = (base + "\n\n" + seo_layer + "\n\n"
                 + FERRY_VIN_COMMON_SOURCE + "\n\n" + wrapper + "\n")
    if guard:
        candidate = candidate.rstrip() + "\n\n" + guard + "\n"
    _validate_task068_source(candidate, path)
    if not candidate.find(SEO_REHAB_SOURCE_MARKER) < candidate.find(FERRY_VIN_SOURCE_MARKER):
        raise RepairBlocked("task068_not_after_seo:" + name)
    final_guard = candidate.rfind("if __name__")
    if final_guard >= 0 and candidate.find(FERRY_VIN_SOURCE_MARKER) > final_guard:
        raise RepairBlocked("task068_not_before_main_after_seo:" + name)
    return candidate


def _upgrade_task068_after_seo(source: str, original_sha: str,
                               path: str, wrapper: str) -> str:
    """Replace only the final task068 layer on the approved rebased hashes."""
    name = os.path.basename(path)
    if original_sha not in (SEO_FINAL_V1_SOURCE_SHA[path], UNIFIED_BASE_SOURCE_SHA[path],
                            UNIFIED_CARHISTORY_SOURCE_SHA[path]):
        raise RepairBlocked("task068_final_layer_hash_changed:" + name)
    if source.count(FERRY_VIN_SOURCE_MARKER) != 1 or source.count(SEO_REHAB_SOURCE_MARKER) != 1:
        raise RepairBlocked("task068_final_layer_marker_count_invalid:" + name)
    body, guard = _detach_main_guard(source)
    seo_position = body.find(SEO_REHAB_SOURCE_MARKER)
    task_position = body.find(FERRY_VIN_SOURCE_MARKER)
    if not 0 < seo_position < task_position:
        raise RepairBlocked("task068_final_layer_order_invalid:" + name)
    old_task_layer = body[task_position:]
    required_binding = {
        STRANICA_PATH: "_ua068_stranica_card_original",
        YADRO_PATH: "_ua068_yadro_card_original",
        MASTER_CARD_PATH: "_ua068_master_card_original",
    }[path]
    if required_binding not in old_task_layer:
        raise RepairBlocked("task068_final_old_layer_invalid:" + name)
    candidate = (body[:task_position].rstrip() + "\n\n"
                 + FERRY_VIN_COMMON_SOURCE + "\n\n" + wrapper + "\n")
    if guard:
        candidate = candidate.rstrip() + "\n\n" + guard + "\n"
    _validate_task068_source(candidate, path)
    return candidate


def _append_task068(source: str, original_sha: str, path: str, wrapper: str) -> str:
    if FERRY_VIN_SOURCE_MARKER in source:
        if SEO_REHAB_SOURCE_MARKER in source:
            if source.find(SEO_REHAB_SOURCE_MARKER) < source.find(FERRY_VIN_SOURCE_MARKER):
                if ("def _ua068_reposition_stage" not in source
                        or "Korea CarHistory" not in source
                        or "Выдача и осмотр — Киев." in source):
                    return _upgrade_task068_after_seo(source, original_sha, path, wrapper)
                _validate_task068_source(source, path)
                return source
            return _rebase_task068_after_seo(source, original_sha, path, wrapper)
        if ("def _ua068_catalog_fallback" in source
                and "_UA068_FALLBACK_START" in source
                and "UA068_CATALOG_INSERTION_POINT_MISSING" in source):
            _validate_task068_source(source, path)
            return source
        if source.count(FERRY_VIN_SOURCE_MARKER) != 1:
            raise RepairBlocked("task068_upgrade_marker_count_invalid:" + os.path.basename(path))
        if original_sha != TASK068_INITIAL_SOURCE_SHA[path]:
            raise RepairBlocked("task068_existing_source_changed:" + os.path.basename(path))
        start = source.find(FERRY_VIN_SOURCE_MARKER)
        base = source[:start].rstrip()
        if not base:
            raise RepairBlocked("task068_upgrade_base_missing:" + os.path.basename(path))
        candidate = _inject_task068(base, wrapper)
        _validate_task068_source(candidate, path)
        return candidate
    if original_sha != EXPECTED_SHA[path]:
        raise RepairBlocked("task068_source_sha_changed:" + os.path.basename(path))
    candidate = _inject_task068(source, wrapper)
    _validate_task068_source(candidate, path)
    return candidate


def _patch_stranica(source: str, original_sha: str) -> str:
    if FERRY_VIN_SOURCE_MARKER not in source:
        if _function_sha(source, "sobrat_kartochku", last=True) != EXPECTED_FUNCTION_SHA[(STRANICA_PATH, "sobrat_kartochku")]:
            raise RepairBlocked("stranica_card_writer_changed")
        if _function_sha(source, "sobrat_katalog", last=True) != EXPECTED_FUNCTION_SHA[(STRANICA_PATH, "sobrat_katalog")]:
            raise RepairBlocked("stranica_catalog_writer_changed")
    return _append_task068(source, original_sha, STRANICA_PATH, STRANICA_FERRY_VIN_WRAPPER)


def _patch_yadro(source: str, original_sha: str) -> str:
    if FERRY_VIN_SOURCE_MARKER not in source:
        if _function_sha(source, "karta_html", last=True) != EXPECTED_FUNCTION_SHA[(YADRO_PATH, "karta_html")]:
            raise RepairBlocked("yadro_card_writer_changed")
        if _function_sha(source, "katalog_html", last=True) != EXPECTED_FUNCTION_SHA[(YADRO_PATH, "katalog_html")]:
            raise RepairBlocked("yadro_catalog_writer_changed")
    return _append_task068(source, original_sha, YADRO_PATH, YADRO_FERRY_VIN_WRAPPER)


def _patch_master_card(source: str, original_sha: str) -> str:
    if FERRY_VIN_SOURCE_MARKER not in source:
        for name, key in (("obrabotat_kartochku", "obrabotat_kartochku:last"),
                          ("proverit", "proverit:last"),
                          ("obrabotat_obshuyu", "obrabotat_obshuyu:last")):
            if _function_sha(source, name, last=True) != EXPECTED_FUNCTION_SHA[(MASTER_CARD_PATH, key)]:
                raise RepairBlocked("master_card_final_writer_changed:" + name)
    return _append_task068(source, original_sha, MASTER_CARD_PATH, MASTER_FERRY_VIN_WRAPPER)


def _validate_task068_source(source: str, path: str) -> None:
    compile(source, path, "exec")
    for value in (FERRY_VIN_SOURCE_MARKER, VIN_START_MARKER, VIN_END_MARKER,
                  CATALOG_VIN_START, CATALOG_VIN_END, "def _ua068_ensure_card",
                  "def _ua068_ensure_catalog", "Korea CarHistory",
                  "def _ua068_primary_action", CARHISTORY_URL):
        if value not in source:
            raise RepairBlocked("task068_contract_missing:%s:%s" % (os.path.basename(path), value))
    if source.count(FERRY_VIN_SOURCE_MARKER) != 1:
        raise RepairBlocked("task068_marker_count_invalid:" + os.path.basename(path))
    if SEO_REHAB_SOURCE_MARKER in source:
        if source.count(SEO_REHAB_SOURCE_MARKER) != 1:
            raise RepairBlocked("task068_seo_marker_count_invalid:" + os.path.basename(path))
        if source.find(SEO_REHAB_SOURCE_MARKER) > source.find(FERRY_VIN_SOURCE_MARKER):
            raise RepairBlocked("task068_final_filter_before_seo:" + os.path.basename(path))
    guards = list(re.finditer(
        r'(?m)^if\s+__name__\s*==\s*["\']__main__["\']\s*:', source
    ))
    if guards and source.find(FERRY_VIN_SOURCE_MARKER) > guards[-1].start():
        raise RepairBlocked("task068_filter_after_main_guard:" + os.path.basename(path))
    expected_last = {
        STRANICA_PATH: ("sobrat_kartochku", "_ua068_stranica_card_original"),
        YADRO_PATH: ("karta_html", "_ua068_yadro_card_original"),
        MASTER_CARD_PATH: ("obrabotat_kartochku", "_ua068_master_card_original"),
    }[path]
    nodes = _function_nodes(source, expected_last[0])
    if expected_last[1] not in _source_segment(source, nodes[-1]):
        raise RepairBlocked("task068_final_wrapper_not_last:" + os.path.basename(path))
    if path == MASTER_CARD_PATH:
        nodes = _function_nodes(source, "obrabotat_obshuyu")
        if "_ua068_master_common_original" not in _source_segment(source, nodes[-1]):
            raise RepairBlocked("task068_common_wrapper_not_last")


def _task068_runtime(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in rows:
        vin = str(row.get("vin") or "").strip().upper()
        counts[vin] = counts.get(vin, 0) + 1
    state: dict[str, Any] = {"rows": {}}
    namespace: dict[str, Any] = {"__name__": "task068_runtime"}
    exec(compile(STAGE_HELPER_SOURCE + "\n\n" + FERRY_VIN_COMMON_SOURCE,
                 "<task068-runtime>", "exec"), namespace)
    for raw in rows:
        row = dict(raw)
        row["_ua068_vin_duplicates"] = counts.get(str(row.get("vin") or "").strip().upper(), 1)
        state["rows"][str(row["auto_number"]).upper()] = row
    namespace["_ua068_rows"] = state["rows"]
    return namespace


def _task068_validate_card(source: str, identifier: str, row: dict[str, Any], runtime: dict[str, Any]) -> None:
    errors = runtime["_ua068_card_errors"](source, identifier, row)
    if errors:
        raise RepairBlocked("task068_card_invalid:%s:%s" % (identifier, ";".join(errors)))
    vin, status, _kind, _reason = runtime["_ua068_vin_result"](row)
    if status != "VIN ПРОВЕРЕН":
        raise RepairBlocked("published_vin_not_verified:%s:%s" % (identifier, status))
    if vin not in source:
        raise RepairBlocked("published_vin_missing:" + identifier)


def _task068_validate_catalog(source: str, rows: list[dict[str, Any]], runtime: dict[str, Any], path: str) -> None:
    if runtime["_ua068_forbidden_count"](source):
        raise RepairBlocked("catalog_sea_wording_remains:" + path)
    for row in rows:
        identifier = str(row["auto_number"])
        if source.count('data-ua-card="%s"' % identifier) != 1:
            raise RepairBlocked("catalog_vin_block_invalid:%s:%s" % (path, identifier))
        vin = str(row.get("vin") or "").strip().upper()
        if vin not in source:
            raise RepairBlocked("catalog_vin_missing:%s:%s" % (path, identifier))
        engine = runtime["_ua068_engine"](row)
        block = _catalog_block_for_id(source, identifier)
        if not block or not re.search(re.escape(engine) + r"\s*см³", block):
            raise RepairBlocked("catalog_engine_mismatch:%s:%s" % (path, identifier))
        if runtime["_ua068_stage"](row) == 4 and (
                "Выдача и осмотр — Киев" in block or "Видача та огляд — Київ" in block):
            raise RepairBlocked("catalog_redundant_kyiv_copy:%s:%s" % (path, identifier))
        expected_videos = runtime["_ua068_video_count"](identifier, row)
        if 'data-ua-video-count="%d"' % expected_videos not in block:
            raise RepairBlocked("catalog_video_count_mismatch:%s:%s" % (path, identifier))
    if source.count(CATALOG_VIN_START) != len(rows):
        raise RepairBlocked("catalog_block_count_invalid:" + path)


def _catalog_block_for_id(source: str, identifier: str) -> str:
    marker = 'data-ua-card="%s"' % identifier
    position = source.find(marker)
    if position < 0:
        return ""
    start = source.rfind(CATALOG_VIN_START, 0, position)
    end = source.find(CATALOG_VIN_END, position)
    return source[start:end + len(CATALOG_VIN_END)] if start >= 0 and end >= 0 else ""


def _collect_candidates(rows: list[dict[str, Any]], patched: dict[str, bytes]) -> dict[str, bytes]:
    candidates = dict(patched)
    runtime = _task068_runtime(rows)
    row_map = runtime["_ua068_rows"]
    ensure_card = runtime["_ua068_ensure_card"]
    ensure_catalog = runtime["_ua068_ensure_catalog"]
    terms = runtime["_ua068_terms"]

    for row in row_map.values():
        identifier = str(row["auto_number"])
        found_primary = set()
        for root in (VIDEO_ROOT, SITE_ROOT):
            diag_path = os.path.join(root, identifier + "-diag.html")
            diag_data = _read(diag_path, required=False)
            if diag_data is None or not _valid_diag_page(diag_data.decode("utf-8", "replace"), identifier):
                diag_source = runtime["_ua068_diag_placeholder"](identifier, row)
            else:
                diag_source = terms(diag_data.decode("utf-8", "replace"))
            diag_source = runtime["_ua068_primary_action"](diag_source, identifier, row)
            diag_errors = runtime["_ua068_primary_action_errors"](diag_source, identifier, row)
            if diag_errors:
                raise RepairBlocked("diagnostics_primary_action_invalid:%s:%s" % (
                    identifier, ";".join(diag_errors)))
            candidates[diag_path] = diag_source.encode("utf-8")
            paths = {os.path.join(root, identifier + ".html")}
            paths.update(glob.glob(os.path.join(root, identifier + "-*.html")))
            for path in sorted(paths):
                name = os.path.basename(path)
                if name.startswith(identifier + "-diag"):
                    continue
                if name != identifier + ".html":
                    try:
                        if os.path.getsize(path) == 0:
                            continue
                    except OSError:
                        continue
                data = _read(path, required=False)
                if data is None:
                    if name == identifier + ".html":
                        raise RepairBlocked("primary_card_missing:" + path)
                    continue
                upgraded = ensure_card(data.decode("utf-8"), identifier, row)
                _task068_validate_card(upgraded, identifier, row, runtime)
                candidates[path] = upgraded.encode("utf-8")
                if name == identifier + ".html":
                    found_primary.add(root)
        if found_primary != {VIDEO_ROOT, SITE_ROOT}:
            raise RepairBlocked("card_roots_incomplete:" + identifier)

        if os.path.isdir(ETALON_ROOT) and not os.path.islink(ETALON_ROOT):
            for path in glob.glob(os.path.join(ETALON_ROOT, "**", identifier + "*.html"), recursive=True):
                if "otklonennye" in pathlib.PurePath(path).parts or os.path.basename(path).startswith(identifier + "-diag"):
                    continue
                data = _read(path)
                assert data is not None
                candidates[path] = ensure_card(data.decode("utf-8"), identifier, row).encode("utf-8")

    for root in (VIDEO_ROOT, SITE_ROOT):
        for path in sorted(glob.glob(os.path.join(root, "*.html"))):
            name = os.path.basename(path)
            if CARD_ID.fullmatch(name[:-5]) or re.fullmatch(r"UA-[0-9]{4,}-.*", name[:-5]):
                continue
            data = _read(path)
            assert data is not None
            # Recovery/forensic fragments may deliberately be HTML snippets,
            # not complete public documents.  They are not card surfaces and
            # must stay byte-for-byte untouched by this contract.
            if b"</html>" not in data[-1200:].lower():
                continue
            source = data.decode("utf-8")
            if name == "katalog.html":
                source = ensure_catalog(source, row_map)
                _task068_validate_catalog(source, list(row_map.values()), runtime, path)
            else:
                source = terms(source)
            candidates[path] = source.encode("utf-8")
    return candidates


def _validate_cards(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runtime = _task068_runtime(rows)
    results = []
    for row in runtime["_ua068_rows"].values():
        identifier = str(row["auto_number"])
        item = {"id": identifier, "stage": runtime["_ua068_stage"](row), "roots": {}}
        for root in (VIDEO_ROOT, SITE_ROOT):
            path = os.path.join(root, identifier + ".html")
            data = _read(path)
            assert data is not None
            source = data.decode("utf-8")
            _task068_validate_card(source, identifier, row, runtime)
            diag_path = os.path.join(root, identifier + "-diag.html")
            diag_data = _read(diag_path)
            assert diag_data is not None
            diag_source = diag_data.decode("utf-8", "replace")
            if not _valid_diag_page(diag_source, identifier):
                raise RepairBlocked("diagnostics_target_invalid:" + diag_path)
            if runtime["_ua068_forbidden_count"](diag_source):
                raise RepairBlocked("diagnostics_sea_wording_remains:" + diag_path)
            diag_cta_errors = runtime["_ua068_primary_action_errors"](
                diag_source, identifier, row)
            if diag_cta_errors:
                raise RepairBlocked("diagnostics_primary_action_invalid:%s:%s" % (
                    identifier, ";".join(diag_cta_errors)))
            item["roots"][os.path.basename(root)] = {
                "sha256": _sha(data), "stage_anchor_count": 1,
                "diagnostics_links": 1, "diagnostics_target_complete": True,
                "vin_guard_count": 1,
                "vin_button_count": 1, "forbidden_sea_terms": 0,
                "primary_action": "Купить" if item["stage"] == 4 else "Задаток 500 $",
                "carhistory": True,
                "legacy_duplicate_ui": 0,
                "native_stage_duplicate_ui": 0,
                "engine_cc": int(row.get("engine_cc") or 0), "vin": row.get("vin"),
                "video_count": runtime["_ua068_video_count"](identifier, row, source),
            }
        results.append(item)
    for root in (VIDEO_ROOT, SITE_ROOT):
        path = os.path.join(root, "katalog.html")
        source = _read(path).decode("utf-8")
        _task068_validate_catalog(source, list(runtime["_ua068_rows"].values()), runtime, path)
    return results


def _fixture_contract() -> dict[str, int]:
    rows = [
        {"auto_number": "UA-9001", "status": "kr_bought", "vin": "KNAGS416BLA375484", "brand": "Kia", "engine_cc": 2000},
        {"auto_number": "UA-9002", "status": "sea_loaded", "vin": "KNAGU416BJA242741", "brand": "Kia", "engine_cc": 2000, "eta_manual": "2099-09-09"},
        {"auto_number": "UA-9003", "status": "ge_waiting", "vin": "WDDZF0EB7HA053001", "brand": "Mercedes-Benz", "engine_cc": 1950},
        {"auto_number": "UA-9004", "status": "ua_ready", "vin": "WDD2452322J561014", "brand": "Mercedes-Benz", "engine_cc": 1700},
    ]
    runtime = _task068_runtime(rows)
    result = {}
    for row in runtime["_ua068_rows"].values():
        identifier = str(row["auto_number"])
        old = ("<html><head></head><body><div>%s</div><div>В море</div>"
               "<div class='blok'><div class='zag'>Где машина сейчас</div>"
               "<div class='etap tut'><div class='krug'>2</div>Море</div></div>"
               "<div class='mcf-etap mcf-kiev'><div>Старый этап</div></div>"
               "<div class='mcf-diag-off'><span>Диагностика готовится</span></div>"
               "<h2>Комплексная диагностика</h2>"
               "<a class='dejstvie' href='#'>Купить</a></body></html>") % identifier
        upgraded = runtime["_ua068_ensure_card"](old, identifier, row)
        upgraded2 = runtime["_ua068_ensure_card"](upgraded, identifier, row)
        if upgraded != upgraded2:
            raise RepairBlocked("task068_card_not_idempotent:" + identifier)
        _task068_validate_card(upgraded, identifier, row, runtime)
        stage = runtime["_ua068_stage"](row)
        result[{1: "korea", 2: "ferry", 3: "georgia", 4: "kyiv"}[stage]] = stage
    return result


def _master_final_fixture_contract() -> dict[str, int]:
    fixtures = _fixture_contract()
    if fixtures != {"korea": 1, "ferry": 2, "georgia": 3, "kyiv": 4}:
        raise RepairBlocked("task068_fixture_stage_contract")
    row = {
        "auto_number": "UA-9202", "status": "sea_loaded", "brand": "Kia",
        "model": "K5", "year": "2018", "vin": "KNAGU416BKA324445",
        "engine_cc": 2000, "eta_manual": "2099-09-09",
    }
    state = {"row": row}
    namespace: dict[str, Any] = {
        "__name__": "task068_master_fixture",
        "dannye": lambda _kod: dict(state["row"]),
        "vse_kody": lambda: ["UA-9202"],
        "obrabotat_kartochku": lambda source, _kod: source,
        "proverit": lambda _source, _kod="": [],
        "obrabotat_obshuyu": lambda source: source,
    }
    installed = STAGE_HELPER_SOURCE + "\n\n" + FERRY_VIN_COMMON_SOURCE + "\n\n" + MASTER_FERRY_VIN_WRAPPER
    exec(compile(installed, "<task068-master-fixture>", "exec"), namespace)
    namespace["_ua068_ensure_diag_files"] = lambda _kod, _row: None
    old = ("<html><head></head><body><div>UA-9202 · 1 800 см³ · В море</div>"
           "<h2>Комплексная диагностика</h2><a href='#'>Купить</a></body></html>")
    upgraded = namespace["obrabotat_kartochku"](old, "UA-9202")
    if namespace["proverit"](upgraded, "UA-9202"):
        raise RepairBlocked("task068_master_fixture_validator")
    catalog = ("<html><head></head><body><article><a href='UA-9202.html'>"
               "UA-9202 · 1 800 см³ · В море</a></article></body></html>")
    catalog = namespace["obrabotat_obshuyu"](catalog)
    if catalog.count(CATALOG_VIN_START) != 1 or "2 000 см³" not in catalog:
        raise RepairBlocked("task068_master_fixture_catalog")
    return fixtures


def _validate_untouched() -> dict[str, str]:
    values = {}
    for path in (CARS_UI_PATH, DB_PATH, TEAM_BOT_PATH, START_SAFE_PATH):
        data = _read(path)
        assert data is not None
        digest = _sha(data)
        if path == CARS_UI_PATH and digest != EXPECTED_SHA[path]:
            _validate_cars_ui(data.decode("utf-8"))
        elif digest != EXPECTED_SHA[path]:
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
        (MASTER_CARD_PATH, _patch_master_card),
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


def run_install(*, sources_only: bool = False) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "mode": MODE,
        "contract_id": CONTRACT,
        "status": "BLOCKED",
        "generated_at_utc": _utc_now(),
        "sources_only": sources_only,
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
        "master_final_fixtures": {},
        "changed_paths": [],
        "errors": [],
        "llm_tokens": 0,
    }
    before: dict[str, bytes | None] = {}
    changed: list[str] = []
    try:
        receipt["protected_files"] = _validate_untouched()
        rows: list[dict[str, Any]] = []
        identifiers: list[str] = []
        db_before: dict[str, Any] = {}
        media_before: dict[str, Any] = {}
        if not sources_only:
            rows, db_before = _db_snapshot()
            identifiers = [str(row["auto_number"]) for row in rows]
            receipt["card_ids"] = identifiers
            receipt["db_before"] = db_before
            media_before = _media_inventory(identifiers)
            receipt["media_before"] = media_before

        source_candidates, before_hashes = _build_sources()
        receipt["source_sha256_before"] = before_hashes
        candidates = source_candidates if sources_only else _collect_candidates(rows, source_candidates)
        receipt["fixtures"] = _fixture_contract()
        receipt["master_final_fixtures"] = _master_final_fixture_contract()

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
        if not sources_only:
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

        _validate_task068_source(_read(STRANICA_PATH).decode("utf-8"), STRANICA_PATH)
        _validate_task068_source(_read(YADRO_PATH).decode("utf-8"), YADRO_PATH)
        _validate_task068_source(_read(MASTER_CARD_PATH).decode("utf-8"), MASTER_CARD_PATH)
        _validate_untouched()
        if not sources_only:
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
            for path in (STRANICA_PATH, YADRO_PATH, MASTER_CARD_PATH, CARS_UI_PATH)
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


def rollback_from_receipt(receipt_path: str = RECEIPT_PATH) -> dict[str, Any]:
    result = {"contract_id": CONTRACT, "status": "BLOCKED", "restored": [],
              "receipt": os.path.basename(receipt_path), "errors": []}
    try:
        if receipt_path not in (RECEIPT_PATH, SOURCE_RECEIPT_PATH):
            raise RepairBlocked("rollback_receipt_path_invalid")
        receipt = json.loads(_read(receipt_path).decode("utf-8"))
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
    guard_fixture = "def main():\n    return 0\n\nif __name__ == '__main__':\n    main()\n"
    injected_fixture = _inject_task068(guard_fixture, "# wrapper-fixture")
    if not (injected_fixture.find(FERRY_VIN_SOURCE_MARKER)
            < injected_fixture.rfind("if __name__ == '__main__'")):
        raise SystemExit("TASK068_FILTER_ORDER_FAIL")
    layered_base = (
        "def nomer(m):\n    return m.get('auto_number', 'UA-9999')\n\n"
        "def sobrat_kartochku(m, kadry, sredn=None):\n    return '<html></html>'\n\n"
        "def sobrat_katalog(spisok, kadry_po_nomeru, legkie_po_nomeru=None):\n"
        "    return '<html></html>'\n\n"
        "def main():\n    return 0\n\nif __name__ == '__main__':\n    main()\n"
    )
    layered = _inject_task068(layered_base, STRANICA_FERRY_VIN_WRAPPER)
    layered += ("\n" + SEO_REHAB_SOURCE_MARKER + "\n"
                "_ua_seo_card_original = sobrat_kartochku\n"
                "def sobrat_kartochku(m, kadry, sredn=None):\n"
                "    return _ua_seo_card_original(m, kadry, sredn)\n"
                "_ua_seo_catalog_original = sobrat_katalog\n"
                "def sobrat_katalog(spisok, kadry_po_nomeru, legkie_po_nomeru=None):\n"
                "    return _ua_seo_catalog_original(spisok, kadry_po_nomeru, legkie_po_nomeru)\n")
    previous_layered_sha = SEO_LAYERED_SOURCE_SHA[STRANICA_PATH]
    try:
        SEO_LAYERED_SOURCE_SHA[STRANICA_PATH] = _sha(layered.encode("utf-8"))
        rebased = _rebase_task068_after_seo(
            layered, SEO_LAYERED_SOURCE_SHA[STRANICA_PATH],
            STRANICA_PATH, STRANICA_FERRY_VIN_WRAPPER,
        )
    finally:
        SEO_LAYERED_SOURCE_SHA[STRANICA_PATH] = previous_layered_sha
    if not (rebased.find(SEO_REHAB_SOURCE_MARKER)
            < rebased.find(FERRY_VIN_SOURCE_MARKER)
            < rebased.rfind("if __name__ == '__main__'")):
        raise SystemExit("TASK068_SEO_REBASE_ORDER_FAIL")
    _validate_task068_source(rebased, STRANICA_PATH)
    previous_final_sha = SEO_FINAL_V1_SOURCE_SHA[STRANICA_PATH]
    try:
        SEO_FINAL_V1_SOURCE_SHA[STRANICA_PATH] = _sha(rebased.encode("utf-8"))
        upgraded_final = _upgrade_task068_after_seo(
            rebased, SEO_FINAL_V1_SOURCE_SHA[STRANICA_PATH],
            STRANICA_PATH, STRANICA_FERRY_VIN_WRAPPER,
        )
    finally:
        SEO_FINAL_V1_SOURCE_SHA[STRANICA_PATH] = previous_final_sha
    if upgraded_final != rebased:
        raise SystemExit("TASK068_FINAL_LAYER_UPGRADE_NOT_IDEMPOTENT")
    fixtures = _fixture_contract()
    if fixtures != {"korea": 1, "ferry": 2, "georgia": 3, "kyiv": 4}:
        raise SystemExit("TASK068_FIXTURE_CONTRACT_FAIL")
    master_fixtures = _master_final_fixture_contract()
    if master_fixtures != {"korea": 1, "ferry": 2, "georgia": 3, "kyiv": 4}:
        raise SystemExit("TASK068_MASTER_FINAL_FIXTURE_CONTRACT_FAIL")
    row = {
        "auto_number": "UA-9999", "status": "sea_loaded", "brand": "Kia",
        "model": "K5", "year": "2018", "vin": "KNAGU416BJA242741",
        "engine_cc": 2000, "sea_container": "<script>",
        "sea_date_out": "2026-08-01", "eta_manual": "2099-01-01",
    }
    runtime = _task068_runtime([row])
    row = runtime["_ua068_rows"]["UA-9999"]
    old = (
        "<html><head></head><body><div>UA-9999 · 1 800 см³ · В море</div>"
        "<video><source src='UA-9999.mp4'></video>"
        "<h2>Комплексная диагностика</h2>"
        "<a class='dejstvie kn_kupit' href='#'>Купить</a></body></html>"
    )
    upgraded = runtime["_ua068_ensure_card"](old, "UA-9999", row)
    upgraded_twice = runtime["_ua068_ensure_card"](upgraded, "UA-9999", row)
    if upgraded != upgraded_twice:
        raise SystemExit("TASK068_IDEMPOTENCY_FAIL")
    _task068_validate_card(upgraded, "UA-9999", row, runtime)
    if 'data-ua-video-count="1"' not in upgraded or "2 000 см³" not in upgraded:
        raise SystemExit("TASK068_MEDIA_ENGINE_FAIL")
    catalog = ("<html><head></head><body><article class='catalog-card'>"
               "<a href='UA-9999.html'>UA-9999 · 1 800 см³ · В море</a></article></body></html>")
    catalog = runtime["_ua068_ensure_catalog"](catalog, {"UA-9999": row})
    _task068_validate_catalog(catalog, [row], runtime, "fixture/katalog.html")
    mixed_catalog = ("<html><head></head><body>"
                     "<article><a href='UA-8888.html'>UA-8888</a></article>"
                     "<a class='legacy-card' href='UA-9999.html'>UA-9999 · 1 800 см³ · В море</a>"
                     "<a class='secondary-link' href='UA-9999.html'>UA-9999</a>"
                     "</body></html>")
    mixed_catalog = runtime["_ua068_ensure_catalog"](mixed_catalog, {"UA-9999": row})
    _task068_validate_catalog(mixed_catalog, [row], runtime, "fixture/mixed-katalog.html")
    if mixed_catalog.count('data-ua-card="UA-9999"') != 1:
        raise SystemExit("TASK068_MIXED_CATALOG_DEDUP_FAIL")
    placeholder = runtime["_ua068_diag_placeholder"]("UA-9999", row)
    if not _valid_diag_page(placeholder, "UA-9999") or "ДИАГНОСТИКА ОЖИДАЕТ ДАННЫХ" not in placeholder:
        raise SystemExit("TASK068_DIAGNOSTICS_FAIL")
    print("TASK068_SELF_TEST_PASS")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    sources_only = "--sources-only" in sys.argv
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
            if "--rollback-source" in sys.argv:
                result = rollback_from_receipt(SOURCE_RECEIPT_PATH)
            elif "--rollback" in sys.argv:
                result = rollback_from_receipt(RECEIPT_PATH)
            else:
                retry_history = []
                for attempt in range(1, 6):
                    result = run_install(sources_only=sources_only)
                    result["attempt_count"] = attempt
                    errors = [str(value) for value in result.get("errors", [])]
                    retryable = (
                        result.get("status") != "PASS"
                        and not result.get("production_write")
                        and not result.get("rollback_attempted")
                        and bool(errors)
                        and all(
                            value.startswith("concurrent_file_change:")
                            or value == "crm_rows_changed_before_install"
                            or value == "OperationalError:database is locked"
                            for value in errors
                        )
                    )
                    if not retryable or attempt == 5:
                        break
                    retry_history.append({
                        "attempt": attempt,
                        "errors": errors,
                        "backup_root": result.get("backup_root", ""),
                    })
                    time.sleep(min(2 ** (attempt - 1), 8))
                result["retry_history"] = retry_history
    finally:
        os.close(descriptor)
    if "--rollback" in sys.argv or "--rollback-source" in sys.argv:
        path = ROLLBACK_RECEIPT_PATH
    elif sources_only:
        path = SOURCE_RECEIPT_PATH
    else:
        path = RECEIPT_PATH
    _atomic_json(path, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
