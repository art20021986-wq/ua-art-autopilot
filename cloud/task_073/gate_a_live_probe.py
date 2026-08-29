#!/usr/bin/env python3
"""TASK 073 live GET-only evidence collector.

The collector uses only PythonAnywhere Files API GET requests, public HTTP
GET requests and a local read-only copy of crm.db.  It never uploads,
deletes, starts a console, reloads a service or writes production data.
Full live source and database bytes stay in the temporary runner and are
never printed or committed.
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


CONTRACT = "CRM-UNIFIED-CATALOG-001-V1.0"
API = "https://www.pythonanywhere.com/api/v0/user/Carix/"
ROOT = "/home/Carix"
OUT = pathlib.Path("cloud/task_073/evidence/live_probe.json")
MAX_SOURCE = 6_000_000
MAX_DB = 128_000_000
MAX_PUBLIC = 8_000_000

REMOTE = {
    "cars_ui.py": (ROOT + "/cars_ui.py", True),
    "konteyner.py": (ROOT + "/konteyner.py", True),
    "cars_schema.py": (ROOT + "/cars_schema.py", True),
    "stranica.py": (ROOT + "/stranica.py", True),
    "yadro.py": (ROOT + "/yadro.py", True),
    "master_card.py": (ROOT + "/master_card.py", True),
    "db.py": (ROOT + "/db.py", True),
    "team_bot.py": (ROOT + "/team_bot.py", True),
    "start_safe.py": (ROOT + "/start_safe.py", True),
    "avtoperedacha.py": (ROOT + "/avtoperedacha.py", False),
    "catalog.py": (ROOT + "/catalog.py", False),
    "diagnostics.py": (ROOT + "/diagnostics.py", False),
    "seo_rehab_guard.py": (ROOT + "/seo_rehab_guard.py", False),
    "site_builder.py": (ROOT + "/site_builder.py", False),
    "www_wsgi.py": ("/var/www/www_uaart_com_ua_wsgi.py", False),
}
CRM_PATH = ROOT + "/crm.db"

NEEDLES = (
    "загружено в контейнер",
    "в пути",
    "sea_loaded",
    "sea_transit",
    "контейнер, даты и сроки",
    "cont_menu:",
    "car_setstage:",
    "показать в каталоге",
    "машина видна клиентам в каталоге",
    "seo068_diagnostic_target_missing",
    "diagnostic_target_missing",
    "материалы диагностики пока не добавлены",
    "toggle_publish",
    "publish_pending",
    "avtoperedacha",
    "-diag.html",
)

WANTED = {
    "cars_ui.py": {
        "card_kb", "open_card", "stage_menu", "stage_set", "toggle_publish",
        "preview", "ad_screen", "register",
    },
    "konteyner.py": {"_ekran", "otkryt", "posle_statusa", "prinyat", "register"},
    "stranica.py": {"main", "build", "generate", "publish", "sobrat", "sdelat"},
    "yadro.py": {"main", "build", "generate", "publish", "sobrat", "sdelat"},
    "master_card.py": {"main", "build", "generate", "publish"},
    "team_bot.py": {"main", "start", "publish"},
}

PUBLIC_URLS = (
    "https://www.uaart.com.ua/video/index.html",
    "https://www.uaart.com.ua/video/katalog.html",
    "https://www.uaart.com.ua/video/UA-0009.html",
    "https://www.uaart.com.ua/video/UA-0009-diag.html",
    "https://www.uaart.com.ua/video/UA-0010.html",
    "https://www.uaart.com.ua/video/UA-0010-diag.html",
    "https://www.uaart.com.ua/video/UA-0011.html",
    "https://www.uaart.com.ua/video/UA-0011-diag.html",
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
    text = re.sub(r"(?<!\d)(?:\+?380|0)\d{9}(?!\d)", "<redacted-phone>", text)
    return text


def request_get(url: str, *, token: str | None = None, limit: int) -> tuple[int, bytes, str]:
    headers = {"User-Agent": "ua-art-task073-live-readonly-probe/1"}
    if token:
        headers["Authorization"] = "Token " + token
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
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


def read_remote(path: str, *, required: bool) -> bytes | None:
    token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
    if not token:
        raise RuntimeError("PYTHONANYWHERE_API_TOKEN_MISSING")
    url = API + "files/path" + urllib.parse.quote(path, safe="/")
    status, body, _ = request_get(
        url, token=token, limit=MAX_DB if path == CRM_PATH else MAX_SOURCE
    )
    if status == 404 and not required:
        return None
    if status != 200:
        raise RuntimeError("REMOTE_GET_%d:%s" % (status, pathlib.PurePosixPath(path).name))
    return body


def segment(source: str, node: ast.AST) -> str:
    lines = source.splitlines()
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def context_excerpt(source: str, lineno: int, radius: int = 7) -> str:
    lines = source.splitlines()
    start = max(0, lineno - radius - 1)
    end = min(len(lines), lineno + radius)
    return "\n".join(lines[start:end])


def inspect_python(name: str, path: str, required: bool) -> dict:
    data = read_remote(path, required=required)
    if data is None:
        return {"path": path, "present": False, "required": required}
    source = data.decode("utf-8")
    tree = ast.parse(source, path)
    lowered = source.casefold()
    needle_counts = {needle: lowered.count(needle) for needle in NEEDLES if needle in lowered}
    definitions = []
    inventory = []
    covered_lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = segment(source, node)
        relevant = node.name in WANTED.get(name, set())
        relevant = relevant or any(needle in body.casefold() for needle in NEEDLES)
        inventory.append({
            "name": node.name,
            "kind": type(node).__name__,
            "line": node.lineno,
            "end_line": node.end_lineno,
            "sha256": sha256(body.encode("utf-8")),
            "relevant": relevant,
        })
        if relevant:
            definitions.append({
                "name": node.name,
                "kind": type(node).__name__,
                "line": node.lineno,
                "end_line": node.end_lineno,
                "sha256": sha256(body.encode("utf-8")),
                "source": redact(body[:180_000]),
            })
            covered_lines.update(range(node.lineno, node.end_lineno + 1))

    excerpts = []
    for needle in NEEDLES:
        for match in re.finditer(re.escape(needle), lowered):
            line = source.count("\n", 0, match.start()) + 1
            if line in covered_lines:
                continue
            excerpts.append({
                "needle": needle,
                "line": line,
                "source": redact(context_excerpt(source, line)),
            })
            if len(excerpts) >= 40:
                break
        if len(excerpts) >= 40:
            break

    return {
        "path": path,
        "present": True,
        "required": required,
        "size": len(data),
        "sha256": sha256(data),
        "needle_counts": needle_counts,
        "definition_inventory": sorted(inventory, key=lambda item: (item["line"], item["name"])),
        "definitions": sorted(definitions, key=lambda item: (item["line"], item["name"])),
        "excerpts": excerpts,
    }


def safe_card(row: sqlite3.Row, columns: list[str]) -> dict:
    direct = {
        "id", "auto_number", "published", "publish_pending", "status", "stage",
        "sea_container", "sea_date_out", "days_to_kyiv", "eta_manual",
    }
    result = {key: row[key] for key in columns if key in direct}
    for key in (
        "diag_report", "diag_link", "diag_text", "condition_text", "description",
        "photos", "videos", "condition_photos", "condition_videos", "cover_photo",
    ):
        if key in columns:
            value = row[key]
            result[key + "_present"] = bool(value)
            result[key + "_length"] = len(str(value or ""))
    return result


def inspect_db() -> dict:
    data = read_remote(CRM_PATH, required=True)
    assert data is not None
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_path = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(data)
        connection = sqlite3.connect("file:%s?mode=ro" % temp_path, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA query_only=ON")
            quick = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            tables = [str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )]
            columns = [str(row[1]) for row in connection.execute("PRAGMA table_info(cars)")]
            rows = connection.execute("SELECT * FROM cars ORDER BY id").fetchall()
            ids = [str(row["auto_number"]) for row in rows if "auto_number" in columns]
            sanitized = {
                str(row["auto_number"]): safe_card(row, columns)
                for row in rows if "auto_number" in columns and row["auto_number"]
            }
            row_hashes = {
                str(row["auto_number"]): sha256(
                    json.dumps(dict(row), ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
                )
                for row in rows if "auto_number" in columns and row["auto_number"]
            }
        finally:
            connection.close()
    finally:
        temp_path.unlink(missing_ok=True)
    return {
        "sha256": sha256(data),
        "size": len(data),
        "quick_check": quick,
        "tables": tables,
        "cars_columns": columns,
        "cars_count": len(rows),
        "card_ids": ids,
        "unique_card_ids": len(ids) == len(set(ids)),
        "cards": sanitized,
        "row_hashes": row_hashes,
        "ua_0009_row_sha256": row_hashes.get("UA-0009"),
    }


def inspect_public(url: str) -> dict:
    status, body, effective = request_get(url, limit=MAX_PUBLIC)
    text = body.decode("utf-8", "replace")
    ids = re.findall(r"UA-\d{4}", text)
    counts = {identifier: ids.count(identifier) for identifier in sorted(set(ids))}
    return {
        "url": url,
        "status": status,
        "effective_url": effective,
        "redirected": effective.rstrip("/") != url.rstrip("/"),
        "size": len(body),
        "sha256": sha256(body),
        "card_id_counts": counts,
        "has_placeholder": "Материалы диагностики пока не добавлены." in text,
        "has_ua_0011": "UA-0011" in text,
        "has_ua_0010": "UA-0010" in text,
        "has_ua_0009": "UA-0009" in text,
    }


def main() -> int:
    evidence = {
        "contract": CONTRACT,
        "mode": "LIVE_GET_ONLY_PROBE",
        "status": "FAIL",
        "production_touched": False,
        "production_write_methods": [],
        "crm_db_write": False,
        "runtime_llm_tokens": 0,
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": {},
        "db": {},
        "public": {},
        "errors": [],
    }
    try:
        for name, (path, required) in REMOTE.items():
            try:
                evidence["files"][name] = inspect_python(name, path, required)
            except Exception as exc:
                if required:
                    raise
                evidence["files"][name] = {
                    "path": path,
                    "present": False,
                    "required": False,
                    "error": type(exc).__name__,
                }
        evidence["db"] = inspect_db()
        for url in PUBLIC_URLS:
            evidence["public"][url] = inspect_public(url)
        if evidence["db"].get("quick_check") != "ok":
            evidence["errors"].append("CRM_QUICK_CHECK_FAILED")
        if evidence["db"].get("cars_count") != 11:
            evidence["errors"].append("CRM_CARD_COUNT_NOT_11")
        if evidence["db"].get("card_ids") != ["UA-%04d" % n for n in range(1, 12)]:
            evidence["errors"].append("CRM_CARD_ID_SET_MISMATCH")
        evidence["status"] = "EVIDENCE_READY" if not evidence["errors"] else "EVIDENCE_WITH_GAPS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("TASK073_LIVE_GET_ONLY_PROBE_%s errors=%d" % (evidence["status"], len(evidence["errors"])))
    return 0 if evidence["status"] in {"EVIDENCE_READY", "EVIDENCE_WITH_GAPS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
