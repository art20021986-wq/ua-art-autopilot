#!/usr/bin/env python3
"""TASK 070 read-only capture of the real CRM writer contract and SQLite schema."""
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
import urllib.parse
import urllib.request


BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
OUT = pathlib.Path("cloud/task_070/evidence/real_context.json")
REMOTE_SOURCES = {
    "db.py": "/home/Carix/db.py",
    "cars_ui.py": "/home/Carix/cars_ui.py",
    "trace_zhurnal.py": "/home/Carix/trace_zhurnal.py",
}
REMOTE_DB = "/home/Carix/crm.db"
MAX_SOURCE_BYTES = 4_000_000
MAX_DB_BYTES = 100_000_000
WANTED = {
    "db.py": {
        "Soedinenie", "connect", "update_card_field", "log_action",
        "_ua_lock3_connect",
    },
    "cars_ui.py": {
        "set_field", "apply_value", "remember_price", "catch_message",
    },
    "trace_zhurnal.py": {
        "_UaSoedinenie", "_ua_connect", "_Obertka", "podklyuchit",
        "connect_s_trassoy",
    },
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request_bytes(path: str, limit: int) -> bytes:
    url = BASE + "files/path" + urllib.parse.quote(path, safe="/")
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
            "User-Agent": "ua-art-task070-real-context-read/1",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise RuntimeError("REMOTE_FILE_TOO_LARGE:" + pathlib.PurePosixPath(path).name)
    return data


def redact(text: str) -> str:
    patterns = [
        (
            r"(?i)((?:token|api[_-]?key|secret|password)\s*=\s*)"
            r"(\"[^\"]*\"|'[^']*')",
            r'\1"<redacted>"',
        ),
        (r"(?i)(bearer\s+)[A-Za-z0-9._:-]{16,}", r"\1<redacted>"),
        (r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b", "<redacted-telegram-token>"),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text


def source_segment(source: str, node: ast.AST) -> str:
    lines = source.splitlines()
    end = getattr(node, "end_lineno", node.lineno)
    return "\n".join(lines[node.lineno - 1:end])


def definitions(filename: str, source: str) -> list[dict]:
    tree = ast.parse(source, filename)
    found = []
    wanted = WANTED[filename]
    for node in ast.walk(tree):
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in wanted:
            continue
        segment = source_segment(source, node)
        found.append({
            "kind": type(node).__name__,
            "name": node.name,
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "sha256": sha(segment.encode("utf-8")),
            "source": redact(segment),
        })
    found.sort(key=lambda item: (item["lineno"], item["name"]))
    return found


def local_db_snapshot(data: bytes) -> dict:
    last_error = None
    for attempt in range(3):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        path = pathlib.Path(handle.name)
        try:
            with handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            uri = "file:" + urllib.parse.quote(str(path), safe="/") + "?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=5)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA query_only=ON")
                quick = conn.execute("PRAGMA quick_check").fetchone()[0]
                if quick != "ok":
                    raise RuntimeError("LOCAL_COPY_QUICK_CHECK:" + str(quick))
                master = conn.execute(
                    "SELECT type,name,tbl_name,sql FROM sqlite_master "
                    "WHERE type IN ('table','index','trigger','view') "
                    "ORDER BY type,name"
                ).fetchall()
                schema = [
                    {
                        "type": row["type"],
                        "name": row["name"],
                        "table": row["tbl_name"],
                        "sql": row["sql"],
                    }
                    for row in master
                ]
                tables = {}
                for row in master:
                    if row["type"] != "table" or str(row["name"]).startswith("sqlite_"):
                        continue
                    table = row["name"]
                    safe_name = '"' + str(table).replace('"', '""') + '"'
                    columns = [
                        dict(item)
                        for item in conn.execute("PRAGMA table_info(%s)" % safe_name).fetchall()
                    ]
                    tables[table] = {"columns": columns}
                result = {
                    "sha256": sha(data),
                    "size": len(data),
                    "quick_check": quick,
                    "schema": schema,
                    "tables": tables,
                }
                if "cars" in tables:
                    result["cars_count"] = conn.execute("SELECT count(*) FROM cars").fetchone()[0]
                    names = {item["name"] for item in tables["cars"]["columns"]}
                    if "auto_number" in names:
                        rows = conn.execute(
                            "SELECT * FROM cars WHERE auto_number IN ('UA-0009','UA0009')"
                        ).fetchall()
                        result["ua0009_rows"] = len(rows)
                        result["ua0009_sha256"] = sha(
                            json.dumps(
                                [dict(row) for row in rows],
                                ensure_ascii=False,
                                sort_keys=True,
                                default=str,
                            ).encode("utf-8")
                        )
                return result
            finally:
                conn.close()
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2)
        finally:
            path.unlink(missing_ok=True)
    raise RuntimeError("CRM_DB_LOCAL_COPY_FAILED:" + repr(last_error))


def main() -> None:
    result = {
        "task_id": "task_070",
        "contract_id": "CRM-DB-SPEED-LOCK-070-v1.2",
        "mode": "READ_ONLY_REAL_CONTEXT",
        "remote_http_methods": ["GET"],
        "production_touched": False,
        "crm_db_write": False,
        "site_write": False,
        "sources": {},
    }
    for label, remote in REMOTE_SOURCES.items():
        data = request_bytes(remote, MAX_SOURCE_BYTES)
        source = data.decode("utf-8")
        compile(source, remote, "exec")
        result["sources"][label] = {
            "path": remote,
            "sha256": sha(data),
            "size": len(data),
            "definitions": definitions(label, source),
        }

    db_data = request_bytes(REMOTE_DB, MAX_DB_BYTES)
    result["database"] = local_db_snapshot(db_data)

    required = {
        "db.py": {"connect", "update_card_field", "log_action"},
        "cars_ui.py": {"set_field", "apply_value", "remember_price", "catch_message"},
        "trace_zhurnal.py": {"_ua_connect", "_Obertka"},
    }
    for label, names in required.items():
        actual = {item["name"] for item in result["sources"][label]["definitions"]}
        missing = names - actual
        if missing:
            raise RuntimeError("REQUIRED_DEFINITION_MISSING:%s:%s" % (
                label, ",".join(sorted(missing))
            ))
    if "cars" not in result["database"]["tables"]:
        raise RuntimeError("CARS_TABLE_MISSING")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "PASS",
        "mode": result["mode"],
        "production_touched": False,
        "quick_check": result["database"]["quick_check"],
    }))


if __name__ == "__main__":
    main()
