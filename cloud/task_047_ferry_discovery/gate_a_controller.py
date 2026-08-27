#!/usr/bin/env python3
"""GitHub-side controller for the isolated ferry-wording Gate A.

It uploads exactly three reviewed scripts to autopilot_inbox, runs one fixed
command, validates the bounded receipt and all candidate hashes, then relays
evidence to GitHub. No production or CRM path is writable through this module.
"""
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

ALLOWED_USERNAME = "Carix"
ALLOWED_HOSTS = ("www.pythonanywhere.com", "eu.pythonanywhere.com")
REMOTE_ROOT = "/home/Carix/autopilot_inbox/cloud/task_047_ferry_discovery"
REMOTE_TRANSFORM = REMOTE_ROOT + "/transform.py"
REMOTE_DISCOVER = REMOTE_ROOT + "/discover.py"
REMOTE_GATE_A = REMOTE_ROOT + "/gate_a_remote.py"
REMOTE_OUTPUT = REMOTE_ROOT + "/ferry_gate_a_receipt.json"
VIDEO_PATHS = [
    "video/index.html", "video/katalog.html", "video/info.html", "video/podbor.html",
] + ["video/UA-%04d.html" % number for number in range(1, 10)]
REMOTE_CANDIDATES = {
    rel_path: REMOTE_ROOT + "/gate_a_candidates/" + rel_path
    for rel_path in VIDEO_PATHS
}
EXACT_COMMAND = (
    "cd " + REMOTE_ROOT
    + " && python3.10 gate_a_remote.py > " + REMOTE_OUTPUT
)

HERE = pathlib.Path(__file__).resolve().parent
LOCAL_FILES = {
    REMOTE_TRANSFORM: HERE / "transform.py",
    REMOTE_DISCOVER: HERE / "discover.py",
    REMOTE_GATE_A: HERE / "gate_a_remote.py",
}
EVIDENCE_PATH = HERE / "evidence" / "ferry_gate_a.json"
REPORT_PATH = HERE / "FERRY_GATE_A_REPORT.md"

