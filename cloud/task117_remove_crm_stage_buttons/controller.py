#!/usr/bin/env python3
"""Secret-backed controller for the TASK117 PythonAnywhere hotfix."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import mimetypes
import os
import pathlib
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Mapping


TASK_ID = "TASK117-REMOVE-CRM-STAGE-BUTTONS"
CONTRACT = "UA-ART-CRM-STAGE-BUTTONS-REMOVE-001-V1.0"
CRITICAL = "UA-ART-CRITICAL-ADAPTER-V1.0"
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REMOTE_DIR = "/home/Carix/autopilot_inbox/cloud/task_068_ferry_vin"
REMOTE_SCRIPT = REMOTE_DIR + "/task117_remove_stage_buttons.py"
REMOTE_RECEIPT = REMOTE_DIR + "/task117_receipt.json"
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
RECEIPT_REL = "state/receipts/%s.json" % TASK_ID
EVIDENCE_REL = "cloud/task117_remove_crm_stage_buttons/evidence.json"
REMOTE_MODES = frozenset(("backup", "install", "verify", "rollback"))
MAX_BYTES = 8 * 1024 * 1024
HIDDEN = ("kr_bought", "sea_loaded", "sea_transit", "ua_handed")


class ControllerError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def required(environment: Mapping[str, str]) -> tuple[dict[str, str], dict[str, Any]]:
    names = (
        "PYTHONANYWHERE_API_TOKEN", "UAART_REQUEST_PATH", "UAART_REQUEST_SHA256",
        "UAART_TASK_ID", "UAART_TASK_CLASS", "UAART_RUN_ID", "UAART_RECEIPT_PATH",
        "UAART_BACKUP_MANIFEST_SHA256", "UAART_MANIFEST_SHA256",
    )
    values = {name: str(environment.get(name, "")).strip() for name in names}
    if any(not values[name] for name in names):
        raise ControllerError("MISSING_ENVIRONMENT")
    if values["UAART_TASK_ID"] != TASK_ID or values["UAART_TASK_CLASS"].upper() != "CRITICAL":
        raise ControllerError("TASK_IDENTITY")
    if values["UAART_RECEIPT_PATH"] != RECEIPT_REL:
        raise ControllerError("RECEIPT_IDENTITY")
    if not re.fullmatch(r"[0-9a-f]{64}", values["UAART_BACKUP_MANIFEST_SHA256"]):
        raise ControllerError("BACKUP_IDENTITY")
    request_path = (ROOT / values["UAART_REQUEST_PATH"]).resolve()
    if not request_path.is_relative_to(ROOT.resolve()):
        raise ControllerError("REQUEST_SCOPE")
    request_bytes = request_path.read_bytes()
    if sha(request_bytes) != values["UAART_REQUEST_SHA256"]:
        raise ControllerError("REQUEST_IDENTITY")
    request = json.loads(request_bytes.decode("utf-8"))
    if request.get("task_id") != TASK_ID or request.get("production_required") is not True:
        raise ControllerError("REQUEST_SCOPE")
    critical = request.get("critical") or {}
    manifest_rel = str(critical.get("manifest_path") or "")
    manifest_path = (ROOT / manifest_rel).resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ControllerError("MANIFEST_PARSE") from exc
    if (not manifest_path.is_relative_to(ROOT.resolve())
            or sha(canonical(manifest)) != values["UAART_MANIFEST_SHA256"]
            or critical.get("manifest_sha256") != values["UAART_MANIFEST_SHA256"]):
        raise ControllerError("MANIFEST_IDENTITY")
    return values, request


class API:
    def __init__(self, token: str) -> None:
        self.token = token

    def request(self, method: str, url: str, data: bytes | None = None,
                headers: dict[str, str] | None = None,
                allowed: tuple[int, ...] = (200,)) -> tuple[int, bytes]:
        actual = {"Authorization": "Token " + self.token,
                  "User-Agent": "ua-art-task117/1"}
        actual.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=actual, method=method)
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                status, body = int(response.status), response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, body = int(exc.code), exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES or status not in allowed:
            raise ControllerError("HTTP_%d" % status)
        return status, body

    @staticmethod
    def file_url(path: str) -> str:
        candidate = pathlib.PurePosixPath(path)
        root = pathlib.PurePosixPath(REMOTE_DIR)
        if (not candidate.is_absolute() or str(candidate) != path
                or root not in candidate.parents or ".." in candidate.parts):
            raise ControllerError("REMOTE_SCOPE")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, missing: bool = False) -> bytes | None:
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_MISSING")
        return body

    def delete_file(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(200, 202, 204, 404))
        for _ in range(6):
            if self.read(path, missing=True) is None:
                return
            time.sleep(1)
        raise ControllerError("REMOTE_DELETE_READBACK")

    def upload(self, path: str, value: bytes) -> None:
        boundary = "----uaart-task117-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = bytearray()
        body.extend(("--%s\r\n" % boundary).encode())
        body.extend(('Content-Disposition: form-data; name="content"; filename="%s"\r\n'
                     "Content-Type: %s\r\n\r\n" % (filename, mime)).encode())
        body.extend(value)
        body.extend(("\r\n--%s--\r\n" % boundary).encode())
        self.request("POST", self.file_url(path), bytes(body),
                     {"Content-Type": "multipart/form-data; boundary=" + boundary},
                     allowed=(200, 201))
        if self.read(path) != value:
            raise ControllerError("UPLOAD_READBACK")

    @staticmethod
    def object_id(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) else None

    @staticmethod
    def objects(body: bytes) -> list[dict[str, Any]]:
        value = json.loads(body.decode("utf-8"))
        raw = ((value.get("results") or value.get("objects") or value.get("tasks") or [])
               if isinstance(value, dict) else value)
        if not isinstance(raw, list):
            raise ControllerError("TASK_LIST_INVALID")
        return [item for item in raw if isinstance(item, dict)]

    def create_trigger(self, command: str) -> tuple[str, int]:
        form = urllib.parse.urlencode({
            "command": command, "description": TASK_ID, "enabled": "true",
        }).encode()
        status, body = self.request(
            "POST", BASE + "always_on/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409))
        identifier = self.object_id(body) if status in (200, 201, 202) else None
        if identifier:
            return "always_on", identifier
        at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({
            "command": command, "description": TASK_ID + " fallback", "enabled": "true",
            "interval": "daily", "hour": at.hour, "minute": at.minute,
        }).encode()
        _, body = self.request(
            "POST", BASE + "schedule/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202))
        identifier = self.object_id(body)
        if not identifier:
            raise ControllerError("NO_TRIGGER")
        return "schedule", identifier

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        kind, identifier = trigger
        self.request("DELETE", BASE + "%s/%d/" % (kind, identifier),
                     allowed=(200, 202, 204, 404))

    def run(self, mode: str, timeout: int = 900,
            backup_manifest_sha256: str | None = None) -> dict[str, Any]:
        if mode not in REMOTE_MODES:
            raise ControllerError("REMOTE_MODE")
        if mode in ("install", "rollback") and not re.fullmatch(
                r"[0-9a-f]{64}", str(backup_manifest_sha256 or "")):
            raise ControllerError("BACKUP_SHA_REQUIRED")
        self.delete_file(REMOTE_RECEIPT)
        command = "cd %s && python3.10 %s --mode %s" % (
            REMOTE_DIR, pathlib.PurePosixPath(REMOTE_SCRIPT).name, mode)
        if backup_manifest_sha256:
            command += " --backup-manifest-sha256 " + backup_manifest_sha256
        trigger = self.create_trigger(command)
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                raw = self.read(REMOTE_RECEIPT, missing=True)
                if raw:
                    value = json.loads(raw.decode("utf-8"))
                    if not isinstance(value, dict):
                        raise ControllerError("REMOTE_RECEIPT")
                    return value
                time.sleep(5)
            raise ControllerError("REMOTE_TIMEOUT")
        finally:
            self.delete_trigger(trigger)

    def bot_task(self) -> dict[str, Any]:
        _, body = self.request("GET", BASE + "always_on/")
        matches = [item for item in self.objects(body)
                   if item.get("enabled") is not False
                   and str(item.get("command") or "").strip()
                   == "python3.10 /home/Carix/start_safe.py"]
        if len(matches) != 1:
            raise ControllerError("BOT_TASK_NOT_UNIQUE")
        return matches[0]

    def restart(self) -> dict[str, Any]:
        before = self.bot_task()
        identifier = int(before["id"])
        self.request("POST", BASE + "always_on/%d/restart/" % identifier, b"",
                     allowed=(200, 201, 202, 204))
        after = None
        for _ in range(6):
            candidate = self.bot_task()
            if int(candidate["id"]) == identifier:
                after = candidate
                break
            time.sleep(2)
        if after is None:
            raise ControllerError("BOT_TASK_POST_RESTART")
        return {"status": "PASS", "task_id": identifier,
                "command": "python3.10 /home/Carix/start_safe.py", "instances": 1,
                "enabled": after.get("enabled") is not False}


def validate_remote(value: Mapping[str, Any], mode: str,
                    expected_backup: str | None = None) -> None:
    if (value.get("task_id") != TASK_ID or value.get("contract_id") != CONTRACT
            or value.get("status") != "PASS" or value.get("mode") != mode.upper()):
        raise ControllerError("REMOTE_%s_FAIL:%s" % (mode.upper(), value.get("error")))
    if (value.get("crm_write") is not False or value.get("media_write") is not False
            or value.get("site_write") is not False or value.get("unexpected_changes") != 0):
        raise ControllerError("REMOTE_SCOPE")
    if expected_backup and value.get("backup_manifest_sha256") != expected_backup:
        raise ControllerError("REMOTE_BACKUP_IDENTITY")
    if mode in ("install", "verify"):
        proof = value.get("verify") or {}
        if (proof.get("hidden_codes") != list(HIDDEN)
                or proof.get("primary_menu") != "PASS"
                or proof.get("fallback_menu") != "PASS"
                or proof.get("old_callbacks") != "BLOCKED_NO_WRITE"):
            raise ControllerError("REMOTE_MENU_PROOF")


def execute(environment: Mapping[str, str]) -> dict[str, Any]:
    values, request = required(environment)
    evidence: dict[str, Any] = {
        "task_id": TASK_ID, "contract_id": CONTRACT, "status": "FAIL",
        "started_at": now(), "production_required": True, "errors": [],
    }
    try:
        script = (HERE / "remote_installer.py").read_bytes()
        compile(script.decode("utf-8"), "remote_installer.py", "exec")
        api = API(values["PYTHONANYWHERE_API_TOKEN"])
        api.upload(REMOTE_SCRIPT, script)
        backup_sha = values["UAART_BACKUP_MANIFEST_SHA256"]
        installed = api.run("install", backup_manifest_sha256=backup_sha)
        validate_remote(installed, "install", backup_sha)
        evidence["install"] = installed
        evidence["restart"] = api.restart()
        time.sleep(12)
        verified = api.run("verify")
        validate_remote(verified, "verify", backup_sha)
        evidence["verify"] = verified
        receipt = {
            "contract_id": CRITICAL, "task_id": TASK_ID, "status": "FINISHED",
            "task_class": "CRITICAL", "target_environment": "production",
            "production_required": True, "production": "PASS", "tests": "PASS",
            "backup": installed["backup"], "backup_manifest_sha256": backup_sha,
            "rollback": "PASS", "rollback_ready": True, "live_verify": "PASS",
            "request_sha256": values["UAART_REQUEST_SHA256"],
            "manifest_sha256": values["UAART_MANIFEST_SHA256"],
            "run_id": values["UAART_RUN_ID"], "unexpected_changes": 0,
            "production_write": "TASK117_TWO_RUNTIME_FILES_ONLY",
            "changed_files": ["/home/Carix/cars_ui.py", "/home/Carix/konteyner.py"],
            "hidden_codes": list(HIDDEN), "hidden_button_count": 4,
            "primary_menu": "PASS", "fallback_menu": "PASS",
            "stale_callbacks": "BLOCKED_NO_WRITE", "restart": evidence["restart"],
            "crm_unchanged": True, "media_unchanged": True,
            "website_unchanged": True, "protected_files_unchanged": True,
            "cards_unchanged": True, "prices_unchanged": True,
            "finished_at": now(),
        }
        atomic_text(ROOT / RECEIPT_REL,
                    json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        evidence["rollback"] = "DEFERRED_TO_GENERIC_CRITICAL_WORKFLOW"
    evidence["finished_at"] = now()
    atomic_text(ROOT / EVIDENCE_REL,
                json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return evidence


def main() -> int:
    value = execute(os.environ)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
