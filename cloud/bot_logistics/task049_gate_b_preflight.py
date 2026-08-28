#!/usr/bin/env python3
"""Read-only TASK 049 Gate B preflight.

Queries only the PythonAnywhere always-on inventory and the two exact source
files required by Gate B. It relays hashes and sanitized task identities; it
cannot upload, delete, restart, patch, or execute anything remotely.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request

USERNAME = "Carix"
HOSTS = ("www.pythonanywhere.com", "eu.pythonanywhere.com")
SOURCE_PATH = "/home/Carix/cars_ui.py"
CANDIDATE_PATH = (
    "/home/Carix/autopilot_inbox/cloud/bot_logistics/"
    "task049_cars_ui.py.candidate"
)
EXPECTED_SOURCE_SHA = (
    "06e7da916ea36c4ffafef01c85f59a0574f06d3cdda24aa1f8c242175de726b7"
)
EXPECTED_CANDIDATE_SHA = (
    "3c6f12227e45a3ba936d48d4a12435378045e879fea481def04f3378f6a0f12f"
)
HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence" / "task_049_gate_b_preflight.json"
MAX_RESPONSE = 2_000_000
ENTRYPOINT_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:/home/Carix/)?"
    r"(start_safe\.py|run_all\.py|team_bot\.py)(?![A-Za-z0-9_])"
)


class PreflightBlocked(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReadOnlyAPI:
    def __init__(self, username: str, host: str, token: str,
                 opener=urllib.request.urlopen):
        if username != USERNAME:
            raise PreflightBlocked("invalid_username")
        if host not in HOSTS:
            raise PreflightBlocked("invalid_host")
        if not token:
            raise PreflightBlocked("missing_token")
        self.username = username
        self.host = host
        self._token = token
        self._opener = opener

    @property
    def base(self) -> str:
        return (
            f"https://{self.host}/api/v0/user/"
            f"{urllib.parse.quote(self.username, safe='')}/"
        )

    def get(self, url: str, label: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": "Token " + self._token,
                "User-Agent": "ua-art-task049-gate-b-preflight/1",
            },
            method="GET",
        )
        if request.method != "GET" or request.data is not None:
            raise PreflightBlocked("non_readonly_request")
        try:
            with self._opener(request, timeout=60) as response:
                status = getattr(response, "status", response.getcode())
                body = response.read(MAX_RESPONSE + 1)
        except urllib.error.HTTPError as exc:
            raise PreflightBlocked(f"http_error:{label}:{exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise PreflightBlocked("network_error:" + label) from exc
        if status != 200:
            raise PreflightBlocked(f"http_status:{label}:{status}")
        if len(body) > MAX_RESPONSE:
            raise PreflightBlocked("response_too_large:" + label)
        return body

    def always_on(self) -> object:
        raw = self.get(self.base + "always_on/", "always_on")
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PreflightBlocked("always_on_invalid_json") from exc

    def file(self, path: str) -> bytes:
        if path not in {SOURCE_PATH, CANDIDATE_PATH}:
            raise PreflightBlocked("file_path_not_allowed")
        url = self.base + "files/path" + urllib.parse.quote(path, safe="/")
        return self.get(url, "file")


def task_list(payload: object) -> list[dict]:
    if isinstance(payload, list):
        tasks = payload
    elif isinstance(payload, dict):
        matches = [
            payload.get(key) for key in ("objects", "tasks", "results")
            if isinstance(payload.get(key), list)
        ]
        if len(matches) != 1:
            raise PreflightBlocked("always_on_shape_unknown")
        tasks = matches[0]
    else:
        raise PreflightBlocked("always_on_shape_unknown")
    if len(tasks) > 40 or any(not isinstance(item, dict) for item in tasks):
        raise PreflightBlocked("always_on_list_invalid")
    return tasks


def sanitize_task(item: dict) -> dict:
    identifier = item.get("id")
    command = item.get("command")
    if not isinstance(identifier, int) or identifier <= 0:
        raise PreflightBlocked("always_on_id_invalid")
    if not isinstance(command, str) or not 1 <= len(command) <= 1000:
        raise PreflightBlocked("always_on_command_invalid")
    entrypoints = sorted(set(ENTRYPOINT_RE.findall(command)))
    result = {
        "id": identifier,
        "enabled": item.get("enabled") is True,
        "running": item.get("running") if isinstance(item.get("running"), bool) else None,
        "inbox_task": "/autopilot_inbox/" in command,
        "entrypoints": entrypoints,
        "command_sha256": sha256(command.encode("utf-8")),
    }
    return result


def run(api: ReadOnlyAPI) -> dict:
    source = api.file(SOURCE_PATH)
    candidate = api.file(CANDIDATE_PATH)
    tasks = [sanitize_task(item) for item in task_list(api.always_on())]
    production = [
        item for item in tasks
        if item["enabled"] and not item["inbox_task"] and item["entrypoints"]
    ]
    source_hash = sha256(source)
    candidate_hash = sha256(candidate)
    status = "PASS" if (
        source_hash == EXPECTED_SOURCE_SHA
        and candidate_hash == EXPECTED_CANDIDATE_SHA
        and len(production) == 1
    ) else "BLOCKED"
    errors = []
    if source_hash != EXPECTED_SOURCE_SHA:
        errors.append("source_sha_mismatch")
    if candidate_hash != EXPECTED_CANDIDATE_SHA:
        errors.append("candidate_sha_mismatch")
    if len(production) != 1:
        errors.append("production_task_count:%d" % len(production))
    return {
        "task_id": "task_049",
        "mode": "GATE_B_READ_ONLY_PREFLIGHT",
        "status": status,
        "source_sha256": source_hash,
        "candidate_sha256": candidate_hash,
        "always_on_count": len(tasks),
        "production_candidates": production,
        "errors": errors,
        "production_write": False,
        "crm_write": False,
        "db_write": False,
        "restart": False,
        "gate_b_executed": False,
    }


def atomic_write(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=path.parent,
        prefix="." + path.name + ".", suffix=".tmp", delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    try:
        api = ReadOnlyAPI(
            os.environ.get("PYTHONANYWHERE_USERNAME", USERNAME),
            os.environ.get("PYTHONANYWHERE_HOST", HOSTS[0]),
            os.environ.get("PYTHONANYWHERE_API_TOKEN", ""),
        )
        receipt = run(api)
        atomic_write(
            EVIDENCE,
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        print(json.dumps({
            "status": receipt["status"],
            "production_write": False,
            "crm_write": False,
            "db_write": False,
            "restart": False,
        }, sort_keys=True))
        return 0 if receipt["status"] == "PASS" else 2
    except PreflightBlocked as exc:
        print("TASK049_PREFLIGHT_BLOCKED:" + str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

