#!/usr/bin/env python3
"""Controller for the bounded TASK 095 PythonAnywhere repair."""
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
LOCAL_REMOTE = ROOT / "cloud/task_095_catalog_visual_repair/remote_repair.py"
EVIDENCE = ROOT / "cloud/task_095_catalog_visual_repair/evidence"
EVIDENCE.mkdir(parents=True, exist_ok=True)
REMOTE_DIR = "/home/Carix/autopilot_inbox/cloud/task_095_catalog_visual_repair"
REMOTE_SCRIPT = REMOTE_DIR + "/task095_remote_repair.py"
RECEIPT = {mode: REMOTE_DIR + "/%s_receipt.json" % mode for mode in ("install", "postcheck", "rollback")}
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
CONTRACT_ID = "CATALOG-VISUAL-ACCEPTANCE-REPAIR-095-V1.0"
MAX_BYTES = 64 * 1024 * 1024


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
            "User-Agent": "ua-art-task095-controller/1",
        }
        all_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=all_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=75) as response:
                status = int(response.status)
                body = response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            body = exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK_ERROR:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES:
            raise ControllerError("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise ControllerError("HTTP_%d:%s:%s" % (status, method, urllib.parse.urlsplit(url).path))
        return status, body

    @staticmethod
    def file_url(path: str) -> str:
        if not path.startswith(REMOTE_DIR + "/"):
            raise ControllerError("REMOTE_PATH_NOT_ALLOWED:" + path)
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, missing: bool = False) -> bytes | None:
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_FILE_MISSING:" + path)
        return body

    def delete_file(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(204, 404))

    def upload(self, path: str, content: bytes) -> None:
        boundary = "----uaart-task095-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = bytearray()
        body.extend(("--%s\r\n" % boundary).encode())
        body.extend(
            (
                'Content-Disposition: form-data; name="content"; filename="%s"\r\n'
                "Content-Type: %s\r\n\r\n" % (filename, mime)
            ).encode()
        )
        body.extend(content)
        body.extend(("\r\n--%s--\r\n" % boundary).encode())
        for attempt in range(1, 6):
            status, _ = self.request(
                "POST",
                self.file_url(path),
                bytes(body),
                {"Content-Type": "multipart/form-data; boundary=" + boundary},
                allowed=(200, 201, 429, 500, 502, 503, 504),
            )
            if status in (200, 201):
                return
            if attempt < 5:
                time.sleep(attempt * 3)
        raise ControllerError("UPLOAD_FAILED:" + filename)

    @staticmethod
    def object_id(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        result = value.get("id") if isinstance(value, dict) else None
        return result if isinstance(result, int) and result > 0 else None

    def create_schedule(self, command: str, description: str):
        moment = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=1)
        form = urllib.parse.urlencode(
            {
                "command": command,
                "description": description,
                "enabled": "true",
                "interval": "daily",
                "hour": moment.hour,
                "minute": moment.minute,
            }
        ).encode()
        status, body = self.request(
            "POST",
            BASE + "schedule/",
            form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self.object_id(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerError("NO_SCHEDULED_EXECUTOR:HTTP_%d" % status)
        return ("schedule", identifier)

    def delete_schedule(self, trigger) -> None:
        kind, identifier = trigger
        self.request("DELETE", BASE + "%s/%d/" % (kind, identifier), allowed=(200, 202, 204, 404))

    def run_remote(self, mode: str, timeout_seconds: int = 600) -> dict[str, Any]:
        receipt = RECEIPT[mode]
        self.delete_file(receipt)
        command = "cd %s && python3.10 %s %s" % (REMOTE_DIR, pathlib.PurePosixPath(REMOTE_SCRIPT).name, mode)
        trigger = self.create_schedule(command, "TASK095 %s one-shot executor" % mode)
        try:
            deadline = time.monotonic() + timeout_seconds
            while time.monotonic() < deadline:
                raw = self.read(receipt, missing=True)
                if raw:
                    try:
                        value = json.loads(raw.decode("utf-8"))
                    except Exception as exc:
                        raise ControllerError("REMOTE_RECEIPT_INVALID:" + mode) from exc
                    return value
                time.sleep(5)
            raise ControllerError("REMOTE_RECEIPT_TIMEOUT:" + mode)
        finally:
            self.delete_schedule(trigger)


def validate(value: dict[str, Any], mode: str) -> None:
    if value.get("contract_id") != CONTRACT_ID:
        raise ControllerError("CONTRACT_MISMATCH:" + mode)
    if value.get("status") != "PASS":
        raise ControllerError("REMOTE_%s_FAIL:%s" % (mode.upper(), ";".join(value.get("errors") or [])))
    if value.get("crm_write") is not False or value.get("media_write") is not False:
        raise ControllerError("REMOTE_SCOPE_VIOLATION:" + mode)
    if mode == "install":
        if value.get("production_write") is not True:
            raise ControllerError("INSTALL_DID_NOT_WRITE")
        audits = value.get("audits") or {}
        if len(audits) != 3 or any((item or {}).get("status") != "PASS" for item in audits.values()):
            raise ControllerError("INSTALL_AUDIT_INVALID")
    if mode == "postcheck" and value.get("production_write") is not False:
        raise ControllerError("POSTCHECK_WROTE_PRODUCTION")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("install", "postcheck", "rollback"))
    args = parser.parse_args()
    output = EVIDENCE / (args.mode + ".json")
    result: dict[str, Any]
    try:
        if not LOCAL_REMOTE.is_file():
            raise ControllerError("LOCAL_REMOTE_SCRIPT_MISSING")
        compile(LOCAL_REMOTE.read_text(encoding="utf-8"), str(LOCAL_REMOTE), "exec")
        api = API()
        api.upload(REMOTE_SCRIPT, LOCAL_REMOTE.read_bytes())
        result = api.run_remote(args.mode)
        validate(result, args.mode)
    except Exception as exc:
        result = {
            "contract_id": CONTRACT_ID,
            "status": "FAIL",
            "mode": args.mode.upper(),
            "production_write": False,
            "crm_write": False,
            "media_write": False,
            "errors": [type(exc).__name__ + ":" + str(exc)],
            "finished_at_utc": utc_now(),
        }
    atomic_json(output, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
