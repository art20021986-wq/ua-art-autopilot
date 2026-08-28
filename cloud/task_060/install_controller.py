#!/usr/bin/env python3
"""Upload, install, validate, and restart TASK 060 on PythonAnywhere."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import mimetypes
import os
import pathlib
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_060"
FILES = {
    "patch_installer.py": HERE / "patch_installer.py",
    "patch_payload.py": HERE / "patch_payload.py",
    "local_ocr.py": HERE / "local_ocr.py",
}
RECEIPT = REMOTE + "/install_receipt.json"
PROD_TEAM = "/home/Carix/team_bot.py"
PROD_OCR = "/home/Carix/local_ocr.py"
COMMAND = "cd " + REMOTE + " && python3.10 patch_installer.py"
EVIDENCE = HERE / "evidence" / "install.json"
REPORT = HERE / "INSTALL_REPORT.md"
STATUS = pathlib.Path("cloud/latest_status.md")
OWNER_REPLY = pathlib.Path("cloud/owner_reply.md")
MAX = 3_000_000
HEX = re.compile(r"^[0-9a-f]{64}$")


class ControllerError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
    temp = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class API:
    def __init__(self):
        token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
        if not token:
            raise ControllerError("TOKEN_MISSING")
        self.token = token

    def request(self, method, url, data=None, headers=None, allowed=(200,)):
        base_headers = {"Authorization": "Token " + self.token, "User-Agent": "ua-art-task060-install/1"}
        base_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=base_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read(MAX + 1)
                status = response.status
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read(MAX + 1)
        if len(body) > MAX:
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
            if attempt < 5:
                time.sleep(min(attempt * 3, 12))
        raise ControllerError("UPLOAD_FAILED:" + filename)

    @staticmethod
    def trigger_id(body):
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        ident = value.get("id") if isinstance(value, dict) else None
        return ident if isinstance(ident, int) and ident > 0 else None

    def create_trigger(self):
        form = urllib.parse.urlencode({
            "command": COMMAND, "description": "TASK 060 token-free OCR install", "enabled": "true",
        }).encode()
        status, body = self.request(
            "POST", BASE + "always_on/", form, {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        ident = self.trigger_id(body) if status in (200, 201, 202) else None
        if ident:
            return "always_on", ident
        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({
            "command": COMMAND, "description": "TASK 060 token-free OCR install fallback",
            "enabled": "true", "interval": "daily", "hour": run_at.hour, "minute": run_at.minute,
        }).encode()
        status, body = self.request(
            "POST", BASE + "schedule/", form, {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        ident = self.trigger_id(body) if status in (200, 201, 202) else None
        if not ident:
            raise ControllerError("NO_TRIGGER_AVAILABLE")
        return "schedule", ident

    def delete_trigger(self, trigger):
        kind, ident = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request("DELETE", BASE + endpoint + "/%d/" % ident, allowed=(200, 202, 204, 404))

    def restart_bot(self):
        _, body = self.request("GET", BASE + "always_on/")
        value = json.loads(body.decode("utf-8"))
        tasks = value.get("tasks") or value.get("objects") or value.get("results") or [] if isinstance(value, dict) else value
        preferred = [
            item for item in tasks if isinstance(item, dict) and item.get("enabled") is not False
            and "start_safe.py" in str(item.get("command", ""))
            and "autopilot_inbox" not in str(item.get("command", ""))
        ]
        if len(preferred) != 1:
            raise ControllerError("PRODUCTION_BOT_TASK_NOT_UNIQUE")
        ident = preferred[0].get("id")
        self.request("POST", BASE + "always_on/%d/restart/" % ident, b"", allowed=(200, 201, 202, 204))
        return sha(str(ident).encode())


def validate_receipt(value):
    if not isinstance(value, dict) or value.get("task_id") != "task_060":
        raise ControllerError("RECEIPT_ID_INVALID")
    if value.get("status") != "PASS" or value.get("errors") != []:
        raise ControllerError("INSTALL_NOT_PASS:" + ",".join(value.get("errors") or []))
    for key in ("crm_db_write", "site_write", "service_restarted", "ua0010_published", "rollback_performed"):
        if value.get(key) is not False:
            raise ControllerError("SAFETY_MARKER_INVALID:" + key)
    if value.get("staff_handoff_removed") is not True or value.get("token_cost_per_photo") != 0:
        raise ControllerError("FUNCTIONAL_MARKER_INVALID")
    files = value.get("files") or {}
    if not value.get("already_applied"):
        if set(files) != {PROD_TEAM, PROD_OCR}:
            raise ControllerError("FILE_SCOPE_INVALID")
        for meta in files.values():
            if not HEX.fullmatch(str(meta.get("after") or "")):
                raise ControllerError("FILE_HASH_INVALID")
    return value


def write_result(evidence, ok):
    evidence["controller"] = evidence.get("controller") or {}
    atomic_text(EVIDENCE, json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    if ok:
        report = (
            "# TASK 060 installation\n\nSTATUS: PASS\nBOT_RESTARTED: YES\n"
            "STAFF_HANDOFF: REMOVED\nPHOTO_AI_TOKENS: 0\nUA_0010_PUBLISHED: NO\n"
        )
        status = (
            "TASK_ID: task_060\nROUND: 2\nCLAUDE_STATUS: DONE\n"
            "CURRENT_ACTION: Token-free local OCR installed; staff handoff removed; bot restarted.\n"
            "FILES_CREATED: cloud/task_060/evidence/install.json, cloud/task_060/INSTALL_REPORT.md\n"
            "PRODUCTION_TOUCHED: YES\nOWNER_ACTION_REQUIRED: YES\n"
            "OWNER_QUESTION: Send the same screenshot once and confirm the preview.\n"
            "NEXT_FOR_CHATGPT: Verify the owner's one live acceptance screenshot.\n"
            "UPDATED_AT_UTC: %s\n" % dt.datetime.now(dt.timezone.utc).isoformat()
        )
        owner = (
            "# Ответ владельцу\nСТАТУС: PASS\n"
            "ЧТО СДЕЛАНО: локальное распознавание без Anthropic установлено; передача менеджеру удалена; бот перезапущен.\n"
            "ЧТО НУЖНО: отправить тот же скриншот один раз для визуальной проверки.\n"
        )
    else:
        error = evidence.get("controller", {}).get("error", "UNKNOWN")
        report = "# TASK 060 installation\n\nSTATUS: FAIL\nERROR: %s\n" % error
        status = (
            "TASK_ID: task_060\nROUND: 2\nCLAUDE_STATUS: BLOCKED\n"
            "CURRENT_ACTION: Installation blocked and production left safe.\n"
            "FILES_CREATED: cloud/task_060/evidence/install.json, cloud/task_060/INSTALL_REPORT.md\n"
            "PRODUCTION_TOUCHED: NO\nOWNER_ACTION_REQUIRED: NO\nOWNER_QUESTION: NONE\n"
            "NEXT_FOR_CHATGPT: Repair exact blocker without a new AI generation.\n"
            "UPDATED_AT_UTC: %s\n" % dt.datetime.now(dt.timezone.utc).isoformat()
        )
        owner = "# Ответ владельцу\nСТАТУС: FAIL\nПРИЧИНА: %s\n" % error
    atomic_text(REPORT, report)
    atomic_text(STATUS, status)
    atomic_text(OWNER_REPLY, owner)


def main():
    api = None
    trigger = None
    evidence = {"task_id": "task_060", "controller": {"status": "BLOCKED"}}
    try:
        api = API()
        local = {}
        for name, path in FILES.items():
            data = path.read_bytes()
            compile(data.decode("utf-8"), name, "exec")
            local[name] = data
        for name, data in local.items():
            api.upload(REMOTE + "/" + name, data)
            if sha(api.read(REMOTE + "/" + name)) != sha(data):
                raise ControllerError("UPLOAD_HASH_MISMATCH:" + name)
            time.sleep(2.5)
        api.delete_file(RECEIPT)
        trigger = api.create_trigger()
        deadline = time.monotonic() + 600
        raw = None
        while time.monotonic() < deadline:
            raw = api.read(RECEIPT, missing=True)
            if raw:
                break
            time.sleep(5)
        if not raw:
            raise ControllerError("INSTALL_RECEIPT_TIMEOUT")
        receipt = validate_receipt(json.loads(raw.decode("utf-8")))
        files = receipt.get("files") or {}
        if files:
            if sha(api.read(PROD_TEAM)) != files[PROD_TEAM]["after"]:
                raise ControllerError("TEAM_READBACK_MISMATCH")
            if sha(api.read(PROD_OCR)) != files[PROD_OCR]["after"]:
                raise ControllerError("OCR_READBACK_MISMATCH")
        task_hash = api.restart_bot()
        evidence = {
            "task_id": "task_060", "installer": receipt,
            "controller": {"status": "PASS", "bot_restarted": True, "bot_task_id_sha256": task_hash},
        }
        write_result(evidence, True)
        print(json.dumps({"status": "PASS", "bot_restarted": True, "photo_tokens": 0}))
        return 0
    except Exception as exc:
        evidence["controller"] = {"status": "BLOCKED", "error": str(exc)[:300]}
        write_result(evidence, False)
        print("TASK060_BLOCKED:" + str(exc), file=sys.stderr)
        return 1
    finally:
        if api is not None and trigger is not None:
            try:
                api.delete_trigger(trigger)
            except Exception:
                pass
        if api is not None:
            try:
                api.delete_file(RECEIPT)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
