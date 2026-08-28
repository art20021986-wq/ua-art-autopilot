#!/usr/bin/env python3
"""Upload, install, restart, and verify the task_064 SQLite hotfix."""
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


HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_064"
FILES = {
    "sqlite_hotfix_installer.py": HERE / "sqlite_hotfix_installer.py",
    "sqlite_hotfix_postcheck.py": HERE / "sqlite_hotfix_postcheck.py",
}
INSTALL_RECEIPT = REMOTE + "/install_receipt.json"
POSTCHECK_RECEIPT = REMOTE + "/postcheck_receipt.json"
ROLLBACK_RECEIPT = REMOTE + "/rollback_receipt.json"
EVIDENCE = HERE / "evidence" / "hotfix.json"
REPORT = HERE / "HOTFIX_REPORT.md"
INSTALL_COMMAND = "cd %s && python3.10 sqlite_hotfix_installer.py" % REMOTE
POSTCHECK_COMMAND = "cd %s && python3.10 sqlite_hotfix_postcheck.py" % REMOTE
ROLLBACK_COMMAND = "cd %s && python3.10 sqlite_hotfix_installer.py --rollback" % REMOTE
LEGACY_COMMANDS = {
    "python3.10 /home/Carix/avto.py",
    "/home/Carix/cikl2.py",
    "python3.10 /home/Carix/poryadok.py",
}
MAX_BYTES = 4_000_000


