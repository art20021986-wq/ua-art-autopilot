#!/usr/bin/env python3
"""Read only the database wrapper needed for task_064 compatibility."""
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
REMOTE = "/home/Carix/trace_zhurnal.py"
OUT = pathlib.Path("cloud/task_064/evidence/trace_wrapper.json")
WANTED = {"_Obertka", "connect_s_trassoy"}


def read_remote() -> bytes:
    request = urllib.request.Request(
        BASE + "files/path" + urllib.parse.quote(REMOTE, safe="/"),
        headers={
            "Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
            "User-Agent": "ua-art-task064-trace-read/1",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(200_001)
    if len(data) > 200_000:
        raise RuntimeError("RESPONSE_TOO_LARGE")
    return data


def redact(value: str) -> str:
    return re.sub(
        r"(?i)(token|secret|password)(\s*=\s*)(['\"]).*?\3",
        r"\1\2\3<redacted>\3",
        value,
    )


def main() -> None:
    data = read_remote()
    source = data.decode("utf-8")
    lines = source.splitlines()
    tree = ast.parse(source, REMOTE)
    definitions = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in WANTED:
            segment = "\n".join(lines[node.lineno - 1:node.end_lineno])
            definitions.append({
                "name": node.name,
                "kind": type(node).__name__,
                "lineno": node.lineno,
                "end_lineno": node.end_lineno,
                "sha256": hashlib.sha256(segment.encode()).hexdigest(),
                "source": redact(segment),
            })
    if {item["name"] for item in definitions} != WANTED:
        raise RuntimeError("WRAPPER_DEFINITIONS_MISSING")
    result = {
        "task_id": "task_064",
        "mode": "READ_ONLY_TRACE_WRAPPER",
        "production_touched": False,
        "file_sha256": hashlib.sha256(data).hexdigest(),
        "definitions": definitions,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print("TASK064_TRACE_WRAPPER_READ_PASS")


if __name__ == "__main__":
    main()
