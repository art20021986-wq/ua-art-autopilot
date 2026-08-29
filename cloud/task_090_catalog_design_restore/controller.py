#!/usr/bin/env python3
"""Upload, execute, restart, verify and roll back TASK 090."""
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

CONTRACT_ID = "CATALOG-DESIGN-STAGE-RESTORE-090-V1.0"
HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_090_catalog_design_restore"
FILES = {
    "task090_remote_installer.py": HERE / "remote_installer.py",
    "catalog_design_guard.py": HERE / "catalog_design_guard.py",
}
RECEIPTS = {mode: REMOTE + "/%s_receipt.json" % mode
            for mode in ("install", "postcheck", "rollback")}
COMMANDS = {mode: "cd %s && python3.10 task090_remote_installer.py %s" % (REMOTE, mode)
            for mode in RECEIPTS}
EVIDENCE = HERE / "evidence/deploy.json"
REPORT = HERE / "TASK_090_REPORT.md"
MAX_BYTES = 14_000_000

class ControllerError(RuntimeError):
    pass

def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix="." + path.name + ".", suffix=".tmp", delete=False)
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
    def __init__(self) -> None:
        self.token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
        if not self.token:
            raise ControllerError("PYTHONANYWHERE_API_TOKEN_MISSING")

    def request(self, method: str, url: str, data: bytes | None = None,
                headers: dict[str, str] | None = None,
                allowed: tuple[int, ...] = (200,)) -> tuple[int, bytes]:
        all_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task090-controller/1",
        }
        all_headers.update(headers or {})
        request = urllib.request.Request(
            url, data=data, headers=all_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                status, body = int(response.status), response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, body = int(exc.code), exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK_ERROR:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES:
            raise ControllerError("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise ControllerError("HTTP_%d:%s" % (
                status, urllib.parse.urlsplit(url).path))
        return status, body

    @staticmethod
    def objects(body: bytes) -> list[dict[str, Any]]:
        value = json.loads(body.decode("utf-8"))
        if isinstance(value, dict):
            return value.get("tasks") or value.get("objects") or value.get("results") or []
        return value if isinstance(value, list) else []

    @staticmethod
    def identifier(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        result = value.get("id") if isinstance(value, dict) else None
        return result if isinstance(result, int) and result > 0 else None

    @staticmethod
    def file_url(path: str) -> str:
        if not path.startswith(REMOTE + "/"):
            raise ControllerError("REMOTE_PATH_NOT_ALLOWED")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, missing: bool = False) -> bytes | None:
        status, body = self.request(
            "GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_FILE_MISSING:" + path)
        return body

    def delete_file(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(204, 404))

    def upload(self, path: str, data: bytes) -> None:
        boundary = "----uaart-task090-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = bytearray()
        body.extend(("--%s\r\n" % boundary).encode())
        body.extend((
            'Content-Disposition: form-data; name="content"; filename="%s"\r\n'
            "Content-Type: %s\r\n\r\n" % (filename, mime)).encode())
        body.extend(data)
        body.extend(("\r\n--%s--\r\n" % boundary).encode())
        for attempt in range(1, 6):
            status, _ = self.request(
                "POST", self.file_url(path), bytes(body),
                {"Content-Type": "multipart/form-data; boundary=" + boundary},
                allowed=(200, 201, 429, 500, 502, 503, 504))
            if status in (200, 201):
                return
            if attempt < 5:
                time.sleep(min(attempt * 3, 12))
        raise ControllerError("UPLOAD_FAILED:" + filename)

    def create_trigger(self, command: str, description: str):
        form = urllib.parse.urlencode({
            "command": command, "description": description, "enabled": "true"}).encode()
        status, body = self.request(
            "POST", BASE + "always_on/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409))
        identifier = self.identifier(body) if status in (200, 201, 202) else None
        if identifier:
            return ("always_on", identifier)
        moment = time.gmtime(time.time() + 120)
        form = urllib.parse.urlencode({
            "command": command, "description": description + " fallback",
            "enabled": "true", "interval": "daily",
            "hour": moment.tm_hour, "minute": moment.tm_min}).encode()
        status, body = self.request(
            "POST", BASE + "schedule/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409))
        identifier = self.identifier(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerError("NO_REMOTE_TRIGGER")
        return ("schedule", identifier)

    def delete_trigger(self, trigger) -> None:
        kind, identifier = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request("DELETE", BASE + "%s/%d/" % (endpoint, identifier),
                     allowed=(200, 202, 204, 404))

    def run_remote(self, mode: str, seconds: int = 1000) -> dict[str, Any]:
        receipt = RECEIPTS[mode]
        self.delete_file(receipt)
        trigger = self.create_trigger(COMMANDS[mode], "task090 " + mode)
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
            if item.get("enabled") is not False
            and str(item.get("command") or "").strip()
            == "python3.10 /home/Carix/start_safe.py"]
        if len(matches) != 1:
            raise ControllerError("ACTIVE_LAUNCHER_NOT_UNIQUE:%d" % len(matches))
        identifier = int(matches[0]["id"])
        self.request("POST", BASE + "always_on/%d/restart/" % identifier,
                     b"", allowed=(200, 201, 202, 204))
        return {"task_id": identifier, "restart_accepted": True}

def validate_install(value: dict[str, Any]) -> None:
    if value.get("contract_id") != CONTRACT_ID or value.get("status") != "PASS":
        raise ControllerError("INSTALL_FAILED:" + ";".join(value.get("errors") or []))
    if value.get("production_write") is not True or value.get("crm_write") is not False:
        raise ControllerError("INSTALL_SCOPE_INVALID")
    before, after = value.get("db_before") or {}, value.get("db_after") or {}
    if before.get("file_sha256") != after.get("file_sha256"):
        raise ControllerError("CRM_FILE_CHANGED")
    if before.get("rows_sha256") != after.get("rows_sha256"):
        raise ControllerError("CRM_ROWS_CHANGED")
    expected = {"all": 13, "kiev": 3, "georgia": 1, "sea": 7, "korea": 2}
    if before.get("counts") != expected:
        raise ControllerError("STAGE_COUNTS_INVALID")
    if not value.get("backup_root") or not value.get("golden_source"):
        raise ControllerError("BACKUP_OR_GOLDEN_MISSING")
    if any(a.get("status") != "PASS" or a.get("article_cards") != 13
           for a in (value.get("catalogs") or {}).values()):
        raise ControllerError("CATALOG_INSTALL_AUDIT_INVALID")

def validate_postcheck(value: dict[str, Any]) -> None:
    if value.get("contract_id") != CONTRACT_ID or value.get("status") != "PASS":
        raise ControllerError("POSTCHECK_FAILED:" + ";".join(value.get("errors") or []))
    if value.get("read_only") is not True or value.get("production_write") is not False:
        raise ControllerError("POSTCHECK_SCOPE_INVALID")
    if value.get("markers") != {"master": 1, "publish_guard": 1}:
        raise ControllerError("PATCH_MARKERS_INVALID")

def validate_public(value: dict[str, Any]) -> None:
    if value.get("contract_id") != CONTRACT_ID or value.get("status") != "PASS":
        raise ControllerError("PUBLIC_VERIFY_FAILED:" + ";".join(value.get("errors") or []))
    if value.get("production_write") is not False or value.get("http_methods") != ["GET"]:
        raise ControllerError("PUBLIC_VERIFY_SCOPE_INVALID")

def report_text(evidence: dict[str, Any]) -> str:
    passed = evidence["status"] == "PASS"
    install = evidence.get("install") or {}
    return "\n".join([
        "# TASK 090 — восстановление каталога", "",
        "STATUS: **%s**" % evidence["status"], "",
        "- Прежний дизайн: %s" % ("ВОССТАНОВЛЕН" if passed else "НЕ ПОДТВЕРЖДЁН"),
        "- Карточки: %s" % ("13/13" if passed else "FAIL"),
        "- Этапы: %s" % ("13 / 3 / 1 / 7 / 2" if passed else "FAIL"),
        "- Защита от повторной перезаписи: %s" % (
            "УСТАНОВЛЕНА" if passed else "ОТКАЧЕНА"),
        "- CRM изменена: НЕТ",
        "- Backup: %s" % install.get("backup_root", ""),
        "- Ошибки: %s" % (
            "; ".join(evidence["errors"]) if evidence["errors"] else "нет"), ""])

def main() -> int:
    evidence: dict[str, Any] = {
        "contract_id": CONTRACT_ID, "status": "FAIL", "errors": [],
        "installed": False, "bot_restarted": False, "rollback": None}
    api: API | None = None
    try:
        api = API()
        for name, path in FILES.items():
            data = path.read_bytes()
            compile(data.decode("utf-8"), name, "exec")
            remote_path = REMOTE + "/" + name
            api.upload(remote_path, data)
            if api.read(remote_path) != data:
                raise ControllerError("UPLOAD_READBACK_MISMATCH:" + name)
        installed = api.run_remote("install")
        evidence["install"] = installed
        validate_install(installed)
        evidence["installed"] = True
        evidence["service"] = api.restart_bot()
        evidence["bot_restarted"] = True
        time.sleep(8)
        immediate = api.run_remote("postcheck")
        evidence["postcheck_immediate"] = immediate
        validate_postcheck(immediate)
        time.sleep(20)
        delayed = api.run_remote("postcheck")
        evidence["postcheck_delayed"] = delayed
        validate_postcheck(delayed)
        public = public_verify.verify(rounds=2, delay_seconds=20)
        evidence["public"] = public
        validate_public(public)
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api is not None and evidence["installed"]:
            try:
                rollback = api.run_remote("rollback")
                evidence["rollback"] = rollback
                if rollback.get("status") != "PASS":
                    raise ControllerError("ROLLBACK_FAILED")
                evidence["rollback_service"] = api.restart_bot()
            except Exception as rollback_exc:
                evidence["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc))
    atomic_text(EVIDENCE, json.dumps(
        evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    atomic_text(REPORT, report_text(evidence))
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0 if evidence["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())

