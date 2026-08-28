#!/usr/bin/env python3
"""TASK 071 GET-only capture of the current CRM save call path."""
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
OUT = pathlib.Path("cloud/task_071/evidence/call_path.json")
REMOTE = {
    "db.py": "/home/Carix/db.py",
    "cars_ui.py": "/home/Carix/cars_ui.py",
    "trace_zhurnal.py": "/home/Carix/trace_zhurnal.py",
}
WANTED = {
    "db.py": {
        "_ua_lock3_connect", "Soedinenie", "connect", "get_card",
        "log_action", "update_card_field", "now",
    },
    "cars_ui.py": {
        "set_field", "apply_value", "remember_price", "catch_message",
        "_v168_cas_write", "price_history", "auto_catch", "card_of",
        "voice_change_plan", "_v167_voice_explicit_fields",
        "_v168_named_fields",
    },
    "trace_zhurnal.py": {
        "_UaSoedinenie", "_ua_connect", "_Obertka", "podklyuchit",
        "connect_s_trassoy",
    },
}
ASSIGNMENTS = {
    "db.py": {"ZAMOK_OZHIDANIE", "DB_FILE"},
    "cars_ui.py": {"NUMERIC"},
    "trace_zhurnal.py": {"CEL"},
}
MAX_BYTES = 4_000_000


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request_bytes(remote: str) -> bytes:
    url = BASE + "files/path" + urllib.parse.quote(remote, safe="/")
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
            "User-Agent": "ua-art-task071-call-path-read/1",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise RuntimeError("SOURCE_TOO_LARGE:" + pathlib.PurePosixPath(remote).name)
    return data


def redact(text: str) -> str:
    patterns = [
        (r"(?i)((?:token|api[_-]?key|secret|password)\s*=\s*)(\"[^\"]*\"|'[^']*')",
         r'\1"<redacted>"'),
        (r"(?i)(bearer\s+)[A-Za-z0-9._:-]{16,}", r"\1<redacted>"),
        (r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b", "<redacted-telegram-token>"),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text


def segment(source: str, node: ast.AST) -> str:
    lines = source.splitlines()
    end = getattr(node, "end_lineno", node.lineno)
    return "\n".join(lines[node.lineno - 1:end])


def target_names(node: ast.AST) -> set[str]:
    targets = []
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    names = set()
    for target in targets:
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            names.update(
                item.id for item in target.elts if isinstance(item, ast.Name)
            )
    return names


def capture(filename: str, source: str) -> dict:
    tree = ast.parse(source, filename)
    definitions = []
    assignments = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in WANTED[filename]:
                body = redact(segment(source, node))
                definitions.append({
                    "kind": type(node).__name__,
                    "name": node.name,
                    "lineno": node.lineno,
                    "end_lineno": node.end_lineno,
                    "sha256": sha(body.encode("utf-8")),
                    "source": body,
                })
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            matched = target_names(node) & ASSIGNMENTS[filename]
            if matched:
                body = redact(segment(source, node))
                assignments.append({
                    "names": sorted(matched),
                    "lineno": node.lineno,
                    "sha256": sha(body.encode("utf-8")),
                    "source": body,
                })
    definitions.sort(key=lambda item: (item["lineno"], item["name"]))
    assignments.sort(key=lambda item: item["lineno"])
    return {"definitions": definitions, "assignments": assignments}


def main() -> None:
    result = {
        "task_id": "task_071",
        "mode": "READ_ONLY_CURRENT_CALL_PATH",
        "remote_http_methods": ["GET"],
        "production_touched": False,
        "crm_db_write": False,
        "sources": {},
    }
    for label, remote in REMOTE.items():
        data = request_bytes(remote)
        source = data.decode("utf-8")
        compile(source, remote, "exec")
        captured = capture(label, source)
        captured.update({"path": remote, "sha256": sha(data), "size": len(data)})
        result["sources"][label] = captured
    for label, meta in result["sources"].items():
        found = {d["name"] for d in meta["definitions"]}
        required = WANTED[label]
        if not required.issubset(found):
            raise RuntimeError(
                "MISSING_DEFINITIONS:%s:%s" % (label, sorted(required - found))
            )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUT.with_suffix(".tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(OUT)
    print("TASK071_CALL_PATH_READ_ONLY_PASS")


if __name__ == "__main__":
    main()
