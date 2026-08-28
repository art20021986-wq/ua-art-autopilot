#!/usr/bin/env python3
"""Disable three known legacy DB contenders and restart the CRM bot."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import urllib.error
import urllib.request


BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
OUT = pathlib.Path("cloud/task_064/evidence/quiesce.json")
TARGETS = {
    "python3.10 /home/Carix/avto.py",
    "/home/Carix/cikl2.py",
    "python3.10 /home/Carix/poryadok.py",
}


def request(method: str, endpoint: str, allowed=(200,), data=None):
    req = urllib.request.Request(
        BASE + endpoint,
        data=data,
        method=method,
        headers={
            "Authorization": "Token " + os.environ["PYTHONANYWHERE_API_TOKEN"],
            "User-Agent": "ua-art-task064-quiesce/1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            status = response.status
            body = response.read(1_000_001)
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read(1_000_001)
    if status not in allowed:
        raise RuntimeError("HTTP_%s:%s" % (status, endpoint))
    if len(body) > 1_000_000:
        raise RuntimeError("RESPONSE_TOO_LARGE")
    return body


def read_list(endpoint: str):
    value = json.loads(request("GET", endpoint).decode("utf-8"))
    return (
        value.get("tasks") or value.get("objects") or value.get("results") or []
        if isinstance(value, dict) else value
    )


def task_record(item):
    return {
        "id_sha256": hashlib.sha256(str(item.get("id")).encode()).hexdigest(),
        "command": str(item.get("command", "")),
        "enabled": item.get("enabled"),
        "interval": item.get("interval"),
        "hour": item.get("hour"),
        "minute": item.get("minute"),
    }


def main():
    schedules = read_list("schedule/")
    matched = [item for item in schedules if str(item.get("command", "")).strip() in TARGETS]
    commands = {str(item.get("command", "")).strip() for item in matched}
    missing = sorted(TARGETS - commands)
    if missing:
        raise RuntimeError("TARGET_SCHEDULE_MISSING:" + ",".join(missing))

    removed = []
    for item in matched:
        ident = item.get("id")
        if not isinstance(ident, int) or ident <= 0:
            raise RuntimeError("INVALID_SCHEDULE_ID")
        snapshot = task_record(item)
        request("DELETE", "schedule/%d/" % ident, allowed=(200, 202, 204, 404))
        removed.append(snapshot)

    remaining = read_list("schedule/")
    conflicts = [
        task_record(item) for item in remaining
        if str(item.get("command", "")).strip() in TARGETS
    ]
    if conflicts:
        raise RuntimeError("SCHEDULES_STILL_ACTIVE")

    always = read_list("always_on/")
    bots = [
        item for item in always
        if item.get("enabled") is not False
        and str(item.get("command", "")).strip() == "python3.10 /home/Carix/start_safe.py"
    ]
    if len(bots) != 1:
        raise RuntimeError("PRODUCTION_BOT_TASK_NOT_UNIQUE")
    bot_id = bots[0].get("id")
    request("POST", "always_on/%d/restart/" % bot_id, allowed=(200, 201, 202, 204), data=b"")

    evidence = {
        "task_id": "task_064",
        "contract_id": "CRM-DB-LOCK-EMERGENCY-001",
        "status": "PASS",
        "production_write": True,
        "crm_db_write": False,
        "site_write": False,
        "legacy_schedules_removed": removed,
        "remaining_conflicts": conflicts,
        "bot_restart_requested": True,
        "bot_task_id_sha256": hashlib.sha256(str(bot_id).encode()).hexdigest(),
        "llm_tokens": 0,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "PASS", "removed": len(removed), "llm_tokens": 0}))


if __name__ == "__main__":
    main()
