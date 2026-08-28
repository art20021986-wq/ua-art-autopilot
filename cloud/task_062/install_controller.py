#!/usr/bin/env python3
"""Upload, install, restart, and verify CRM-VOICE-FILL-001."""
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
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_062"
FILES = {
    "patch_installer.py": HERE / "patch_installer.py",
    "patch_payload.py": HERE / "patch_payload.py",
    "postcheck.py": HERE / "postcheck.py",
}
INSTALL_RECEIPT = REMOTE + "/install_receipt.json"
POSTCHECK_RECEIPT = REMOTE + "/postcheck.json"
PROD_CARS = "/home/Carix/cars_ui.py"
PROD_TEAM = "/home/Carix/team_bot.py"
INSTALL_COMMAND = "cd " + REMOTE + " && python3.10 patch_installer.py"
POSTCHECK_COMMAND = "cd " + REMOTE + " && python3.10 postcheck.py"
EVIDENCE = HERE / "evidence" / "install.json"
REPORT = HERE / "INSTALL_REPORT.md"
STATUS = pathlib.Path("cloud/latest_status.md")
OWNER_REPLY = pathlib.Path("cloud/owner_reply.md")
MAX_BYTES = 4_000_000
HEX = re.compile(r"^[0-9a-f]{64}$")


class ControllerError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic_text(path, value):
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
            "User-Agent": "ua-art-task062-crm-voice/1",
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

    def run_remote(self, command, description, receipt_path, seconds=600):
        self.delete_file(receipt_path)
        trigger = self.create_trigger(command, description)
        try:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                raw = self.read(receipt_path, missing=True)
                if raw:
                    return raw
                time.sleep(5)
            raise ControllerError("REMOTE_RECEIPT_TIMEOUT:" + pathlib.PurePosixPath(receipt_path).name)
        finally:
            self.delete_trigger(trigger)

    def restart_bot(self):
        _, body = self.request("GET", BASE + "always_on/")
        value = json.loads(body.decode("utf-8"))
        tasks = (
            value.get("tasks") or value.get("objects") or value.get("results") or []
            if isinstance(value, dict) else value
        )
        preferred = [
            item for item in tasks
            if isinstance(item, dict) and item.get("enabled") is not False
            and "start_safe.py" in str(item.get("command", ""))
            and "autopilot_inbox" not in str(item.get("command", ""))
        ]
        if len(preferred) != 1:
            raise ControllerError("PRODUCTION_BOT_TASK_NOT_UNIQUE")
        ident = preferred[0].get("id")
        self.request("POST", BASE + "always_on/%d/restart/" % ident,
                     b"", allowed=(200, 201, 202, 204))
        return sha(str(ident).encode())


def validate_install(value):
    if not isinstance(value, dict):
        raise ControllerError("INSTALL_RECEIPT_INVALID")
    if value.get("task_id") != "task_062" or value.get("contract_id") != "CRM-VOICE-FILL-001":
        raise ControllerError("INSTALL_ID_INVALID")
    if value.get("status") != "PASS" or value.get("errors") != []:
        raise ControllerError("INSTALL_NOT_PASS:" + ",".join(value.get("errors") or []))
    for key in ("crm_db_write", "site_write", "service_restarted", "rollback_performed",
                "automatic_new_card"):
        if value.get(key) is not False:
            raise ControllerError("SAFETY_MARKER_INVALID:" + key)
    if value.get("voice_deadline_seconds") != 15:
        raise ControllerError("VOICE_DEADLINE_INVALID")
    if value.get("llm_tokens_per_voice") != 0 or value.get("stt_calls_max_per_voice") != 1:
        raise ControllerError("VOICE_COST_MARKER_INVALID")
    for key in ("fill_empty_only", "explicit_override_supported", "deduplication", "undo",
                "card_count_unchanged", "ua0009_unchanged"):
        if value.get(key) is not True:
            raise ControllerError("FUNCTIONAL_MARKER_INVALID:" + key)
    if value.get("crm_db_sha256_before") != value.get("crm_db_sha256_after"):
        raise ControllerError("CRM_DB_HASH_CHANGED")
    if value.get("site_state_sha256_before") != value.get("site_state_sha256_after"):
        raise ControllerError("SITE_HASH_CHANGED")
    after = value.get("readonly_after") or {}
    if after.get("quick_check") != "ok" or after.get("ua0009_rows") != 1:
        raise ControllerError("CRM_READONLY_CHECK_INVALID")
    files = value.get("files") or {}
    if set(files) != {PROD_CARS, PROD_TEAM}:
        raise ControllerError("FILE_SCOPE_INVALID")
    for metadata in files.values():
        if not HEX.fullmatch(str(metadata.get("after") or "")):
            raise ControllerError("FILE_HASH_INVALID")
    return value


