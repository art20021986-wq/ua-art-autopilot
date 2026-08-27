#!/usr/bin/env python3
"""GitHub-side controller for TASK 049 isolated PythonAnywhere Gate A.

It uploads exactly two reviewed scripts to autopilot_inbox, runs one fixed
Gate A command, validates the bounded receipt and candidate hash, then relays
evidence to GitHub. No production/CRM path is writable through this module.
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
REMOTE_ROOT = "/home/Carix/autopilot_inbox/cloud/bot_logistics"
REMOTE_TRANSFORM = REMOTE_ROOT + "/task049_transform.py"
REMOTE_GATE_A = REMOTE_ROOT + "/task049_gate_a.py"
REMOTE_OUTPUT = REMOTE_ROOT + "/task049_gate_a_receipt.json"
REMOTE_CANDIDATE = REMOTE_ROOT + "/task049_cars_ui.py.candidate"
EXACT_COMMAND = (
    "cd " + REMOTE_ROOT
    + " && python3.10 task049_gate_a.py > " + REMOTE_OUTPUT
)

HERE = pathlib.Path(__file__).resolve().parent
LOCAL_FILES = {
    REMOTE_TRANSFORM: HERE / "task049_transform.py",
    REMOTE_GATE_A: HERE / "task049_gate_a.py",
}
EVIDENCE_PATH = HERE / "evidence" / "task_049_gate_a.json"
REPORT_PATH = HERE / "TASK_049_GATE_A_REPORT.md"

MAX_RESPONSE_BYTES = 2_000_000
MAX_RECEIPT_BYTES = 30_000
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
    boundary = "----task049-" + uuid.uuid4().hex
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
            "User-Agent": "ua-art-task049-gate-a/1",
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
        if path not in {
            REMOTE_TRANSFORM, REMOTE_GATE_A, REMOTE_OUTPUT, REMOTE_CANDIDATE
        }:
            raise ControllerBlocked("remote_file_path_not_allowed")
        return self.base + "files/path" + urllib.parse.quote(path, safe="/")

    def upload_script(self, remote_path: str, data: bytes) -> None:
        if remote_path not in {REMOTE_TRANSFORM, REMOTE_GATE_A}:
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
                "description": "UA ART task049 isolated Gate A",
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
                "description": "UA ART task049 isolated Gate A fallback",
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
            "task_id", "mode", "status", "source_path", "candidate_path",
            "production_write", "crm_write", "db_write", "service_reload",
            "gate_b_executed", "ua0009_published", "errors", "source_sha256",
            "candidate_sha256", "candidate_size", "operations", "checks",
            "already_applied",
        }
        if set(receipt) - allowed:
            raise ControllerBlocked("receipt_unknown_key")
        if receipt.get("task_id") != "task_049":
            raise ControllerBlocked("receipt_task_invalid")
        if receipt.get("mode") != "GATE_A_ISOLATED_CANDIDATE":
            raise ControllerBlocked("receipt_mode_invalid")
        for field in (
            "production_write", "crm_write", "db_write", "service_reload",
            "gate_b_executed", "ua0009_published",
        ):
            if receipt.get(field) is not False:
                raise ControllerBlocked("receipt_safety_invalid:" + field)
        if receipt.get("source_path") != "/home/Carix/cars_ui.py":
            raise ControllerBlocked("receipt_source_path_invalid")
        if receipt.get("candidate_path") != REMOTE_CANDIDATE:
            raise ControllerBlocked("receipt_candidate_path_invalid")
        if receipt.get("status") != "PASS":
            raise ControllerBlocked("remote_gate_a_not_pass")
        if receipt.get("errors") != []:
            raise ControllerBlocked("pass_receipt_has_errors")
        source_sha = receipt.get("source_sha256")
        candidate_sha = receipt.get("candidate_sha256")
        if source_sha != "06e7da916ea36c4ffafef01c85f59a0574f06d3cdda24aa1f8c242175de726b7":
            raise ControllerBlocked("receipt_source_sha_invalid")
        if not isinstance(candidate_sha, str) or not HEX64.fullmatch(candidate_sha):
            raise ControllerBlocked("receipt_candidate_sha_invalid")
        if not isinstance(receipt.get("candidate_size"), int) or not 1 <= receipt["candidate_size"] <= 2_000_000:
            raise ControllerBlocked("receipt_candidate_size_invalid")
        operations = receipt.get("operations")
        if operations != [
            "centralize_card_keyboard",
            "remove_logistics_from_editor_grid",
            "add_editor_hub_entry",
            "rename_eta_field_label",
            "remove_post_stage_delivery_button",
            "insert_logistics_hub",
            "register_logistics_hub",
        ]:
            raise ControllerBlocked("receipt_operations_invalid")
        checks = receipt.get("checks")
        if not isinstance(checks, dict) or checks.get("compiled") is not True:
            raise ControllerBlocked("receipt_checks_invalid")
        exact_checks = {
            "hub_outer_labels": 2,
            "card_entry": 1,
            "editor_entry": 1,
            "hub_handler_registration": 1,
            "hub_stage_action": 1,
            "hub_container_action": 1,
            "hub_days_action": 1,
            "old_delivery_button": 0,
            "old_post_stage_button": 0,
            "old_editor_days": 0,
            "old_editor_container": 0,
        }
        for key, value in exact_checks.items():
            if checks.get(key) != value:
                raise ControllerBlocked("receipt_check_invalid:" + key)
        if receipt.get("already_applied") is not False:
            raise ControllerBlocked("receipt_already_applied_invalid")
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
        checks = receipt["checks"]
        report = f'''# TASK 049 Gate A report

status: PASS
source_sha256: {receipt["source_sha256"]}
candidate_sha256: {receipt["candidate_sha256"]}
candidate_compiled: {str(checks["compiled"]).lower()}
card_hub_entries: {checks["card_entry"]}
editor_hub_entries: {checks["editor_entry"]}
old_delivery_buttons: {checks["old_delivery_button"]}
old_post_stage_buttons: {checks["old_post_stage_button"]}
old_editor_days_entries: {checks["old_editor_days"]}
old_editor_container_entries: {checks["old_editor_container"]}
production_write: false
crm_write: false
db_write: false
service_reload: false
gate_b_executed: false
ua0009_published: false

Gate A created and compiled only the isolated candidate under autopilot_inbox.
Gate B is waiting for separate explicit owner approval.
'''
        self.atomic_write(REPORT_PATH, report)

    def run(self) -> dict:
        self.upload_and_verify()
        trigger = None
        try:
            self.api.delete_output()
            trigger = self.api.create_trigger()
            receipt = self.validate_receipt(self.poll_receipt())
            candidate = self.api.read_file(REMOTE_CANDIDATE)
            if len(candidate) != receipt["candidate_size"]:
                raise ControllerBlocked("candidate_size_readback_mismatch")
            if sha256_bytes(candidate) != receipt["candidate_sha256"]:
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
            "status": "PASS",
            "remote_gate_a": receipt["status"],
            "production_write": False,
            "crm_write": False,
            "db_write": False,
            "service_reload": False,
        }, sort_keys=True))
        return 0
    except (ControllerBlocked, OSError, UnicodeError, SyntaxError) as exc:
        label = str(exc) if isinstance(exc, ControllerBlocked) else "local_controller_failure"
        print("TASK048_GATE_A_BLOCKED:" + label)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

