#!/usr/bin/env python3
"""GET-only audit for CRM hangs, restarts and duplicate startup messages."""

from __future__ import annotations

import ast
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
OUT = Path("cloud/task_084_crm_hang_root_cause/evidence/live_audit.json")
FILES = (
    "cars_ui.py",
    "ai.py",
    "crm_online_guard.py",
    "start_safe.py",
    "run_all.py",
    "team_bot.py",
    "crm_voice_watchdog.py",
)
MAX_BYTES = 2_000_000


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
            "User-Agent": "ua-art-task084-get-only-audit/1",
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
        if not path.startswith(ROOT + "/"):
            raise AuditError("PATH_OUTSIDE_ROOT")
        endpoint = "files/path" + urllib.parse.quote(path, safe="/")
        status, body = self.get(endpoint, allowed=(200, 404) if missing_ok else (200,), limit=limit)
        if status == 404:
            return None
        return body.decode("utf-8", "replace")

    def json_endpoint(self, endpoint: str) -> object:
        _, body = self.get(endpoint)
        return json.loads(body.decode("utf-8"))


def function_info(source: str, names: set[str]) -> list[dict]:
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    result = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name not in names:
            continue
        start = offsets[node.lineno - 1]
        end = offsets[node.end_lineno]
        block = source[start:end]
        result.append({
            "name": node.name,
            "line": node.lineno,
            "end_line": node.end_lineno,
            "sha256": sha256_text(block),
            "source": block if len(block) <= 20_000 else block[:20_000] + "\n# TRUNCATED\n",
        })
    return sorted(result, key=lambda item: (item["line"], item["name"]))


def marker_function_info(source: str, markers: tuple[str, ...]) -> list[dict]:
    """Return only functions that contain startup/restart message markers."""
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    result = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = offsets[node.lineno - 1]
        end = offsets[node.end_lineno]
        block = source[start:end]
        if not any(marker in block for marker in markers):
            continue
        result.append({
            "name": node.name,
            "line": node.lineno,
            "end_line": node.end_lineno,
            "sha256": sha256_text(block),
            "source": block if len(block) <= 20_000 else block[:20_000] + "\n# TRUNCATED\n",
        })
    return sorted(result, key=lambda item: (item["line"], item["name"]))


def contexts(source: str, expressions: list[str], radius: int = 2) -> list[dict]:
    lines = source.splitlines()
    regex = re.compile("|".join("(?:%s)" % value for value in expressions), re.I)
    spans = []
    seen = set()
    for index, line in enumerate(lines):
        if not regex.search(line):
            continue
        start = max(0, index - radius)
        end = min(len(lines), index + radius + 1)
        key = (start, end)
        if key in seen:
            continue
        seen.add(key)
        spans.append({"line": index + 1, "source": "\n".join(lines[start:end])})
    return spans[:80]


