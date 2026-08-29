#!/usr/bin/env python3
"""Upload, preflight, install, restart, verify and roll back TASK 091."""
from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any


CONTRACT_ID = "CRM-NUMERIC-SINGLE-CLAIM-091-V1.0"
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_091_numeric_claim_guard"
FILES = {
    "field_claim_guard.py": HERE / "field_claim_guard.py",
    "patcher.py": HERE / "patcher.py",
    "task091_remote_installer.py": HERE / "remote_installer.py",
}
RECEIPTS = {
    mode: REMOTE + "/%s_receipt.json" % mode
    for mode in ("preflight", "install", "postcheck", "rollback")
}
COMMANDS = {
    mode: "cd %s && python3.10 task091_remote_installer.py %s" % (REMOTE, mode)
    for mode in RECEIPTS
}
EVIDENCE = HERE / "evidence/deploy.json"
REPORT = HERE / "TASK_091_REPORT.md"
LATEST_STATUS = REPO / "cloud/latest_status.md"
OWNER_REPLY = REPO / "cloud/owner_reply.md"
MAX_BYTES = 14_000_000


class ControllerError(RuntimeError):
    pass


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix="." + path.name + ".", suffix=".tmp", delete=False,
    )
    temporary = Path(handle.name)
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

    def request(
        self,
        method: str,
        url: str,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        allowed: tuple[int, ...] = (200,),
    ) -> tuple[int, bytes]:
        all_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task091-controller/1",
        }
        all_headers.update(headers or {})
        request = urllib.request.Request(
            url, data=data, headers=all_headers, method=method
        )
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
                status, urllib.parse.urlsplit(url).path
            ))
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
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) and identifier > 0 else None

    @staticmethod
    def file_url(path: str) -> str:
        if not path.startswith(REMOTE + "/"):
            raise ControllerError("REMOTE_PATH_NOT_ALLOWED")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, missing: bool = False) -> bytes | None:
        status, body = self.request(
            "GET", self.file_url(path), allowed=(200, 404)
        )
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_FILE_MISSING:" + path)
        return body

    def delete_file(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(204, 404))

    def upload(self, path: str, data: bytes) -> None:
        boundary = "----uaart-task091-" + uuid.uuid4().hex
        filename = PurePosixPath(path).name
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

    def create_trigger(self, command: str, description: str):
        form = urllib.parse.urlencode({
            "command": command,
            "description": description,
            "enabled": "true",
        }).encode()
        status, body = self.request(
            "POST", BASE + "always_on/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self.identifier(body) if status in (200, 201, 202) else None
        if identifier:
            return "always_on", identifier
        moment = time.gmtime(time.time() + 120)
        form = urllib.parse.urlencode({
            "command": command,
            "description": description + " fallback",
            "enabled": "true",
            "interval": "daily",
            "hour": moment.tm_hour,
            "minute": moment.tm_min,
        }).encode()
        status, body = self.request(
            "POST", BASE + "schedule/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self.identifier(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerError("NO_REMOTE_TRIGGER")
        return "schedule", identifier

    def delete_trigger(self, trigger) -> None:
        kind, identifier = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request(
            "DELETE", BASE + "%s/%d/" % (endpoint, identifier),
            allowed=(200, 202, 204, 404),
        )

    def run_remote(self, mode: str, seconds: int = 600) -> dict[str, Any]:
        receipt = RECEIPTS[mode]
        self.delete_file(receipt)
        trigger = self.create_trigger(COMMANDS[mode], "task091 " + mode)
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
            == "python3.10 /home/Carix/start_safe.py"
        ]
        if len(matches) != 1:
            raise ControllerError("ACTIVE_LAUNCHER_NOT_UNIQUE:%d" % len(matches))
        identifier = int(matches[0]["id"])
        self.request(
            "POST", BASE + "always_on/%d/restart/" % identifier,
            b"", allowed=(200, 201, 202, 204),
        )
        return {"task_id": identifier, "restart_accepted": True}


def validate(value: dict[str, Any], mode: str) -> None:
    if value.get("contract_id") != CONTRACT_ID or value.get("status") != "PASS":
        raise ControllerError(mode.upper() + "_FAILED:" + ";".join(value.get("errors") or []))
    if mode in ("preflight", "postcheck"):
        if value.get("production_write") is not False or value.get("crm_write") is not False:
            raise ControllerError(mode.upper() + "_SCOPE_INVALID")
    if mode == "install":
        if value.get("production_write") is not True:
            raise ControllerError("INSTALL_WRITE_MISSING")
        migration = value.get("migration") or {}
        after = migration.get("after") or {}
        if str(after.get("year") or "").strip():
            raise ControllerError("UA0015_YEAR_NOT_CLEARED")
        if int(after.get("engine_cc") or 0) != 1999:
            raise ControllerError("UA0015_ENGINE_INVALID")
    if mode == "postcheck":
        target = ((value.get("database") or {}).get("target") or {})
        if str(target.get("year") or "").strip():
            raise ControllerError("POSTCHECK_UA0015_YEAR_INVALID")
        if int(target.get("engine_cc") or 0) != 1999:
            raise ControllerError("POSTCHECK_UA0015_ENGINE_INVALID")


def write_human_files(evidence: dict[str, Any]) -> None:
    passed = evidence.get("status") == "PASS"
    report = "\n".join([
        "# TASK 091 — одно число в одну ячейку", "",
        "STATUS: **%s**" % evidence.get("status", "FAIL"), "",
        "- Общий парсер текста/OCR/голоса: %s" % ("ИСПРАВЛЕН" if passed else "НЕ УСТАНОВЛЕН"),
        "- UA-0015: год %s" % ("ОЧИЩЕН" if passed else "НЕ ПОДТВЕРЖДЁН"),
        "- UA-0015: объём 1999 см³: %s" % ("СОХРАНЁН" if passed else "НЕ ПОДТВЕРЖДЁН"),
        "- UA-0015: пробег 395 459 км: %s" % ("СОХРАНЁН" if passed else "НЕ ПОДТВЕРЖДЁН"),
        "- Backup и автооткат: %s" % ("PASS" if passed else "FAIL/ОТКАТ"),
        "- Ошибки: %s" % ("; ".join(evidence.get("errors") or []) or "нет"), "",
    ])
    atomic_text(REPORT, report)
    status = "\n".join([
        "TASK_ID: task_091",
        "ROUND: 1",
        "CLAUDE_STATUS: %s" % ("DONE" if passed else "BLOCKED"),
        "CURRENT_ACTION: %s" % (
            "Numeric single-claim guard installed and verified."
            if passed else "Installation failed or was rolled back."
        ),
        "FILES_CREATED: cloud/task_091_numeric_claim_guard/, tasks/task_091.md, .github/workflows/task091_numeric_claim_guard.yml",
        "PRODUCTION_TOUCHED: %s" % ("YES" if passed else "NO_OR_ROLLED_BACK"),
        "OWNER_ACTION_REQUIRED: %s" % ("NO" if passed else "YES"),
        "OWNER_QUESTION: %s" % ("NONE" if passed else "Restore GitHub Actions availability and rerun task091."),
        "NEXT_FOR_CHATGPT: %s" % (
            "Report verified PASS to owner."
            if passed else "Inspect blocker; do not claim live completion."
        ),
        "UPDATED_AT_UTC: %s" % time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "",
    ])
    atomic_text(LATEST_STATUS, status)
    owner = "\n".join([
        "# Ответ Claude владельцу",
        "СТАТУС: %s" % ("PASS" if passed else "ЖДЁТ"),
        "ЗАДАЧА: Закрепить правило «одно число — одна ячейка» и исправить UA-0015.",
        "ЧТО СДЕЛАНО: %s" % (
            "Общий парсер исправлен; ошибочный год UA-0015 очищен; объём и пробег сохранены."
            if passed else "Пакет проверен, но production-установка не подтверждена."
        ),
        "СОЗДАННЫЕ ФАЙЛЫ: cloud/task_091_numeric_claim_guard/",
        "ЧТО НУЖНО ОТ ВЛАДЕЛЬЦА: %s" % ("НИЧЕГО" if passed else "Восстановить GitHub Actions."),
        "БЕЗОПАСНОСТЬ: %s" % (
            "backup, атомарная запись и postcheck PASS"
            if passed else "live-изменение не подтверждено"
        ), "",
    ])
    atomic_text(OWNER_REPLY, owner)


def main() -> int:
    evidence: dict[str, Any] = {
        "contract_id": CONTRACT_ID,
        "status": "FAIL",
        "errors": [],
        "installed": False,
        "bot_restarted": False,
        "rollback": None,
    }
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
        preflight = api.run_remote("preflight")
        evidence["preflight"] = preflight
        validate(preflight, "preflight")
        installed = api.run_remote("install")
        evidence["install"] = installed
        validate(installed, "install")
        evidence["installed"] = True
        evidence["service"] = api.restart_bot()
        evidence["bot_restarted"] = True
        time.sleep(8)
        immediate = api.run_remote("postcheck")
        evidence["postcheck_immediate"] = immediate
        validate(immediate, "postcheck")
        time.sleep(15)
        delayed = api.run_remote("postcheck")
        evidence["postcheck_delayed"] = delayed
        validate(delayed, "postcheck")
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api is not None and evidence["installed"]:
            try:
                rollback = api.run_remote("rollback")
                evidence["rollback"] = rollback
                validate(rollback, "rollback")
                evidence["rollback_service"] = api.restart_bot()
            except Exception as rollback_exc:
                evidence["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )
    atomic_text(EVIDENCE, json.dumps(
        evidence, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n")
    write_human_files(evidence)
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
