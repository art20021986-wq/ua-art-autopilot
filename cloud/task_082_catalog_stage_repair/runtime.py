#!/usr/bin/env python3
"""Permanent fail-closed catalog stage/media guard for UA ART TASK 082."""
from __future__ import annotations

import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import tempfile
import uuid
from typing import Any

import catalog_stage_guard_core as core


CONTRACT_ID = "UA-0011-CATALOG-FERRY-REPAIR-001-V1.0"
ROOT = pathlib.Path("/home/Carix")
DB_PATH = ROOT / "crm.db"
CATALOGS = (ROOT / "video/katalog.html", ROOT / "site/katalog.html")
BACKUP_PARENT = ROOT / "autopilot_inbox/cloud/task_082_catalog_stage_repair/runtime_backups"
LOCK_PATH = ROOT / ".task082_catalog_stage_guard.lock"
PUBLIC = "https://www.uaart.com.ua"
MAX_BYTES = 24 * 1024 * 1024

FILTER_SCRIPT = r"""<script id="ua-stage-card-v2-filter">(function(){
function norm(v){v=(v||'all').toLowerCase().trim();var a={
'1':'korea','2':'more','3':'gruzia','4':'kiev',
'kr':'korea','korea':'korea','корея':'korea',
'sea':'more','sea_loaded':'more','ferry':'more','more':'more','ocean':'more','паром':'more','пором':'more',
'ge':'gruzia','georgia':'gruzia','gruzia':'gruzia','грузия':'gruzia',
'ua':'kiev','kyiv':'kiev','kiev':'kiev','киев':'kiev','київ':'kiev',
'all':'all'};return a[v]||v;}
function apply(){var p=new URLSearchParams(location.search);
var f=norm(p.get('f')||p.get('etap')||p.get('stage')||p.get('category')||'all');
var cards=document.querySelectorAll('[data-ua-card-stage]');for(var i=0;i<cards.length;i++){
var s=norm(cards[i].getAttribute('data-ua-card-stage'));cards[i].style.display=(f==='all'||s===f)?'':'none';}
var chips=document.querySelectorAll('.chipy [data-f]');for(var j=0;j<chips.length;j++){
if(norm(chips[j].getAttribute('data-f'))===f){chips[j].classList.add('on')}else{chips[j].classList.remove('on')}}}
if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',apply)}else{apply()}})();</script>"""


class GuardError(RuntimeError):
    pass


def _configure_core() -> None:
    core.FILTER_SCRIPT = FILTER_SCRIPT
    original = core.title

    def with_vin(row):
        base = original(row)
        vin = re.sub(r"[^A-Z0-9]", "", str(row.get("vin") or "").upper())
        return (base + " · VIN " + vin[-4:]) if len(vin) >= 4 else base

    core.title = with_vin


_configure_core()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read(path: pathlib.Path) -> bytes:
    data = path.read_bytes()
    if len(data) > MAX_BYTES:
        raise GuardError("FILE_TOO_LARGE:" + str(path))
    return data


def _atomic(path: pathlib.Path, data: bytes, mode: int | None = None) -> None:
    handle = tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name + ".", suffix=".tmp", delete=False)
    temp = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _rows() -> tuple[list[dict[str, Any]], str]:
    con = sqlite3.connect("file:%s?mode=ro" % DB_PATH, uri=True, timeout=20)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA query_only=ON")
        quick = con.execute("PRAGMA quick_check").fetchone()[0]
        rows = [dict(row) for row in con.execute(
            "SELECT * FROM cars WHERE published=1 ORDER BY auto_number, id"
        ).fetchall()]
    finally:
        con.close()
    if quick != "ok":
        raise GuardError("CRM_QUICK_CHECK:" + str(quick))
    normalized = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode()
    return rows, _sha(normalized)


def _catalog_ids(source: str) -> list[str]:
    return [item.card_id for item in core.card_spans(source)]


def _resolve_target(rows: list[dict[str, Any]], target: Any) -> str | None:
    if target is None:
        return None
    if isinstance(target, dict):
        target = target.get("auto_number") or target.get("id")
    text = str(target).strip().upper()
    if re.fullmatch(r"UA-[0-9]{4,}", text):
        return text
    try:
        numeric = int(target)
    except (TypeError, ValueError):
        numeric = None
    if numeric is not None:
        for row in rows:
            if int(row.get("id") or -1) == numeric:
                return str(row.get("auto_number") or "").upper()
    raise GuardError("TARGET_NOT_RESOLVED")


def _main_photo(identifier: str) -> str:
    for variant in ("video", "site"):
        path = ROOT / variant / (identifier + ".html")
        if not path.is_file():
            continue
        page = _read(path).decode("utf-8", "replace")
        value = core.extract_main_photo(
            page, "%s/%s/%s.html" % (PUBLIC, variant, identifier), identifier
        )
        if value:
            return value
    return ""


def _backup(originals: dict[pathlib.Path, bytes]) -> pathlib.Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = BACKUP_PARENT / (stamp + "-" + uuid.uuid4().hex[:12])
    for path, data in originals.items():
        target = root / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic(target, data, path.stat().st_mode & 0o777)
    return root