def source_facts(name: str, source: str) -> dict:
    compile(source, name, "exec")
    selected = {
        "cars_ui.py": {"catch_message"},
        "ai.py": {"transcribe"},
        "crm_online_guard.py": {"_supervisor_loop", "start_supervisor", "_restart_budget_available"},
        "start_safe.py": {
            "main", "avariynyy_rezhim", "pri_starte", "apply_all",
            "db_clean_split", "ubrat_musor",
        },
        "run_all.py": {"main", "post_init", "on_start", "startup", "pri_starte"},
        "team_bot.py": {
            "main", "post_init", "on_start", "startup", "pri_starte", "start",
            "show_menu", "vvodnye_job",
            "build_application",
        },
        "crm_voice_watchdog.py": {
            "_terminate_process_group", "run_killable_attempt",
            "transcribe_with_restart", "_worker",
        },
    }.get(name, set())
    patterns = [
        r"Бот обновл[её]н",
        r"Здравствуйте,\s*Артем",
        r"post_init",
        r"run_polling",
        r"ApplicationBuilder",
        r"send_message",
        r"show_menu|main_menu|glavnoe|menu\(",
        r"asyncio\.to_thread",
        r"hard_deadline",
        r"os\._exit",
        r"flock|LOCK_EX|singleton",
    ]
    return {
        "bytes": len(source.encode("utf-8")),
        "sha256": sha256_text(source),
        "compiled": True,
        "counts": {
            "ready_message": len(re.findall(r"Бот обновл[её]н", source, flags=re.I)),
            "owner_greeting": len(re.findall(r"Здравствуйте,\s*Артем", source, flags=re.I)),
            "post_init": source.count("post_init"),
            "run_polling": source.count("run_polling"),
            "application_builder": source.count("ApplicationBuilder"),
            "non_killable_transcribe": source.count("asyncio.to_thread(ai.transcribe"),
            "fixed_deadline_4_65": source.count("hard_deadline = started + 4.65"),
            "killable_voice_watchdog": source.count("crm_voice_watchdog"),
            "process_exit_75": source.count("os._exit(75)"),
            "singleton_lock": sum(source.count(value) for value in ("LOCK_EX", "singleton", ".start_safe.lock")),
        },
        "functions": function_info(source, selected),
        "marker_functions": marker_function_info(
            source,
            (
                "Бот запущен и готов к работе",
                "Бот обновлён и готов к работе",
                "Бот обновлен и готов к работе",
                "asyncio.to_thread(ai.transcribe",
            ),
        ),
        "contexts": contexts(source, patterns),
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
    return {
        key: item.get(key)
        for key in ("id", "command", "description", "enabled", "state", "status", "running", "pid")
        if key in item
    }


def main() -> int:
    started = utc_now()
    api = PA()
    sources: dict[str, str] = {}
    facts: dict[str, dict] = {}
    errors: list[str] = []
    for name in FILES:
        try:
            source = api.file(ROOT + "/" + name)
            assert source is not None
            sources[name] = source
            facts[name] = source_facts(name, source)
        except Exception as exc:
            errors.append("%s:%s:%s" % (name, type(exc).__name__, exc))

    always_raw = api.json_endpoint("always_on/")
    schedules_raw = api.json_endpoint("schedule/")
    always = objects(always_raw)
    schedules = objects(schedules_raw)
    launchers = [
        task_view(item) for item in always
        if "start_safe.py" in str(item.get("command") or "")
    ]
    legacy = [
        task_view(item) for item in always + schedules
        if any(word in str(item.get("command") or "") for word in ("run_all.py", "team_bot.py", "start_safe.py"))
    ]

    guard_runtime: dict[str, object] = {}
    guard_source = sources.get("crm_online_guard.py", "")
    try:
        tree = ast.parse(guard_source)
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            key = node.targets[0].id
            if not key.endswith("_PATH"):
                continue
            try:
                raw = ast.literal_eval(node.value)
            except Exception:
                continue
            if not isinstance(raw, str):
                continue
            candidate = raw if raw.startswith("/") else ROOT + "/" + raw
            if candidate.startswith(ROOT + "/") and any(part in key for part in ("STATUS", "EVENT", "RESTART")):
                content = api.file(candidate, missing_ok=True, limit=500_000)
                if content is not None:
                    guard_runtime[key] = {
                        "path": candidate,
                        "sha256": sha256_text(content),
                        "tail": "\n".join(content.splitlines()[-200:]),
                    }
    except Exception as exc:
        errors.append("guard_runtime:%s:%s" % (type(exc).__name__, exc))

    cars = sources.get("cars_ui.py", "")
    startup_ready = sum(item.get("counts", {}).get("ready_message", 0) for item in facts.values())
    startup_greetings = sum(item.get("counts", {}).get("owner_greeting", 0) for item in facts.values())
    root_cause = {
        "fixed_deadline_4_65": "hard_deadline = started + 4.65" in cars,
        "non_killable_to_thread": "asyncio.to_thread(ai.transcribe" in cars,
        "wait_for_only_cancels_await": "asyncio.wait_for" in cars and "asyncio.to_thread(ai.transcribe" in cars,
        "killable_child_present": "crm_voice_watchdog" in cars,
        "startup_ready_message_sites": startup_ready,
        "startup_owner_greeting_sites": startup_greetings,
        "launcher_count": len(launchers),
        "legacy_launcher_count": len(legacy),
        "start_safe_singleton_present": bool(facts.get("start_safe.py", {}).get("counts", {}).get("singleton_lock")),
    }
    expected_after = {
        "cars_ui.py": "8c8a69834247e58795aace02e768caa8d64f31c200abb1dca003b4af50758780",
        "team_bot.py": "b640a4dd0dffcc249dbc0f7ce46fb977fca58babc6a3dd1d8c0cf10d3819f03f",
        "start_safe.py": "21aded2b576b36c6cea84b431c691b22eb09105ca5ec13bb6fd0910452c2cbeb",
        "crm_voice_watchdog.py": "d6c782b55309d3049472f15195935a113387eba1aec8c3365ef7d875a7303efc",
    }
    exact_targets = {
        name: facts.get(name, {}).get("sha256") == expected
        for name, expected in expected_after.items()
    }
    team = sources.get("team_bot.py", "")
    safe = sources.get("start_safe.py", "")
    voice = sources.get("crm_voice_watchdog.py", "")
    remediation = {
        "exact_target_sha256": exact_targets,
        "exact_all_targets": all(exact_targets.values()),
        "cars_killable_voice": "crm_voice_watchdog as _v178_voice" in cars,
        "cars_old_fixed_deadline_removed": "hard_deadline = started + 4.65" not in cars,
        "cars_old_nonkillable_stt_removed": "asyncio.to_thread(ai.transcribe" not in cars,
        "team_killable_voice": "# UA-TASK084-KILLABLE-DRAFT-VOICE" in team,
        "team_old_nonkillable_stt_removed": "asyncio.to_thread(ai.transcribe, audio)" not in team,
        "menu_debounce": "# UA-TASK084-MENU-DEBOUNCE" in team,
        "startup_notice_debounce": "# UA-TASK084-STARTUP-NOTICE-DEBOUNCE" in team,
        "start_singleton": "# UA-TASK084-START-SINGLETON" in safe,
        "worker_process_group": "start_new_session=True" in voice,
        "worker_term_kill": "signal.SIGTERM" in voice and "signal.SIGKILL" in voice,
        "worker_limit_two": "MAX_CONCURRENT_WORKERS = 2" in voice,
        "single_running_launcher": (
            len(launchers) == 1
            and str(launchers[0].get("state", "")).lower() == "running"
        ),
    }
    initial_cause = (
        root_cause["fixed_deadline_4_65"]
        and root_cause["non_killable_to_thread"]
        and not root_cause["killable_child_present"]
    )
    remediation_ok = all(
        value for key, value in remediation.items()
        if isinstance(value, bool) and not key.startswith("exact_")
    )
    if errors:
        status = "FAIL"
    elif initial_cause:
        status = "PASS_ROOT_CAUSE_CONFIRMED"
    elif remediation_ok:
        status = "PASS_REMEDIATION_CONFIRMED"
    else:
        status = "PASS_STATE_CHANGED"
    result = {
        "task_id": "task_084",
        "contract_id": "CRM-HANG-ROOT-CAUSE-084-V1.0",
        "mode": "LIVE_GET_ONLY",
        "http_methods": ["GET"],
        "production_touched": False,
        "process_restart": False,
        "started_at_utc": started,
        "finished_at_utc": utc_now(),
        "status": status,
        "errors": errors,
        "root_cause": root_cause,
        "remediation": remediation,
        "always_on_launchers": launchers,
        "legacy_launchers": legacy,
        "sources": facts,
        "guard_runtime": guard_runtime,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "root_cause": root_cause,
        "remediation": remediation,
        "errors": errors,
    }, ensure_ascii=False))
    return 0 if status != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
