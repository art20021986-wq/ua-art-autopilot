#!/usr/bin/env python3
"""GET-only production audit for CRM voice mileage and photo intake/opening."""

from __future__ import annotations

import ast
import collections
import datetime as dt
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
ROOT = "/home/Carix"
OUT = Path("cloud/task_089_crm_voice_photo_repair/evidence/live_audit.json")
FILES = (
    "cars_ui.py",
    "local_ocr.py",
    "ai_fast_schema.py",
    "ai_filter.py",
    "team_bot.py",
    "crm_voice_watchdog.py",
    "db.py",
)
SPOOL = ROOT + "/.crm_media_spool.jsonl"
LOG = "/var/log/alwayson-log-266084.log"
MAX_BYTES = 3_000_000


class AuditError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PA:
    def __init__(self) -> None:
        token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "").strip()
        if not token:
            raise AuditError("PYTHONANYWHERE_API_TOKEN_MISSING")
        self.headers = {
            "Authorization": "Token " + token,
            "User-Agent": "ua-art-task089-get-only-audit/1",
        }

    def get(self, endpoint: str, *, allowed=(200,), limit: int = MAX_BYTES) -> tuple[int, bytes]:
        request = urllib.request.Request(BASE + endpoint, headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.status
                body = response.read(limit + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read(limit + 1)
        if status not in allowed:
            raise AuditError("GET_%s_HTTP_%d" % (endpoint.split("?", 1)[0], status))
        if len(body) > limit:
            raise AuditError("RESPONSE_TOO_LARGE")
        return status, body

    def file(self, path: str, *, missing_ok: bool = False, limit: int = MAX_BYTES) -> str | None:
        if not (path.startswith(ROOT + "/") or path == LOG):
            raise AuditError("PATH_OUTSIDE_ALLOWLIST")
        endpoint = "files/path" + urllib.parse.quote(path, safe="/")
        status, body = self.get(endpoint, allowed=(200, 404) if missing_ok else (200,), limit=limit)
        if status == 404:
            return None
        return body.decode("utf-8", "replace")

    def json_endpoint(self, endpoint: str) -> object:
        _, body = self.get(endpoint)
        return json.loads(body.decode("utf-8"))


def function_blocks(source: str, wanted: set[str], markers: tuple[str, ...] = ()) -> list[dict]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    result = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = offsets[node.lineno - 1]
        end = offsets[node.end_lineno]
        block = source[start:end]
        if node.name not in wanted and not any(marker in block for marker in markers):
            continue
        result.append({
            "name": node.name,
            "line": node.lineno,
            "end_line": node.end_lineno,
            "sha256": sha256_text(block),
            "source": block if len(block) <= 40_000 else block[:40_000] + "\n# TRUNCATED\n",
        })
    return result


def catch_name_facts(source: str) -> dict:
    tree = ast.parse(source)
    catches = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "catch_message"]
    if len(catches) != 1:
        return {"catch_count": len(catches), "override_loaded": False, "override_stored": False}
    catch = catches[0]
    loaded = any(isinstance(node, ast.Name) and node.id == "override" and isinstance(node.ctx, ast.Load)
                 for node in ast.walk(catch))
    stored = any(isinstance(node, ast.Name) and node.id == "override" and isinstance(node.ctx, ast.Store)
                 for node in ast.walk(catch))
    return {
        "catch_count": 1,
        "override_loaded": loaded,
        "override_stored": stored,
        "undefined_override": loaded and not stored,
    }


def source_facts(name: str, source: str) -> dict:
    compile(source, name, "exec")
    selected = {
        "cars_ui.py": {
            "catch_message", "voice_change_plan", "_v168_is_correction",
            "_v168_named_fields", "_v168_cas_write", "_v167_voice_explicit_fields",
            "_v165_spool_enqueue", "_v165_spool_drain", "_v165_spool_remove",
            "_v165_read_rows", "_v165_status", "_v165_progress_job",
            "_v165_schedule_progress", "media_spool_worker_job", "save_media",
            "_save_media_bazovoe", "_save_media_proverka",
        },
        "local_ocr.py": {"fields_from_text"},
        "ai_fast_schema.py": {"labeled_text_data", "fast_text_data", "clean_car", "parsed_from_data"},
        "ai_filter.py": {"normalize_key", "clean"},
        "team_bot.py": {"main", "build_application", "post_init"},
        "db.py": {"update_card_field"},
    }.get(name, set())
    markers = (
        "car_open:", "car_media_wait", "media_spool_worker_job",
    ) if name in ("cars_ui.py", "team_bot.py") else ()
    facts = {
        "bytes": len(source.encode("utf-8")),
        "sha256": sha256_text(source),
        "compiled": True,
        "functions": function_blocks(source, selected, markers),
        "counts": {
            "mileage_km": source.count("mileage_km"),
            "legacy_mileage": len(re.findall(r"(?<![_\w])mileage(?![_\w])", source)),
            "kilometre_suffix_regex": source.count("(km|км)"),
            "photo_spool": source.count("_v165_spool"),
            "photo_progress": source.count("_v165_progress"),
            "voice_watchdog": source.count("crm_voice_watchdog"),
            "media_wait": source.count("car_media_wait"),
        },
    }
    if name == "cars_ui.py":
        facts["catch_name_facts"] = catch_name_facts(source)
    return facts


def spool_facts(raw: str | None) -> dict:
    if raw is None:
        return {"exists": False, "rows": 0}
    rows = []
    invalid = 0
    for line in raw.splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
            else:
                invalid += 1
        except Exception:
            invalid += 1
    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    grouped = collections.Counter((str(row.get("card_id")), str(row.get("target"))) for row in rows)
    ages = [max(0, now - int(row.get("accepted_at") or now)) for row in rows]
    keys = [str(row.get("key") or "") for row in rows]
    return {
        "exists": True,
        "bytes": len(raw.encode("utf-8")),
        "sha256": sha256_text(raw),
        "rows": len(rows),
        "invalid_rows": invalid,
        "unique_keys": len(set(keys)),
        "duplicate_keys": len(keys) - len(set(keys)),
        "oldest_age_seconds": max(ages, default=0),
        "by_card_target": dict(sorted(("%s:%s" % key, count) for key, count in grouped.items())),
        "retry_fields_present": any(any(key in row for key in ("attempts", "last_error", "next_retry_at")) for row in rows),
    }


def log_facts(raw: str | None) -> dict:
    if raw is None:
        return {"available": False, "matching_lines": []}
    pattern = re.compile(r"voice|photo|media|spool|traceback|exception|error|warning", re.I)
    noise = re.compile(r"heartbeat.*(?:successful|executed)|job .* executed successfully", re.I)
    lines = [line[-700:] for line in raw.splitlines()[-8000:] if pattern.search(line) and not noise.search(line)]
    safe = []
    for line in lines[-160:]:
        line = re.sub(r"bot\d+:[A-Za-z0-9_-]{20,}", "bot<TOKEN>", line)
        line = re.sub(r"\b[A-Za-z0-9_-]{40,}\b", "<OPAQUE>", line)
        safe.append(line)
    return {
        "available": True,
        "sha256": sha256_text(raw),
        "matching_lines": safe,
        "heartbeat_success_lines_in_tail": sum(1 for line in raw.splitlines()[-8000:] if noise.search(line)),
    }


def objects(value: object) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("tasks", "objects", "results"):
            nested = value.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def task_view(item: dict) -> dict:
    return {key: item.get(key) for key in ("id", "command", "description", "enabled", "state", "status", "running", "pid") if key in item}


def main() -> int:
    started = utc_now()
    api = PA()
    sources = {}
    facts = {}
    errors = []
    for name in FILES:
        try:
            source = api.file(ROOT + "/" + name)
            assert source is not None
            sources[name] = source
            facts[name] = source_facts(name, source)
        except Exception as exc:
            errors.append("%s:%s:%s" % (name, type(exc).__name__, exc))

    try:
        spool = spool_facts(api.file(SPOOL, missing_ok=True, limit=MAX_BYTES))
    except Exception as exc:
        spool = {"exists": None, "error": type(exc).__name__ + ":" + str(exc)}
    try:
        logs = log_facts(api.file(LOG, missing_ok=True, limit=MAX_BYTES))
    except Exception as exc:
        logs = {"available": False, "error": type(exc).__name__ + ":" + str(exc), "matching_lines": []}

    always = objects(api.json_endpoint("always_on/"))
    schedules = objects(api.json_endpoint("schedule/"))
    launchers = [task_view(item) for item in always if "start_safe.py" in str(item.get("command") or "")]
    jobs = [task_view(item) for item in always + schedules if any(word in str(item.get("command") or "")
            for word in ("start_safe.py", "team_bot.py", "run_all.py"))]

    cars = sources.get("cars_ui.py", "")
    ocr = sources.get("local_ocr.py", "")
    team = sources.get("team_bot.py", "")
    catch_facts = facts.get("cars_ui.py", {}).get("catch_name_facts", {})
    diagnosis = {
        "undefined_override": bool(catch_facts.get("undefined_override")),
        "mileage_requires_km_suffix": bool(re.search(r"\(km\|км\).*?\\b", ocr, re.S)),
        "mileage_named_field_exists": "mileage_km" in cars and "mileage_km" in ocr,
        "voice_watchdog_present": "crm_voice_watchdog" in cars,
        "photo_spool_present": "_v165_spool_enqueue" in cars and "_v165_spool_drain" in cars,
        "photo_worker_registered": "cars_ui.media_spool_worker_job" in team,
        "photo_worker_one_second": bool(re.search(r"media_spool_worker_job.{0,180}interval\s*=\s*1(?:\.0)?", team, re.S)),
        "photo_progress_wait_loop": "for _attempt in range(10)" in cars,
        "photo_open_button": "Открыть карточку" in cars and "car_open:" in cars,
        "photo_wait_cleared_somewhere": "pop(\"car_media_wait\"" in cars,
        "spool_rows": spool.get("rows"),
        "spool_oldest_age_seconds": spool.get("oldest_age_seconds"),
    }
    result = {
        "task_id": "task_089",
        "contract_id": "CRM-VOICE-PHOTO-REPAIR-089-AUDIT-V1",
        "mode": "GET_ONLY",
        "status": "PASS_READ_ONLY" if not errors else "FAIL_INCOMPLETE",
        "http_methods": ["GET"],
        "production_touched": False,
        "crm_db_write": False,
        "media_write": False,
        "process_restart": False,
        "started_at_utc": started,
        "finished_at_utc": utc_now(),
        "sources": facts,
        "spool": spool,
        "logs": logs,
        "always_on_launchers": launchers,
        "bot_jobs": jobs,
        "diagnosis": diagnosis,
        "errors": errors,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "diagnosis": diagnosis, "errors": errors}, ensure_ascii=False))
    return 0 if result["status"] == "PASS_READ_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
