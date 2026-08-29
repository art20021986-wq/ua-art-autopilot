#!/usr/bin/env python3
"""Fresh GET-only audit for UA-0012/UA-0013 publication repair.

Reads the live PythonAnywhere source, the SQLite database (including an
optional WAL snapshot), generated pages, and the public site.  It never sends
POST/PUT/PATCH/DELETE requests and never changes production.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


CONTRACT = "UA-0012-UA-0013-PUBLISH-REPAIR-002-V1.0"
API = "https://www.pythonanywhere.com/api/v0/user/Carix/"
ROOT = "/home/Carix"
OUT = pathlib.Path("cloud/task_081_publish_repair/evidence/live_audit_v2.json")
REPORT = pathlib.Path("cloud/task_081_publish_repair/LIVE_AUDIT_V2.md")
AUTO_IDS = ("UA-0012", "UA-0013")
MAX_SOURCE = 8_000_000
MAX_DB = 160_000_000
MAX_PUBLIC = 10_000_000

REMOTE = {
    "cars_ui.py": ROOT + "/cars_ui.py",
    "publikaciya.py": ROOT + "/publikaciya.py",
    "stranica.py": ROOT + "/stranica.py",
    "master_card.py": ROOT + "/master_card.py",
    "yadro.py": ROOT + "/yadro.py",
    "cars_schema.py": ROOT + "/cars_schema.py",
    "db.py": ROOT + "/db.py",
    "start_safe.py": ROOT + "/start_safe.py",
}

WANTED = {
    "cars_ui.py": {"toggle_publish", "preview", "ad_screen", "set_field", "card_of"},
    "publikaciya.py": {"opublikovat", "sobrat_kartochku"},
    "stranica.py": {
        "sobrat_kartochku", "_ua_seo068_normalize", "_ua068_ensure_card",
        "_ua068_ensure_stage_diag", "_ua068_card_errors", "_ua068_catalog_errors",
    },
    "master_card.py": {"sobrat_kartochku", "build", "generate", "publish"},
    "yadro.py": {
        "karta_html", "katalog_html", "_ua_seo068_normalize", "_ua068_ensure_card",
        "_ua068_ensure_stage_diag", "_ua068_card_errors", "_ua068_catalog_errors",
    },
    "cars_schema.py": {"missing_required", "stage_of", "status_label"},
    "db.py": {"update_card_field", "connect", "Soedinenie"},
}

SIGNALS = (
    "SEO068_DIAGNOSTIC_TARGET_MISSING",
    "DIAGNOSTIC_TARGET_MISSING",
    "Материалы диагностики",
    "Машина видна клиентам в каталоге",
    "Публикация отменена",
    "publish_pending",
    "-diag.html",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def redact(text: str) -> str:
    text = re.sub(r"\b\d{8,}:[A-Za-z0-9_-]{20,}\b", "<redacted-token>", text)
    text = re.sub(
        r"(?i)((?:token|api[_-]?key|password|secret)\s*=\s*)['\"][^'\"]{8,}['\"]",
        r"\1'<redacted-secret>'",
        text,
    )
    return text


def request_get(url: str, *, token: str | None = None, limit: int) -> tuple[int, bytes, str]:
    headers = {"User-Agent": "ua-art-task081-live-readonly-v2/1"}
    if token:
        headers["Authorization"] = "Token " + token
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            body = response.read(limit + 1)
            status = int(response.status)
            effective = response.geturl()
    except urllib.error.HTTPError as exc:
        body = exc.read(limit + 1)
        status = int(exc.code)
        effective = exc.geturl()
    if len(body) > limit:
        raise RuntimeError("RESPONSE_TOO_LARGE:" + urllib.parse.urlsplit(url).path)
    return status, body, effective


def read_remote(path: str, *, required: bool = True, limit: int = MAX_SOURCE) -> bytes | None:
    token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
    if not token:
        raise RuntimeError("PYTHONANYWHERE_API_TOKEN_MISSING")
    url = API + "files/path" + urllib.parse.quote(path, safe="/")
    status, body, _ = request_get(url, token=token, limit=limit)
    if status == 404 and not required:
        return None
    if status != 200:
        raise RuntimeError("REMOTE_GET_%d:%s" % (status, pathlib.PurePosixPath(path).name))
    return body


def node_source(source: str, node: ast.AST) -> str:
    lines = source.splitlines()
    return "\n".join(lines[node.lineno - 1 : node.end_lineno])


def inspect_python(name: str, path: str) -> dict:
    data = read_remote(path)
    assert data is not None
    source = data.decode("utf-8")
    tree = ast.parse(source, path)
    wanted = WANTED.get(name, set())
    definitions = []
    inventory = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = node_source(source, node)
        inventory.append({
            "name": node.name,
            "kind": type(node).__name__,
            "line": node.lineno,
            "end_line": node.end_lineno,
            "sha256": sha256(body.encode("utf-8")),
        })
        relevant = node.name in wanted or any(signal.casefold() in body.casefold() for signal in SIGNALS)
        if relevant:
            definitions.append({
                "name": node.name,
                "kind": type(node).__name__,
                "line": node.lineno,
                "end_line": node.end_lineno,
                "sha256": sha256(body.encode("utf-8")),
                "source": redact(body[:240_000]),
            })

    assignments = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        body = node_source(source, node)
        names = []
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                names.append(target.id)
        if any(name in {"STATUSES", "STAGES", "REQUIRED", "LABELS_ALL"} for name in names):
            assignments.append({"names": names, "source": redact(body), "sha256": sha256(body.encode())})

    result = {
        "path": path,
        "size": len(data),
        "sha256": sha256(data),
        "definitions": sorted(definitions, key=lambda item: (item["line"], item["name"])),
        "definition_inventory": sorted(inventory, key=lambda item: (item["line"], item["name"])),
        "assignments": assignments,
        "signal_counts": {s: source.casefold().count(s.casefold()) for s in SIGNALS},
    }
    if name in {"publikaciya.py", "stranica.py", "master_card.py", "yadro.py"}:
        result["tail_source"] = redact("\n".join(source.splitlines()[-900:]))[-180_000:]
    return result


LONG_FIELDS = {
    "photos", "videos", "docs", "condition_text", "condition_photos",
    "condition_videos", "diag_report", "diag_link", "description", "history",
    "price_history", "hidden_photos", "diag_text",
}


def safe_row(row: sqlite3.Row) -> dict:
    result = {}
    for key in row.keys():
        value = row[key]
        if isinstance(value, bytes):
            result[key] = {"type": "bytes", "length": len(value), "sha256": sha256(value)}
        elif key in LONG_FIELDS or (isinstance(value, str) and len(value) > 600):
            encoded = str(value or "").encode("utf-8")
            result[key] = {
                "present": bool(value),
                "length": len(str(value or "")),
                "sha256": sha256(encoded),
            }
        else:
            result[key] = value
    return result


def inspect_media(connection: sqlite3.Connection, card_rows: dict[str, sqlite3.Row]) -> dict:
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "media" not in tables:
        return {"present": False}
    columns = [str(row[1]) for row in connection.execute("PRAGMA table_info(media)")]
    output = {"present": True, "columns": columns, "cards": {}}
    for auto_id, card in card_rows.items():
        matches = []
        if "car_id" in columns:
            matches = connection.execute("SELECT * FROM media WHERE car_id=?", (card["id"],)).fetchall()
        elif "card_id" in columns:
            matches = connection.execute("SELECT * FROM media WHERE card_id=?", (card["id"],)).fetchall()
        elif "auto_number" in columns:
            matches = connection.execute("SELECT * FROM media WHERE auto_number=?", (auto_id,)).fetchall()
        kinds = {}
        for item in matches:
            kind = "unknown"
            for candidate in ("kind", "type", "media_type", "category"):
                if candidate in columns and item[candidate] is not None:
                    kind = str(item[candidate])
                    break
            kinds[kind] = kinds.get(kind, 0) + 1
        output["cards"][auto_id] = {"count": len(matches), "by_kind": kinds}
    return output


def inspect_db() -> dict:
    db_data = read_remote(ROOT + "/crm.db", limit=MAX_DB)
    assert db_data is not None
    wal_data = read_remote(ROOT + "/crm.db-wal", required=False, limit=MAX_DB)
    shm_data = read_remote(ROOT + "/crm.db-shm", required=False, limit=8_000_000)
    with tempfile.TemporaryDirectory() as directory:
        base = pathlib.Path(directory) / "crm.db"
        base.write_bytes(db_data)
        if wal_data:
            (base.parent / "crm.db-wal").write_bytes(wal_data)
        if shm_data:
            (base.parent / "crm.db-shm").write_bytes(shm_data)
        connection = sqlite3.connect("file:%s?mode=ro" % base, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only=ON")
            quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            columns = [str(row[1]) for row in connection.execute("PRAGMA table_info(cars)")]
            selected_rows = connection.execute(
                "SELECT * FROM cars WHERE auto_number IN (?,?) ORDER BY auto_number", AUTO_IDS
            ).fetchall()
            card_rows = {str(row["auto_number"]): row for row in selected_rows}
            all_ids = [str(row[0]) for row in connection.execute(
                "SELECT auto_number FROM cars WHERE auto_number IS NOT NULL ORDER BY auto_number"
            )]
            media = inspect_media(connection, card_rows)
            result = {
                "quick_check": quick,
                "db_sha256": sha256(db_data),
                "db_bytes": len(db_data),
                "wal_present": bool(wal_data),
                "wal_sha256": sha256(wal_data) if wal_data else None,
                "cars_columns": columns,
                "cars_count": len(all_ids),
                "card_ids": all_ids,
                "cards": {key: safe_row(row) for key, row in card_rows.items()},
                "media": media,
            }
        finally:
            connection.close()
    return result


def inspect_remote_page(path: str) -> dict:
    data = read_remote(path, required=False, limit=MAX_PUBLIC)
    if data is None:
        return {"present": False, "path": path}
    text = data.decode("utf-8", "replace")
    return {
        "present": True,
        "path": path,
        "bytes": len(data),
        "sha256": sha256(data),
        "card_counts": {auto_id: text.count(auto_id) for auto_id in AUTO_IDS},
        "has_diag_placeholder": "Материалы диагностики" in text,
    }


def inspect_public(url: str) -> dict:
    status, body, effective = request_get(url, limit=MAX_PUBLIC)
    text = body.decode("utf-8", "replace")
    return {
        "url": url,
        "status": status,
        "effective_url": effective,
        "redirected": effective.rstrip("/") != url.rstrip("/"),
        "bytes": len(body),
        "sha256": sha256(body),
        "card_counts": {auto_id: text.count(auto_id) for auto_id in AUTO_IDS},
        "has_diag_placeholder": "Материалы диагностики" in text,
    }


def main() -> int:
    evidence = {
        "contract": CONTRACT,
        "mode": "LIVE_GET_ONLY",
        "status": "FAIL",
        "production_touched": False,
        "http_methods": ["GET"],
        "crm_write": False,
        "site_write": False,
        "restart": False,
        "runtime_llm_tokens": 0,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": {},
        "db": {},
        "remote_pages": {},
        "public": {},
        "errors": [],
    }
    try:
        for name, path in REMOTE.items():
            evidence["files"][name] = inspect_python(name, path)
        evidence["db"] = inspect_db()
        for root in (ROOT + "/mysite/video", ROOT + "/mysite/site"):
            for filename in (
                "katalog.html",
                "UA-0012.html", "UA-0012-diag.html",
                "UA-0013.html", "UA-0013-diag.html",
            ):
                path = root + "/" + filename
                evidence["remote_pages"][path] = inspect_remote_page(path)
        for prefix in ("/video", "/site"):
            for filename in (
                "katalog.html",
                "UA-0012.html", "UA-0012-diag.html",
                "UA-0013.html", "UA-0013-diag.html",
            ):
                url = "https://www.uaart.com.ua" + prefix + "/" + filename
                evidence["public"][url] = inspect_public(url)
        if evidence["db"].get("quick_check") != "ok":
            evidence["errors"].append("CRM_QUICK_CHECK_FAILED")
        missing = [auto_id for auto_id in AUTO_IDS if auto_id not in evidence["db"].get("cards", {})]
        if missing:
            evidence["errors"].append("DB_ROWS_MISSING:" + ",".join(missing))
        evidence["status"] = "PASS_GET_ONLY" if not evidence["errors"] else "FAIL"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = evidence.get("db", {}).get("cards", {})
    REPORT.write_text("\n".join([
        "# TASK 081 live audit v2 — UA-0012 / UA-0013",
        "",
        "Status: **%s**" % evidence["status"],
        "",
        "- Production touched: NO",
        "- UA-0012 DB row: %s" % ("FOUND" if "UA-0012" in rows else "MISSING"),
        "- UA-0013 DB row: %s" % ("FOUND" if "UA-0013" in rows else "MISSING"),
        "- Errors: %s" % (", ".join(evidence["errors"]) or "NONE"),
        "",
    ]), encoding="utf-8")
    print(json.dumps({"status": evidence["status"], "errors": evidence["errors"]}, ensure_ascii=False))
    return 0 if evidence["status"] == "PASS_GET_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
