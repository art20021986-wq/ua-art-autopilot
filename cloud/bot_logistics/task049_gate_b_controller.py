#!/usr/bin/env python3
"""Approved TASK 049 Gate B controller.

Uploads only the approved installer and approval marker to autopilot_inbox,
executes one fixed install command, restarts the one preflight-proven BOT CRM
always-on task through PythonAnywhere's restart endpoint, validates live source
readback, and relays evidence. A restart failure invokes the fixed rollback
command and restarts the original bot code.
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

USERNAME = "Carix"
HOSTS = ("www.pythonanywhere.com", "eu.pythonanywhere.com")
REMOTE_ROOT = "/home/Carix/autopilot_inbox/cloud/bot_logistics"
REMOTE_SCRIPT = REMOTE_ROOT + "/task049_gate_b.py"
REMOTE_APPROVAL = REMOTE_ROOT + "/task_049_owner_approval.marker"
REMOTE_INSTALL_OUTPUT = REMOTE_ROOT + "/task049_gate_b_output.json"
REMOTE_ROLLBACK_OUTPUT = REMOTE_ROOT + "/task049_gate_b_rollback_output.json"
REMOTE_CANDIDATE = REMOTE_ROOT + "/task049_cars_ui.py.candidate"
REMOTE_BACKUP = REMOTE_ROOT + "/task049_cars_ui.py.before_gate_b.20260828T045145Z"
REMOTE_SOURCE = "/home/Carix/cars_ui.py"

INSTALL_COMMAND = (
    "cd " + REMOTE_ROOT + " && python3.10 task049_gate_b.py > "
    + REMOTE_INSTALL_OUTPUT
)
ROLLBACK_COMMAND = (
    "cd " + REMOTE_ROOT
    + " && python3.10 task049_gate_b.py --rollback-after-restart-failure > "
    + REMOTE_ROLLBACK_OUTPUT
)

TARGET_TASK_ID = 266084
TARGET_COMMAND_SHA = "bb7491b6a7cbf510aefe675ed052bf3c1b64fe0cff47edebcccfd8b6848ff240"
EXPECTED_SOURCE_SHA = (
    "06e7da916ea36c4ffafef01c85f59a0574f06d3cdda24aa1f8c242175de726b7"
)
EXPECTED_CANDIDATE_SHA = (
    "3c6f12227e45a3ba936d48d4a12435378045e879fea481def04f3378f6a0f12f"
)

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOCAL_SCRIPT = HERE / "task049_gate_b.py"
LOCAL_APPROVAL = ROOT / "tasks" / "task_049_owner_approval.marker"
EVIDENCE = HERE / "evidence" / "task_049_gate_b.json"
REPORT = HERE / "TASK_049_GATE_B_REPORT.md"

MAX_RESPONSE = 2_000_000
MAX_RECEIPT = 80_000
POLL_INTERVAL = 5
POLL_TIMEOUT = 600
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ControllerBlocked(RuntimeError):
    pass


def sha256(data: bytes) -> str:
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
    boundary = "----task049-gate-b-" + uuid.uuid4().hex
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body = bytearray()
    body.extend((f"--{boundary}\r\n").encode())
    body.extend((
        f'Content-Disposition: form-data; name="content"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode())
    body.extend(data)
    body.extend((f"\r\n--{boundary}--\r\n").encode())
    return bytes(body), "multipart/form-data; boundary=" + boundary


class PythonAnywhereAPI:
    def __init__(self, username: str, host: str, token: str,
                 opener=urllib.request.urlopen):
        if username != USERNAME:
            raise ControllerBlocked("invalid_username")
        if host not in HOSTS:
            raise ControllerBlocked("invalid_host")
        if not token:
            raise ControllerBlocked("missing_token")
        self.username = username
        self.host = host
        self._token = token
        self._opener = opener

    @property
    def base(self) -> str:
        return (
            f"https://{self.host}/api/v0/user/"
            f"{urllib.parse.quote(self.username, safe='')}/"
        )

    def request(self, method: str, url: str, *, data=None, headers=None,
                allowed=(200,), label="request") -> tuple[int, bytes]:
        all_headers = {
            "Authorization": "Token " + self._token,
            "User-Agent": "ua-art-task049-gate-b/1",
        }
        all_headers.update(headers or {})
        request = urllib.request.Request(
            url, data=data, headers=all_headers, method=method
        )
        try:
            with self._opener(request, timeout=60) as response:
                status = getattr(response, "status", response.getcode())
                body = response.read(MAX_RESPONSE + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read(MAX_RESPONSE + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ControllerBlocked("network_error:" + label) from exc
        if len(body) > MAX_RESPONSE:
            raise ControllerBlocked("response_too_large:" + label)
        if status not in allowed:
            raise ControllerBlocked(f"http_status:{label}:{status}")
        return status, body

    def file_url(self, path: str) -> str:
        allowed = {
            REMOTE_SCRIPT, REMOTE_APPROVAL, REMOTE_INSTALL_OUTPUT,
            REMOTE_ROLLBACK_OUTPUT, REMOTE_CANDIDATE, REMOTE_BACKUP,
            REMOTE_SOURCE,
        }
        if path not in allowed:
            raise ControllerBlocked("file_path_not_allowed")
        return self.base + "files/path" + urllib.parse.quote(path, safe="/")

    def upload(self, path: str, data: bytes) -> None:
        if path not in {REMOTE_SCRIPT, REMOTE_APPROVAL}:
            raise ControllerBlocked("upload_path_not_allowed")
        body, content_type = multipart(pathlib.PurePosixPath(path).name, data)
        self.request(
            "POST", self.file_url(path), data=body,
            headers={"Content-Type": content_type}, allowed=(200, 201),
            label="upload",
        )

    def read_file(self, path: str) -> bytes:
        status, body = self.request(
            "GET", self.file_url(path), allowed=(200, 404), label="read_file"
        )
        if status == 404:
            raise FileNotFoundError(path)
        return body

    def delete_output(self, path: str) -> None:
        if path not in {REMOTE_INSTALL_OUTPUT, REMOTE_ROLLBACK_OUTPUT}:
            raise ControllerBlocked("delete_path_not_allowed")
        self.request(
            "DELETE", self.file_url(path), allowed=(204, 404), label="delete_output"
        )

    @staticmethod
    def trigger_id(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) and identifier > 0 else None

    def create_trigger(self, command: str) -> tuple[str, int]:
        if command not in {INSTALL_COMMAND, ROLLBACK_COMMAND}:
            raise ControllerBlocked("command_not_allowed")
        form = urllib.parse.urlencode({
            "command": command,
            "description": (
                "UA ART task049 approved Gate B"
                if command == INSTALL_COMMAND
                else "UA ART task049 automatic rollback"
            ),
            "enabled": "true",
        }).encode()
        status, body = self.request(
            "POST", self.base + "always_on/", data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
            label="create_trigger",
        )
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
        if identifier is not None:
            if identifier == TARGET_TASK_ID:
                raise ControllerBlocked("temporary_trigger_collides_with_target")
            return "always_on", identifier

        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({
            "command": command,
            "description": (
                "UA ART task049 approved Gate B fallback"
                if command == INSTALL_COMMAND
                else "UA ART task049 automatic rollback fallback"
            ),
            "enabled": "true",
            "interval": "daily",
            "hour": run_at.hour,
            "minute": run_at.minute,
        }).encode()
        status, body = self.request(
            "POST", self.base + "schedule/", data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
            label="create_schedule_fallback",
        )
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
        if identifier is None:
            raise ControllerBlocked("temporary_trigger_unavailable")
        return "schedule", identifier

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        kind, identifier = trigger
        if kind not in {"always_on", "schedule"} or not isinstance(identifier, int) or identifier <= 0:
            raise ControllerBlocked("trigger_invalid")
        if kind == "always_on" and identifier == TARGET_TASK_ID:
            raise ControllerBlocked("refuse_delete_target")
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request(
            "DELETE", self.base + f"{endpoint}/{identifier}/",
            allowed=(200, 202, 204, 404), label="delete_trigger",
        )

    def task(self, identifier: int) -> dict:
        if identifier != TARGET_TASK_ID:
            raise ControllerBlocked("task_id_not_allowed")
        _, body = self.request(
            "GET", self.base + f"always_on/{identifier}/",
            allowed=(200,), label="get_target_task",
        )
        return strict_json(body, "target_task")

    def restart_target(self) -> int:
        status, _ = self.request(
            "POST", self.base + f"always_on/{TARGET_TASK_ID}/restart/",
            data=b"", allowed=(200, 201, 202, 204), label="restart_target",
        )
        return status


def validate_target(item: dict) -> dict:
    identifier = item.get("id")
    command = item.get("command")
    if identifier != TARGET_TASK_ID:
        raise ControllerBlocked("target_id_changed")
    if not isinstance(command, str) or sha256(command.encode("utf-8")) != TARGET_COMMAND_SHA:
        raise ControllerBlocked("target_command_changed")
    if item.get("enabled") is not True:
        raise ControllerBlocked("target_not_enabled")
    return {
        "id": identifier,
        "command_sha256": TARGET_COMMAND_SHA,
        "enabled": True,
        "running": item.get("running") if isinstance(item.get("running"), bool) else None,
    }


def validate_install_receipt(receipt: dict) -> dict:
    if receipt.get("task_id") != "task_049" or receipt.get("mode") != "GATE_B_INSTALL":
        raise ControllerBlocked("install_receipt_identity_invalid")
    if receipt.get("status") != "PASS":
        raise ControllerBlocked("install_not_pass")
    if receipt.get("production_write") is not True:
        raise ControllerBlocked("install_write_marker_invalid")
    if receipt.get("source_path") != REMOTE_SOURCE:
        raise ControllerBlocked("install_source_path_invalid")
    if receipt.get("candidate_path") != REMOTE_CANDIDATE:
        raise ControllerBlocked("install_candidate_path_invalid")
    if receipt.get("backup_path") != REMOTE_BACKUP:
        raise ControllerBlocked("install_backup_path_invalid")
    for field in ("crm_write", "db_write", "service_restart", "website_write", "rollback"):
        if receipt.get(field) is not False:
            raise ControllerBlocked("install_safety_marker_invalid:" + field)
    if receipt.get("source_sha256_before") != EXPECTED_SOURCE_SHA:
        raise ControllerBlocked("install_source_before_invalid")
    if receipt.get("source_sha256_after") != EXPECTED_CANDIDATE_SHA:
        raise ControllerBlocked("install_source_after_invalid")
    if receipt.get("backup_sha256") != EXPECTED_SOURCE_SHA:
        raise ControllerBlocked("install_backup_invalid")
    before = receipt.get("db_sha256_before")
    after = receipt.get("db_sha256_after")
    if not isinstance(before, str) or not HEX64.fullmatch(before) or before != after:
        raise ControllerBlocked("install_db_hash_invalid")
    if receipt.get("ua0006_container_preserved") is not True:
        raise ControllerBlocked("container_not_preserved")
    if receipt.get("ua0006_sea_date_preserved") is not True:
        raise ControllerBlocked("sea_date_not_preserved")
    if receipt.get("ua0006_container") != "ONEYSELGF1046602":
        raise ControllerBlocked("container_value_invalid")
    if receipt.get("ua0006_sea_date_out") != "2026-01-24":
        raise ControllerBlocked("sea_date_value_invalid")
    checks = receipt.get("checks")
    if not isinstance(checks, dict) or checks.get("compiled") is not True:
        raise ControllerBlocked("install_checks_invalid")
    expected_checks = {
        "outer_hub_labels": 2,
        "card_entry": 1,
        "editor_entry": 1,
        "handler": 1,
        "old_delivery_button": 0,
        "old_post_stage_button": 0,
        "old_editor_days": 0,
        "old_editor_container": 0,
    }
    for key, value in expected_checks.items():
        if checks.get(key) != value:
            raise ControllerBlocked("install_check_invalid:" + key)
    if receipt.get("errors") != []:
        raise ControllerBlocked("install_pass_has_errors")
    return receipt


def validate_rollback_receipt(receipt: dict) -> dict:
    if receipt.get("task_id") != "task_049":
        raise ControllerBlocked("rollback_task_invalid")
    if receipt.get("mode") != "GATE_B_ROLLBACK_AFTER_RESTART_FAILURE":
        raise ControllerBlocked("rollback_mode_invalid")
    if receipt.get("status") != "PASS" or receipt.get("rollback") is not True:
        raise ControllerBlocked("rollback_not_pass")
    if receipt.get("source_path") != REMOTE_SOURCE:
        raise ControllerBlocked("rollback_source_path_invalid")
    if receipt.get("backup_path") != REMOTE_BACKUP:
        raise ControllerBlocked("rollback_backup_path_invalid")
    if receipt.get("production_write") is not True:
        raise ControllerBlocked("rollback_write_marker_invalid")
    if receipt.get("source_sha256_after") != EXPECTED_SOURCE_SHA:
        raise ControllerBlocked("rollback_source_invalid")
    for field in ("db_write", "crm_write", "service_restart", "website_write"):
        if receipt.get(field) is not False:
            raise ControllerBlocked("rollback_safety_marker_invalid:" + field)
    before = receipt.get("db_sha256_before")
    after = receipt.get("db_sha256_after")
    if not isinstance(before, str) or not HEX64.fullmatch(before) or before != after:
        raise ControllerBlocked("rollback_db_hash_invalid")
    if receipt.get("ua0006_container_preserved") is not True:
        raise ControllerBlocked("rollback_container_not_preserved")
    if receipt.get("ua0006_sea_date_preserved") is not True:
        raise ControllerBlocked("rollback_sea_date_not_preserved")
    if receipt.get("ua0006_container") != "ONEYSELGF1046602":
        raise ControllerBlocked("rollback_container_value_invalid")
    if receipt.get("ua0006_sea_date_out") != "2026-01-24":
        raise ControllerBlocked("rollback_sea_date_value_invalid")
    if receipt.get("errors") != []:
        raise ControllerBlocked("rollback_pass_has_errors")
    return receipt


class GateBController:
    def __init__(self, api, sleep=time.sleep, monotonic=time.monotonic,
                 poll_interval=POLL_INTERVAL, poll_timeout=POLL_TIMEOUT):
        self.api = api
        self.sleep = sleep
        self.monotonic = monotonic
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self.install_started = False
        self.relayed = False
        self.target_before = None

    def upload_and_verify(self) -> None:
        script = LOCAL_SCRIPT.read_bytes()
        approval = LOCAL_APPROVAL.read_bytes()
        compile(script.decode("utf-8"), str(LOCAL_SCRIPT), "exec")
        if b"DECISION: APPROVE" not in approval or b"USER_REPLY: APPROVE" not in approval:
            raise ControllerBlocked("local_approval_invalid")
        for remote, data in ((REMOTE_SCRIPT, script), (REMOTE_APPROVAL, approval)):
            self.api.upload(remote, data)
            if sha256(self.api.read_file(remote)) != sha256(data):
                raise ControllerBlocked("remote_upload_hash_mismatch")

    def poll(self, path: str, label: str) -> dict:
        deadline = self.monotonic() + self.poll_timeout
        while self.monotonic() < deadline:
            try:
                data = self.api.read_file(path)
            except FileNotFoundError:
                data = b""
            if data:
                if len(data) > MAX_RECEIPT:
                    raise ControllerBlocked("receipt_too_large:" + label)
                return strict_json(data, label)
            self.sleep(self.poll_interval)
        raise ControllerBlocked("receipt_timeout:" + label)

    def execute(self, command: str, output: str) -> dict:
        self.api.delete_output(output)
        trigger = None
        try:
            trigger = self.api.create_trigger(command)
            if command == INSTALL_COMMAND:
                self.install_started = True
            return self.poll(output, "install" if command == INSTALL_COMMAND else "rollback")
        finally:
            if trigger is not None:
                try:
                    self.api.delete_trigger(trigger)
                except Exception:
                    pass

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
            EVIDENCE,
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        report = f'''# TASK 049 Gate B report

controller_status: {receipt.get("controller_status", "BLOCKED")}
status: {receipt.get("status", "BLOCKED")}
source_sha256_before: {receipt.get("source_sha256_before", "NONE")}
source_sha256_after: {receipt.get("source_sha256_after", "NONE")}
backup_sha256: {receipt.get("backup_sha256", "NONE")}
db_hash_unchanged: {str(receipt.get("db_sha256_before") == receipt.get("db_sha256_after") and bool(receipt.get("db_sha256_before"))).lower()}
production_write: {"true" if receipt.get("production_write") is True else "false" if receipt.get("production_write") is False else "unknown"}
ua0006_container_preserved: {str(receipt.get("ua0006_container_preserved") is True).lower()}
ua0006_sea_date_preserved: {str(receipt.get("ua0006_sea_date_preserved") is True).lower()}
ua0006_container: {receipt.get("ua0006_container", "NONE")}
ua0006_sea_date_out: {receipt.get("ua0006_sea_date_out", "NONE")}
card_hub_entries: {receipt.get("checks", {}).get("card_entry", "NONE")}
editor_hub_entries: {receipt.get("checks", {}).get("editor_entry", "NONE")}
old_delivery_buttons: {receipt.get("checks", {}).get("old_delivery_button", "NONE")}
old_editor_days_entries: {receipt.get("checks", {}).get("old_editor_days", "NONE")}
old_editor_container_entries: {receipt.get("checks", {}).get("old_editor_container", "NONE")}
target_always_on_id: {receipt.get("target_always_on_id", "NONE")}
restart_accepted: {str(receipt.get("restart_accepted") is True).lower()}
service_restart: {str(receipt.get("service_restart") is True).lower()}
website_write: {str(receipt.get("website_write") is True).lower()}
crm_write: {str(receipt.get("crm_write") is True).lower()}
db_write: {str(receipt.get("db_write") is True).lower()}
rollback: {str(receipt.get("rollback") is True).lower()}
errors: {','.join(receipt.get("errors", [])) or 'NONE'}
'''
        self.atomic_write(REPORT, report)
        self.relayed = True

    def blocked_receipt(self, reason: str) -> dict:
        target = self.target_before or {}
        return {
            "task_id": "task_049",
            "mode": "GATE_B_CONTROLLER",
            "controller_status": "BLOCKED",
            "status": "BLOCKED",
            "production_write": None if self.install_started else False,
            "crm_write": False,
            "db_write": False,
            "service_restart": False,
            "website_write": False,
            "rollback": False,
            "restart_accepted": False,
            "target_always_on_id": target.get("id"),
            "target_command_sha256": target.get("command_sha256"),
            "errors": [reason],
        }

    def relay_invalid_install(self, receipt: dict, reason: str) -> None:
        failed = dict(receipt)
        errors = failed.get("errors")
        if not isinstance(errors, list) or not all(isinstance(item, str) for item in errors):
            errors = []
        if reason not in errors:
            errors.append(reason)
        failed.update({
            "controller_status": "BLOCKED",
            "restart_accepted": False,
            "target_always_on_id": (self.target_before or {}).get("id"),
            "target_command_sha256": (self.target_before or {}).get(
                "command_sha256"
            ),
            "errors": errors,
        })
        self.relay(failed)

    def rollback_for_restart_failure(self, reason: str) -> dict:
        rollback = validate_rollback_receipt(
            self.execute(ROLLBACK_COMMAND, REMOTE_ROLLBACK_OUTPUT)
        )
        rollback_status = self.api.restart_target()
        target = validate_target(self.api.task(TARGET_TASK_ID))
        rollback.update({
            "controller_status": "ROLLED_BACK",
            "status": "ROLLED_BACK",
            "restart_accepted": rollback_status in (200, 201, 202, 204),
            "target_always_on_id": target["id"],
            "target_command_sha256": target["command_sha256"],
            "errors": [reason],
        })
        self.relay(rollback)
        return rollback

    def run(self) -> dict:
        try:
            self.upload_and_verify()
            target_before = validate_target(self.api.task(TARGET_TASK_ID))
            self.target_before = target_before
            source_before = self.api.read_file(REMOTE_SOURCE)
            candidate = self.api.read_file(REMOTE_CANDIDATE)
            if sha256(source_before) != EXPECTED_SOURCE_SHA:
                raise ControllerBlocked("preinstall_source_hash_changed")
            if sha256(candidate) != EXPECTED_CANDIDATE_SHA:
                raise ControllerBlocked("preinstall_candidate_hash_changed")

            raw_install = self.execute(INSTALL_COMMAND, REMOTE_INSTALL_OUTPUT)
            try:
                install = validate_install_receipt(raw_install)
            except ControllerBlocked as exc:
                self.relay_invalid_install(raw_install, str(exc))
                raise

            try:
                backup = self.api.read_file(REMOTE_BACKUP)
                if sha256(backup) != EXPECTED_SOURCE_SHA:
                    raise ControllerBlocked("postinstall_backup_hash_invalid")
                restart_status = self.api.restart_target()
                self.sleep(5)
                target_after = validate_target(self.api.task(TARGET_TASK_ID))
                live = self.api.read_file(REMOTE_SOURCE)
                if sha256(live) != EXPECTED_CANDIDATE_SHA:
                    raise ControllerBlocked("post_restart_source_hash_invalid")
                install.update({
                    "controller_status": "PASS",
                    "service_restart": True,
                    "restart_accepted": restart_status in (200, 201, 202, 204),
                    "target_always_on_id": target_after["id"],
                    "target_command_sha256": target_after["command_sha256"],
                    "target_running": target_after["running"],
                    "pre_restart_target_running": target_before["running"],
                    "post_restart_source_sha256": sha256(live),
                })
                self.relay(install)
                return install
            except Exception as exc:
                reason = (
                    str(exc)
                    if isinstance(exc, ControllerBlocked)
                    else "restart_failure"
                )
                self.rollback_for_restart_failure(reason)
                raise ControllerBlocked(
                    "install_rolled_back_after_restart_failure"
                ) from exc
        finally:
            for path in (REMOTE_INSTALL_OUTPUT, REMOTE_ROLLBACK_OUTPUT):
                try:
                    self.api.delete_output(path)
                except Exception:
                    pass


def main() -> int:
    controller = None
    try:
        api = PythonAnywhereAPI(
            os.environ.get("PYTHONANYWHERE_USERNAME", USERNAME),
            os.environ.get("PYTHONANYWHERE_HOST", HOSTS[0]),
            os.environ.get("PYTHONANYWHERE_API_TOKEN", ""),
        )
        controller = GateBController(api)
        receipt = controller.run()
        print(json.dumps({
            "status": receipt["controller_status"],
            "source_installed": receipt["source_sha256_after"] == EXPECTED_CANDIDATE_SHA,
            "restart_accepted": receipt["restart_accepted"],
            "db_write": False,
            "website_write": False,
        }, sort_keys=True))
        return 0
    except (ControllerBlocked, OSError, UnicodeError, SyntaxError) as exc:
        label = str(exc) if isinstance(exc, ControllerBlocked) else "controller_failure"
        if controller is not None and not controller.relayed:
            try:
                controller.relay(controller.blocked_receipt(label))
            except OSError:
                pass
        print("TASK049_GATE_B_BLOCKED:" + label)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
