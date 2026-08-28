#!/usr/bin/env python3
"""Install, restart, verify, and roll back CRM rehabilitation v2 if needed."""
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
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_065"
FILES = {
    "counter_v2_installer.py": HERE / "counter_v2_installer.py",
    "counter_v2_postcheck.py": HERE / "counter_v2_postcheck.py",
    "voice_fields_repair.py": HERE / "voice_fields_repair.py",
}
INSTALL_RECEIPT = REMOTE + "/counter_v2_install_receipt.json"
POSTCHECK_RECEIPT = REMOTE + "/counter_v2_postcheck_receipt.json"
ROLLBACK_RECEIPT = REMOTE + "/counter_v2_rollback_receipt.json"
FIELD_REPAIR_RECEIPT = REMOTE + "/voice_fields_repair_receipt.json"
INSTALL_COMMAND = "cd %s && python3.10 counter_v2_installer.py" % REMOTE
POSTCHECK_COMMAND = "cd %s && python3.10 counter_v2_postcheck.py" % REMOTE
ROLLBACK_COMMAND = "cd %s && python3.10 counter_v2_installer.py --rollback" % REMOTE
FIELD_REPAIR_COMMAND = "cd %s && python3.10 voice_fields_repair.py" % REMOTE
EVIDENCE = HERE / "evidence" / "counter_v2_hotfix.json"
REPORT = HERE / "COUNTER_V2_REPORT.md"
MAX_BYTES = 5_000_000
MARKER = "CRM-PHOTO-COUNTER-002"
VOICE_MARKER = "CRM-VOICE-FIELDS-003"


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
            "User-Agent": "ua-art-task065-rehabilitation-v2/1",
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
                "POST", self.file_url(path), bytes(body),
                {"Content-Type": "multipart/form-data; boundary=" + boundary},
                allowed=(200, 201, 429, 500, 502, 503, 504),
            )
            if status in (200, 201):
                return
            time.sleep(min(attempt * 2, 10))
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
            "command": command, "description": description, "enabled": "true",
        }).encode()
        status, body = self.request(
            "POST", BASE + "always_on/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        ident = self.trigger_id(body) if status in (200, 201, 202) else None
        if ident:
            return "always_on", ident
        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({
            "command": command, "description": description + " fallback",
            "enabled": "true", "interval": "daily",
            "hour": run_at.hour, "minute": run_at.minute,
        }).encode()
        status, body = self.request(
            "POST", BASE + "schedule/", form,
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

    def run_remote(self, command, description, receipt_path, seconds=900):
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
        matches = [item for item in tasks if isinstance(item, dict)
                   and item.get("enabled") is not False
                   and str(item.get("command", "")).strip()
                   == "python3.10 /home/Carix/start_safe.py"]
        if len(matches) != 1:
            raise ControllerError("PRODUCTION_BOT_TASK_NOT_UNIQUE")
        ident = matches[0].get("id")
        self.request("POST", BASE + "always_on/%d/restart/" % ident,
                     b"", allowed=(200, 201, 202, 204))
        return {"command": "python3.10 /home/Carix/start_safe.py",
                "enabled": True, "restart_accepted": True}


def validate_install(value):
    if value.get("status") != "PASS":
        raise ControllerError("INSTALL_FAILED:" + ";".join(value.get("errors", [])))
    if value.get("contract_id") != MARKER:
        raise ControllerError("INSTALL_CONTRACT_INVALID")
    if VOICE_MARKER not in value.get("contract_ids", []):
        raise ControllerError("VOICE_INSTALL_CONTRACT_INVALID")
    if value.get("crm_db_write") is not False or value.get("site_write") is not False:
        raise ControllerError("INSTALL_SCOPE_VIOLATION")
    if value.get("readonly_after", {}).get("quick_check") != "ok":
        raise ControllerError("INSTALL_DB_CHECK_FAILED")


def validate_postcheck(value, install):
    if value.get("status") != "PASS":
        raise ControllerError("POSTCHECK_FAILED:" + ";".join(value.get("errors", [])))
    if not value.get("static_contract", {}).get("ok"):
        raise ControllerError("STATIC_CONTRACT_FAILED")
    concurrent = value.get("concurrency_test", {})
    batch = concurrent.get("batch_17", {})
    capacity = concurrent.get("capacity_100", {})
    if (not concurrent.get("ok") or batch.get("saved_total") != 22
            or batch.get("session_saved") != 17 or batch.get("queued") != 0
            or not batch.get("order_exact")):
        raise ControllerError("PHOTO_BATCH_17_TEST_FAILED")
    if (not capacity.get("ok") or capacity.get("saved_total") != 100
            or capacity.get("saved_unique") != 100 or capacity.get("queued") != 0):
        raise ControllerError("PHOTO_CAPACITY_100_TEST_FAILED")
    if not value.get("voice_regression", {}).get("ok"):
        raise ControllerError("VOICE_REGRESSION_FAILED")
    live = value.get("live_ua0011", {})
    if live.get("quick_check") != "ok" or live.get("duplicate_count") != 0:
        raise ControllerError("LIVE_UA0011_CHECK_FAILED")
    if value.get("cars_ui_sha256") != install.get("cars_ui_sha256_after"):
        raise ControllerError("PRODUCTION_SOURCE_CHANGED_DURING_CHECK")


def validate_field_repair(value):
    if value.get("status") != "PASS":
        raise ControllerError("FIELD_REPAIR_FAILED:" + ";".join(value.get("errors", [])))
    if value.get("contract_id") != VOICE_MARKER:
        raise ControllerError("FIELD_REPAIR_CONTRACT_INVALID")
    desired = {"fuel": "LPI", "engine_cc": 2000, "color": "белый"}
    after = value.get("after", {})
    if {key: after.get(key) for key in desired} != desired:
        raise ControllerError("FIELD_REPAIR_VALUES_INVALID")
    if value.get("quick_check") != "ok" or value.get("site_write") is not False:
        raise ControllerError("FIELD_REPAIR_SCOPE_INVALID")
    if value.get("before", {}).get("protected_sha256") != after.get("protected_sha256"):
        raise ControllerError("FIELD_REPAIR_PROTECTED_FIELDS_CHANGED")


def main() -> int:
    evidence = {"task_id": "task_065", "contract_id": MARKER,
                "contract_ids": [MARKER, VOICE_MARKER], "status": "FAIL",
                "llm_tokens": 0, "bot_restarted": False, "rollback": None,
                "errors": []}
    api = None
    install = None
    code_verified = False
    try:
        api = API()
        for name, local in FILES.items():
            data = local.read_bytes()
            compile(data.decode("utf-8"), name, "exec")
            api.upload(REMOTE + "/" + name, data)
            if api.read(REMOTE + "/" + name) != data:
                raise ControllerError("UPLOAD_READBACK_MISMATCH:" + name)
        install = api.run_remote(INSTALL_COMMAND, "task065 install CRM rehabilitation v2",
                                 INSTALL_RECEIPT)
        evidence["install"] = install
        validate_install(install)
        evidence["service_contract"] = api.restart_bot()
        evidence["bot_restarted"] = True
        time.sleep(10)
        postcheck = api.run_remote(POSTCHECK_COMMAND, "task065 verify CRM rehabilitation v2",
                                   POSTCHECK_RECEIPT)
        evidence["postcheck"] = postcheck
        validate_postcheck(postcheck, install)
        code_verified = True
        field_repair = api.run_remote(
            FIELD_REPAIR_COMMAND, "task065 apply UA0011 explicit voice values",
            FIELD_REPAIR_RECEIPT)
        evidence["field_repair"] = field_repair
        validate_field_repair(field_repair)
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        if (api is not None and install and install.get("status") == "PASS"
                and not install.get("already_applied") and not code_verified):
            try:
                rollback = api.run_remote(ROLLBACK_COMMAND, "task065 rollback CRM rehabilitation v2",
                                          ROLLBACK_RECEIPT)
                evidence["rollback"] = rollback
                api.restart_bot()
            except Exception as rollback_exc:
                evidence["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc))
    atomic_text(EVIDENCE, json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    atomic_text(REPORT, "# %s\n\nSTATUS: %s\nBOT_RESTARTED: %s\nLLM_TOKENS: 0\nERRORS: %s\n" % (
        MARKER, evidence["status"], "YES" if evidence["bot_restarted"] else "NO",
        "; ".join(evidence["errors"]) if evidence["errors"] else "NONE"))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
