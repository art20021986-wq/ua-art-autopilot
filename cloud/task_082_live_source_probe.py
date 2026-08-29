#!/usr/bin/env python3
"""TASK 082 GET-only live CRM title renderer and sanitized VIN4 audit."""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import tempfile
import urllib.parse
import urllib.request

API = "https://www.pythonanywhere.com/api/v0/user/Carix/files/path"
ROOT = "/home/Carix"
OUT = pathlib.Path(__file__).resolve().parent / "task_082_probe" / "evidence.json"
TARGETS = {"render", "card_kb", "open_card", "cars_list"}
MAX = 80_000_000


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(value: bytes):
    return hashlib.sha256(value).hexdigest()


def get(path: str) -> bytes:
    if not path.startswith(ROOT + "/"):
        raise RuntimeError("PATH_SCOPE")
    token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TOKEN_MISSING")
    request = urllib.request.Request(
        API + urllib.parse.quote(path, safe="/"),
        method="GET",
        headers={"Authorization": "Token " + token, "User-Agent": "ua-art-task082-probe/1"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read(MAX + 1)
    if len(data) > MAX:
        raise RuntimeError("FILE_TOO_LARGE")
    return data


def clean(source: str) -> str:
    source = re.sub(r"\b\d{7,12}:[A-Za-z0-9_-]{20,}\b", "[REDACTED_BOT_TOKEN]", source)
    source = re.sub(r"(?i)(token\s*[=:]\s*[\"'])[^\"']+", r"\1[REDACTED]", source)
    source = re.sub(r"sk-[A-Za-z0-9_-]{16,}", "[REDACTED_KEY]", source)
    return source


def function_sources(source: str):
    tree = ast.parse(source, filename="cars_ui.py")
    lines = source.splitlines(keepends=True)
    result = {}
    header_defs = {}
    inventory = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        segment = "".join(lines[node.lineno - 1:node.end_lineno])
        digest = hashlib.sha256(segment.encode()).hexdigest()
        inventory.append({"name": node.name, "line": node.lineno, "end_line": node.end_lineno, "sha256": digest})
        if "auto_number" in segment or "без названия" in segment:
            header_defs[node.name] = {
                "line": node.lineno,
                "end_line": node.end_lineno,
                "sha256": digest,
                "source": clean(segment),
            }
        if node.name in TARGETS:
            result[node.name] = {
                "line": node.lineno,
                "end_line": node.end_lineno,
                "sha256": digest,
                "source": clean(segment),
            }
    missing = TARGETS - set(result)
    if missing:
        raise RuntimeError("TARGETS_MISSING:" + ",".join(sorted(missing)))
    return result, sorted(inventory, key=lambda x: (x["line"], x["name"])), header_defs


def db_audit(payload: bytes):
    with tempfile.TemporaryDirectory(prefix="task082-") as raw:
        path = pathlib.Path(raw) / "crm.db"
        path.write_bytes(payload)
        uri = "file:%s?mode=ro" % urllib.parse.quote(str(path), safe="/")
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        columns = [row[1] for row in connection.execute("PRAGMA table_info(cars)")]
        needed = [
            "id", "auto_number", "brand", "model", "year", "vin",
            "status", "stage", "published", "photos",
        ]
        if any(name not in columns for name in needed):
            raise RuntimeError("DB_COLUMNS_MISSING")
        rows = [dict(row) for row in connection.execute(
            "SELECT id,auto_number,brand,model,year,vin,status,stage,published,photos "
            "FROM cars ORDER BY id")]
        target = next((row for row in rows if row.get("auto_number") == "UA-0011"), None)
        status_audit = []
        if target is not None:
            status_audit = [dict(row) for row in connection.execute(
                "SELECT action,field,old_value,new_value,created_at "
                "FROM audit WHERE entity_type='cars' AND entity_id=? AND field='status' "
                "ORDER BY id DESC LIMIT 20", (target["id"],)
            )]
        connection.close()
    cards = []
    for row in rows:
        vin = re.sub(r"[\s-]+", "", str(row.get("vin") or "")).upper()
        valid = bool(re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin))
        raw_photos = row.get("photos")
        try:
            loaded_photos = json.loads(raw_photos) if isinstance(raw_photos, str) else raw_photos
        except Exception:
            loaded_photos = []
        cards.append({
            "id": row.get("auto_number"),
            "db_id": row.get("id"),
            "brand": row.get("brand"),
            "model": row.get("model"),
            "year": row.get("year"),
            "status": row.get("status"),
            "stage": row.get("stage"),
            "published": bool(row.get("published")),
            "photo_count": len(loaded_photos) if isinstance(loaded_photos, list) else 0,
            "vin4": vin[-4:] if valid else None,
            "vin_valid": valid,
            "vin_present": bool(vin),
            "expected_text_title": "%s · %s %s %s · VIN %s" % (
                row.get("auto_number") or ("#" + str(row.get("id"))),
                row.get("brand") or "",
                row.get("model") or "",
                row.get("year") or "",
                vin[-4:] if valid else "НЕТ",
            ),
        })
    return {
        "quick_check": quick,
        "sha256": sha(payload),
        "count": len(cards),
        "cards": cards,
        "ua0011_status_audit": status_audit,
    }


def main():
    value = {
        "contract": "CRM-VIN4-TITLE-001-V1.0",
        "mode": "GET_ONLY",
        "production_touched": False,
        "http_methods": ["GET"],
        "generated_at_utc": now(),
        "errors": [],
    }
    try:
        source_raw = get(ROOT + "/cars_ui.py")
        source = source_raw.decode("utf-8")
        compile(source, "cars_ui.py", "exec")
        definitions, inventory, header_defs = function_sources(source)
        db_raw = get(ROOT + "/crm.db")
        value.update({
            "status": "PASS",
            "cars_ui": {"sha256": sha(source_raw), "bytes": len(source_raw), "definitions": definitions, "inventory": inventory, "header_definitions": header_defs},
            "db": db_audit(db_raw),
        })
    except Exception as exc:
        value["status"] = "FAIL"
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("TASK082_PROBE_" + value["status"] + (":" + ";".join(value["errors"]) if value["errors"] else ""))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