MAX_RESPONSE_BYTES = 2_000_000
MAX_RECEIPT_BYTES = 500_000
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 600
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ControllerBlocked(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_json(data: bytes, label: str) -> dict:
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ControllerBlocked("duplicate_json_key:" + label)
            result[key] = value
        return result

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ControllerBlocked("invalid_json:" + label) from exc
    if not isinstance(value, dict):
        raise ControllerBlocked("json_not_object:" + label)
    return value


def multipart(filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = "----ferry-gate-a-" + uuid.uuid4().hex
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body = bytearray()
    body.extend((f"--{boundary}\r\n").encode())
    body.extend(
        (
            f'Content-Disposition: form-data; name="content"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode()
    )
    body.extend(data)
    body.extend((f"\r\n--{boundary}--\r\n").encode())
    return bytes(body), "multipart/form-data; boundary=" + boundary


class PythonAnywhereAPI:
    def __init__(self, username: str, host: str, token: str, opener=urllib.request.urlopen):
        if username != ALLOWED_USERNAME:
            raise ControllerBlocked("invalid_username")
        if host not in ALLOWED_HOSTS:
            raise ControllerBlocked("invalid_host")
        if not token:
            raise ControllerBlocked("missing_api_token")
        self.username = username
        self.host = host
        self._token = token
        self._opener = opener

    @property
    def base(self) -> str:
        return f"https://{self.host}/api/v0/user/{urllib.parse.quote(self.username)}/"

    def _request(self, method: str, url: str, *, data=None, headers=None,
                 allowed=(200,), operation="request") -> tuple[int, bytes]:
        all_headers = {
            "Authorization": "Token " + self._token,
            "User-Agent": "ua-art-ferry-gate-a/1",
        }
        all_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=all_headers, method=method)
        try:
            with self._opener(request, timeout=60) as response:
                status = getattr(response, "status", response.getcode())
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read(MAX_RESPONSE_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ControllerBlocked("network_error:" + operation) from exc
        if len(body) > MAX_RESPONSE_BYTES:
            raise ControllerBlocked("response_too_large:" + operation)
        if status not in allowed:
            raise ControllerBlocked(f"unexpected_http_status:{operation}:{status}")
        return status, body

    def _file_url(self, path: str) -> str:
        allowed = set(LOCAL_FILES) | {REMOTE_OUTPUT} | set(REMOTE_CANDIDATES.values())
        if path not in allowed:
            raise ControllerBlocked("remote_file_path_not_allowed")
        return self.base + "files/path" + urllib.parse.quote(path, safe="/")

    def upload_script(self, remote_path: str, data: bytes) -> None:
        if remote_path not in LOCAL_FILES:
            raise ControllerBlocked("upload_path_not_allowed")
        body, content_type = multipart(pathlib.PurePosixPath(remote_path).name, data)
        self._request(
            "POST",
            self._file_url(remote_path),
            data=body,
            headers={"Content-Type": content_type},
            allowed=(200, 201),
            operation="upload_script",
        )

    def read_file(self, path: str) -> bytes:
        status, body = self._request(
            "GET", self._file_url(path), allowed=(200, 404), operation="read_file"
        )
        if status == 404:
            raise FileNotFoundError(path)
        return body

    def delete_output(self) -> None:
        self._request(
            "DELETE", self._file_url(REMOTE_OUTPUT), allowed=(204, 404),
            operation="delete_output"
        )

    @staticmethod
    def _trigger_id(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) and identifier > 0 else None

    def create_trigger(self) -> tuple[str, int]:
        form = urllib.parse.urlencode(
            {
                "command": EXACT_COMMAND,
                "description": "UA ART ferry wording isolated Gate A",
                "enabled": "true",
            }
        ).encode()
        status, body = self._request(
            "POST", self.base + "always_on/", data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409), operation="create_always_on"
        )
        identifier = self._trigger_id(body) if status in (200, 201, 202) else None
        if identifier:
            return "always_on", identifier

        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode(
            {
                "command": EXACT_COMMAND,
                "description": "UA ART ferry wording Gate A fallback",
                "enabled": "true",
                "interval": "daily",
                "hour": run_at.hour,
                "minute": run_at.minute,
            }
        ).encode()
        status, body = self._request(
            "POST", self.base + "schedule/", data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409), operation="create_schedule"
        )
        identifier = self._trigger_id(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerBlocked("no_remote_trigger_available")
        return "schedule", identifier

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        kind, identifier = trigger
        if kind not in {"always_on", "schedule"} or not isinstance(identifier, int):
            raise ControllerBlocked("invalid_trigger")
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self._request(
            "DELETE", self.base + f"{endpoint}/{identifier}/",
            allowed=(200, 202, 204, 404), operation="delete_trigger"
        )


class GateAController:
    def __init__(self, api, sleep=time.sleep, monotonic=time.monotonic,
                 poll_interval=POLL_INTERVAL_SECONDS, poll_timeout=POLL_TIMEOUT_SECONDS):
        self.api = api
        self.sleep = sleep
        self.monotonic = monotonic
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout

    def upload_and_verify(self) -> None:
        for remote, local in LOCAL_FILES.items():
            data = local.read_bytes()
            compile(data.decode("utf-8"), str(local), "exec")
            self.api.upload_script(remote, data)
            if sha256_bytes(self.api.read_file(remote)) != sha256_bytes(data):
                raise ControllerBlocked("uploaded_script_hash_mismatch")

    def poll_receipt(self) -> dict:
        deadline = self.monotonic() + self.poll_timeout
        while self.monotonic() < deadline:
            try:
                data = self.api.read_file(REMOTE_OUTPUT)
            except FileNotFoundError:
                data = b""
            if data:
                if len(data) > MAX_RECEIPT_BYTES:
                    raise ControllerBlocked("receipt_too_large")
                return strict_json(data, "gate_a_receipt")
            self.sleep(self.poll_interval)
        raise ControllerBlocked("receipt_timeout")

    @staticmethod
    def validate_receipt(receipt: dict) -> dict:
        allowed = {
            "mode", "status", "source_root", "candidate_root", "generated_at_utc",
            "production_write", "crm_write", "db_write", "service_reload",
            "gate_b_executed", "ua0009_published", "unexpected_protected_changes",
            "production_sources_unchanged", "discovery_reasons", "candidates",
            "python_sources", "crm", "errors",
        }
        if set(receipt) - allowed:
            raise ControllerBlocked("receipt_unknown_key")
        if receipt.get("mode") != "FERRY_GATE_A_READONLY_INPUTS_ISOLATED_CANDIDATES":
            raise ControllerBlocked("receipt_mode_invalid")
        for field in (
            "production_write", "crm_write", "db_write", "service_reload",
            "gate_b_executed", "ua0009_published",
        ):
            if receipt.get(field) is not False:
                raise ControllerBlocked("receipt_safety_invalid:" + field)
        if receipt.get("unexpected_protected_changes") != 0:
            raise ControllerBlocked("receipt_protected_changes_invalid")
        if receipt.get("source_root") != "/home/Carix":
            raise ControllerBlocked("receipt_source_root_invalid")
        if receipt.get("candidate_root") != REMOTE_ROOT + "/gate_a_candidates":
            raise ControllerBlocked("receipt_candidate_root_invalid")
        status = receipt.get("status")
        if status not in {"PASS", "PASS_NEEDS_GENERATOR_PATCH", "BLOCKED"}:
            raise ControllerBlocked("receipt_status_invalid")
        if not isinstance(receipt.get("generated_at_utc"), str):
            raise ControllerBlocked("receipt_timestamp_invalid")
        if not isinstance(receipt.get("discovery_reasons"), list):
            raise ControllerBlocked("receipt_discovery_reasons_invalid")
        if not isinstance(receipt.get("errors"), list):
            raise ControllerBlocked("receipt_errors_invalid")
        if not isinstance(receipt.get("python_sources"), list):
            raise ControllerBlocked("receipt_python_sources_invalid")
        if status == "BLOCKED":
            if not receipt["errors"]:
                raise ControllerBlocked("blocked_receipt_without_error")
            return receipt
        if receipt["errors"] != [] or receipt["discovery_reasons"] != []:
            raise ControllerBlocked("pass_receipt_has_errors")
        if receipt.get("production_sources_unchanged") is not True:
            raise ControllerBlocked("receipt_sources_unchanged_invalid")

        crm = receipt.get("crm")
        if not isinstance(crm, dict) or set(crm) != {
            "status", "table", "id_column", "container_column", "id_count", "sha256",
        }:
            raise ControllerBlocked("receipt_crm_invalid")
        if (
            crm.get("status") != "OK" or crm.get("table") != "cars"
            or crm.get("id_column") != "auto_number"
            or crm.get("container_column") != "sea_container"
            or crm.get("id_count") != 9
            or not isinstance(crm.get("sha256"), str)
            or not HEX64.fullmatch(crm["sha256"])
        ):
            raise ControllerBlocked("receipt_crm_contract_invalid")

        candidates = receipt.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != len(VIDEO_PATHS):
            raise ControllerBlocked("receipt_candidates_invalid")
        by_path = {}
        for item in candidates:
            if not isinstance(item, dict) or set(item) != {
                "path", "candidate_path", "source_sha256", "candidate_sha256",
                "source_size", "candidate_size", "changes", "occurrences",
            }:
                raise ControllerBlocked("receipt_candidate_entry_invalid")
            rel_path = item.get("path")
            if rel_path in by_path or rel_path not in REMOTE_CANDIDATES:
                raise ControllerBlocked("receipt_candidate_path_invalid")
            if item.get("candidate_path") != REMOTE_CANDIDATES[rel_path]:
                raise ControllerBlocked("receipt_candidate_remote_path_invalid")
            for hash_key in ("source_sha256", "candidate_sha256"):
                digest = item.get(hash_key)
                if not isinstance(digest, str) or not HEX64.fullmatch(digest):
                    raise ControllerBlocked("receipt_candidate_hash_invalid")
            for size_key in ("source_size", "candidate_size"):
                size = item.get(size_key)
                if not isinstance(size, int) or not 0 < size <= 20 * 1024 * 1024:
                    raise ControllerBlocked("receipt_candidate_size_invalid")
            if not isinstance(item.get("changes"), int) or item["changes"] < 0:
                raise ControllerBlocked("receipt_candidate_change_count_invalid")
            if not isinstance(item.get("occurrences"), list):
                raise ControllerBlocked("receipt_candidate_occurrences_invalid")
            by_path[rel_path] = item
        if set(by_path) != set(VIDEO_PATHS):
            raise ControllerBlocked("receipt_candidate_set_invalid")

        user_facing = [
            item for item in receipt["python_sources"]
            if isinstance(item, dict) and item.get("classification") == "USER_FACING"
        ]
        if status == "PASS_NEEDS_GENERATOR_PATCH" and not user_facing:
            raise ControllerBlocked("receipt_generator_status_invalid")
        if status == "PASS" and user_facing:
            raise ControllerBlocked("receipt_generator_status_invalid")
        return receipt

    @staticmethod
    def atomic_write(path: pathlib.Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=path.parent,
            prefix="." + path.name + ".", suffix=".tmp", delete=False,
        )
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

    def relay(self, receipt: dict) -> None:
        self.atomic_write(
            EVIDENCE_PATH,
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        candidates = receipt.get("candidates", [])
        total_changes = sum(
            item.get("changes", 0) for item in candidates if isinstance(item, dict)
        )
        generator_items = [
            item for item in receipt.get("python_sources", [])
            if isinstance(item, dict) and item.get("classification") == "USER_FACING"
        ]
        rows = "\n".join(
            "- `%s`: %s changes; `%s` → `%s`" % (
                item["path"], item["changes"], item["source_sha256"],
                item["candidate_sha256"],
            )
            for item in candidates
        ) or "- No candidate files were accepted."
        report = f'''# Ferry wording Gate A report

status: {receipt["status"]}
generated_at_utc: {receipt["generated_at_utc"]}
candidate_files: {len(candidates)}
total_html_changes: {total_changes}
generator_literals_requiring_patch: {len(generator_items)}
crm_table: {receipt.get("crm", {}).get("table")}
crm_id_column: {receipt.get("crm", {}).get("id_column")}
crm_container_column: {receipt.get("crm", {}).get("container_column")}
production_write: false
crm_write: false
db_write: false
service_reload: false
gate_b_executed: false
ua0009_published: false

## Isolated HTML candidates

{rows}

Candidates exist only under `autopilot_inbox`. No live card or generator was
changed. Gate B requires separate explicit owner approval.
'''
        self.atomic_write(REPORT_PATH, report)

    def run(self) -> dict:
        self.upload_and_verify()
        trigger = None
        try:
            self.api.delete_output()
            trigger = self.api.create_trigger()
            receipt = self.validate_receipt(self.poll_receipt())
            if receipt["status"] != "BLOCKED":
                for item in receipt["candidates"]:
                    candidate = self.api.read_file(item["candidate_path"])
                    if len(candidate) != item["candidate_size"]:
                        raise ControllerBlocked("candidate_size_readback_mismatch")
                    if sha256_bytes(candidate) != item["candidate_sha256"]:
                        raise ControllerBlocked("candidate_hash_readback_mismatch")
            self.relay(receipt)
            return receipt
        finally:
            if trigger is not None:
                try:
                    self.api.delete_trigger(trigger)
                except Exception:
                    pass
            try:
                self.api.delete_output()
            except Exception:
                pass


def main() -> int:
    try:
        api = PythonAnywhereAPI(
            os.environ.get("PYTHONANYWHERE_USERNAME", ALLOWED_USERNAME),
            os.environ.get("PYTHONANYWHERE_HOST", ALLOWED_HOSTS[0]),
            os.environ.get("PYTHONANYWHERE_API_TOKEN", ""),
        )
        receipt = GateAController(api).run()
        print(json.dumps({
            "status": receipt["status"],
            "remote_gate_a": receipt["status"],
            "production_write": False,
            "crm_write": False,
            "db_write": False,
            "service_reload": False,
        }, sort_keys=True))
        return 0
    except (ControllerBlocked, OSError, UnicodeError, SyntaxError) as exc:
        label = str(exc) if isinstance(exc, ControllerBlocked) else "local_controller_failure"
        print("FERRY_GATE_A_CONTROLLER_BLOCKED:" + label)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