def _validate_global(source: str, expected_ids: set[str]) -> dict[str, Any]:
    spans = core.card_spans(source)
    ids = [span.card_id for span in spans]
    if len(ids) != len(set(ids)):
        raise GuardError("DUPLICATE_PUBLIC_CARD")
    missing = sorted(expected_ids - set(ids))
    if missing:
        raise GuardError("EXPECTED_CARD_MISSING:" + ",".join(missing))
    return {"card_count": len(ids), "unique": len(ids), "ids": ids}


def _prepare(target: Any = None) -> dict[str, Any]:
    rows, rows_hash = _rows()
    by_id = {str(row.get("auto_number") or "").upper(): row for row in rows}
    if "UA-0009" not in by_id or "UA-0011" not in by_id:
        raise GuardError("PROTECTED_CARD_ROW_MISSING")
    if core.stage_number(by_id["UA-0011"]) != 2:
        raise GuardError("UA0011_NOT_FERRY_IN_CRM")
    target_id = _resolve_target(rows, target)

    originals = {path: _read(path) for path in CATALOGS}
    id_sets = [set(_catalog_ids(data.decode("utf-8", "replace"))) for data in originals.values()]
    existing_ids = set().union(*id_sets)
    if "UA-0011" not in existing_ids:
        existing_ids.add("UA-0011")
    if target_id:
        existing_ids.add(target_id)
    unknown = sorted(existing_ids - set(by_id))
    if unknown:
        raise GuardError("CATALOG_CARD_WITHOUT_PUBLISHED_ROW:" + ",".join(unknown))

    selected = [by_id[identifier] for identifier in sorted(existing_ids)]
    photos = {identifier: _main_photo(identifier) for identifier in sorted(existing_ids)}
    missing_photos = sorted(identifier for identifier, value in photos.items() if not value)
    if missing_photos:
        raise GuardError("MAIN_PHOTO_NOT_READY:" + ",".join(missing_photos))

    candidates: dict[pathlib.Path, bytes] = {}
    audits: dict[str, Any] = {}
    for path, original in originals.items():
        candidate = core.enforce_catalog(original.decode("utf-8", "replace"), selected, photos)
        audit = core.audit_catalog(candidate, selected)
        if audit.get("status") != "PASS":
            raise GuardError(path.parent.name.upper() + "_AUDIT:" + ";".join(audit.get("errors") or []))
        global_audit = _validate_global(candidate, existing_ids)
        ua11 = audit["cards"].get("UA-0011") or {}
        if not (ua11.get("stage") == 2 and ua11.get("category") == "more"
                and ua11.get("template") and ua11.get("absolute_photo")):
            raise GuardError("UA0011_CONTRACT_INVALID:" + path.parent.name)
        spans = [span.block for span in core.card_spans(candidate) if span.card_id == "UA-0011"]
        if len(spans) != 1 or "VIN 4289" not in spans[0]:
            raise GuardError("UA0011_VIN_SUFFIX_INVALID:" + path.parent.name)
        audits[path.parent.name] = {"audit": audit, "global": global_audit}
        candidates[path] = candidate.encode("utf-8")

    return {
        "rows_hash": rows_hash,
        "target_id": target_id,
        "selected_ids": sorted(existing_ids),
        "originals": originals,
        "candidates": candidates,
        "audits": audits,
        "photos": {identifier: _sha(value.encode()) for identifier, value in photos.items()},
    }


def enforce_live_catalog(target: Any = None, dry_run: bool = False) -> dict[str, Any]:
    """Rebuild current catalog cards after media sync; never writes CRM or media."""
    LOCK_PATH.touch(exist_ok=True)
    with LOCK_PATH.open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        prepared = _prepare(target)
        result = {
            "contract_id": CONTRACT_ID,
            "status": "PASS",
            "mode": "DRY_RUN" if dry_run else "INSTALL",
            "started_at_utc": _now(),
            "target_id": prepared["target_id"],
            "selected_ids": prepared["selected_ids"],
            "rows_sha256_before": prepared["rows_hash"],
            "catalogs": {},
            "backup_root": None,
            "crm_write": False,
            "media_write": False,
            "llm_tokens": 0,
        }
        for path in CATALOGS:
            result["catalogs"][path.parent.name] = {
                "before_sha256": _sha(prepared["originals"][path]),
                "candidate_sha256": _sha(prepared["candidates"][path]),
                **prepared["audits"][path.parent.name],
            }
        if dry_run:
            result["finished_at_utc"] = _now()
            return result

        backup_root = _backup(prepared["originals"])
        result["backup_root"] = str(backup_root)
        changed: list[str] = []
        try:
            for path in CATALOGS:
                candidate = prepared["candidates"][path]
                if candidate != prepared["originals"][path]:
                    _atomic(path, candidate, path.stat().st_mode & 0o777)
                    changed.append(str(path))
            for path in CATALOGS:
                readback = _read(path)
                if readback != prepared["candidates"][path]:
                    raise GuardError("READBACK_MISMATCH:" + str(path))
            _after_rows, after_hash = _rows()
            if after_hash != prepared["rows_hash"]:
                raise GuardError("CRM_ROWS_CHANGED")
            result["rows_sha256_after"] = after_hash
            result["changed_paths"] = changed
        except Exception:
            for path, data in prepared["originals"].items():
                _atomic(path, data, path.stat().st_mode & 0o777)
            raise
        result["finished_at_utc"] = _now()
        return result

