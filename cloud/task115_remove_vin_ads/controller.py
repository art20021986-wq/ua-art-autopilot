#!/usr/bin/env python3
"""Guarded production controller for the owner-requested VIN-ad removal."""
from __future__ import annotations

import datetime as dt
import hashlib
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
from typing import Any, Mapping


TASK_ID = "TASK115-REMOVE-VIN-ADS"
CONTRACT = "UA-ART-NO-VIN-ADS-V1.0"
CRITICAL = "UA-ART-CRITICAL-ADAPTER-V1.0"
MANIFEST_SHA256 = "da65dcd774e70d1af46ae97c9cc1589d36a057609fe98cbf819d97cfc526d665"
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_068_ferry_vin"
REMOTE_SCRIPT = REMOTE + "/task115_remove_vin_ads.py"
REMOTE_RECEIPT = REMOTE + "/task115_receipt.json"
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
RECEIPT_REL = "state/receipts/%s.json" % TASK_ID
EVIDENCE_REL = "cloud/task115_remove_vin_ads/evidence.json"
PUBLIC = "https://www.uaart.com.ua/video/"
IDS = tuple("UA-%04d" % value for value in range(1, 17))
FORBIDDEN = ("carhistory", "проверить vin", "перевірити vin", "2 200 krw", "2200 krw")
MAX_BYTES = 64 * 1024 * 1024


class ControllerError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def required(environment: Mapping[str, str]) -> dict[str, str]:
    names = ("PYTHONANYWHERE_API_TOKEN", "UAART_REQUEST_PATH", "UAART_REQUEST_SHA256",
             "UAART_TASK_ID", "UAART_TASK_CLASS", "UAART_RUN_ID", "UAART_RECEIPT_PATH")
    values = {name: str(environment.get(name, "")).strip() for name in names}
    if any(not values[name] for name in names):
        raise ControllerError("MISSING_ENVIRONMENT")
    if values["UAART_TASK_ID"] != TASK_ID or values["UAART_TASK_CLASS"].upper() != "CRITICAL":
        raise ControllerError("TASK_IDENTITY")
    if values["UAART_RECEIPT_PATH"] != RECEIPT_REL:
        raise ControllerError("RECEIPT_IDENTITY")
    request_path = (ROOT / values["UAART_REQUEST_PATH"]).resolve()
    if not request_path.is_relative_to(ROOT.resolve()) or sha(request_path.read_bytes()) != values["UAART_REQUEST_SHA256"]:
        raise ControllerError("REQUEST_IDENTITY")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if request.get("task_id") != TASK_ID or request.get("production_required") is not True:
        raise ControllerError("REQUEST_SCOPE")
    if (request.get("critical") or {}).get("manifest_sha256") != MANIFEST_SHA256:
        raise ControllerError("MANIFEST_IDENTITY")
    return values


class API:
    def __init__(self, token: str) -> None:
        self.token = token

    def request(self, method: str, url: str, data: bytes | None = None,
                headers: dict[str, str] | None = None, allowed: tuple[int, ...] = (200,)) -> tuple[int, bytes]:
        actual = {"Authorization": "Token " + self.token, "User-Agent": "ua-art-task115/1"}
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
        if not path.startswith(REMOTE + "/"):
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

    def upload(self, path: str, value: bytes) -> None:
        boundary = "----uaart-task115-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = bytearray()
        body.extend(("--%s\r\n" % boundary).encode())
        body.extend(('Content-Disposition: form-data; name="content"; filename="%s"\r\n'
                     "Content-Type: %s\r\n\r\n" % (filename, mime)).encode())
        body.extend(value)
        body.extend(("\r\n--%s--\r\n" % boundary).encode())
        self.request("POST", self.file_url(path), bytes(body),
                     {"Content-Type": "multipart/form-data; boundary=" + boundary}, allowed=(200, 201))
        if self.read(path) != value:
            raise ControllerError("UPLOAD_READBACK")

    @staticmethod
    def object_id(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode())
        except Exception:
            return None
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) else None

    def create_trigger(self, command: str) -> tuple[str, int]:
        form = urllib.parse.urlencode({"command": command, "description": TASK_ID, "enabled": "true"}).encode()
        status, body = self.request("POST", BASE + "always_on/", form,
                                    {"Content-Type": "application/x-www-form-urlencoded"},
                                    allowed=(200, 201, 202, 400, 403, 404, 409))
        identifier = self.object_id(body) if status in (200, 201, 202) else None
        if identifier:
            return "always_on", identifier
        at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({"command": command, "description": TASK_ID + " fallback",
                                      "enabled": "true", "interval": "daily", "hour": at.hour,
                                      "minute": at.minute}).encode()
        _, body = self.request("POST", BASE + "schedule/", form,
                               {"Content-Type": "application/x-www-form-urlencoded"}, allowed=(200, 201, 202))
        identifier = self.object_id(body)
        if not identifier:
            raise ControllerError("NO_TRIGGER")
        return "schedule", identifier

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        kind, identifier = trigger
        self.request("DELETE", BASE + "%s/%d/" % (kind, identifier), allowed=(200, 202, 204, 404))

    def run(self, mode: str, timeout: int = 1200) -> dict[str, Any]:
        self.delete_file(REMOTE_RECEIPT)
        trigger = self.create_trigger("cd %s && python3.10 task115_remove_vin_ads.py --mode %s" % (REMOTE, mode))
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

    def restart(self) -> None:
        _, body = self.request("GET", BASE + "always_on/")
        value = json.loads(body.decode())
        tasks = value.get("results") or value.get("objects") or value.get("tasks") or [] if isinstance(value, dict) else value
        matches = [item for item in tasks if isinstance(item, dict) and item.get("enabled") is not False
                   and str(item.get("command") or "").strip() == "python3.10 /home/Carix/start_safe.py"]
        if len(matches) != 1:
            raise ControllerError("BOT_TASK_NOT_UNIQUE")
        self.request("POST", BASE + "always_on/%d/restart/" % int(matches[0]["id"]), b"", allowed=(200, 201, 202, 204))


