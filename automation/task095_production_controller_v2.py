#!/usr/bin/env python3
"""PythonAnywhere controller for TASK 095 repair v2."""
from __future__ import annotations

import argparse
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
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCAL = ROOT / "cloud/task_095_catalog_visual_repair/remote_repair_v2.py"
EVIDENCE = ROOT / "cloud/task_095_catalog_visual_repair/evidence_v2"
EVIDENCE.mkdir(parents=True, exist_ok=True)
REMOTE_DIR = "/home/Carix/autopilot_inbox/cloud/task_095_catalog_visual_repair"
REMOTE_SCRIPT = REMOTE_DIR + "/task095_remote_repair_v2.py"
RECEIPTS = {mode: REMOTE_DIR + "/%s_v2_receipt.json" % mode for mode in ("install", "postcheck", "rollback")}
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
CONTRACT_ID = "CATALOG-VISUAL-ACCEPTANCE-REPAIR-095-V1.0"
MAX_BYTES = 64 * 1024 * 1024


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix="." + path.name + ".", suffix=".tmp", delete=False
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class ControllerError(RuntimeError):
    pass


class API:
    def __init__(self) -> None:
        self.token = (os.environ.get("PYTHONANYWHERE_API_TOKEN") or "").strip()
        if not self.token:
            raise ControllerError("PYTHONANYWHERE_API_TOKEN_MISSING")

    def request(self, method: str, url: str, data: bytes | None = None,
                headers: dict[str, str] | None = None,
                allowed: tuple[int, ...] = (200,)) -> tuple[int, bytes]:
        all_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task095-v2/1",
        }
        all_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=all_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=75) as response:
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

    @staticmethod
    def file_url(path: str) -> str:
        if not path.startswith(REMOTE_DIR + "/"):
            raise ControllerError("REMOTE_PATH_NOT_ALLOWED")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, missing: bool = False) -> bytes | None:
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_FILE_MISSING:" + path)
        return body

    def delete(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(204, 404))

    def upload(self, path: str, data: bytes) -> None:
        boundary = "----uaart-task095v2-" + uuid.uuid4().hex
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
                time.sleep(attempt * 3)
        raise ControllerError("UPLOAD_FAILED")

    @staticmethod
    def identifier(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        result = value.get("id") if isinstance(value, dict) else None
        return result if isinstance(result, int) and result > 0 else None

    def create_trigger(self, command: str, description: str):
        moment = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=1)
        form = urllib.parse.urlencode({
            "command": command,
            "description": description,
            "enabled": "true",
            "interval": "daily",
            "hour": moment.hour,
            "minute": moment.minute,
        }).encode()
        status, body = self.request(
            "POST", BASE + "schedule/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self.identifier(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerError("NO_SCHEDULED_EXECUTOR:HTTP_%d" % status)
        return ("schedule", identifier)

    def delete_trigger(self, trigger) -> None:
        self.request("DELETE", BASE + "%s/%d/" % trigger, allowed=(200, 202, 204, 404))

    def run(self, mode: str, timeout: int = 600) -> dict[str, Any]:
        receipt = RECEIPTS[mode]
        self.delete(receipt)
        command = "cd %s && python3.10 %s %s" % (
            REMOTE_DIR, pathlib.PurePosixPath(REMOTE_SCRIPT).name, mode
        )
        trigger = self.create_trigger(command, "TASK095 v2 %s one-shot" % mode)
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                raw = self.read(receipt, missing=True)
                if raw:
                    return json.loads(raw.decode("utf-8"))
                time.sleep(5)
            raise ControllerError("RECEIPT_TIMEOUT:" + mode)
        finally:
            self.delete_trigger(trigger)


def validate(value: dict[str, Any], mode: str) -> None:
    if value.get("contract_id") != CONTRACT_ID or value.get("status") != "PASS":
        raise ControllerError("REMOTE_%s_FAIL:%s" % (mode.upper(), ";".join(value.get("errors") or [])))
    if value.get("crm_write") is not False or value.get("media_write") is not False:
        raise ControllerError("SCOPE_VIOLATION")
    if mode == "install":
        if value.get("production_write") is not True:
            raise ControllerError("INSTALL_WRITE_MISSING")
        audits = value.get("audits") or {}
        if len(audits) != 2 or any((item or {}).get("status") != "PASS" for item in audits.values()):
            raise ControllerError("INSTALL_AUDIT_INVALID")
    if mode == "postcheck" and value.get("production_write") is not False:
        raise ControllerError("POSTCHECK_WROTE")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("install", "postcheck", "rollback"))
    args = parser.parse_args()
    path = EVIDENCE / (args.mode + ".json")
    try:
        if not LOCAL.is_file():
            raise ControllerError("LOCAL_REMOTE_MISSING")
        compile(LOCAL.read_text(encoding="utf-8"), str(LOCAL), "exec")
        api = API()
        api.upload(REMOTE_SCRIPT, LOCAL.read_bytes())
        value = api.run(args.mode)
        validate(value, args.mode)
    except Exception as exc:
        value = {
            "contract_id": CONTRACT_ID,
            "status": "FAIL",
            "mode": args.mode.upper(),
            "production_write": False,
            "crm_write": False,
            "media_write": False,
            "errors": [type(exc).__name__ + ":" + str(exc)],
            "finished_at_utc": now(),
        }
    write_json(path, value)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
