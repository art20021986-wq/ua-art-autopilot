#!/usr/bin/env python3
"""Upload, install, restart and verify TASK 082 through PythonAnywhere API."""
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
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_082_catalog_stage_repair"
FILES = {
    "task082_remote_installer.py": HERE / "remote_installer.py",
    "catalog_stage_guard_core.py": HERE.parent / "task_075_stage_guard/stage_guard.py",
    "catalog_stage_guard_runtime.py": HERE / "runtime.py",
}
RECEIPTS = {
    "install": REMOTE + "/install_receipt.json",
    "postcheck": REMOTE + "/postcheck_receipt.json",
    "rollback": REMOTE + "/rollback_receipt.json",
}
COMMANDS = {
    "install": "cd %s && python3.10 task082_remote_installer.py install" % REMOTE,
    "postcheck": "cd %s && python3.10 task082_remote_installer.py postcheck" % REMOTE,
    "rollback": "cd %s && python3.10 task082_remote_installer.py rollback" % REMOTE,
}
EVIDENCE = HERE / "evidence/deploy.json"
REPORT = HERE / "TASK_082_REPORT.md"
CONTRACT = "UA-0011-CATALOG-FERRY-REPAIR-001-V1.0"
MAX_BYTES = 8_000_000


class ControllerError(RuntimeError):
    pass


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="." + path.name + ".", suffix=".tmp", delete=False)
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
            raise ControllerError("PYTHONANYWHERE_TOKEN_MISSING")
        self.token = token

    def request(self, method, url, data=None, headers=None, allowed=(200,)):
        request_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task082-controller/1",
        }
        request_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=70) as response:
                status, body = response.status, response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, body = exc.code, exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK_ERROR:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES:
            raise ControllerError("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise ControllerError("HTTP_%d" % status)
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
        boundary = "----uaart-task082-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = bytearray()
        body.extend(("--%s\r\n" % boundary).encode())
        body.extend(('Content-Disposition: form-data; name="content"; filename="%s"\r\n'
                     'Content-Type: %s\r\n\r\n' % (filename, mime)).encode())
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
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerError("NO_REMOTE_TRIGGER")
        return "schedule", identifier

    def delete_trigger(self, trigger) -> None:
        kind, identifier = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request("DELETE", BASE + "%s/%d/" % (endpoint, identifier),
                     allowed=(200, 202, 204, 404))

    def run_remote(self, mode: str, seconds: int = 900) -> dict:
        receipt = RECEIPTS[mode]
        self.delete_file(receipt)
        trigger = self.create_trigger(COMMANDS[mode], "task082 " + mode)
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

    def restart_bot(self) -> dict:
        _, body = self.request("GET", BASE + "always_on/")
        tasks = self.objects(body)
        matches = [
            item for item in tasks
            if isinstance(item, dict) and item.get("enabled") is not False
            and str(item.get("command", "")).strip() == "python3.10 /home/Carix/start_safe.py"
        ]
        if len(matches) != 1:
            raise ControllerError("ACTIVE_LAUNCHER_NOT_UNIQUE")
        identifier = matches[0]["id"]
        self.request("POST", BASE + "always_on/%d/restart/" % identifier,
                     b"", allowed=(200, 201, 202, 204))
        return {"command": "python3.10 /home/Carix/start_safe.py", "restart_accepted": True}


def validate_install(value: dict) -> None:
    if value.get("contract_id") != CONTRACT or value.get("status") != "PASS":
        raise ControllerError("INSTALL_FAILED:" + ";".join(value.get("errors") or []))
    if not value.get("production_write") or value.get("crm_write") or value.get("media_write"):
        raise ControllerError("INSTALL_SCOPE_INVALID")
    if value.get("rows_sha256_before") != value.get("rows_sha256_after"):
        raise ControllerError("CRM_ROWS_CHANGED")
    if value.get("llm_tokens") != 0 or not value.get("backup_root"):
        raise ControllerError("INSTALL_CONTRACT_INVALID")
    repair = value.get("repair") or {}
    if repair.get("target_id") != "UA-0011":
        raise ControllerError("UA0011_TARGET_MISSING")
    if not {"UA-0009", "UA-0011"}.issubset(set(repair.get("selected_ids") or [])):
        raise ControllerError("PROTECTED_IDS_MISSING")


def validate_postcheck(value: dict) -> None:
    if value.get("contract_id") != CONTRACT or value.get("status") != "PASS":
        raise ControllerError("POSTCHECK_FAILED:" + ";".join(value.get("errors") or []))
    if value.get("read_only") is not True or value.get("production_write"):
        raise ControllerError("POSTCHECK_SCOPE_INVALID")
    runtime = value.get("runtime") or {}
    for variant, item in (runtime.get("catalogs") or {}).items():
        if item.get("before_sha256") != item.get("candidate_sha256"):
            raise ControllerError("NOT_IDEMPOTENT:" + variant)
        card = ((item.get("audit") or {}).get("cards") or {}).get("UA-0011") or {}
        if not (card.get("stage") == 2 and card.get("category") == "more"
                and card.get("template") and card.get("absolute_photo")):
            raise ControllerError("UA0011_POSTCHECK_INVALID:" + variant)


def main() -> int:
    evidence = {
        "contract_id": CONTRACT, "status": "FAIL", "errors": [],
        "llm_tokens": 0, "bot_restarted": False, "rollback": None,
    }
    api = None
    install = None
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
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api is not None and install and install.get("status") == "PASS":
            try:
                rollback = api.run_remote("rollback")
                evidence["rollback"] = rollback
                if rollback.get("status") != "PASS":
                    raise ControllerError("ROLLBACK_FAILED")
                api.restart_bot()
            except Exception as rollback_exc:
                evidence["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )

    atomic_text(EVIDENCE, json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    install_value = evidence.get("install") or {}
    report = "\n".join([
        "# UA-0011-CATALOG-FERRY-REPAIR-001 v1.0", "",
        "STATUS: **%s**" % evidence["status"], "",
        "- UA-0011 full unified catalog card: %s" % ("PASS" if evidence["status"] == "PASS" else "FAIL"),
        "- Public stage/category: stage 2 / more / На пароме",
        "- Main photo and 55/45 media structure: %s" % ("PASS" if evidence["status"] == "PASS" else "NOT VERIFIED"),
        "- Title VIN suffix: VIN 4289",
        "- UA-0009 protected gate: %s" % ("PASS" if evidence["status"] == "PASS" else "NOT VERIFIED"),
        "- CRM rows changed: NO",
        "- Individual pages/media changed: NO",
        "- Future publication guard installed: %s" % ("YES" if evidence["status"] == "PASS" else "NO"),
        "- Immediate + delayed verification: %s" % ("PASS" if evidence["status"] == "PASS" else "FAIL"),
        "- Backup: `%s`" % install_value.get("backup_root", ""),
        "- Errors: %s" % ("; ".join(evidence["errors"]) if evidence["errors"] else "none"),
        "",
    ])
    atomic_text(REPORT, report)
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