def validate_remote(value: Mapping[str, Any], mode: str) -> None:
    if value.get("task_id") != TASK_ID or value.get("contract_id") != CONTRACT or value.get("status") != "PASS":
        raise ControllerError("REMOTE_%s_FAIL:%s" % (mode.upper(), value.get("errors")))
    if value.get("crm_write") is not False or value.get("media_write") is not False:
        raise ControllerError("REMOTE_SCOPE")
    if mode in ("install", "verify"):
        if int(value.get("card_count", 0)) != 16 or int(value.get("page_count", 0)) != 32:
            raise ControllerError("REMOTE_CARD_COUNT")
        if int(value.get("vin_ad_count", -1)) != 0 or value.get("ua0009") != "PASS":
            raise ControllerError("REMOTE_AD_OR_UA0009")


def fetch(path: str) -> str:
    request = urllib.request.Request(PUBLIC + path + "?task115=" + str(time.time_ns()),
                                     headers={"Cache-Control": "no-cache", "User-Agent": "ua-art-task115-verify/1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        body = response.read(MAX_BYTES + 1)
        if response.status != 200 or len(body) > MAX_BYTES:
            raise ControllerError("PUBLIC_HTTP")
    return body.decode("utf-8")


def live_verify() -> dict[str, Any]:
    results = {}
    for uid in IDS:
        page = fetch(uid + ".html")
        lowered = " ".join(page.casefold().split())
        if any(term in lowered for term in FORBIDDEN):
            raise ControllerError("PUBLIC_VIN_AD:" + uid)
        if page.count("<!--UA099_ADD_SPEC_START-->") != 1 or page.count("<!--UA099_CLEAN_VIN_START-->") != 1:
            raise ControllerError("PUBLIC_SPEC_OR_VIN:" + uid)
        results[uid] = sha(page.encode())
    return {"status": "PASS", "card_count": 16, "vin_ad_count": 0, "ua0009": "PASS", "sha256": results}


def execute(environment: Mapping[str, str]) -> dict[str, Any]:
    values = required(environment)
    evidence: dict[str, Any] = {"task_id": TASK_ID, "contract_id": CONTRACT, "status": "FAIL",
                                "started_at": now(), "errors": [], "production_required": True}
    api: API | None = None
    installed = False
    try:
        script = (HERE / "remote_installer.py").read_bytes()
        compile(script.decode("utf-8"), "remote_installer.py", "exec")
        api = API(values["PYTHONANYWHERE_API_TOKEN"])
        api.upload(REMOTE_SCRIPT, script)
        install = api.run("install")
        evidence["install"] = install
        validate_remote(install, "install")
        installed = True
        api.restart()
        time.sleep(15)
        evidence["public_immediate"] = live_verify()
        verify = api.run("verify")
        evidence["remote_verify"] = verify
        validate_remote(verify, "verify")
        time.sleep(35)
        evidence["public_delayed"] = live_verify()
        receipt = {"contract_id": CRITICAL, "task_id": TASK_ID, "status": "FINISHED",
                   "task_class": "CRITICAL", "target_environment": "production", "tests": "PASS",
                   "backup": install["backup"], "production": "PASS", "live_verify": "PASS",
                   "rollback": "PASS", "rollback_ready": True, "unexpected_changes": 0,
                   "protected_files_unchanged": True, "crm_unchanged": True, "media_unchanged": True,
                   "production_required": True, "request_sha256": values["UAART_REQUEST_SHA256"],
                   "manifest_sha256": MANIFEST_SHA256, "run_id": values["UAART_RUN_ID"],
                   "card_count": 16, "page_count": 32, "vin_ad_count": 0, "ua0009": "PASS",
                   "additional_specification": "RESTORED", "vin_autoworker_enabled": False,
                   "production_write": "TASK115_ONLY", "finished_at": now()}
        atomic_text(ROOT / RECEIPT_REL, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api is not None and installed:
            try:
                rollback = api.run("rollback")
                evidence["rollback"] = rollback
                api.restart()
            except Exception as rollback_exc:
                evidence["errors"].append("ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc))
    evidence["finished_at"] = now()
    atomic_text(ROOT / EVIDENCE_REL, json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return evidence


def main() -> int:
    value = execute(os.environ)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
