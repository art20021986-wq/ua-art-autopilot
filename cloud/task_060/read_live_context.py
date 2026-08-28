#!/usr/bin/env python3
"""TASK 060 bounded read-only production context probe."""
from __future__ import annotations
import ast, hashlib, json, os, pathlib, re, urllib.parse, urllib.request

BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
PATHS = {
    "team_bot.py": "/home/Carix/team_bot.py",
    "ai_fast_schema.py": "/home/Carix/ai_fast_schema.py",
    "ai.py": "/home/Carix/ai.py",
    "ai_filter.py": "/home/Carix/ai_filter.py",
}
OUT = pathlib.Path("cloud/task_060/evidence/live_context.json")
MAX = 1_000_000
NEEDLES = ("менедж", "manager", "передал", "run_ai_draft")

def read_api_json(endpoint):
    req = urllib.request.Request(BASE + endpoint, headers={
        "Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
        "User-Agent": "ua-art-task060-read/1",
    })
    with urllib.request.urlopen(req, timeout=60) as response:
        data = response.read(MAX + 1)
    if len(data) > MAX:
        raise RuntimeError("API_RESPONSE_TOO_LARGE")
    return json.loads(data.decode("utf-8"))

def read_remote(path):
    url = BASE + "files/path" + urllib.parse.quote(path, safe="/")
    req = urllib.request.Request(url, headers={
        "Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
        "User-Agent": "ua-art-task060-read/1",
    })
    with urllib.request.urlopen(req, timeout=60) as response:
        data = response.read(MAX + 1)
    if len(data) > MAX:
        raise RuntimeError("SOURCE_TOO_LARGE")
    return data

def redact(text):
    text = re.sub(r'(?i)((?:token|api[_-]?key|secret|password)\s*=\s*)("[^"]*"|\'[^\']*\')', r'\1"<redacted>"', text)
    text = re.sub(r'(?i)(bearer\s+)[A-Za-z0-9._-]{16,}', r'\1<redacted>', text)
    return text

def function_records(source, filename):
    tree = ast.parse(source, filename)
    lines = source.splitlines()
    rows = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        segment = "\n".join(lines[node.lineno - 1:node.end_lineno])
        low = segment.lower()
        wanted = (
            node.name in {"run_ai_draft", "ai_save", "parse_image", "parse_message", "_post_json", "anthropic_key", "clean", "render", "flatten"}
            or any(n in low for n in NEEDLES)
        )
        if not wanted:
            continue
        if len(segment) > 30000:
            segment = segment[:30000] + "\n<TRUNCATED>"
        rows.append({
            "name": node.name,
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "sha256": hashlib.sha256(segment.encode()).hexdigest(),
            "source": redact(segment),
        })
    rows.sort(key=lambda x: (x["lineno"], x["name"]))
    return rows

def allowed_record(source):
    tree = ast.parse(source, "ai_filter.py")
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "ALLOWED" for t in targets):
                try:
                    value = ast.literal_eval(node.value)
                except Exception:
                    return {"kind": "nonliteral"}
                if isinstance(value, dict):
                    return {"kind": "dict", "keys": sorted(map(str, value.keys())), "mapping": value}
                if isinstance(value, (set, list, tuple)):
                    return {"kind": type(value).__name__, "keys": sorted(map(str, value))}
    return {"kind": "missing"}

def scalar_globals(source):
    tree = ast.parse(source, "ai.py")
    result = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [t.id for t in targets if isinstance(t, ast.Name)]
        for name in names:
            if name not in {"MODEL", "MAX_TOKENS", "IMAGE_PROMPT", "SYSTEM_PROMPT"}:
                continue
            try:
                value = ast.literal_eval(node.value)
            except Exception:
                result[name] = {"kind": "nonliteral"}
                continue
            if name in {"IMAGE_PROMPT", "SYSTEM_PROMPT"}:
                raw = str(value).encode()
                result[name] = {"length": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            else:
                result[name] = value
    return result

def main():
    evidence = {"task_id": "task_060", "mode": "READ_ONLY_SOURCE_CONTEXT", "production_touched": False, "files": {}}
    always = read_api_json("always_on/")
    if isinstance(always, dict):
        tasks = always.get("tasks") or always.get("objects") or always.get("results") or []
    elif isinstance(always, list):
        tasks = always
    else:
        tasks = []
    evidence["always_on"] = []
    if isinstance(tasks, list):
        for item in tasks:
            if not isinstance(item, dict):
                continue
            command = str(item.get("command", ""))
            if "start_safe.py" not in command and "run_all.py" not in command:
                continue
            log_ref = item.get("logfile") or item.get("log_file") or item.get("log_path")
            evidence["always_on"].append({
                "id_sha256": hashlib.sha256(str(item.get("id")).encode()).hexdigest(),
                "keys": sorted(item.keys()),
                "enabled": item.get("enabled"),
                "status": item.get("status"),
                "command": redact(command),
                "logfile": log_ref,
            })
            if isinstance(log_ref, str):
                log_path = log_ref.replace("/user/Carix/files", "", 1)
                try:
                    raw_log = read_remote(log_path)[-100000:].decode("utf-8", "replace")
                    selected = []
                    for line in raw_log.splitlines():
                        low = line.lower()
                        if any(mark in low for mark in ("inbox=126", "разбор изображения", "не распознал изображение", "ai photo hard timeout", "anthropic")):
                            selected.append(redact(line)[-1000:])
                    evidence["recent_ai_log"] = selected[-100:]
                except Exception as exc:
                    evidence["recent_ai_log_error"] = type(exc).__name__
    for label, path in PATHS.items():
        data = read_remote(path)
        source = data.decode("utf-8")
        evidence["files"][label] = {
            "path": path,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
            "functions": function_records(source, label),
        }
        if label == "ai_filter.py":
            evidence["allowed"] = allowed_record(source)
        if label == "ai.py":
            evidence["ai_globals"] = scalar_globals(source)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "production_touched": False}))
if __name__ == "__main__":
    main()
