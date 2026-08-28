#!/usr/bin/env python3
"""Bounded read-only probe for slow CRM photo ingestion."""
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request


API = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = {
    "cars_ui.py": "/home/Carix/cars_ui.py",
    "team_bot.py": "/home/Carix/team_bot.py",
    "db.py": "/home/Carix/db.py",
}
OUT = pathlib.Path("cloud/task_065/evidence/photo_path.json")
MAX_FILE = 1_500_000


def read_remote(path: str) -> bytes:
    request = urllib.request.Request(
        API + "files/path" + urllib.parse.quote(path, safe="/"),
        headers={
            "Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
            "User-Agent": "ua-art-task065-photo-read/1",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise RuntimeError("REMOTE_FILE_TOO_LARGE:" + pathlib.PurePosixPath(path).name)
    return data


def redact(text: str) -> str:
    text = re.sub(r"\b\d{8,}:[A-Za-z0-9_-]{20,}\b", "<redacted-token>", text)
    text = re.sub(r"\b-?\d{9,}\b", "<redacted-id>", text)
    return text


def source_segment(lines, node):
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def wanted(filename: str, node: ast.AST) -> bool:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return False
    name = node.name.casefold()
    if filename == "cars_ui.py":
        return name == "catch_message" or "save_media" in name
    if filename == "team_bot.py":
        return name in {"build_application", "intake"} or "handler" in name
    if filename == "db.py":
        return name in {"connect", "update_card_field"}
    return False


def main() -> None:
    evidence = {
        "task_id": "task_065",
        "mode": "READ_ONLY_PHOTO_PATH",
        "production_touched": False,
        "llm_tokens": 0,
        "files": {},
    }
    for filename, path in REMOTE.items():
        data = read_remote(path)
        source = data.decode("utf-8")
        tree = ast.parse(source, path)
        lines = source.splitlines()
        definitions = []
        for node in ast.walk(tree):
            if wanted(filename, node):
                segment = source_segment(lines, node)
                definitions.append({
                    "name": node.name,
                    "kind": type(node).__name__,
                    "lineno": node.lineno,
                    "end_lineno": node.end_lineno,
                    "sha256": hashlib.sha256(segment.encode()).hexdigest(),
                    "source": redact(segment[:50_000]),
                })
        evidence["files"][filename] = {
            "path": path,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
            "definitions": sorted(definitions, key=lambda item: item["lineno"]),
        }
    names = {
        item["name"]
        for item in evidence["files"]["cars_ui.py"]["definitions"]
    }
    if "catch_message" not in names or "save_media" not in names:
        raise RuntimeError("PHOTO_PATH_DEFINITIONS_MISSING")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print("TASK065_PHOTO_PATH_READ_PASS")


if __name__ == "__main__":
    main()
