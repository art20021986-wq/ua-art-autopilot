#!/usr/bin/env python3
"""Real GET-only Gate A audit for TASK 076.

The script downloads a point-in-time backup through the PythonAnywhere Files
API, opens only the local copy of crm.db with query_only enabled, and inspects
the live/public ETA surfaces.  It never sends a mutating HTTP method and never
writes to PythonAnywhere or production.
"""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import html
import json
import os
import pathlib
import re
import sqlite3
import tempfile
import urllib.error
import urllib.parse
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence" / "gate_a_live.json"
REPORT = ROOT / "GATE_A_LIVE_REPORT.md"
API = "https://www.pythonanywhere.com/api/v0/user/Carix/files/path"
PUBLIC = "https://www.uaart.com.ua"
REMOTE_ROOT = "/home/Carix"
CONTRACT_ID = "CRM-ETA-SYNC-GUARD-004-V1.0"
TARGETS = ("UA-0009", "UA-0010", "UA-0011")
MAX_FILE = 80_000_000


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_remote(path: str, missing: bool = False, limit: int = MAX_FILE) -> bytes | None:
    token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
    if not token:
        raise RuntimeError("PYTHONANYWHERE_API_TOKEN_MISSING")
    request = urllib.request.Request(
        API + urllib.parse.quote(path, safe="/"),
        method="GET",
        headers={"Authorization": "Token " + token,
                 "User-Agent": "ua-art-task076-get-only/2"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        if missing and exc.code == 404:
            return None
        raise
    if len(data) > limit:
        raise RuntimeError("REMOTE_FILE_TOO_LARGE:" + pathlib.PurePosixPath(path).name)
    return data


def get_public(url: str, missing: bool = False, limit: int = 4_000_000) -> bytes | None:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "ua-art-task076-public-audit/2", "Accept": "text/html"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        if missing and exc.code == 404:
            return None
        raise
    if len(data) > limit:
        raise RuntimeError("PUBLIC_PAGE_TOO_LARGE")
    return data


def manifest(path: str, data: bytes | None) -> dict:
    if data is None:
        return {"path": path, "missing": True}
    return {"path": path, "bytes": len(data), "sha256": digest(data)}


def parse_iso_date(value) -> dt.date | None:
    text = str(value or "").strip()[:10]
    try:
        return dt.date.fromisoformat(text)
    except ValueError:
        return None


def open_snapshot(db_bytes: bytes, wal_bytes: bytes | None):
    directory = tempfile.TemporaryDirectory(prefix="task076-gate-a-")
    db_path = pathlib.Path(directory.name) / "crm.db"
    db_path.write_bytes(db_bytes)
    if wal_bytes:
        pathlib.Path(str(db_path) + "-wal").write_bytes(wal_bytes)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return directory, connection


def database_evidence(db_bytes: bytes, wal_bytes: bytes | None) -> dict:
    directory, connection = open_snapshot(db_bytes, wal_bytes)
    try:
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        columns = [row[1] for row in connection.execute("PRAGMA table_info(cars)")]
        required = {"id", "auto_number", "status", "days_to_kyiv", "eta_manual", "updated_at"}
        missing = sorted(required - set(columns))
        if missing:
            raise RuntimeError("CRM_COLUMNS_MISSING:" + ",".join(missing))
        optional = [name for name in ("description", "published") if name in columns]
        selected = ["id", "auto_number", "status", "days_to_kyiv", "eta_manual", "updated_at"] + optional
        placeholders = ",".join("?" for _ in TARGETS)
        sql = "SELECT %s FROM cars WHERE auto_number IN (%s) ORDER BY auto_number" % (
            ",".join(selected), placeholders)
        raw_rows = [dict(row) for row in connection.execute(sql, TARGETS)]
        if [row["auto_number"] for row in raw_rows] != list(TARGETS):
            raise RuntimeError("TARGET_ROWS_MISSING")
        today = dt.datetime.now(dt.timezone.utc).date()
        rows = []
        ids = []
        for raw in raw_rows:
            ids.append(int(raw["id"]))
            eta = parse_iso_date(raw.get("eta_manual"))
            try:
                days = int(raw.get("days_to_kyiv"))
            except (TypeError, ValueError):
                days = None
            expected = today + dt.timedelta(days=days) if days is not None else None
            description = str(raw.get("description") or "")
            rows.append({
                "id": int(raw["id"]),
                "auto_number": raw["auto_number"],
                "status": raw.get("status"),
                "days_to_kyiv": days,
                "eta_manual": eta.isoformat() if eta else raw.get("eta_manual"),
                "updated_at": raw.get("updated_at"),
                "published": raw.get("published"),
                "pair_consistent_today": bool(eta and expected and eta == expected),
                "desired_30_match": bool(days == 30 and eta == today + dt.timedelta(days=30)),
                "description_sha256": digest(description.encode("utf-8")),
                "description_date_contexts": date_contexts(description),
            })
        audit_rows = []
        audit_columns = [row[1] for row in connection.execute("PRAGMA table_info(audit)")]
        needed = {"entity_id", "field", "old_value", "new_value", "created_at"}
        if needed.issubset(audit_columns):
            placeholders = ",".join("?" for _ in ids)
            audit_sql = (
                "SELECT entity_id, action, field, old_value, new_value, created_at "
                "FROM audit WHERE entity_type='cars' AND entity_id IN (%s) "
                "AND field IN ('status','days_to_kyiv','eta_manual') "
                "ORDER BY id DESC LIMIT 60" % placeholders
            )
            for row in connection.execute(audit_sql, ids):
                audit_rows.append(dict(row))
        return {
            "quick_check": quick,
            "journal_mode_local_copy": connection.execute("PRAGMA journal_mode").fetchone()[0],
            "schema_columns": columns,
            "rows": rows,
            "audit_tail": audit_rows,
        }
    finally:
        connection.close()
        directory.cleanup()


DATE_PATTERNS = (
    re.compile(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b"),
    re.compile(r"\b20\d{2}-\d{2}-\d{2}\b"),
    re.compile(
        r"\b\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|"
        r"сентября|октября|ноября|декабря|січня|лютого|березня|квітня|травня|"
        r"червня|липня|серпня|вересня|жовтня|листопада|грудня)(?:\s+20\d{2})?\b",
        re.I,
    ),
)


def date_contexts(value: str, limit: int = 12) -> list[str]:
    result = []
    compact = re.sub(r"\s+", " ", html.unescape(value))
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(compact):
            start, end = max(match.start() - 90, 0), min(match.end() + 90, len(compact))
            context = compact[start:end]
            if context not in result:
                result.append(context)
            if len(result) >= limit:
                return result
    return result


def page_evidence(data: bytes | None, path_or_url: str) -> dict:
    if data is None:
        return {"path_or_url": path_or_url, "missing": True}
    source = data.decode("utf-8", "replace")
    visible = re.sub(r"<script\b.*?</script\s*>", " ", source, flags=re.I | re.S)
    visible = re.sub(r"<style\b.*?</style\s*>", " ", visible, flags=re.I | re.S)
    visible = re.sub(r"<[^>]+>", " ", visible)
    visible = re.sub(r"\s+", " ", html.unescape(visible))
    days = sorted(set(int(x) for x in re.findall(r"(?<!\d)(\d{1,3})\s*(?:дн|день|дня|дней|днів)", visible, re.I)))
    return {
        "path_or_url": path_or_url,
        "bytes": len(data),
        "sha256": digest(data),
        "day_values": days,
        "date_contexts": date_contexts(visible),
        "updated_contexts": [m.group(0) for m in re.finditer(
            r".{0,80}(?:обновлен[ао]?|оновлен[ао]?|updated).{0,100}", visible, re.I)][:4],
    }


def function_source(source: str, node: ast.AST) -> str:
    lines = source.splitlines(keepends=True)
    return "".join(lines[node.lineno - 1:node.end_lineno]).rstrip("\r\n")


def source_evidence(filename: str, data: bytes) -> dict:
    source = data.decode("utf-8", "replace")
    result = {"bytes": len(data), "sha256": digest(data), "definitions": []}
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        result["parse_error"] = str(exc)
        return result
    terms = ("eta_manual", "days_to_kyiv", "eta_days", "opublikovat", "description", "updated_at")
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        raw = function_source(source, node)
        if not any(term in raw for term in terms):
            continue
        result["definitions"].append({
            "name": node.name,
            "kind": type(node).__name__,
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "sha256": digest(raw.encode("utf-8")),
            "source": raw,
        })
    return result


def diagnose(database: dict, sources: dict, remote_pages: dict, public_pages: dict) -> dict:
    cars_ui_defs = {d["name"]: d["source"] for d in sources.get("cars_ui.py", {}).get("definitions", [])}
    apply_value = cars_ui_defs.get("apply_value", "")
    split_writes = (
        apply_value.count('set_field(card_id, "eta_manual"') == 1
        and apply_value.count('set_field(card_id, "days_to_kyiv"') == 1
    )
    returns_before_publish = bool(apply_value and "opublik" not in apply_value and "publish" not in apply_value)
    by_id = {row["auto_number"]: row for row in database["rows"]}
    findings = []
    for identifier in TARGETS:
        row = by_id[identifier]
        if not row["desired_30_match"]:
            findings.append(identifier + ":CRM_ETA_NOT_30")
        if not row["pair_consistent_today"]:
            findings.append(identifier + ":CRM_ETA_PAIR_CONFLICT")
        expected = str(row.get("eta_manual") or "")
        for surface in ("video", "site"):
            page = remote_pages[surface + ":" + identifier]
            contexts = " ".join(page.get("date_contexts") or [])
            if expected and expected not in contexts:
                # HTML normally renders a localized date, so this is a signal only;
                # detailed contexts remain in the evidence for controller review.
                localized = ""
                parsed = parse_iso_date(expected)
                if parsed:
                    localized = parsed.strftime("%d.%m.%Y")
                if localized and localized not in contexts:
                    findings.append(identifier + ":" + surface.upper() + "_DATE_NOT_CANONICAL")
        public = public_pages.get("video:" + identifier) or {}
        if public.get("missing"):
            findings.append(identifier + ":PUBLIC_VIDEO_MISSING")
    return {
        "split_eta_writes_in_current_cars_ui": split_writes,
        "crm_success_path_has_no_publisher_verification": returns_before_publish,
        "findings": sorted(set(findings)),
        "root_cause_confirmed": bool(split_writes and returns_before_publish),
    }


def write_json(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    evidence = {
        "task_id": "task_076",
        "contract_id": CONTRACT_ID,
        "status": "FAIL",
        "mode": "BACKUP_GET_ONLY_LIVE_AUDIT",
        "production_touched": False,
        "crm_write": False,
        "site_write": False,
        "pythonanywhere_methods": ["GET"],
        "public_methods": ["GET"],
        "runtime_llm_tokens": 0,
        "started_at_utc": utc_now(),
        "errors": [],
    }
    try:
        paths = {
            "crm.db": REMOTE_ROOT + "/crm.db",
            "crm.db-wal": REMOTE_ROOT + "/crm.db-wal",
            "db.py": REMOTE_ROOT + "/db.py",
            "cars_ui.py": REMOTE_ROOT + "/cars_ui.py",
            "konteyner.py": REMOTE_ROOT + "/konteyner.py",
            "stranica.py": REMOTE_ROOT + "/stranica.py",
            "master_card.py": REMOTE_ROOT + "/master_card.py",
            "yadro.py": REMOTE_ROOT + "/yadro.py",
            "publikaciya.py": REMOTE_ROOT + "/publikaciya.py",
            "video/katalog.html": REMOTE_ROOT + "/video/katalog.html",
            "site/katalog.html": REMOTE_ROOT + "/site/katalog.html",
        }
        blobs = {}
        for name, path in paths.items():
            blobs[name] = get_remote(path, missing=(name == "crm.db-wal"))
        evidence["backup"] = {
            "captured_before_analysis": True,
            "files": {name: manifest(paths[name], data) for name, data in blobs.items()},
        }
        evidence["database"] = database_evidence(blobs["crm.db"], blobs["crm.db-wal"])
        if evidence["database"]["quick_check"] != "ok":
            raise RuntimeError("CRM_QUICK_CHECK_FAILED")

        source_names = ("db.py", "cars_ui.py", "konteyner.py", "stranica.py", "master_card.py", "yadro.py", "publikaciya.py")
        evidence["sources"] = {name: source_evidence(name, blobs[name]) for name in source_names}

        remote_pages = {}
        public_pages = {}
        for surface in ("video", "site"):
            for identifier in TARGETS:
                key = surface + ":" + identifier
                remote_path = "%s/%s/%s.html" % (REMOTE_ROOT, surface, identifier)
                remote_data = get_remote(remote_path, missing=True, limit=4_000_000)
                remote_pages[key] = page_evidence(remote_data, remote_path)
                public_url = "%s/%s/%s.html" % (PUBLIC, surface, identifier)
                public_data = get_public(public_url, missing=True)
                public_pages[key] = page_evidence(public_data, public_url)
        evidence["remote_pages"] = remote_pages
        evidence["public_pages"] = public_pages
        evidence["diagnosis"] = diagnose(evidence["database"], evidence["sources"], remote_pages, public_pages)
        if not evidence["diagnosis"]["root_cause_confirmed"]:
            raise RuntimeError("ROOT_CAUSE_GUARDS_NOT_CONFIRMED")
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
    evidence["finished_at_utc"] = utc_now()
    write_json(EVIDENCE, evidence)

    lines = [
        "# CRM-ETA-SYNC-GUARD-004 v1.0 — Gate A live audit",
        "",
        "Status: **%s**" % evidence["status"],
        "",
        "- Production touched: **NO**",
        "- PythonAnywhere/public HTTP methods: **GET only**",
        "- CRM/site/media writes: **NO**",
    ]
    if evidence["status"] == "PASS":
        diagnosis = evidence["diagnosis"]
        lines.extend([
            "- Backup manifest + SQLite quick_check: **PASS**",
            "- Existing UA-0009/0010/0011 rows and public surfaces captured: **PASS**",
            "- Split ETA database writes found in current cars_ui.py: **%s**" % ("YES" if diagnosis["split_eta_writes_in_current_cars_ui"] else "NO"),
            "- CRM reports success without verified publisher completion: **%s**" % ("YES" if diagnosis["crm_success_path_has_no_publisher_verification"] else "NO"),
            "- Findings: `%s`" % (", ".join(diagnosis["findings"]) or "none"),
            "",
            "Gate A is read-only. Production remains locked pending a separate exact owner command.",
        ])
    else:
        lines.extend(["- Errors: `%s`" % "; ".join(evidence["errors"]), "", "Production remains locked."])
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("TASK076_GATE_A_" + evidence["status"])
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
