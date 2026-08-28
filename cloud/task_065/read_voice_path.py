#!/usr/bin/env python3
"""Bounded read-only probe for CRM voice field updates on UA-0011."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import tempfile
import urllib.error
import urllib.parse
import urllib.request


API = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = {
    "cars_ui.py": "/home/Carix/cars_ui.py",
    "ai_fast_schema.py": "/home/Carix/ai_fast_schema.py",
    "local_ocr.py": "/home/Carix/local_ocr.py",
    "ai_filter.py": "/home/Carix/ai_filter.py",
}
OUT = pathlib.Path("cloud/task_065/evidence/voice_path.json")
MAX_FILE = 1_500_000
DB = "/home/Carix/crm.db"


def read_remote(path: str, *, limit=MAX_FILE, missing=False) -> bytes | None:
    request = urllib.request.Request(
        API + "files/path" + urllib.parse.quote(path, safe="/"),
        headers={
            "Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
            "User-Agent": "ua-art-task065-voice-read/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        if missing and exc.code == 404:
            return None
        raise
    if len(data) > limit:
        raise RuntimeError("REMOTE_FILE_TOO_LARGE")
    return data


def redact(text: str) -> str:
    text = re.sub(r"\b\d{8,}:[A-Za-z0-9_-]{20,}\b", "<redacted-token>", text)
    return re.sub(r"\b-?\d{9,}\b", "<redacted-id>", text)


def definitions(source: str, names: set[str]):
    tree = ast.parse(source)
    lines = source.splitlines()
    rows = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            segment = "\n".join(lines[node.lineno - 1:node.end_lineno])
            rows.append({"name": node.name, "lineno": node.lineno,
                         "sha256": hashlib.sha256(segment.encode()).hexdigest(),
                         "source": redact(segment[:80_000])})
    return rows


def snippets(source: str, patterns: tuple[str, ...], radius: int = 18):
    lines = source.splitlines()
    rows = []
    used = set()
    for index, line in enumerate(lines):
        if not any(value.casefold() in line.casefold() for value in patterns):
            continue
        start, end = max(0, index - radius), min(len(lines), index + radius + 1)
        if (start, end) in used:
            continue
        used.add((start, end))
        rows.append({"lineno": index + 1,
                     "source": redact("\n".join(lines[start:end]))})
    return rows[:30]


def db_state():
    with tempfile.TemporaryDirectory(prefix="task065-voice-") as directory:
        local = pathlib.Path(directory) / "crm.db"
        local.write_bytes(read_remote(DB, limit=80_000_000))
        wal = read_remote(DB + "-wal", limit=80_000_000, missing=True)
        if wal:
            pathlib.Path(str(local) + "-wal").write_bytes(wal)
        con = sqlite3.connect("file:%s?mode=ro" % local, uri=True, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            quick = con.execute("PRAGMA quick_check").fetchone()[0]
            columns = [row[1] for row in con.execute("PRAGMA table_info(cars)")]
            wanted = [name for name in columns if name.casefold() in {
                "id", "auto_number", "fuel", "fuel_type", "engine", "engine_cc",
                "engine_volume", "volume", "color", "colour", "updated_at"
            }]
            row = con.execute(
                "SELECT %s FROM cars WHERE auto_number=?" % ",".join(
                    '"%s"' % value.replace('"', '""') for value in wanted),
                ("UA-0011",),
            ).fetchone()
            return {"quick_check": quick, "columns": columns,
                    "ua0011": dict(row) if row else None}
        finally:
            con.close()


def main():
    evidence = {"task_id": "task_065", "mode": "READ_ONLY_VOICE_PATH",
                "production_touched": False, "llm_tokens": 0, "files": {}}
    wanted = {
        "cars_ui.py": {"catch_message", "voice_change_plan", "apply_value", "card_of"},
        "ai_fast_schema.py": {"car_fields", "fast_text_data", "parsed_from_data", "clean_car"},
        "local_ocr.py": {"fields_from_text"},
        "ai_filter.py": set(),
    }
    patterns = ("fuel", "engine_cc", "engine_volume", "color", "colour",
                "LPG", "LPI", "топлив", "объ.м", "цвет", "voice_change_plan")
    for name, path in REMOTE.items():
        data = read_remote(path)
        source = data.decode("utf-8")
        compile(source, path, "exec")
        evidence["files"][name] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "definitions": definitions(source, wanted[name]),
            "snippets": snippets(source, patterns),
        }
    evidence["db"] = db_state()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print("TASK065_VOICE_PATH_READ_PASS")


if __name__ == "__main__":
    main()
