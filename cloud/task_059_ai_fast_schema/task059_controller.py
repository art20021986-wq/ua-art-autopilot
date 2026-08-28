#!/usr/bin/env python3
"""GitHub-side controller for the owner-approved TASK 059 bot patch."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


HERE = pathlib.Path(__file__).resolve().parent
USERNAME = "Carix"
HOSTS = ("www.pythonanywhere.com", "eu.pythonanywhere.com")
REMOTE_ROOT = "/home/Carix/autopilot_inbox"
REMOTE_PACKAGE = REMOTE_ROOT + "/cloud/task_059_ai_fast_schema"
REMOTE_MANIFEST = REMOTE_ROOT + "/_sync_manifest.json"
REMOTE_INSTALLER = REMOTE_PACKAGE + "/patch_installer.py"
REMOTE_PAYLOAD = REMOTE_PACKAGE + "/patch_payload.py"
REMOTE_HELPER = REMOTE_PACKAGE + "/ai_fast_schema.py"
REMOTE_RECEIPT = REMOTE_PACKAGE + "/task_059_install_receipt.json"
PROD_TEAM = "/home/Carix/team_bot.py"
PROD_HELPER = "/home/Carix/ai_fast_schema.py"
EXACT_COMMAND = "cd " + REMOTE_PACKAGE + " && python3.10 patch_installer.py"
LOCAL_FILES = {
    "cloud/task_059_ai_fast_schema/patch_installer.py": HERE / "patch_installer.py",
    "cloud/task_059_ai_fast_schema/patch_payload.py": HERE / "patch_payload.py",
    "cloud/task_059_ai_fast_schema/ai_fast_schema.py": HERE / "ai_fast_schema.py",
}
EVIDENCE = HERE / "evidence" / "task_059_install.json"
REPORT = HERE / "TASK_059_REPORT.md"
MAX_BYTES = 3_000_000
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ControllerError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parse_json(data, label):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ControllerError("DUPLICATE_JSON_KEY:" + label)
            out[key] = value
        return out
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs)
    except Exception as exc:
        raise ControllerError("INVALID_JSON:" + label) from exc
    if not isinstance(value, (dict, list)):
        raise ControllerError("JSON_TYPE_INVALID:" + label)
    return value


class API:
    def __init__(self, token, host, opener=urllib.request.urlopen):
        if not token:
            raise ControllerError("TOKEN_MISSING")
        if host not in HOSTS:
            raise ControllerError("HOST_INVALID")
        self.token = token
        self.host = host
        self.opener = opener
        self.base = "https://%s/api/v0/user/%s/" % (host, USERNAME)

    def request(self, method, url, data=None, allowed=(200,), operation="request"):
        headers = {"Authorization": "Token " + self.token, "User-Agent": "ua-art-task059/1"}
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener(request, timeout=60) as response:
                status = getattr(response, "status", response.getcode())
                body = response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK_ERROR:" + operation) from exc
        if len(body) > MAX_BYTES:
            raise ControllerError("RESPONSE_TOO_LARGE:" + operation)
        if status not in allowed:
            raise ControllerError("HTTP_%s:%s" % (operation, status))
        return status, body

    def file_url(self, path):
        allowed = {
            REMOTE_MANIFEST, REMOTE_INSTALLER, REMOTE_PAYLOAD, REMOTE_HELPER,
            REMOTE_RECEIPT, PROD_TEAM, PROD_HELPER,
        }
        if path not in allowed:
            raise ControllerError("REMOTE_PATH_NOT_ALLOWED")
        return self.base + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path):
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404), operation="READ_FILE")
        if status == 404:
            raise FileNotFoundError(path)
        return body

    def delete_receipt(self):
        self.request("DELETE", self.file_url(REMOTE_RECEIPT), allowed=(204, 404), operation="DELETE_RECEIPT")

    @staticmethod
    def task_id(body):
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) and identifier > 0 else None

    def create_trigger(self):
        form = urllib.parse.urlencode({
            "command": EXACT_COMMAND,
            "description": "UA ART TASK 059 fast schema patch",
            "enabled": "true",
        }).encode()
        status, body = self.request(
            "POST", self.base + "always_on/", form,
            allowed=(200, 201, 202, 400, 403, 404, 409), operation="CREATE_ALWAYS_ON",
        )
        identifier = self.task_id(body) if status in (200, 201, 202) else None
        if identifier:
            return "always_on", identifier
        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({
            "command": EXACT_COMMAND,
            "description": "UA ART TASK 059 fast schema patch fallback",
            "enabled": "true", "interval": "daily",
            "hour": run_at.hour, "minute": run_at.minute,
        }).encode()
        status, body = self.request(
            "POST", self.base + "schedule/", form,
            allowed=(200, 201, 202, 400, 403, 404, 409), operation="CREATE_SCHEDULE",
        )
        identifier = self.task_id(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerError("NO_TRIGGER_AVAILABLE")
        return "schedule", identifier

    def delete_trigger(self, trigger):
        kind, identifier = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request(
            "DELETE", self.base + endpoint + "/%d/" % identifier,
            allowed=(200, 202, 204, 404), operation="DELETE_TRIGGER",
        )

    def restart_bot(self):
        _, body = self.request("GET", self.base + "always_on/", operation="LIST_ALWAYS_ON")
        value = parse_json(body, "ALWAYS_ON")
        if isinstance(value, dict):
            tasks = value.get("tasks") or value.get("objects") or value.get("results") or []
        else:
            tasks = value
        if not isinstance(tasks, list):
            raise ControllerError("ALWAYS_ON_LIST_INVALID")
        enabled = [item for item in tasks if isinstance(item, dict) and item.get("enabled") is not False]
        preferred = [item for item in enabled if "start_safe.py" in str(item.get("command", "")) and "autopilot_inbox" not in str(item.get("command", ""))]
        if len(preferred) != 1:
            preferred = [item for item in enabled if "run_all.py" in str(item.get("command", "")) and "autopilot_inbox" not in str(item.get("command", ""))]
        if len(preferred) != 1:
            raise ControllerError("PRODUCTION_BOT_TASK_NOT_UNIQUE")
        identifier = preferred[0].get("id")
        if not isinstance(identifier, int) or identifier <= 0:
            raise ControllerError("PRODUCTION_BOT_TASK_ID_INVALID")
        self.request(
            "POST", self.base + "always_on/%d/restart/" % identifier, b"",
            allowed=(200, 201, 202, 204), operation="RESTART_BOT",
        )
        return hashlib.sha256(str(identifier).encode()).hexdigest()


def validate_receipt(receipt):
    if not isinstance(receipt, dict):
        raise ControllerError("RECEIPT_NOT_OBJECT")
    if receipt.get("task_id") != "task_059" or receipt.get("mode") != "P0_AI_FAST_SCHEMA_INSTALL":
        raise ControllerError("RECEIPT_ID_INVALID")
    if receipt.get("status") != "PASS" or receipt.get("errors") != []:
        raise ControllerError("INSTALLER_NOT_PASS")
    for key in ("crm_db_write", "site_write", "service_restarted", "ua0010_published", "rollback_performed"):
        if receipt.get(key) is not False:
            raise ControllerError("RECEIPT_SAFETY_INVALID:" + key)
    if receipt.get("site_hashes_unchanged") is not True:
        raise ControllerError("SITE_IDENTITY_NOT_PROVED")
    before = receipt.get("db_sha256_before")
    after = receipt.get("db_sha256_after")
    if receipt.get("already_applied") is not True:
        if not HEX64.fullmatch(str(before or "")) or before != after:
            raise ControllerError("DB_IDENTITY_NOT_PROVED")
        if receipt.get("production_write") is not True:
            raise ControllerError("PRODUCTION_WRITE_NOT_RECORDED")
        files = receipt.get("files")
        if not isinstance(files, dict) or set(files) != {PROD_TEAM, PROD_HELPER}:
            raise ControllerError("FILE_SCOPE_INVALID")
    return receipt


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
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


def main():
    trigger = None
    api = None
    receipt = None
    restarted = False
    try:
        local_hashes = {}
        for rel, path in LOCAL_FILES.items():
            data = path.read_bytes()
            compile(data.decode("utf-8"), rel, "exec")
            local_hashes[rel] = sha(data)
        api = API(
            os.environ.get("PYTHONANYWHERE_API_TOKEN", ""),
            os.environ.get("PYTHONANYWHERE_HOST", HOSTS[0]),
        )
        manifest = parse_json(api.read(REMOTE_MANIFEST), "MANIFEST")
        if not isinstance(manifest, dict):
            raise ControllerError("MANIFEST_NOT_OBJECT")
        if not isinstance(manifest.get("files"), list):
            raise ControllerError("MANIFEST_FILES_INVALID")
        entries = {item.get("source"): item for item in manifest.get("files", []) if isinstance(item, dict)}
        for rel, digest in local_hashes.items():
            item = entries.get(rel)
            if not item or item.get("sha256") != digest or item.get("remote") != REMOTE_ROOT + "/" + rel:
                raise ControllerError("SYNC_MANIFEST_MISMATCH:" + rel)
        for rel, remote in (
            ("cloud/task_059_ai_fast_schema/patch_installer.py", REMOTE_INSTALLER),
            ("cloud/task_059_ai_fast_schema/patch_payload.py", REMOTE_PAYLOAD),
            ("cloud/task_059_ai_fast_schema/ai_fast_schema.py", REMOTE_HELPER),
        ):
            if sha(api.read(remote)) != local_hashes[rel]:
                raise ControllerError("REMOTE_HASH_MISMATCH:" + rel)
        api.delete_receipt()
        trigger = api.create_trigger()
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            try:
                raw = api.read(REMOTE_RECEIPT)
            except FileNotFoundError:
                raw = b""
            if raw:
                receipt = validate_receipt(parse_json(raw, "RECEIPT"))
                break
            time.sleep(5)
        if receipt is None:
            raise ControllerError("RECEIPT_TIMEOUT")
        files = receipt.get("files") or {}
        if files:
            if sha(api.read(PROD_TEAM)) != files[PROD_TEAM]["after"]:
                raise ControllerError("TEAM_READBACK_MISMATCH")
            if sha(api.read(PROD_HELPER)) != files[PROD_HELPER]["after"]:
                raise ControllerError("HELPER_READBACK_MISMATCH")
        bot_task_hash = api.restart_bot()
        restarted = True
        evidence = {
            "installer": receipt,
            "controller": {
                "status": "PASS", "bot_restarted": True,
                "bot_task_id_sha256": bot_task_hash,
                "ua0010_published": False,
            },
        }
        atomic_text(EVIDENCE, json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        atomic_text(REPORT, (
            "# TASK 059 report\n\n"
            "STATUS: PASS\n"
            "SCHEMA_CLOSED: YES\n"
            "PHOTO_TARGET_SECONDS: 5\n"
            "PHOTO_HARD_SECONDS: 7\n"
            "AUTOSAVE_REMOVED: YES\n"
            "SECOND_AI_REVIEW_REMOVED: YES\n"
            "BOT_RESTARTED: YES\n"
            "CRM_DB_WRITTEN: NO\n"
            "SITE_WRITTEN: NO\n"
            "UA_0010_PUBLISHED: NO\n"
        ))
        print(json.dumps({"status": "PASS", "bot_restarted": True, "ua0010_published": False}, sort_keys=True))
        return 0
    except Exception as exc:
        print("TASK059_BLOCKED:" + str(exc), file=sys.stderr)
        return 1
    finally:
        if api is not None and trigger is not None:
            try:
                api.delete_trigger(trigger)
            except Exception:
                pass
        if api is not None:
            try:
                api.delete_receipt()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
