#!/usr/bin/env python3
"""GitHub-side controller for the exact TASK099 partial-install recovery."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import time
import urllib.parse
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
TASK099 = ROOT / "cloud/task_099_site_crm_repair"
sys.path.insert(0, str(TASK099))
import task099_controller as core

CONTRACT = "UA-ART-16-SITE-CRM-COMPLETION-099-V1"
APPROVAL = "UA_ART_TASK099_SITE_CRM_PRODUCTION_APPROVED"
REMOTE_WORKER = "task099_partial_recovery_remote.py"
OUTPUT = TASK099 / "evidence/production_gate.json"
LIVE_AUDIT = TASK099 / "evidence/live_audit.json"


class Blocked(RuntimeError):
    pass


def run_custom(api: core.API, mode: str, timeout: int) -> dict[str, Any]:
    receipt = core.REMOTE + "/partial_" + mode + "_receipt.json"
    api.delete(receipt)
    command = "cd %s && python3.10 %s %s" % (core.REMOTE, REMOTE_WORKER, mode)
    description = "TASK099 partial recovery %s %s" % (mode, os.environ.get("GITHUB_RUN_ID", ""))
    form = urllib.parse.urlencode({"command": command, "description": description, "enabled": "true"}).encode()
    status, body = api.request(
        "POST", core.BASE + "always_on/", form,
        {"Content-Type": "application/x-www-form-urlencoded"}, allowed=(200, 201, 202, 400, 403, 404, 409),
    )
    identifier = api.object_id(body) if status in (200, 201, 202) else None
    if identifier:
        trigger = ("always_on", identifier)
    else:
        at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({
            "command": command, "description": description + " fallback", "enabled": "true",
            "interval": "daily", "hour": at.hour, "minute": at.minute,
        }).encode()
        _, body = api.request("POST", core.BASE + "schedule/", form,
                              {"Content-Type": "application/x-www-form-urlencoded"}, allowed=(200, 201, 202))
        identifier = api.object_id(body)
        if not identifier:
            raise Blocked("RECOVERY_TRIGGER_MISSING")
        trigger = ("schedule", identifier)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = api.read(receipt, missing=True)
            if raw:
                return json.loads(raw.decode("utf-8"))
            time.sleep(5)
        raise Blocked("RECOVERY_RECEIPT_TIMEOUT:" + mode)
    finally:
        api.delete_trigger(trigger)


def read_audit() -> dict[str, Any]:
    value = json.loads(LIVE_AUDIT.read_text(encoding="utf-8"))
    if value.get("contract_id") != CONTRACT or value.get("status") != "PASS_READ_ONLY":
        raise Blocked("FRESH_AUDIT_NOT_PASS")
    if value.get("finished_at_utc", "") < "2026-08-31T05:00:00Z":
        raise Blocked("FRESH_AUDIT_TOO_OLD")
    database = value.get("database") or {}
    if database.get("ids") != ["UA-%04d" % n for n in range(1, 17)]:
        raise Blocked("AUDIT_CARD_REGISTRY")
    if sorted(database.get("published_ids") or []) != ["UA-%04d" % n for n in range(1, 17)]:
        raise Blocked("AUDIT_PUBLISHED_REGISTRY")
    return value


def write(value: dict[str, Any]) -> None:
    core.atomic_json(OUTPUT, value)


def rollback(api: core.API, value: dict[str, Any]) -> None:
    result = api.run("rollback", timeout=900)
    core.require_pass(result, "ROLLBACK")
    value["rollback"] = result
    value["rollback_restart"] = api.restart()
    time.sleep(18)
    value["status"] = "ROLLED_BACK"


def run() -> int:
    value = {
        "contract_id": CONTRACT, "status": "BLOCKED", "mode": "EXACT_PARTIAL_RECOVERY",
        "started_at_utc": core.utc_now(), "errors": [], "issue_35_closed": False,
        "github_comment_published": False,
    }
    api = None
    installed = False
    try:
        if os.environ.get("TASK099_OWNER_APPROVAL") != APPROVAL:
            raise Blocked("OWNER_APPROVAL_MISSING")
        conflicts = core.active_production_conflicts()
        if conflicts:
            raise Blocked("PARALLEL_PRODUCTION_GATE:" + json.dumps(conflicts))
        audit = read_audit()
        value["audit_finished_at_utc"] = audit.get("finished_at_utc")
        api = core.API()
        worker = HERE / REMOTE_WORKER
        compile(worker.read_text(encoding="utf-8"), REMOTE_WORKER, "exec")
        api.upload(core.REMOTE + "/" + REMOTE_WORKER, worker.read_bytes())
        probe = run_custom(api, "probe", 600)
        if probe.get("status") != "PASS" or probe.get("mode") != "PROBE" or probe.get("lock_free") is not True:
            raise Blocked("PARTIAL_PROBE_FAIL:" + json.dumps(probe.get("errors") or []))
        value["probe"] = probe
        resume = run_custom(api, "resume", 2400)
        value["install"] = resume
        core.require_pass(resume, "INSTALL")
        installed = True
        if resume.get("main_fields_changed") is not False or resume.get("media_changed") is not False:
            raise Blocked("RECOVERY_PROTECTED_SCOPE")
        value["prerequisites"] = probe.get("expected_live")
        value["restart"] = api.restart()
        time.sleep(18)
        value["launcher_after_restart"] = api.launcher()
        immediate = api.run("postcheck", timeout=600)
        core.require_pass(immediate, "POSTCHECK")
        value["postcheck_immediate"] = immediate
        time.sleep(35)
        delayed = api.run("postcheck", timeout=600)
        core.require_pass(delayed, "POSTCHECK")
        value["postcheck_delayed"] = delayed
        value["status"] = "PASS_READY_FOR_BROWSER_GATE"
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc)[:1600])
        if api is not None and installed:
            try:
                rollback(api, value)
            except Exception as rollback_exc:
                value["errors"].append("ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)[:1200])
    value["finished_at_utc"] = core.utc_now()
    write(value)
    print(json.dumps({"status": value["status"], "errors": value["errors"]}, ensure_ascii=False))
    return 0 if value["status"] == "PASS_READY_FOR_BROWSER_GATE" else 1


def run_rollback() -> int:
    value = json.loads(OUTPUT.read_text(encoding="utf-8"))
    api = core.API()
    rollback(api, value)
    value["finished_at_utc"] = core.utc_now()
    write(value)
    return 0 if value.get("status") == "ROLLED_BACK" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    return run_rollback() if args.rollback else run()


if __name__ == "__main__":
    raise SystemExit(main())
