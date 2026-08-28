#!/usr/bin/env python3
"""Read-only production probe for the UA ART CRM SQLite lock incident."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request


BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE_FILES = {
    "db.py": "/home/Carix/db.py",
    "start_safe.py": "/home/Carix/start_safe.py",
    "run_all.py": "/home/Carix/run_all.py",
    "trace_zhurnal.py": "/home/Carix/trace_zhurnal.py",
}
OUT = pathlib.Path("cloud/task_064/evidence/lock_context.json")
MAX_BYTES = 1_500_000


def request_bytes(endpoint: str) -> bytes:
    request = urllib.request.Request(
        BASE + endpoint,
        headers={
            "Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
            "User-Agent": "ua-art-task064-lock-read/1",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise RuntimeError("API_RESPONSE_TOO_LARGE")
    return data


def read_json(endpoint: str):
    return json.loads(request_bytes(endpoint).decode("utf-8"))


def read_remote(path: str) -> bytes:
    return request_bytes("files/path" + urllib.parse.quote(path, safe="/"))


def redact(text: str) -> str:
    text = re.sub(
        r'(?i)((?:token|api[_-]?key|secret|password)\s*=\s*)("[^"]*"|\'[^\']*\')',
        r'\1"<redacted>"',
        text,
    )
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._-]{16,}", r"\1<redacted>", text)
    return text


def source_segment(source: str, node: ast.AST) -> str:
    lines = source.splitlines()
    end = getattr(node, "end_lineno", node.lineno)
    return "\n".join(lines[node.lineno - 1:end])


def db_context(source: str):
    tree = ast.parse(source, "db.py")
    records = []
    for node in tree.body:
        wanted = (
            isinstance(node, ast.ClassDef) and node.name == "Soedinenie"
        ) or (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in {"connect", "_ua_lock3_connect"}
        )
        if wanted:
            segment = source_segment(source, node)
            records.append({
                "kind": type(node).__name__,
                "name": node.name,
                "lineno": node.lineno,
                "end_lineno": node.end_lineno,
                "sha256": hashlib.sha256(segment.encode()).hexdigest(),
                "source": redact(segment),
            })

    globals_wanted = {
        "DB_FILE", "ZAMOK", "ZAMOK_OZHIDANIE", "OZHIDANIE_SEK",
        "_ua_lock3_original_connect",
    }
    globals_found = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        names = []
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                names.append(target.id)
        if globals_wanted.intersection(names):
            globals_found.append({
                "lineno": node.lineno,
                "source": redact(source_segment(source, node)),
            })
    return {"definitions": records, "globals": globals_found}


def launcher_context(source: str, filename: str):
    tree = ast.parse(source, filename)
    records = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            segment = source_segment(source, node)
            if any(word in segment.casefold() for word in (
                "lock", "pid", "process", "run_all", "subprocess", "singleton", "bot",
            )):
                records.append({
                    "kind": type(node).__name__,
                    "name": node.name,
                    "lineno": node.lineno,
                    "end_lineno": node.end_lineno,
                    "source": redact(segment[:40000]),
                })
    return records


def normalized_tasks(value):
    tasks = (
        value.get("tasks") or value.get("objects") or value.get("results") or []
        if isinstance(value, dict) else value
    )
    result = []
    for item in tasks if isinstance(tasks, list) else []:
        if not isinstance(item, dict):
            continue
        result.append({
            "id_sha256": hashlib.sha256(str(item.get("id")).encode()).hexdigest(),
            "enabled": item.get("enabled"),
            "command": redact(str(item.get("command", ""))),
            "description": redact(str(item.get("description", ""))),
            "interval": item.get("interval"),
            "hour": item.get("hour"),
            "minute": item.get("minute"),
        })
    return result


def main() -> None:
    evidence = {
        "task_id": "task_064",
        "contract_id": "CRM-DB-LOCK-EMERGENCY-001",
        "mode": "READ_ONLY_LOCK_CONTEXT",
        "production_touched": False,
        "files": {},
        "always_on": normalized_tasks(read_json("always_on/")),
        "schedules": normalized_tasks(read_json("schedule/")),
    }
    for label, path in REMOTE_FILES.items():
        data = read_remote(path)
        source = data.decode("utf-8")
        record = {
            "path": path,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        if label == "db.py":
            record["context"] = db_context(source)
        else:
            record["context"] = launcher_context(source, label)
        evidence["files"][label] = record

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "PASS", "production_touched": False}))


if __name__ == "__main__":
    main()