class ControllerError(RuntimeError):
    pass


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class API:
    def __init__(self):
        token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
        if not token:
            raise ControllerError("TOKEN_MISSING")
        self.token = token

    def request(self, method, url, data=None, headers=None, allowed=(200,)):
        request_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task064-db-lock/1",
        }
        request_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read(MAX_BYTES + 1)
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ControllerError("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise ControllerError("HTTP_%s" % status)
        return status, body

    def file_url(self, path):
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path, missing=False):
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_FILE_MISSING:" + pathlib.PurePosixPath(path).name)
        return body

    def delete_file(self, path):
        self.request("DELETE", self.file_url(path), allowed=(204, 404))

    def upload(self, path, data):
        boundary = "----uaart-" + uuid.uuid4().hex
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
                "POST",
                self.file_url(path),
                bytes(body),
                {"Content-Type": "multipart/form-data; boundary=" + boundary},
                allowed=(200, 201, 429, 500, 502, 503, 504),
            )
            if status in (200, 201):
                return
            if attempt < 5:
                time.sleep(min(attempt * 3, 12))
        raise ControllerError("UPLOAD_FAILED:" + filename)

    @staticmethod
    def objects(body):
        value = json.loads(body.decode("utf-8"))
        if isinstance(value, dict):
            return value.get("tasks") or value.get("objects") or value.get("results") or []
        return value

    @staticmethod
    def trigger_id(body):
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        ident = value.get("id") if isinstance(value, dict) else None
        return ident if isinstance(ident, int) and ident > 0 else None

    def create_trigger(self, command, description):
        form = urllib.parse.urlencode({
            "command": command,
            "description": description,
            "enabled": "true",
        }).encode()
        status, body = self.request(
            "POST",
            BASE + "always_on/",
            form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        ident = self.trigger_id(body) if status in (200, 201, 202) else None
        if ident:
            return "always_on", ident

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
            "POST",
            BASE + "schedule/",
            form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        ident = self.trigger_id(body) if status in (200, 201, 202) else None
        if not ident:
            raise ControllerError("NO_TRIGGER_AVAILABLE")
        return "schedule", ident

    def delete_trigger(self, trigger):
        kind, ident = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request("DELETE", BASE + endpoint + "/%d/" % ident,
                     allowed=(200, 202, 204, 404))

    def run_remote(self, command, description, receipt_path, seconds=600):
        self.delete_file(receipt_path)
        trigger = self.create_trigger(command, description)
        try:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                raw = self.read(receipt_path, missing=True)
                if raw:
                    return json.loads(raw.decode("utf-8"))
                time.sleep(5)
            raise ControllerError("REMOTE_RECEIPT_TIMEOUT:" + pathlib.PurePosixPath(receipt_path).name)
        finally:
            self.delete_trigger(trigger)

    def restart_bot(self):
        _, body = self.request("GET", BASE + "always_on/")
        tasks = self.objects(body)
        preferred = [
            item for item in tasks
            if isinstance(item, dict)
            and item.get("enabled") is not False
            and str(item.get("command", "")).strip() == "python3.10 /home/Carix/start_safe.py"
        ]
        if len(preferred) != 1:
            raise ControllerError("PRODUCTION_BOT_TASK_NOT_UNIQUE")
        ident = preferred[0].get("id")
        self.request("POST", BASE + "always_on/%d/restart/" % ident,
                     b"", allowed=(200, 201, 202, 204))

    def assert_legacy_schedules_absent(self):
        _, body = self.request("GET", BASE + "schedule/")
        conflicts = [
            str(item.get("command", "")).strip()
            for item in self.objects(body)
            if isinstance(item, dict)
            and str(item.get("command", "")).strip() in LEGACY_COMMANDS
        ]
        if conflicts:
            raise ControllerError("LEGACY_SCHEDULES_ACTIVE")
        return conflicts


def validate_install(value):
    if value.get("status") != "PASS":
        raise ControllerError("INSTALL_FAILED:" + ";".join(value.get("errors", [])))
    if value.get("crm_db_write") is not False or value.get("site_write") is not False:
        raise ControllerError("INSTALL_SCOPE_VIOLATION")
    if value.get("readonly_after", {}).get("quick_check") != "ok":
        raise ControllerError("INSTALL_DB_CHECK_FAILED")


def validate_postcheck(value):
    if value.get("status") != "PASS":
        raise ControllerError("POSTCHECK_FAILED:" + ";".join(value.get("errors", [])))
    if value.get("operations") != 40:
        raise ControllerError("POSTCHECK_OPERATION_COUNT_INVALID")
    if value.get("readonly_after", {}).get("quick_check") != "ok":
        raise ControllerError("POSTCHECK_DB_CHECK_FAILED")
    if any(item.get("returncode") != 0 for item in value.get("workers", [])):
        raise ControllerError("POSTCHECK_WORKER_FAILED")
    bot_health = value.get("bot_health", {})
    bots = bot_health.get("bots", {})
    if not bot_health.get("tokens_distinct") or any(
        not bots.get(name, {}).get("ok") for name in ("client", "crm")
    ):
        raise ControllerError("POSTCHECK_BOT_HEALTH_FAILED")
    if not value.get("service_process", {}).get("running"):
        raise ControllerError("POSTCHECK_BOT_SERVICE_NOT_RUNNING")
    if not value.get("runtime_contract", {}).get("ok"):
        raise ControllerError("POSTCHECK_BOT_RUNTIME_CONTRACT_FAILED")


def main() -> int:
    evidence = {
        "task_id": "task_064",
        "contract_id": "CRM-DB-LOCK-EMERGENCY-001",
        "status": "FAIL",
        "llm_tokens": 0,
        "legacy_schedules_active": None,
        "bot_restarted": False,
        "rollback": None,
        "errors": [],
    }
    api = None
    install = None
    try:
        api = API()
        for name, local in FILES.items():
            data = local.read_bytes()
            compile(data.decode("utf-8"), name, "exec")
            api.upload(REMOTE + "/" + name, data)
            if api.read(REMOTE + "/" + name) != data:
                raise ControllerError("UPLOAD_READBACK_MISMATCH:" + name)

        evidence["legacy_schedules_active"] = api.assert_legacy_schedules_absent()
        install = api.run_remote(
            INSTALL_COMMAND,
            "task064 install CRM SQLite lock hotfix",
            INSTALL_RECEIPT,
        )
        evidence["install"] = install
        validate_install(install)
        api.restart_bot()
        evidence["bot_restarted"] = True
        time.sleep(8)
        postcheck = api.run_remote(
            POSTCHECK_COMMAND,
            "task064 verify CRM SQLite lock hotfix",
            POSTCHECK_RECEIPT,
        )
        evidence["postcheck"] = postcheck
        validate_postcheck(postcheck)
        api.assert_legacy_schedules_absent()
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api is not None and install and install.get("status") == "PASS" and not install.get("already_applied"):
            try:
                rollback = api.run_remote(
                    ROLLBACK_COMMAND,
                    "task064 rollback CRM SQLite lock hotfix",
                    ROLLBACK_RECEIPT,
                )
                evidence["rollback"] = rollback
                api.restart_bot()
            except Exception as rollback_exc:
                evidence["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )

    atomic_text(EVIDENCE, json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    report = (
        "# CRM-DB-LOCK-EMERGENCY-001\n\n"
        "STATUS: %s\n"
        "LEGACY_SCHEDULES_ACTIVE: %s\n"
        "BOT_RESTARTED: %s\n"
        "LLM_TOKENS: 0\n"
        "ERRORS: %s\n"
        % (
            evidence["status"],
            len(evidence.get("legacy_schedules_active") or []),
            "YES" if evidence["bot_restarted"] else "NO",
            "; ".join(evidence["errors"]) if evidence["errors"] else "NONE",
        )
    )
    atomic_text(REPORT, report)
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