def validate_postcheck(value):
    if not isinstance(value, dict):
        raise ControllerError("POSTCHECK_INVALID")
    if value.get("task_id") != "task_062" or value.get("status") != "PASS":
        raise ControllerError("POSTCHECK_NOT_PASS")
    for key in ("production_write", "crm_db_write", "site_write"):
        if value.get(key) is not False:
            raise ControllerError("POSTCHECK_WRITE_MARKER_INVALID:" + key)
    for key in ("code_readback", "db_hash_unchanged", "site_unchanged",
                "card_count_unchanged", "ua0009_unchanged"):
        if value.get(key) is not True:
            raise ControllerError("POSTCHECK_MARKER_INVALID:" + key)
    if value.get("db_quick_check") != "ok" or value.get("ua0009_rows") != 1:
        raise ControllerError("POSTCHECK_CRM_INVALID")
    return value


def write_result(evidence, ok):
    atomic_text(EVIDENCE, json.dumps(evidence, ensure_ascii=False, indent=2,
                                     sort_keys=True) + "\n")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    if ok:
        report = (
            "# CRM-VOICE-FILL-001 installation\n\n"
            "STATUS: PASS\nVOICE_LIMIT: 15_SECONDS\n"
            "ACTIVE_CARD_ONLY: YES\nAUTO_NEW_CARD: NO\n"
            "FILL_EMPTY_ONLY: YES\nEXPLICIT_OVERRIDE: YES\n"
            "DEDUPLICATION: YES\nUNDO: YES\n"
            "LLM_TOKENS: 0\nSTT_CALLS_MAX: 1\nBOT_RESTARTED: YES\n"
            "CRM_DB_CHANGED: NO\nSITE_CHANGED: NO\nUA_0009_CHANGED: NO\n"
        )
        status = (
            "TASK_ID: task_062\nCONTRACT_ID: CRM-VOICE-FILL-001\n"
            "CLAUDE_STATUS: DONE\n"
            "CURRENT_ACTION: Voice now fills only the explicitly open CRM card; no automatic new card; bot restarted.\n"
            "PRODUCTION_TOUCHED: YES\nCRM_DB_TOUCHED: NO\nSITE_TOUCHED: NO\n"
            "OWNER_ACTION_REQUIRED: YES\n"
            "OWNER_QUESTION: Reopen UA-0009 and send one short voice value for visual acceptance.\n"
            "UPDATED_AT_UTC: %s\n" % now
        )
        owner = (
            "# Ответ владельцу\nСТАТУС: PASS\n"
            "Голос привязан к открытой карточке; новая карточка автоматически не создаётся; "
            "лимит 15 секунд; 0 LLM-токенов; бот перезапущен.\n"
            "ПРОВЕРКА: снова откройте UA-0009 и отправьте короткое «привод передний».\n"
        )
    else:
        error = evidence.get("controller", {}).get("error", "UNKNOWN")
        report = "# CRM-VOICE-FILL-001 installation\n\nSTATUS: FAIL\nERROR: %s\n" % error
        status = (
            "TASK_ID: task_062\nCONTRACT_ID: CRM-VOICE-FILL-001\n"
            "CLAUDE_STATUS: BLOCKED\nCURRENT_ACTION: Install or verification blocked.\n"
            "OWNER_ACTION_REQUIRED: NO\nOWNER_QUESTION: NONE\nUPDATED_AT_UTC: %s\n" % now
        )
        owner = "# Ответ владельцу\nСТАТУС: FAIL\nПРИЧИНА: %s\n" % error
    atomic_text(REPORT, report)
    atomic_text(STATUS, status)
    atomic_text(OWNER_REPLY, owner)


def main():
    api = None
    evidence = {
        "task_id": "task_062", "contract_id": "CRM-VOICE-FILL-001",
        "controller": {"status": "BLOCKED"},
    }
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

        raw_install = api.run_remote(
            INSTALL_COMMAND, "TASK 062 CRM-VOICE-FILL-001 install", INSTALL_RECEIPT)
        install = validate_install(json.loads(raw_install.decode("utf-8")))
        for path, metadata in (install.get("files") or {}).items():
            if sha(api.read(path)) != metadata["after"]:
                raise ControllerError("CODE_READBACK_MISMATCH:" + pathlib.PurePosixPath(path).name)

        task_hash = api.restart_bot()
        time.sleep(8)
        raw_post = api.run_remote(
            POSTCHECK_COMMAND, "TASK 062 CRM-VOICE-FILL-001 postcheck", POSTCHECK_RECEIPT)
        postcheck = validate_postcheck(json.loads(raw_post.decode("utf-8")))
        evidence = {
            "task_id": "task_062", "contract_id": "CRM-VOICE-FILL-001",
            "installer": install, "post_restart": postcheck,
            "controller": {
                "status": "PASS", "bot_restarted": True,
                "bot_task_id_sha256": task_hash,
            },
        }
        write_result(evidence, True)
        print(json.dumps({"status": "PASS", "bot_restarted": True,
                          "voice_seconds": 15, "automatic_new_card": False}))
        return 0
    except Exception as exc:
        evidence["controller"] = {"status": "BLOCKED", "error": str(exc)[:300]}
        write_result(evidence, False)
        print("TASK062_BLOCKED:" + str(exc), file=sys.stderr)
        return 1
    finally:
        if api is not None:
            for path in (POSTCHECK_RECEIPT, INSTALL_RECEIPT):
                try:
                    api.delete_file(path)
                except Exception:
                    pass


if __name__ == "__main__":
    raise SystemExit(main())
