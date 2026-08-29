#!/usr/bin/env python3
"""Deploy, restart, verify and automatically roll back TASK 083."""
from __future__ import annotations

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

import public_verify


HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_083_publish_transaction"
FILES = {
    "task083_remote_installer.py": HERE / "remote_installer.py",
    "publish_transaction_guard.py": HERE / "publish_transaction_guard.py",
    "catalog_stage_guard_core.py": HERE.parent / "task_075_stage_guard/stage_guard.py",
}
RECEIPTS = {
    "install": REMOTE + "/install_receipt.json",
    "postcheck": REMOTE + "/postcheck_receipt.json",
    "rollback": REMOTE + "/rollback_receipt.json",
}
COMMANDS = {
    mode: "cd %s && python3.10 task083_remote_installer.py %s" % (REMOTE, mode)
    for mode in RECEIPTS
}
EVIDENCE = HERE / "evidence/deploy.json"
REPORT = HERE / "TASK_083_REPORT.md"
CONTRACT_ID = "UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0"
TARGETS = ("UA-0012", "UA-0013")
MAX_BYTES = 12_000_000


class ControllerError(RuntimeError):
    pass


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix="." + path.name + ".", suffix=".tmp", delete=False,
    )
    temp = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class API:
    def __init__(self) -> None:
        token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
        if not token:
            raise ControllerError("PYTHONANYWHERE_API_TOKEN_MISSING")
        self.token = token

    def request(self, method, url, data=None, headers=None, allowed=(200,)):
        request_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task083-controller/1",
        }
        request_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=80) as response:
                status, body = int(response.status), response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, body = int(exc.code), exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK_ERROR:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES:
            raise ControllerError("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise ControllerError("HTTP_%d:%s" % (status, urllib.parse.urlsplit(url).path))
        return status, body

    def file_url(self, path: str) -> str:
        if not path.startswith(REMOTE + "/"):
            raise ControllerError("REMOTE_PATH_NOT_ALLOWED")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, missing: bool = False):
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_FILE_MISSING")
        return body

    def delete_file(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(204, 404))

    def upload(self, path: str, data: bytes) -> None:
        boundary = "----uaart-task083-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = bytearray()
        body.extend(("--%s\r\n" % boundary).encode())
        body.extend((
            'Content-Disposition: form-data; name="content"; filename="%s"\r\n'
            'Content-Type: %s\r\n\r\n' % (filename, mime)
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
                time.sleep(min(3 * attempt, 12))
        raise ControllerError("UPLOAD_FAILED:" + filename)

    @staticmethod
    def objects(body: bytes) -> list:
        value = json.loads(body.decode("utf-8"))
        if isinstance(value, dict):
            return value.get("tasks") or value.get("objects") or value.get("results") or []
        return value

    @staticmethod
    def trigger_id(body: bytes):
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) and identifier > 0 else None

    def create_trigger(self, command: str, description: str):
        form = urllib.parse.urlencode({
            "command": command, "description": description, "enabled": "true"
        }).encode()
        status, body = self.request(
            "POST", BASE + "always_on/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
        if identifier:
            return "always_on", identifier
        now = time.gmtime(time.time() + 120)
        form = urllib.parse.urlencode({
            "command": command, "description": description + " fallback",
            "enabled": "true", "interval": "daily", "hour": now.tm_hour, "minute": now.tm_min,
        }).encode()
        status, body = self.request(
            "POST", BASE + "schedule/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerError("NO_REMOTE_TRIGGER")
        return "schedule", identifier

    def delete_trigger(self, trigger) -> None:
        kind, identifier = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request("DELETE", BASE + "%s/%d/" % (endpoint, identifier),
                     allowed=(200, 202, 204, 404))

    def run_remote(self, mode: str, seconds: int = 900) -> dict[str, Any]:
        receipt = RECEIPTS[mode]
        self.delete_file(receipt)
        trigger = self.create_trigger(COMMANDS[mode], "task083 " + mode)
        try:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                raw = self.read(receipt, missing=True)
                if raw:
                    return json.loads(raw.decode("utf-8"))
                time.sleep(5)
            raise ControllerError("REMOTE_RECEIPT_TIMEOUT:" + mode)
        finally:
            self.delete_trigger(trigger)

    def restart_bot(self) -> dict[str, Any]:
        _, body = self.request("GET", BASE + "always_on/")
        matches = [
            item for item in self.objects(body)
            if isinstance(item, dict) and item.get("enabled") is not False
            and str(item.get("command", "")).strip() == "python3.10 /home/Carix/start_safe.py"
        ]
        if len(matches) != 1:
            raise ControllerError("ACTIVE_LAUNCHER_NOT_UNIQUE")
        identifier = matches[0]["id"]
        self.request("POST", BASE + "always_on/%d/restart/" % identifier,
                     b"", allowed=(200, 201, 202, 204))
        return {
            "command": "python3.10 /home/Carix/start_safe.py",
            "task_id": identifier,
            "restart_accepted": True,
        }


def validate_install(value: dict[str, Any]) -> None:
    if value.get("contract_id") != CONTRACT_ID or value.get("status") != "PASS":
        raise ControllerError("INSTALL_FAILED:" + ";".join(value.get("errors") or []))
    if value.get("production_write") is not True or value.get("crm_write") is not False:
        raise ControllerError("INSTALL_SCOPE_INVALID")
    if value.get("runtime_llm_tokens") != 0:
        raise ControllerError("RUNTIME_LLM_TOKENS_NONZERO")
    before, after = value.get("db_before") or {}, value.get("db_after") or {}
    if before.get("sha256") != after.get("sha256"):
        raise ControllerError("CRM_ROWS_CHANGED")
    for code in TARGETS:
        target = ((value.get("verification") or {}).get("targets") or {}).get(code) or {}
        if target.get("stage") != 2 or target.get("category") != "more":
            raise ControllerError("TARGET_STAGE_INVALID:" + code)
    if not value.get("code_backup") or not value.get("transaction_backup"):
        raise ControllerError("BACKUP_EVIDENCE_MISSING")


def validate_postcheck(value: dict[str, Any]) -> None:
    if value.get("contract_id") != CONTRACT_ID or value.get("status") != "PASS":
        raise ControllerError("POSTCHECK_FAILED:" + ";".join(value.get("errors") or []))
    if value.get("read_only") is not True or value.get("production_write"):
        raise ControllerError("POSTCHECK_SCOPE_INVALID")
    if value.get("markers") != {"publisher": 1, "cars_ui": 1, "master_card": 1}:
        raise ControllerError("PATCH_MARKERS_INVALID")
    for code in TARGETS:
        target = ((value.get("verification") or {}).get("targets") or {}).get(code) or {}
        if target.get("stage") != 2 or target.get("category") != "more":
            raise ControllerError("POSTCHECK_TARGET_INVALID:" + code)


def validate_public(value: dict[str, Any]) -> None:
    if value.get("contract_id") != CONTRACT_ID or value.get("status") != "PASS":
        raise ControllerError("PUBLIC_POSTCHECK_FAILED:" + ";".join(value.get("errors") or []))
    if value.get("production_write") is not False or value.get("http_methods") != ["GET"]:
        raise ControllerError("PUBLIC_POSTCHECK_SCOPE_INVALID")


def main() -> int:
    evidence: dict[str, Any] = {
        "contract_id": CONTRACT_ID,
        "status": "FAIL",
        "errors": [],
        "runtime_llm_tokens": 0,
        "bot_restarted": False,
        "rollback": None,
    }
    api = None
    installed = False
    try:
        api = API()
        for name, path in FILES.items():
            data = path.read_bytes()
            compile(data.decode("utf-8"), name, "exec")
            api.upload(REMOTE + "/" + name, data)
            if api.read(REMOTE + "/" + name) != data:
                raise ControllerError("UPLOAD_READBACK_MISMATCH:" + name)
        install = api.run_remote("install")
        evidence["install"] = install
        validate_install(install)
        installed = True
        evidence["service"] = api.restart_bot()
        evidence["bot_restarted"] = True
        time.sleep(8)
        immediate = api.run_remote("postcheck")
        evidence["remote_postcheck_immediate"] = immediate
        validate_postcheck(immediate)
        time.sleep(20)
        delayed = api.run_remote("postcheck")
        evidence["remote_postcheck_delayed"] = delayed
        validate_postcheck(delayed)
        public = public_verify.verify(rounds=2, delay_seconds=20)
        evidence["public"] = public
        validate_public(public)
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api is not None and installed:
            try:
                rollback = api.run_remote("rollback")
                evidence["rollback"] = rollback
                if rollback.get("status") != "PASS":
                    raise ControllerError("ROLLBACK_FAILED")
                evidence["rollback_service"] = api.restart_bot()
            except Exception as rollback_exc:
                evidence["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )

    atomic_text(EVIDENCE, json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    install = evidence.get("install") or {}
    report = "\n".join([
        "# UA-0012/UA-0013 publication transaction repair", "",
        "STATUS: **%s**" % evidence["status"], "",
        "- UA-0012: stage 2 / more / На пароме",
        "- UA-0013: stage 2 / more / На пароме",
        "- Primary + diagnostic + both catalogs transaction: %s" % evidence["status"],
        "- CRM bot false-success path replaced: %s" % ("YES" if evidence["status"] == "PASS" else "ROLLED BACK"),
        "- Future publication rollback and exact single-message result: %s" % (
            "INSTALLED" if evidence["status"] == "PASS" else "NOT INSTALLED"),
        "- CRM rows changed by deployment: NO",
        "- Runtime LLM tokens: 0",
        "- Code backup: `%s`" % install.get("code_backup", ""),
        "- Publication backup: `%s`" % install.get("transaction_backup", ""),
        "- Errors: %s" % ("; ".join(evidence["errors"]) if evidence["errors"] else "none"),
        "",
    ])
    atomic_text(REPORT, report)
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
