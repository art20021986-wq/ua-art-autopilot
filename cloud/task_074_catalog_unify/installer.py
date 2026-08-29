#!/usr/bin/env python3
"""Atomic TASK 074 installer for CATALOG-CARD-UNIFY-002 v1.0.

Runs on PythonAnywhere.  It changes only the three persistent catalog
generators and the two generated catalog HTML files.  CRM rows, media and
individual vehicle pages are read-only invariants.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import html as html_lib
import json
import os
import pathlib
import re
import shutil
import sqlite3
import tempfile
from typing import Any


CONTRACT = "CATALOG-CARD-UNIFY-002-V1.0"
SOURCE_MARKER = "# CATALOG-CARD-UNIFY-002-V1.0-PERMANENT"
STYLE_MARKER = "UA-CATALOG-CARD-UNIFY-002-V1.0"
ROOT = pathlib.Path("/home/Carix")
REMOTE_ROOT = ROOT / "autopilot_inbox/cloud/task_074_catalog_unify"
BACKUP_PARENT = REMOTE_ROOT / "backups"
RECEIPTS = {
    "shadow": REMOTE_ROOT / "shadow_receipt.json",
    "install": REMOTE_ROOT / "install_receipt.json",
    "rollback": REMOTE_ROOT / "rollback_receipt.json",
}
LOCK_PATH = ROOT / ".task074_catalog_unify.lock"
DB_PATH = ROOT / "crm.db"
SOURCE_PATHS = [ROOT / name for name in ("stranica.py", "yadro.py", "master_card.py")]
CATALOG_PATHS = [ROOT / "video/katalog.html", ROOT / "site/katalog.html"]
CARD_PAGE_GLOBS = [ROOT / "video/UA-*.html", ROOT / "site/UA-*.html"]

# Exact source layer produced by successful task068 run 33232099399.
EXPECTED_BASE_SHA256 = {
    str(ROOT / "stranica.py"): "28cf48583459b79cf2848eaaf1b69ab22a7d27601130162942cf5a41785f6a07",
    str(ROOT / "yadro.py"): "3e5589b2a3b967c75a7d06aeb1b0be6b27a10d529a9a6520406ea4b1f8bbc4ac",
    str(ROOT / "master_card.py"): "8562a864febafe11a39cd6a3a13550b464bf0f79dd39d7b707d0dbeec83f4659",
}

RU_DUPLICATE = "Автомобиль на пароме: Корея → Грузия."
UK_DUPLICATE = "Автомобіль на поромі: Корея → Грузія."
RU_UNKNOWN_OLD = "Автомобиль на пароме · количество дней до Киева уточняется."
UK_UNKNOWN_OLD = "Автомобіль на поромі · кількість днів до Києва уточнюється."
RU_UNKNOWN_NEW = "Количество дней до Киева уточняется."
UK_UNKNOWN_NEW = "Кількість днів до Києва уточнюється."

SOURCE_STYLE_OVERRIDE = (
    "/* " + STYLE_MARKER + " */"
    ".catalog-card{--ua-card-surface:#0f2137;overflow:hidden!important;}"
    ".catalog-card .catalog-body{background:var(--ua-card-surface)!important;"
    "border-radius:0!important;margin-bottom:0!important;}"
    ".catalog-card .ua-cat-vin-v1{margin:0!important;padding:14px 20px 18px!important;"
    "border:0!important;border-top:1px solid rgba(240,166,60,.32)!important;"
    "border-radius:0 0 20px 20px!important;background:var(--ua-card-surface)!important;"
    "box-shadow:none!important;}"
    "@media(max-width:520px){.catalog-card .ua-cat-vin-v1{padding:13px 20px 17px!important;}}"
)

CATALOG_STYLE = "<style id=\"ua-catalog-card-unify-002-style\">" + SOURCE_STYLE_OVERRIDE + "</style>"
CAT_START = "<!-- UA-ART-CATALOG-VIN-V1:START -->"
CAT_END = "<!-- UA-ART-CATALOG-VIN-V1:END -->"


class Blocked(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_bytes(path: pathlib.Path) -> bytes:
    data = path.read_bytes()
    if len(data) > 24 * 1024 * 1024:
        raise Blocked("FILE_TOO_LARGE:" + str(path))
    return data


def atomic_write(path: pathlib.Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name + ".", delete=False)
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


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())


def db_snapshot() -> dict[str, Any]:
    data = read_bytes(DB_PATH)
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(data)
        connection = sqlite3.connect("file:%s?mode=ro" % temp, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only=ON")
            quick = connection.execute("PRAGMA quick_check").fetchone()[0]
            rows = [dict(row) for row in connection.execute(
                "SELECT * FROM cars WHERE published=1 ORDER BY id"
            )]
        finally:
            connection.close()
    finally:
        temp.unlink(missing_ok=True)
    normalized = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str).encode()
    identifiers = [str(row.get("auto_number") or "") for row in rows]
    return {
        "file_sha256": sha256(data),
        "rows_sha256": sha256(normalized),
        "quick_check": str(quick),
        "count": len(rows),
        "identifiers": identifiers,
        "ua0009": next((row for row in rows if row.get("auto_number") == "UA-0009"), None),
    }


def protected_pages_snapshot() -> dict[str, str]:
    result: dict[str, str] = {}
    for pattern in CARD_PAGE_GLOBS:
        for path in sorted(pattern.parent.glob(pattern.name)):
            # Catalog is the only public HTML write target.
            if path.name == "katalog.html":
                continue
            result[str(path)] = sha256(read_bytes(path))
    return result


def patch_eta_source(source: str) -> str:
    if SOURCE_MARKER in source:
        validate_source(source)
        return source
    replacements = (
        ('"' + RU_DUPLICATE + '",', '"",'),
        ('"' + UK_DUPLICATE + '",', '"",'),
        ('"' + RU_UNKNOWN_OLD + '",', '"' + RU_UNKNOWN_NEW + '",'),
        ('"' + UK_UNKNOWN_OLD + '",', '"' + UK_UNKNOWN_NEW + '",'),
    )
    for old, new in replacements:
        if source.count(old) != 1:
            raise Blocked("SOURCE_EXPECTED_LITERAL_COUNT:" + old[:36])
        source = source.replace(old, new, 1)

    start = source.find("def _ua068_ensure_catalog")
    end = source.find("def _ua068_card_errors", start)
    if start < 0 or end < 0:
        raise Blocked("SOURCE_CATALOG_FUNCTION_BOUNDARY")
    chunk = source[start:end]
    terminator = "</style>\"\"\""
    if chunk.count(terminator) != 1:
        raise Blocked("SOURCE_CATALOG_STYLE_BOUNDARY")
    chunk = chunk.replace(terminator, SOURCE_STYLE_OVERRIDE + terminator, 1)
    source = source[:start] + chunk + source[end:]
    insert = source.find("\n", source.find("# UA-CARDS-FERRY-VIN-001-V1.1-PERMANENT"))
    if insert < 0:
        raise Blocked("SOURCE_TASK068_MARKER_MISSING")
    source = source[: insert + 1] + SOURCE_MARKER + "\n" + source[insert + 1 :]
    validate_source(source)
    return source


def validate_source(source: str) -> None:
    if source.count(SOURCE_MARKER) != 1:
        raise Blocked("SOURCE_MARKER_COUNT")
    if source.count(STYLE_MARKER) != 1:
        raise Blocked("SOURCE_STYLE_MARKER_COUNT")
    if RU_DUPLICATE in source or UK_DUPLICATE in source:
        raise Blocked("SOURCE_DUPLICATE_TEXT_REMAINS")
    if RU_UNKNOWN_OLD in source or UK_UNKNOWN_OLD in source:
        raise Blocked("SOURCE_UNKNOWN_TEXT_REMAINS")
    if source.count('"' + RU_UNKNOWN_NEW + '",') != 1:
        raise Blocked("SOURCE_RU_UNKNOWN_INVALID")
    if source.count('"' + UK_UNKNOWN_NEW + '",') != 1:
        raise Blocked("SOURCE_UK_UNKNOWN_INVALID")
    compile(source, "production-generator.py", "exec")


def strip_task074_style(source: str) -> str:
    return re.sub(
        r'<style\b[^>]*id=["\']ua-catalog-card-unify-002-style["\'][^>]*>.*?</style\s*>',
        "", source, flags=re.I | re.S,
    )


def patch_catalog_block(block: str) -> str:
    block = block.replace(RU_DUPLICATE, "").replace(UK_DUPLICATE, "")
    block = block.replace(RU_UNKNOWN_OLD, RU_UNKNOWN_NEW)
    block = block.replace(UK_UNKNOWN_OLD, UK_UNKNOWN_NEW)
    # Remove only whitespace made redundant inside the two language spans.
    block = re.sub(r"([.!?])\s{2,}", r"\1 ", block)
    return block


def patch_catalog(source: str) -> str:
    source = strip_task074_style(source)
    pattern = re.compile(re.escape(CAT_START) + r".*?" + re.escape(CAT_END), re.S)
    blocks = pattern.findall(source)
    if not blocks:
        raise Blocked("CATALOG_CANONICAL_BLOCKS_MISSING")
    source = pattern.sub(lambda match: patch_catalog_block(match.group(0)), source)
    head_end = source.lower().find("</head>")
    if head_end < 0:
        raise Blocked("CATALOG_HEAD_MISSING")
    source = source[:head_end] + CATALOG_STYLE + source[head_end:]
    validate_catalog(source)
    return source


def catalog_blocks(source: str) -> list[str]:
    return re.findall(re.escape(CAT_START) + r".*?" + re.escape(CAT_END), source, re.S)


def ferry_status_present(source: str) -> bool:
    decoded = html_lib.unescape(source)
    for match in re.finditer(r"status-pill", decoded, flags=re.I):
        # Bound the check to the current card, while accepting div/span/custom
        # markup and route arrows represented as literal or HTML entities.
        card_end = decoded.find("</article", match.start())
        if card_end < 0:
            card_end = min(len(decoded), match.start() + 1800)
        context = decoded[match.start():card_end]
        if all(term in context for term in ("На пароме", "Маршрут", "Корея", "Грузия")):
            return True
    return False


def validate_catalog(source: str) -> dict[str, Any]:
    if source.count(STYLE_MARKER) != 1:
        raise Blocked("CATALOG_STYLE_MARKER_COUNT")
    blocks = catalog_blocks(source)
    identifiers = []
    for block in blocks:
        found = re.search(r'data-ua-card=["\'](UA-[0-9]{4,})["\']', block, re.I)
        if not found:
            raise Blocked("CATALOG_BLOCK_IDENTIFIER_MISSING")
        identifiers.append(found.group(1).upper())
        if RU_DUPLICATE in block or UK_DUPLICATE in block:
            raise Blocked("CATALOG_DUPLICATE_TEXT_REMAINS")
        if RU_UNKNOWN_OLD in block or UK_UNKNOWN_OLD in block:
            raise Blocked("CATALOG_UNKNOWN_TEXT_REMAINS")
    if len(identifiers) != len(set(identifiers)):
        raise Blocked("CATALOG_DUPLICATE_CARD_BLOCK")
    if "UA-0009" not in identifiers:
        raise Blocked("CATALOG_UA0009_MISSING")
    # The upper stage pill remains the only ferry/route indication.
    if not ferry_status_present(source):
        raise Blocked("CATALOG_ROUTE_STATUS_MISSING")
    return {"card_count": len(identifiers), "identifiers": identifiers}


def semantic_catalog_without_task074(source: str) -> str:
    value = strip_task074_style(source)
    value = value.replace(RU_DUPLICATE, "").replace(UK_DUPLICATE, "")
    value = value.replace(RU_UNKNOWN_OLD, RU_UNKNOWN_NEW).replace(UK_UNKNOWN_OLD, UK_UNKNOWN_NEW)
    value = re.sub(r"([.!?])\s{2,}", r"\1 ", value)
    return value


def source_snapshot() -> dict[str, dict[str, Any]]:
    result = {}
    for path in SOURCE_PATHS:
        data = read_bytes(path)
        result[str(path)] = {"sha256": sha256(data), "bytes": len(data), "marker": SOURCE_MARKER in data.decode()}
    return result


def catalog_snapshot() -> dict[str, dict[str, Any]]:
    result = {}
    for path in CATALOG_PATHS:
        data = read_bytes(path)
        source = data.decode("utf-8")
        identifiers = []
        for block in catalog_blocks(source):
            found = re.search(r'data-ua-card=["\'](UA-[0-9]{4,})["\']', block, re.I)
            if found:
                identifiers.append(found.group(1).upper())
        result[str(path)] = {
            "sha256": sha256(data),
            "bytes": len(data),
            "duplicate_ru": source.count(RU_DUPLICATE),
            "duplicate_uk": source.count(UK_DUPLICATE),
            "unknown_old_ru": source.count(RU_UNKNOWN_OLD),
            "unknown_old_uk": source.count(UK_UNKNOWN_OLD),
            "style_marker": source.count(STYLE_MARKER),
            "canonical_blocks": len(catalog_blocks(source)),
            "canonical_identifiers": identifiers,
            "ua0009": "UA-0009" in source,
            "ferry_status": ferry_status_present(source),
        }
    return result


def backup(paths: list[pathlib.Path]) -> pathlib.Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = BACKUP_PARENT / (stamp + "-" + hashlib.sha256(os.urandom(32)).hexdigest()[:12])
    for path in paths:
        target = root / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return root


def restore(root: pathlib.Path, paths: list[pathlib.Path]) -> list[str]:
    changed = []
    for path in paths:
        saved = root / path.relative_to(ROOT)
        if not saved.is_file():
            raise Blocked("ROLLBACK_BACKUP_MISSING:" + str(saved))
        old = read_bytes(saved)
        if not path.exists() or read_bytes(path) != old:
            atomic_write(path, old, saved.stat().st_mode & 0o777)
            changed.append(str(path))
    return changed


def inspect_base() -> dict[str, Any]:
    db = db_snapshot()
    if db["quick_check"] != "ok" or db["count"] != 11 or not db["ua0009"]:
        raise Blocked("DATABASE_INVARIANT")
    sources = source_snapshot()
    for path, item in sources.items():
        if not item["marker"] and item["sha256"] != EXPECTED_BASE_SHA256[path]:
            raise Blocked("SOURCE_BASE_SHA_MISMATCH:" + pathlib.Path(path).name)
        if item["marker"]:
            validate_source(pathlib.Path(path).read_text(encoding="utf-8"))
    catalogs = catalog_snapshot()
    for path, item in catalogs.items():
        if item["canonical_blocks"] != 11 or not item["ua0009"] or not item["ferry_status"]:
            raise Blocked(
                "CATALOG_BASE_INVARIANT:" + pathlib.Path(path).name + ":"
                + json.dumps(item, ensure_ascii=False, sort_keys=True)
            )
    return {"database": db, "sources": sources, "catalogs": catalogs, "protected_pages": protected_pages_snapshot()}


def run_shadow() -> dict[str, Any]:
    before = inspect_base()
    candidate_sources = {}
    for path in SOURCE_PATHS:
        source = path.read_text(encoding="utf-8")
        candidate = patch_eta_source(source)
        candidate_sources[str(path)] = {"sha256": sha256(candidate.encode()), "changed": candidate != source}
    candidate_catalogs = {}
    for path in CATALOG_PATHS:
        source = path.read_text(encoding="utf-8")
        candidate = patch_catalog(source)
        # Outside the approved text removal + style layer, HTML is byte-identical.
        if semantic_catalog_without_task074(candidate) != semantic_catalog_without_task074(source):
            raise Blocked("CATALOG_UNEXPECTED_SEMANTIC_CHANGE:" + path.name)
        candidate_catalogs[str(path)] = {"sha256": sha256(candidate.encode()), **validate_catalog(candidate)}
    after = inspect_base()
    if before != after:
        raise Blocked("SHADOW_PRODUCTION_CHANGED")
    return {
        "contract_id": CONTRACT, "status": "PASS", "mode": "SHADOW",
        "production_write": False, "crm_db_write": False,
        "before": before, "candidate_sources": candidate_sources,
        "candidate_catalogs": candidate_catalogs,
    }


def run_install() -> dict[str, Any]:
    before = inspect_base()
    paths = SOURCE_PATHS + CATALOG_PATHS
    backup_root = backup(paths)
    changed: list[str] = []
    try:
        for path in SOURCE_PATHS:
            data = read_bytes(path)
            candidate = patch_eta_source(data.decode("utf-8")).encode()
            if candidate != data:
                atomic_write(path, candidate, path.stat().st_mode & 0o777)
                changed.append(str(path))
        for path in CATALOG_PATHS:
            data = read_bytes(path)
            old_source = data.decode("utf-8")
            candidate_source = patch_catalog(old_source)
            if semantic_catalog_without_task074(candidate_source) != semantic_catalog_without_task074(old_source):
                raise Blocked("CATALOG_UNEXPECTED_SEMANTIC_CHANGE:" + path.name)
            candidate = candidate_source.encode()
            if candidate != data:
                atomic_write(path, candidate, path.stat().st_mode & 0o777)
                changed.append(str(path))
        after = inspect_base()
        if before["database"] != after["database"]:
            raise Blocked("DATABASE_CHANGED")
        if before["protected_pages"] != after["protected_pages"]:
            raise Blocked("PROTECTED_CARD_PAGES_CHANGED")
        for item in after["catalogs"].values():
            if any(item[key] for key in ("duplicate_ru", "duplicate_uk", "unknown_old_ru", "unknown_old_uk")):
                raise Blocked("CATALOG_DUPLICATE_TEXT_AFTER")
            if item["style_marker"] != 1:
                raise Blocked("CATALOG_STYLE_AFTER")
        return {
            "contract_id": CONTRACT, "status": "PASS", "mode": "INSTALL",
            "production_write": True, "crm_db_write": False,
            "backup_root": str(backup_root), "changed_paths": changed,
            "before": before, "after": after,
        }
    except Exception:
        restore(backup_root, paths)
        raise


def run_rollback() -> dict[str, Any]:
    receipt = json.loads(RECEIPTS["install"].read_text(encoding="utf-8"))
    backup_root = pathlib.Path(str(receipt.get("backup_root") or ""))
    if BACKUP_PARENT not in backup_root.parents:
        raise Blocked("ROLLBACK_SCOPE_INVALID")
    changed = restore(backup_root, SOURCE_PATHS + CATALOG_PATHS)
    return {
        "contract_id": CONTRACT, "status": "PASS", "mode": "ROLLBACK",
        "production_write": True, "crm_db_write": False,
        "backup_root": str(backup_root), "restored": changed,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("shadow", "install", "rollback"))
    args = parser.parse_args()
    REMOTE_ROOT.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.touch(exist_ok=True)
    receipt = RECEIPTS[args.mode]
    value: dict[str, Any]
    with LOCK_PATH.open("r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            value = {"shadow": run_shadow, "install": run_install, "rollback": run_rollback}[args.mode]()
        except Exception as exc:
            value = {
                "contract_id": CONTRACT, "status": "FAIL", "mode": args.mode.upper(),
                "production_write": args.mode != "shadow", "crm_db_write": False,
                "errors": [type(exc).__name__ + ":" + str(exc)],
            }
        atomic_json(receipt, value)
    print(json.dumps({"status": value["status"], "mode": value["mode"], "errors": value.get("errors", [])}, ensure_ascii=False))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
