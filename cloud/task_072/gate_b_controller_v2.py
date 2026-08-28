#!/usr/bin/env python3
"""Approved-only production controller for TASK 072 Gate B."""
from __future__ import annotations

import datetime as dt
import json
import mimetypes
import os
import pathlib
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any


CONTRACT = "CRM-DESCRIPTION-SAVE-072-V2"
APPROVAL = "TASK_072_GATE_B_APPROVED"
HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_072"
FILES = {
    "installer_v2.py": HERE / "installer_v2.py",
    "postcheck_v2.py": HERE / "postcheck_v2.py",
    "crm_description_writer_v2.py": HERE / "crm_description_writer_v2.py",
    "patch_cars_ui_v2.py": HERE / "patch_cars_ui_v2.py",
}
RECEIPTS = {
    "shadow": REMOTE + "/shadow_receipt_v2.json",
    "install": REMOTE + "/install_receipt_v2.json",
    "postcheck": REMOTE + "/postcheck_receipt_v2.json",
    "rollback": REMOTE + "/rollback_receipt_v2.json",
}
COMMANDS = {
    "shadow": "cd %s && python3.10 installer_v2.py --shadow" % REMOTE,
    "install": "cd %s && python3.10 installer_v2.py" % REMOTE,
    "postcheck": "cd %s && python3.10 postcheck_v2.py" % REMOTE,
    "rollback": "cd %s && python3.10 installer_v2.py --rollback" % REMOTE,
}
EVIDENCE = HERE / "evidence" / "gate_b_v2.json"
REPORT = HERE / "GATE_B_V2_REPORT.md"
GATE_A = HERE / "evidence" / "gate_a_v2.json"
MAX_BYTES = 12_000_000
CONFLICTING_WORKFLOWS = {
    "task067-crm-online-guard-v1-3-deploy",
    "task068-ferry-vin-v1-1-deploy",
    "task069-crm-container-production-gate-b",
    "task064-emergency-crm-quiesce",
    "SEO Rehab Guard 068 production",
}


