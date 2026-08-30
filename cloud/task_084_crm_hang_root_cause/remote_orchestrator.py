#!/usr/bin/env python3
"""One-shot install, restart, verify and rollback orchestration for TASK 084."""

from __future__ import annotations

import datetime as dt
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import task084_remote_installer as installer


BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
LAUNCHER = "python3.10 /home/Carix/start_safe.py"
FINAL = installer.REMOTE / "orchestrator_receipt.json"
CONTRACT = installer.CONTRACT
MAX_BYTES = 2_000_000


class OrchestratorError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def token() -> str:
    value = os.environ.get("API_TOKEN") or os.environ.get("PYTHONANYWHERE_API_TOKEN")
    if not value:
        raise OrchestratorError("PYTHONANYWHERE_TOKEN_MISSING")
    return value


def request(method: str, url: str, data=None, allowed=(200,)) -> bytes:
    headers = {
        "Authorization": "Token " + token(),
        "User-Agent": "ua-art-task084-remote-orchestrator/1",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            status = response.status
            body = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise OrchestratorError("API_RESPONSE_TOO_LARGE")
    if status not in allowed:
        raise OrchestratorError("API_HTTP_%d" % status)
    return body


def objects(body: bytes) -> list:
    value = json.loads(body.decode("utf-8"))
    if isinstance(value, dict):
        return value.get("tasks") or value.get("objects") or value.get("results") or []
    return value


def launcher() -> dict:
    tasks = objects(request("GET", BASE + "always_on/"))
    matches = [
        item for item in tasks
        if isinstance(item, dict) and item.get("enabled") is not False
        and str(item.get("command", "")).strip() == LAUNCHER
    ]
    if len(matches) != 1:
        raise OrchestratorError("ACTIVE_LAUNCHER_NOT_UNIQUE:%d" % len(matches))
    return matches[0]


def restart() -> dict:
    item = launcher()
    identifier = int(item["id"])
    request(
        "POST", BASE + "always_on/%d/restart/" % identifier,
        b"", allowed=(200, 201, 202, 204),
    )
    return {"id": identifier, "command": LAUNCHER, "restart_accepted": True}


def wait_running(seconds: int = 150) -> dict:
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        last = launcher()
        if str(last.get("state", "")).lower() == "running":
            return {
                "id": last.get("id"),
                "state": last.get("state"),
                "enabled": last.get("enabled"),
                "command": last.get("command"),
            }
        time.sleep(5)
    raise OrchestratorError("LAUNCHER_NOT_RUNNING:" + str((last or {}).get("state")))


def run() -> dict:
    value = {
        "contract_id": CONTRACT,
        "transport": "SINGLE_REMOTE_TASK",
        "status": "FAIL",
        "started_at_utc": utc_now(),
        "errors": [],
        "bot_restarted": False,
        "rollback": None,
    }
    install = None
    try:
        token()
        value["launcher_before"] = launcher()
        install = installer.run_install()
        installer.atomic_json(installer.RECEIPTS["install"], install)
        value["install"] = install
        value["service"] = restart()
        value["bot_restarted"] = True
        time.sleep(8)
        value["launcher_immediate"] = wait_running()
        time.sleep(7)
        immediate = installer.run_postcheck()
        installer.atomic_json(installer.RECEIPTS["postcheck"], immediate)
        value["postcheck_immediate"] = immediate
        time.sleep(30)
        value["launcher_delayed"] = wait_running()
        delayed = installer.run_postcheck()
        value["postcheck_delayed"] = delayed
        value["status"] = "PASS"
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
        if install and install.get("status") == "PASS":
            try:
                rollback = installer.run_rollback()
                installer.atomic_json(installer.RECEIPTS["rollback"], rollback)
                value["rollback"] = rollback
                if rollback.get("status") != "PASS":
                    raise OrchestratorError("ROLLBACK_FAILED")
            except Exception as rollback_exc:
                value["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )
            finally:
                try:
                    value["rollback_service"] = restart()
                    value["rollback_launcher"] = wait_running()
                except Exception as restart_exc:
                    value["errors"].append(
                        "ROLLBACK_RESTART_" + type(restart_exc).__name__ + ":"
                        + str(restart_exc)
                    )
    value["finished_at_utc"] = utc_now()
    return value


def main() -> int:
    installer.REMOTE.mkdir(parents=True, exist_ok=True)
    value = run()
    installer.atomic_json(FINAL, value)
    print(json.dumps({
        "status": value["status"],
        "bot_restarted": value["bot_restarted"],
        "errors": value["errors"],
    }, ensure_ascii=False))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
