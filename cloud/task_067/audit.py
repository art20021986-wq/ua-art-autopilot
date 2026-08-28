#!/usr/bin/env python3
"""Read-only production audit for CRM-ONLINE-GUARD-001 v1.3.

The probe reads bounded PythonAnywhere files and a consistent SQLite snapshot.
It never writes production code, CRM rows, media, the public site, or bot state.
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


ACCOUNT = "Carix"
API = "https://www.pythonanywhere.com/api/v0/user/%s/" % ACCOUNT
ROOT = "/home/Carix"
DB_PATH = ROOT + "/crm.db"
OUT = pathlib.Path("cloud/task_067/evidence/read_only_audit.json")
MAX_FILE = 2_500_000
MAX_DB = 100_000_000
FILES = {
    "cars_ui.py": ROOT + "/cars_ui.py",
    "team_bot.py": ROOT + "/team_bot.py",
    "lead_bot.py": ROOT + "/lead_bot.py",
    "run_all.py": ROOT + "/run_all.py",
    "start_safe.py": ROOT + "/start_safe.py",
    "db.py": ROOT + "/db.py",
    "ai.py": ROOT + "/ai.py",
    "ai_fast_schema.py": ROOT + "/ai_fast_schema.py",
    "ai_filter.py": ROOT + "/ai_filter.py",
    "local_ocr.py": ROOT + "/local_ocr.py",
}
SENSITIVE = re.compile(r"\b\d{8,}:[A-Za-z0-9_-]{20,}\b")


def request(method: str, endpoint: str, *, limit: int = MAX_FILE) -> tuple[int, bytes]:
    req = urllib.request.Request(
        API + endpoint,
        headers={
            "Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
            "User-Agent": "ua-art-task067-read-only-audit/1",
        },
        method=method,
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            body = response.read(limit + 1)
            status = response.status
    except urllib.error.HTTPError as exc:
        body = exc.read(limit + 1)
        status = exc.code
    if len(body) > limit:
        raise RuntimeError("RESPONSE_TOO_LARGE:" + endpoint)
    request.last_elapsed = round(time.monotonic() - started, 3)
    return status, body


request.last_elapsed = 0.0


def read_remote(path: str, *, limit: int = MAX_FILE, missing: bool = False) -> bytes | None:
    endpoint = "files/path" + urllib.parse.quote(path, safe="/")
    status, body = request("GET", endpoint, limit=limit)
    if status == 404 and missing:
        return None
    if status != 200:
        raise RuntimeError("REMOTE_READ_HTTP_%d:%s" % (status, pathlib.PurePosixPath(path).name))
    return body


def tree_remote(path: str) -> list[str]:
    status, body = request("GET", "files/tree/?" + urllib.parse.urlencode({"path": path}))
    if status != 200:
        return []
    value = json.loads(body.decode("utf-8"))
    if isinstance(value, dict):
        value = value.get("files") or value.get("paths") or value.get("objects") or []
    return [str(item) for item in value] if isinstance(value, list) else []


def redact(text: str) -> str:
    text = SENSITIVE.sub("<redacted-token>", text)
    text = re.sub(r"(?i)(token\s*[=:]\s*)['\"][^'\"]+['\"]", r"\1<redacted>", text)
    return text


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def segment(source: str, node: ast.AST) -> str:
    lines = source.splitlines()
    return "\n".join(lines[node.lineno - 1:node.end_lineno])


def relevant_definition(filename: str, name: str, body: str) -> bool:
    lowered = (name + "\n" + body).casefold()
    if filename == "cars_ui.py":
        keys = (
            "catch_message", "voice_change_plan", "card_kb", "stage_menu",
            "stage_set", "diag", "diagn", "delivery", "dostav", "route",
            "car_stage", "car_diag", "car_open", "callbackqueryhandler",
            "register", "build_application", "_v165_", "_v166_", "_v167_",
        )
        return any(key in lowered for key in keys)
    if filename in {"team_bot.py", "lead_bot.py", "run_all.py", "start_safe.py"}:
        return any(key in lowered for key in (
            "build_application", "add_handler", "callbackqueryhandler",
            "cars_ui", "run_polling", "start", "health", "error", "catalog",
            "каталог", "webapp", "url",
        ))
    if filename == "db.py":
        return name in {"connect", "update_card_field", "get_card"} or "commit" in lowered
    if filename == "ai.py":
        return any(key in lowered for key in ("voice", "transcrib", "openai", "whisper"))
    if filename in {"ai_fast_schema.py", "ai_filter.py", "local_ocr.py"}:
        return any(key in lowered for key in (
            "field", "clean", "fast_text", "labeled", "image", "ocr", "car_fields",
        ))
    return False


def definitions(filename: str, source: str) -> list[dict]:
    tree = ast.parse(source, filename)
    rows = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = segment(source, node)
        if relevant_definition(filename, node.name, body):
            rows.append({
                "name": node.name,
                "kind": type(node).__name__,
                "lineno": node.lineno,
                "end_lineno": node.end_lineno,
                "sha256": sha(body.encode()),
                "source": redact(body[:100_000]),
            })
    return rows


def snippets(source: str, patterns: tuple[str, ...], radius: int = 7, maximum: int = 80) -> list[dict]:
    lines = source.splitlines()
    found = []
    used = set()
    for index, line in enumerate(lines):
        if not any(pattern.casefold() in line.casefold() for pattern in patterns):
            continue
        start = max(0, index - radius)
        end = min(len(lines), index + radius + 1)
        key = (start, end)
        if key in used:
            continue
        used.add(key)
        found.append({"lineno": index + 1, "source": redact("\n".join(lines[start:end]))})
        if len(found) >= maximum:
            break
    return found


def callback_inventory(source: str) -> dict:
    literals = sorted(set(re.findall(r"callback_data\s*=\s*['\"]([^'\"]+)['\"]", source)))
    patterns = sorted(set(re.findall(r"pattern\s*=\s*r?['\"]([^'\"]+)['\"]", source)))
    target_literals = [value for value in literals if any(
        word in value.casefold() for word in ("stage", "diag", "deliver", "dostav", "car_open")
    )]
    target_patterns = [value for value in patterns if any(
        word in value.casefold() for word in ("stage", "diag", "deliver", "dostav", "car_")
    )]
    return {
        "target_callback_literals": target_literals,
        "target_handler_patterns": target_patterns,
        "all_literal_count": len(literals),
        "all_pattern_count": len(patterns),
    }


def consistent_db_snapshot() -> dict:
    with tempfile.TemporaryDirectory(prefix="task067-audit-") as directory:
        local = pathlib.Path(directory) / "crm.db"
        local.write_bytes(read_remote(DB_PATH, limit=MAX_DB))
        wal = read_remote(DB_PATH + "-wal", limit=MAX_DB, missing=True)
        shm = read_remote(DB_PATH + "-shm", limit=MAX_DB, missing=True)
        if wal:
            pathlib.Path(str(local) + "-wal").write_bytes(wal)
        if shm:
            pathlib.Path(str(local) + "-shm").write_bytes(shm)
        con = sqlite3.connect("file:%s?mode=ro" % local, uri=True, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            quick = con.execute("PRAGMA quick_check").fetchone()[0]
            columns = [row[1] for row in con.execute("PRAGMA table_info(cars)")]
            card_count = con.execute("SELECT COUNT(*) FROM cars").fetchone()[0]
            published = con.execute("SELECT COUNT(*) FROM cars WHERE COALESCE(published,0)<>0").fetchone()[0]
            ids = [dict(row) for row in con.execute(
                "SELECT id,auto_number,status,updated_at,length(COALESCE(photos,'')) AS photos_bytes,"
                "length(COALESCE(videos,'')) AS videos_bytes FROM cars ORDER BY id"
            )]
            return {
                "quick_check": quick,
                "journal_mode": con.execute("PRAGMA journal_mode").fetchone()[0],
                "card_count": card_count,
                "published_count": published,
                "columns": columns,
                "cards": ids,
                "rows_sha256": sha(json.dumps(ids, ensure_ascii=False, sort_keys=True).encode()),
            }
        finally:
            con.close()


def telegram_health() -> dict:
    results = {}
    tokens = {}
    for name, filename in (("client", "bot_token.txt"), ("crm", "team_token.txt")):
        token = read_remote(ROOT + "/" + filename, limit=4096).decode("utf-8").strip()
        tokens[name] = token
        started = time.monotonic()
        try:
            url = "https://api.telegram.org/bot%s/getMe" % urllib.parse.quote(token, safe=":")
            with urllib.request.urlopen(url, timeout=10) as response:
                value = json.loads(response.read(100_000).decode("utf-8"))
            identity = value.get("result") or {}
            results[name] = {
                "ok": bool(value.get("ok") and identity.get("id")),
                "latency_seconds": round(time.monotonic() - started, 3),
                "identity_sha256": sha(str(identity.get("id", "")).encode()),
            }
        except Exception as exc:
            results[name] = {
                "ok": False,
                "latency_seconds": round(time.monotonic() - started, 3),
                "error": type(exc).__name__,
            }
    return {"bots": results, "tokens_distinct": tokens.get("client") != tokens.get("crm")}


def service_state() -> dict:
    status, body = request("GET", "always_on/", limit=500_000)
    if status != 200:
        return {"ok": False, "http_status": status}
    value = json.loads(body.decode("utf-8"))
    if isinstance(value, dict):
        value = value.get("tasks") or value.get("objects") or value.get("results") or []
    tasks = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        tasks.append({
            "id": item.get("id"),
            "command": str(item.get("command") or ""),
            "enabled": item.get("enabled") is not False,
            "description": str(item.get("description") or ""),
        })
    production = [item for item in tasks if item["command"].strip() == "python3.10 /home/Carix/start_safe.py"]
    return {"ok": len(production) == 1 and production[0]["enabled"], "tasks": tasks,
            "production_launcher_count": len(production)}


def error_log_signals() -> dict:
    paths = tree_remote(ROOT + "/")
    candidates = sorted({path for path in paths if path.startswith(ROOT + "/") and path.endswith(".log")
                         and "/backups/" not in path and "/.local/" not in path})[:80]
    patterns = re.compile(
        r"database is locked|OperationalError|Traceback|timeout|timed out|callback|error|exception",
        re.IGNORECASE,
    )
    hits = {}
    for path in candidates:
        try:
            data = read_remote(path, limit=2_000_000)
            text = data.decode("utf-8", errors="replace")
        except Exception:
            continue
        matched = [redact(line[-1000:]) for line in text.splitlines()[-2000:] if patterns.search(line)]
        if matched:
            hits[path] = matched[-80:]
    return {"candidate_count": len(candidates), "hits": hits}


def spool_state() -> dict:
    raw = read_remote(ROOT + "/.crm_media_spool.jsonl", limit=10_000_000, missing=True)
    rows = []
    bad = 0
    for line in (raw or b"").decode("utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line)
            rows.append({
                "card_id": item.get("card_id"), "target": item.get("target"),
                "key_sha256": sha(str(item.get("key") or item.get("file_id") or "").encode()),
            })
        except Exception:
            bad += 1
    return {"queued": len(rows), "invalid_lines": bad,
            "unique_keys": len({row["key_sha256"] for row in rows}), "rows": rows[:100]}


def main() -> None:
    started = time.monotonic()
    evidence = {
        "task_id": "task_067",
        "contract_id": "CRM-ONLINE-GUARD-001-V1.3-AUDIT",
        "mode": "READ_ONLY_FRESH_PRODUCTION_AUDIT",
        "production_touched": False,
        "crm_write": False,
        "site_write": False,
        "media_write": False,
        "llm_tokens": 0,
        "status": "FAIL",
        "errors": [],
        "files": {},
    }
    try:
        sources = {}
        for filename, path in FILES.items():
            data = read_remote(path)
            source = data.decode("utf-8")
            compile(source, path, "exec")
            sources[filename] = source
            evidence["files"][filename] = {
                "path": path,
                "bytes": len(data),
                "sha256": sha(data),
                "definitions": definitions(filename, source),
            }
        cars = sources["cars_ui.py"]
        team = sources["team_bot.py"]
        evidence["callbacks"] = callback_inventory(cars + "\n" + team)
        evidence["callback_snippets"] = snippets(
            cars + "\n" + team,
            ("Доставка и этапы", "Комплексная диагностика", "car_stage", "car_diag",
             "CallbackQueryHandler", "add_handler", "callback_data"),
            radius=9,
        )
        evidence["db"] = consistent_db_snapshot()
        evidence["bots"] = telegram_health()
        evidence["service"] = service_state()
        evidence["spool"] = spool_state()
        evidence["logs"] = error_log_signals()
        required = {
            "db_ok": evidence["db"]["quick_check"] == "ok",
            "client_ok": evidence["bots"]["bots"]["client"]["ok"],
            "crm_ok": evidence["bots"]["bots"]["crm"]["ok"],
            "tokens_distinct": evidence["bots"]["tokens_distinct"],
            "launcher_unique": evidence["service"]["ok"],
        }
        evidence["baseline_checks"] = required
        if not all(required.values()):
            raise RuntimeError("BASELINE_CHECK_FAILED")
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
    evidence["elapsed_seconds"] = round(time.monotonic() - started, 3)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    print("TASK067_READ_ONLY_AUDIT_%s" % evidence["status"])
    raise SystemExit(0 if evidence["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
