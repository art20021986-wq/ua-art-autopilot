#!/usr/bin/env python3
"""Bounded read-only source probe for CRM-VOICE-FILL-001."""
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
PATHS = {
    "team_bot.py": "/home/Carix/team_bot.py",
    "db.py": "/home/Carix/db.py",
    "cars_ui.py": "/home/Carix/cars_ui.py",
    "ai_filter.py": "/home/Carix/ai_filter.py",
    "ai.py": "/home/Carix/ai.py",
}
OUT = pathlib.Path("cloud/task_062/evidence/voice_context.json")
MAX_BYTES = 1_500_000


def read_api_json(endpoint):
    request = urllib.request.Request(
        BASE + endpoint,
        headers={
            "Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
            "User-Agent": "ua-art-task062-read/1",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise RuntimeError("API_RESPONSE_TOO_LARGE")
    return json.loads(data.decode("utf-8"))


def read_remote(path):
    url = BASE + "files/path" + urllib.parse.quote(path, safe="/")
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
            "User-Agent": "ua-art-task062-read/1",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise RuntimeError("SOURCE_TOO_LARGE")
    return data


def redact(text):
    text = re.sub(
        r'(?i)((?:token|api[_-]?key|secret|password)\s*=\s*)("[^"]*"|\'[^\']*\')',
        r'\1"<redacted>"', text,
    )
    return re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._-]{16,}", r"\1<redacted>", text)


def wanted_function(filename, name, source):
    low_name = name.casefold()
    low = source.casefold()
    if filename == "team_bot.py":
        return any(word in low_name for word in (
            "card", "car", "field", "edit", "open", "intake", "ai_", "menu", "save",
        )) or "car_last" in low or "user_data" in low
    if filename == "db.py":
        return any(word in low_name for word in (
            "card", "car", "update", "field", "comment", "inbox", "audit", "connect",
        ))
    if filename == "cars_ui.py":
        return True
    if filename == "ai_filter.py":
        return name in {"store", "clean", "render", "render_from"}
    if filename == "ai.py":
        return name in {"transcribe", "voice_enabled"}
    return False


def function_records(source, filename):
    tree = ast.parse(source, filename)
    lines = source.splitlines()
    records = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        segment = "\n".join(lines[node.lineno - 1:node.end_lineno])
        if not wanted_function(filename, node.name, segment):
            continue
        if len(segment) > 40000:
            segment = segment[:40000] + "\n<TRUNCATED>"
        records.append({
            "name": node.name,
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "sha256": hashlib.sha256(segment.encode()).hexdigest(),
            "source": redact(segment),
        })
    records.sort(key=lambda item: (item["lineno"], item["name"]))
    return records


def registration_records(source, filename):
    tree = ast.parse(source, filename)
    lines = source.splitlines()
    records = []
    for node in tree.body:
        segment = "\n".join(lines[node.lineno - 1:getattr(node, "end_lineno", node.lineno)])
        if any(name in segment for name in (
            "CallbackQueryHandler", "MessageHandler", "CommandHandler", "ConversationHandler",
        )):
            records.append({"lineno": node.lineno, "source": redact(segment[:40000])})
    return records


def context_snippets(source):
    lines = source.splitlines()
    records = []
    for index, line in enumerate(lines):
        if not any(needle in line for needle in (
            "car_last", "active_card", "user_data", "callback_data=\"card_", "callback_data=f\"card_",
        )):
            continue
        start = max(0, index - 3)
        end = min(len(lines), index + 4)
        records.append({
            "lineno": index + 1,
            "source": redact("\n".join(lines[start:end])),
        })
    return records[:200]


def main():
    evidence = {
        "task_id": "task_062",
        "contract_id": "CRM-VOICE-FILL-001",
        "mode": "READ_ONLY_SOURCE_CONTEXT",
        "production_touched": False,
        "files": {},
    }
    always = read_api_json("always_on/")
    tasks = (
        always.get("tasks") or always.get("objects") or always.get("results") or []
        if isinstance(always, dict) else always
    )
    evidence["production_bot_tasks"] = []
    for item in tasks if isinstance(tasks, list) else []:
        if not isinstance(item, dict) or "start_safe.py" not in str(item.get("command", "")):
            continue
        evidence["production_bot_tasks"].append({
            "id_sha256": hashlib.sha256(str(item.get("id")).encode()).hexdigest(),
            "enabled": item.get("enabled"),
            "command": redact(str(item.get("command", ""))),
        })

    for label, path in PATHS.items():
        data = read_remote(path)
        source = data.decode("utf-8")
        record = {
            "path": path,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
            "functions": function_records(source, label),
        }
        if label == "team_bot.py":
            record["registrations"] = registration_records(source, label)
            record["context_snippets"] = context_snippets(source)
        evidence["files"][label] = record

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "PASS", "production_touched": False}))


if __name__ == "__main__":
    main()