class ControllerBlocked(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix="." + path.name + ".", suffix=".tmp", delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_gate_a() -> dict[str, Any]:
    value = json.loads(GATE_A.read_text(encoding="utf-8"))
    if value.get("status") != "PASS" or value.get("gate_b_executed") is not False:
        raise ControllerBlocked("GATE_A_NOT_READY")
    if value.get("live_database", {}).get("cards_count") != 11:
        raise ControllerBlocked("GATE_A_CARD_COUNT")
    if value.get("database_tests", {}).get("existing_cards_tested") != 11:
        raise ControllerBlocked("GATE_A_EXISTING_CARDS")
    if value.get("performance", {}).get("concurrent_operations") != 100:
        raise ControllerBlocked("GATE_A_CONCURRENCY")
    if not value.get("queue_tests", {}).get("multiprocess_no_loss_or_duplicates"):
        raise ControllerBlocked("GATE_A_QUEUE")
    return {
        "status": "PASS",
        "live_cars_sha256": value["sources"]["live_source_sha256"]["cars_ui.py"],
        "patched_cars_sha256": value["sources"]["patched_cars_ui_sha256"],
        "writer_sha256": value["sources"]["candidate_writer_sha256"],
    }


def active_production_conflicts() -> list[dict[str, Any]]:
    token = os.environ.get("GITHUB_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    current = str(os.environ.get("GITHUB_RUN_ID", ""))
    if not token or not repository or not current:
        raise ControllerBlocked("GITHUB_CONFLICT_GUARD_MISSING")
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ua-art-task072-conflict-guard/1",
    }
    conflicts = []
    for status in ("queued", "in_progress", "waiting", "pending"):
        request = urllib.request.Request(
            "https://api.github.com/repos/%s/actions/runs?status=%s&per_page=100"
            % (repository, status), headers=headers,
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read(4_000_001).decode())
        for run in payload.get("workflow_runs") or []:
            if str(run.get("id")) == current:
                continue
            if run.get("name") in CONFLICTING_WORKFLOWS:
                conflicts.append({
                    "id": run.get("id"),
                    "name": run.get("name"),
                    "status": run.get("status"),
                })
    return conflicts


def require_exclusive_window() -> dict[str, Any]:
    conflicts = active_production_conflicts()
    if conflicts:
        raise ControllerBlocked("PARALLEL_PRODUCTION_GATE:" + json.dumps(conflicts))
    return {"status": "PASS", "active_conflicts": 0}


class API:
    def __init__(self) -> None:
        token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
        if not token:
            raise ControllerBlocked("PYTHONANYWHERE_TOKEN_MISSING")
        self.token = token

    def request(self, method, url, data=None, headers=None, allowed=(200,), timeout=90):
        request_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task072-approved-gate-b/1",
        }
        request_headers.update(headers or {})
        request = urllib.request.Request(
            url, data=data, headers=request_headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = response.status
                body = response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerBlocked("NETWORK:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES:
            raise ControllerBlocked("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise ControllerBlocked("HTTP_%d" % status)
        return status, body

    def file_url(self, path: str) -> str:
        if not path.startswith(REMOTE + "/"):
            raise ControllerBlocked("REMOTE_PATH_SCOPE")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, missing: bool = False) -> bytes | None:
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerBlocked("REMOTE_FILE_MISSING:" + pathlib.PurePosixPath(path).name)
        return body

    def delete_file(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(200, 202, 204, 404))

    def upload(self, path: str, data: bytes) -> None:
        boundary = "----task072-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = bytearray()
        body.extend(("--%s\r\n" % boundary).encode())
        body.extend((
            'Content-Disposition: form-data; name="content"; filename="%s"\r\n'
            "Content-Type: %s\r\n\r\n" % (filename, mime)
        ).encode())
        body.extend(data)
        body.extend(("\r\n--%s--\r\n" % boundary).encode())
        for attempt in range(1, 6):
            status, _ = self.request(
                "POST", self.file_url(path), bytes(body),
                {"Content-Type": "multipart/form-data; boundary=" + boundary},
                allowed=(200, 201, 429, 500, 502, 503, 504),
            )
            if status in (200, 201):
                return
            time.sleep(min(attempt * 2, 10))
        raise ControllerBlocked("UPLOAD_FAILED:" + filename)

    @staticmethod
    def objects(body: bytes) -> list[Any]:
        value = json.loads(body.decode())
        if isinstance(value, dict):
            return value.get("tasks") or value.get("objects") or value.get("results") or []
        return value

    @staticmethod
    def trigger_id(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode())
        except Exception:
            return None
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) and identifier > 0 else None

    def create_trigger(self, command: str, description: str) -> tuple[str, int]:
        form = urllib.parse.urlencode({
            "command": command, "description": description, "enabled": "true",
        }).encode()
        status, body = self.request(
            "POST", BASE + "always_on/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
        if identifier:
            return "always_on", identifier
        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({
            "command": command,
            "description": description + " fallback",
            "enabled": "true",
            "interval": "daily",
            "hour": run_at.hour,
            "minute": run_at.minute,
        }).encode()
        status, body = self.request(
            "POST", BASE + "schedule/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerBlocked("NO_REMOTE_TRIGGER")
        return "schedule", identifier

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        kind, identifier = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request(
            "DELETE", BASE + "%s/%d/" % (endpoint, identifier),
            allowed=(200, 202, 204, 404),
        )

    def run_remote(self, key: str, timeout: int = 900) -> dict[str, Any]:
        receipt = RECEIPTS[key]
        self.delete_file(receipt)
        trigger = self.create_trigger(COMMANDS[key], "task072 " + key)
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                raw = self.read(receipt, missing=True)
                if raw:
                    return json.loads(raw.decode())
                time.sleep(5)
            raise ControllerBlocked("RECEIPT_TIMEOUT:" + key)
        finally:
            self.delete_trigger(trigger)

    def restart_bot(self) -> dict[str, Any]:
        _, body = self.request("GET", BASE + "always_on/")
        tasks = self.objects(body)
        matches = [
            item for item in tasks
            if isinstance(item, dict)
            and item.get("enabled") is not False
            and str(item.get("command", "")).strip()
            == "python3.10 /home/Carix/start_safe.py"
        ]
        if len(matches) != 1:
            raise ControllerBlocked("PRODUCTION_LAUNCHER_COUNT:%d" % len(matches))
        identifier = int(matches[0]["id"])
        self.request(
            "POST", BASE + "always_on/%d/restart/" % identifier,
            b"", allowed=(200, 201, 202, 204),
        )
        return {"status": "accepted", "launcher_id": identifier}


def require_pass(value: dict[str, Any], mode: str) -> None:
    if value.get("contract_id") != CONTRACT or value.get("status") != "PASS":
        raise ControllerBlocked(mode + "_FAIL")
    if value.get("runtime_llm_tokens") != 0:
        raise ControllerBlocked(mode + "_LLM_TOKENS")


def validate_shadow(value: dict[str, Any]) -> None:
    require_pass(value, "SHADOW")
    if value.get("production_write") is not False or value.get("crm_db_write") is not False:
        raise ControllerBlocked("SHADOW_WRITE_SCOPE")
    database = value.get("database") or {}
    if database.get("cards_count") != 11 or database.get("quick_check") != "ok":
        raise ControllerBlocked("SHADOW_DATABASE")


def validate_install(value: dict[str, Any]) -> None:
    require_pass(value, "INSTALL")
    if value.get("crm_db_write") is not False:
        raise ControllerBlocked("INSTALL_DB_WRITE")
    if value.get("database_before") != value.get("database_after"):
        raise ControllerBlocked("INSTALL_DATABASE_CHANGED")
    if value.get("queue_preserved") is not True:
        raise ControllerBlocked("INSTALL_QUEUE_CHANGED")


def validate_postcheck(value: dict[str, Any]) -> None:
    require_pass(value, "POSTCHECK")
    if value.get("production_write") is not False or value.get("crm_db_write") is not False:
        raise ControllerBlocked("POSTCHECK_WRITE_SCOPE")
    if value.get("live_database", {}).get("cards_count") != 11:
        raise ControllerBlocked("POSTCHECK_CARD_COUNT")
    clone = value.get("temporary_clone") or {}
    if clone.get("cards_tested") != 11 or clone.get("new_cards_created") != 0:
        raise ControllerBlocked("POSTCHECK_CLONE")


def report(value: dict[str, Any]) -> str:
    install = value.get("install") or {}
    post = value.get("postcheck_delayed") or value.get("postcheck") or {}
    return "\n".join([
        "# TASK 072 — Production Gate B V2",
        "",
        "Status: **%s**" % value.get("status", "BLOCKED"),
        "",
        "- Existing CRM cards: %s" % post.get("live_database", {}).get("cards_count", "—"),
        "- Temporary post-deploy card tests: %s" % post.get("temporary_clone", {}).get("cards_tested", "—"),
        "- Production CRM database changed by installer: no",
        "- Durable queue preserved: %s" % ("yes" if install.get("queue_preserved") else "not verified"),
        "- Backup: `%s`" % install.get("backup_root", ""),
        "- Runtime LLM tokens: 0",
        "- Rollback: %s" % ("not needed" if value.get("status") == "PASS" else value.get("rollback")),
        "",
    ])


def main() -> int:
    result: dict[str, Any] = {
        "contract_id": CONTRACT,
        "mode": "OWNER_APPROVED_PRODUCTION_GATE_B",
        "status": "BLOCKED",
        "owner_approval": os.environ.get("TASK072_OWNER_APPROVAL", ""),
        "runtime_llm_tokens": 0,
        "started_at_utc": utc_now(),
        "errors": [],
        "rollback": None,
    }
    api = None
    install = None
    try:
        if result["owner_approval"] != APPROVAL:
            raise ControllerBlocked("OWNER_APPROVAL_MISSING")
        result["gate_a"] = validate_gate_a()
        result["exclusive_window_before_shadow"] = require_exclusive_window()
        api = API()
        for name, path in FILES.items():
            data = path.read_bytes()
            compile(data.decode("utf-8"), name, "exec")
            api.upload(REMOTE + "/" + name, data)
            if api.read(REMOTE + "/" + name) != data:
                raise ControllerBlocked("UPLOAD_READBACK:" + name)
        shadow = api.run_remote("shadow")
        result["shadow"] = shadow
        validate_shadow(shadow)
        result["exclusive_window_before_install"] = require_exclusive_window()
        install = api.run_remote("install")
        result["install"] = install
        validate_install(install)
        result["restart"] = api.restart_bot()
        time.sleep(15)
        postcheck = api.run_remote("postcheck")
        result["postcheck"] = postcheck
        validate_postcheck(postcheck)
        time.sleep(30)
        delayed = api.run_remote("postcheck")
        result["postcheck_delayed"] = delayed
        validate_postcheck(delayed)
        result["status"] = "PASS"
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api is not None and install and install.get("production_write"):
            try:
                rollback = api.run_remote("rollback")
                result["rollback"] = rollback
                require_pass(rollback, "ROLLBACK")
                if rollback.get("queue_preserved") is not True:
                    raise ControllerBlocked("ROLLBACK_QUEUE")
                result["rollback_restart"] = api.restart_bot()
                time.sleep(12)
                rollback_shadow = api.run_remote("shadow")
                result["rollback_shadow"] = rollback_shadow
                validate_shadow(rollback_shadow)
                result["status"] = "ROLLED_BACK"
            except Exception as rollback_exc:
                result["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )
                result["status"] = "BLOCKED"
    result["finished_at_utc"] = utc_now()
    atomic_text(EVIDENCE, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    atomic_text(REPORT, report(result))
    print(json.dumps({"status": result["status"]}, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

