#!/usr/bin/env python3
"""Run and relay one tightly bounded PythonAnywhere read-only discovery.

This is the GitHub-side controller for TASK 039. It validates local tests,
the safe-inbox sync manifest and remote script bytes before creating one
temporary trigger. The only remote file mutation is deletion/creation of the
exact safe-inbox receipt path. Production files and crm.db are never written.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ALLOWED_USERNAME = "Carix"
ALLOWED_HOSTS = ("www.pythonanywhere.com", "eu.pythonanywhere.com")
REMOTE_ROOT = "/home/Carix/autopilot_inbox"
REMOTE_MANIFEST_PATH = REMOTE_ROOT + "/_sync_manifest.json"
REMOTE_OUTPUT_PATH = (
    REMOTE_ROOT + "/cloud/bot_logistics/task037_discovery_output.json"
)
REMOTE_DISCOVERY_SCRIPT = (
    REMOTE_ROOT + "/cloud/bot_logistics/bot_logistics_discovery.py"
)
REMOTE_DB_PATH = "/home/Carix/crm.db"
REMOTE_SOURCES = (
    "/home/Carix/cars_ui.py",
    "/home/Carix/team_bot.py",
    "/home/Carix/avtoperedacha.py",
    "/home/Carix/db.py",
    "/home/Carix/run_all.py",
    "/home/Carix/start_safe.py",
)

EXACT_DISCOVERY_COMMAND = (
    "python3.10 "
    + REMOTE_DISCOVERY_SCRIPT
    + " --db "
    + REMOTE_DB_PATH
    + "".join(" --source " + path for path in REMOTE_SOURCES)
)
EXACT_EXECUTION_COMMAND = EXACT_DISCOVERY_COMMAND + " > " + REMOTE_OUTPUT_PATH

BOT_LOGISTICS_DIR = pathlib.Path(__file__).resolve().parent
REPOSITORY_ROOT = BOT_LOGISTICS_DIR.parents[1]
LOCAL_ARTIFACTS = {
    "cloud/bot_logistics/bot_logistics_discovery.py":
        BOT_LOGISTICS_DIR / "bot_logistics_discovery.py",
    "cloud/bot_logistics/test_bot_logistics.py":
        BOT_LOGISTICS_DIR / "test_bot_logistics.py",
    "cloud/bot_logistics/pythonanywhere_discovery_controller.py":
        BOT_LOGISTICS_DIR / "pythonanywhere_discovery_controller.py",
    "cloud/bot_logistics/test_discovery_controller.py":
        BOT_LOGISTICS_DIR / "test_discovery_controller.py",
}
EVIDENCE_PATH_LOCAL = (
    BOT_LOGISTICS_DIR / "evidence" / "task_037_discovery.json"
)
REPORT_PATH_LOCAL = (
    BOT_LOGISTICS_DIR / "TASK_039_DISCOVERY_CONTROLLER_REPORT.md"
)

MAX_REMOTE_BYTES = 400_000
MAX_MANIFEST_AGE_SECONDS = 3_600
MAX_RECEIPT_BYTES = 300_000
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 600
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
SENSITIVE_RE = re.compile(
    r"(?i)(?:secret|token|password|api[-_ ]?key|authorization|"
    r"private[-_ ]?key|credential)"
)
TOKEN_SHAPE_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:sk-[A-Za-z0-9_-]{16,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|"
    r"eyJ[A-Za-z0-9_-]{20,}(?:\.[A-Za-z0-9_-]+){1,2}|"
    r"[A-Za-z0-9_-]{40,})(?![A-Za-z0-9_-])"
)
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d ()-]{7,}\d(?!\w)")
VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.IGNORECASE)
FORBIDDEN_RECEIPT_KEYS = {
    "container_value",
    "current_container",
    "old_container",
    "new_container",
    "vin",
    "phone",
    "email",
}


class ControllerError(RuntimeError):
    """A sanitized, fail-closed controller error."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: pathlib.Path | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ControllerError("duplicate_json_key")
        result[key] = value
    return result


def parse_strict_json(text: str, label: str) -> dict:
    try:
        value = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ControllerError("invalid_json:" + label) from exc
    if not isinstance(value, dict):
        raise ControllerError("json_not_object:" + label)
    return value


def _parse_utc(value: object) -> dt.datetime:
    if not isinstance(value, str):
        raise ControllerError("manifest_time_missing")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ControllerError("manifest_time_invalid") from exc
    if parsed.tzinfo is None:
        raise ControllerError("manifest_time_naive")
    return parsed.astimezone(dt.timezone.utc)


def _contains_sensitive(value: object, key: str | None = None) -> bool:
    if isinstance(value, dict):
        for item_key, item in value.items():
            lowered = str(item_key).casefold()
            if lowered in FORBIDDEN_RECEIPT_KEYS:
                return True
            if _contains_sensitive(item, lowered):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_sensitive(item, key) for item in value)
    if not isinstance(value, str):
        return False
    if key and "sha256" in key and HEX64_RE.fullmatch(value):
        return False
    if "ONEYSELGF1046602" in value.upper():
        return True
    return bool(
        SENSITIVE_RE.search(value)
        or TOKEN_SHAPE_RE.search(value)
        or EMAIL_RE.search(value)
        or PHONE_RE.search(value)
        or VIN_RE.search(value)
    )


class PythonAnywhereAPI:
    """Minimal allowlisted PythonAnywhere REST transport."""

    def __init__(
        self,
        *,
        username: str,
        host: str,
        token: str,
        opener=urllib.request.urlopen,
        timeout: int = 45,
    ):
        if username != ALLOWED_USERNAME:
            raise ControllerError("invalid_username")
        if host not in ALLOWED_HOSTS:
            raise ControllerError("invalid_host")
        if not token:
            raise ControllerError("missing_api_token")
        self.username = username
        self.host = host
        self._token = token
        self._opener = opener
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        username = urllib.parse.quote(self.username, safe="")
        return f"https://{self.host}/api/v0/user/{username}/"

    def _request(
        self,
        method: str,
        url: str,
        *,
        form: dict | None = None,
        allowed_statuses=(200,),
        operation: str,
    ) -> tuple[int, bytes]:
        data = None
        headers = {
            "Authorization": "Token " + self._token,
            "User-Agent": "ua-art-bot-logistics-discovery/1",
        }
        if form is not None:
            data = urllib.parse.urlencode(form).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(
            url, data=data, headers=headers, method=method
        )
        try:
            with self._opener(request, timeout=self.timeout) as response:
                status = getattr(response, "status", response.getcode())
                body = response.read(MAX_REMOTE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read(MAX_REMOTE_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ControllerError("network_error:" + operation) from exc
        if len(body) > MAX_REMOTE_BYTES:
            raise ControllerError("remote_response_too_large:" + operation)
        if status not in allowed_statuses:
            raise ControllerError(
                "unexpected_http_status:%s:%s" % (operation, status)
            )
        return status, body

    def _file_url(self, path: str) -> str:
        allowed = {
            REMOTE_MANIFEST_PATH,
            REMOTE_OUTPUT_PATH,
            *(REMOTE_ROOT + "/" + source for source in LOCAL_ARTIFACTS),
        }
        if path not in allowed:
            raise ControllerError("remote_file_path_not_allowed")
        return self.base_url + "files/path" + urllib.parse.quote(path, safe="/")

    def read_file(self, path: str) -> str:
        status, body = self._request(
            "GET",
            self._file_url(path),
            allowed_statuses=(200, 404),
            operation="read_file",
        )
        if status == 404:
            raise FileNotFoundError(path)
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ControllerError("remote_file_not_utf8") from exc

    def delete_output(self, path: str) -> None:
        if path != REMOTE_OUTPUT_PATH:
            raise ControllerError("delete_path_not_allowed")
        self._request(
            "DELETE",
            self._file_url(path),
            allowed_statuses=(204, 404),
            operation="delete_output",
        )

    @staticmethod
    def _task_id(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        task_id = value.get("id") if isinstance(value, dict) else None
        return task_id if isinstance(task_id, int) and task_id > 0 else None

    def create_always_on_task(self, command: str) -> tuple[str, int] | None:
        if command != EXACT_EXECUTION_COMMAND:
            raise ControllerError("execution_command_not_allowed")
        status, body = self._request(
            "POST",
            self.base_url + "always_on/",
            form={
                "command": command,
                "description": "UA ART task037 read-only discovery",
                "enabled": "true",
            },
            allowed_statuses=(200, 201, 202, 400, 403, 404, 409),
            operation="create_always_on",
        )
        if status not in (200, 201, 202):
            return None
        task_id = self._task_id(body)
        return ("always_on", task_id) if task_id is not None else None

    def create_scheduled_task(self, command: str) -> tuple[str, int] | None:
        if command != EXACT_EXECUTION_COMMAND:
            raise ControllerError("execution_command_not_allowed")
        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        status, body = self._request(
            "POST",
            self.base_url + "schedule/",
            form={
                "command": command,
                "description": "UA ART task037 read-only discovery fallback",
                "enabled": "true",
                "interval": "daily",
                "hour": run_at.hour,
                "minute": run_at.minute,
            },
            allowed_statuses=(200, 201, 202, 400, 403, 404, 409),
            operation="create_schedule",
        )
        if status not in (200, 201, 202):
            return None
        task_id = self._task_id(body)
        return ("schedule", task_id) if task_id is not None else None

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        kind, task_id = trigger
        if kind not in {"always_on", "schedule"}:
            raise ControllerError("trigger_kind_not_allowed")
        if not isinstance(task_id, int) or task_id <= 0:
            raise ControllerError("trigger_id_invalid")
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self._request(
            "DELETE",
            self.base_url + f"{endpoint}/{task_id}/",
            allowed_statuses=(200, 202, 204, 404),
            operation="delete_trigger",
        )


class DiscoveryController:
    def __init__(
        self,
        api,
        *,
        env=None,
        sleep=time.sleep,
        monotonic=time.monotonic,
        utc_now=lambda: dt.datetime.now(dt.timezone.utc),
        subprocess_runner=None,
        poll_interval=POLL_INTERVAL_SECONDS,
        poll_timeout=POLL_TIMEOUT_SECONDS,
    ):
        self.api = api
        self.env = os.environ if env is None else env
        self.sleep = sleep
        self.monotonic = monotonic
        self.utc_now = utc_now
        self.subprocess_runner = (
            subprocess_runner or self._default_subprocess_runner
        )
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout

    @staticmethod
    def _default_subprocess_runner(command):
        completed = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        return completed.returncode

    def validate_environment(self) -> None:
        if self.env.get("PYTHONANYWHERE_USERNAME", ALLOWED_USERNAME) != ALLOWED_USERNAME:
            raise ControllerError("invalid_username")
        if self.env.get("PYTHONANYWHERE_HOST", ALLOWED_HOSTS[0]) not in ALLOWED_HOSTS:
            raise ControllerError("invalid_host")
        if not self.env.get("PYTHONANYWHERE_API_TOKEN"):
            raise ControllerError("missing_api_token")

    def verify_local_artifacts(self) -> dict[str, str]:
        paths = [str(path) for path in LOCAL_ARTIFACTS.values()]
        compile_command = [sys.executable, "-m", "py_compile", *paths]
        if self.subprocess_runner(compile_command) != 0:
            raise ControllerError("local_compile_failed")
        test_command = [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-v",
            "-s",
            str(BOT_LOGISTICS_DIR),
            "-p",
            "test*.py",
        ]
        if self.subprocess_runner(test_command) != 0:
            raise ControllerError("local_tests_failed")
        return {
            source: sha256_file(path)
            for source, path in LOCAL_ARTIFACTS.items()
        }

    def verify_manifest(self, local_hashes: dict[str, str]) -> dict:
        manifest = parse_strict_json(
            self.api.read_file(REMOTE_MANIFEST_PATH), "sync_manifest"
        )
        if manifest.get("status") != "PASS":
            raise ControllerError("manifest_not_pass")
        if manifest.get("remote_root") != REMOTE_ROOT:
            raise ControllerError("manifest_remote_root_invalid")
        for field in (
            "production_touched",
            "crm_touched",
            "executed_remote_code",
            "webapp_reloaded",
        ):
            if manifest.get(field) is not False:
                raise ControllerError("manifest_safety_field_invalid:" + field)

        generated = _parse_utc(manifest.get("generated_at_utc"))
        age = (self.utc_now() - generated).total_seconds()
        if age < -300 or age > MAX_MANIFEST_AGE_SECONDS:
            raise ControllerError("manifest_stale")

        entries = manifest.get("files")
        if not isinstance(entries, list) or not 1 <= len(entries) <= 40:
            raise ControllerError("manifest_file_list_invalid")
        by_source = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise ControllerError("manifest_entry_invalid")
            source = entry.get("source")
            if not isinstance(source, str) or source in by_source:
                raise ControllerError("manifest_source_invalid")
            by_source[source] = entry

        for source, local_hash in local_hashes.items():
            entry = by_source.get(source)
            if entry is None:
                raise ControllerError("manifest_required_source_missing")
            expected_remote = REMOTE_ROOT + "/" + source
            if entry.get("remote") != expected_remote:
                raise ControllerError("manifest_remote_path_mismatch")
            if entry.get("sha256") != local_hash:
                raise ControllerError("manifest_hash_mismatch")
            if entry.get("http_status") not in (200, 201):
                raise ControllerError("manifest_upload_status_invalid")

        remote_script = self.api.read_file(REMOTE_DISCOVERY_SCRIPT).encode(
            "utf-8"
        )
        expected_script_hash = local_hashes[
            "cloud/bot_logistics/bot_logistics_discovery.py"
        ]
        if sha256_bytes(remote_script) != expected_script_hash:
            raise ControllerError("remote_script_hash_mismatch")
        return manifest

    def _create_trigger(self) -> tuple[str, int]:
        trigger = self.api.create_always_on_task(EXACT_EXECUTION_COMMAND)
        if trigger is None:
            trigger = self.api.create_scheduled_task(EXACT_EXECUTION_COMMAND)
        if trigger is None:
            raise ControllerError("no_remote_trigger_available")
        return trigger

    def _poll_receipt(self) -> dict:
        deadline = self.monotonic() + self.poll_timeout
        last_invalid = None
        stable_invalid_reads = 0
        while self.monotonic() < deadline:
            try:
                raw = self.api.read_file(REMOTE_OUTPUT_PATH)
            except FileNotFoundError:
                raw = ""
            if raw:
                if len(raw.encode("utf-8")) > MAX_RECEIPT_BYTES:
                    raise ControllerError("receipt_too_large")
                try:
                    return parse_strict_json(raw, "discovery_receipt")
                except ControllerError:
                    if raw == last_invalid:
                        stable_invalid_reads += 1
                    else:
                        last_invalid = raw
                        stable_invalid_reads = 1
                    if stable_invalid_reads >= 2:
                        raise ControllerError("stable_malformed_receipt")
            self.sleep(self.poll_interval)
        raise ControllerError("receipt_timeout")

    @staticmethod
    def _validate_source_entry(entry: object) -> str:
        if not isinstance(entry, dict):
            raise ControllerError("receipt_source_entry_invalid")
        if set(entry) - {"path", "sha256", "size", "line_count", "anchors"}:
            raise ControllerError("receipt_source_keys_invalid")
        path = entry.get("path")
        if path not in REMOTE_SOURCES:
            raise ControllerError("receipt_source_path_invalid")
        if not HEX64_RE.fullmatch(str(entry.get("sha256", ""))):
            raise ControllerError("receipt_source_hash_invalid")
        size = entry.get("size")
        line_count = entry.get("line_count")
        if not isinstance(size, int) or not 0 <= size <= 2_000_000:
            raise ControllerError("receipt_source_size_invalid")
        if not isinstance(line_count, int) or not 0 <= line_count <= 40_000:
            raise ControllerError("receipt_source_lines_invalid")
        anchors = entry.get("anchors")
        if not isinstance(anchors, list) or len(anchors) > 80:
            raise ControllerError("receipt_anchor_list_invalid")
        for anchor in anchors:
            if not isinstance(anchor, dict):
                raise ControllerError("receipt_anchor_invalid")
            if set(anchor) - {"line", "matches", "function", "snippet"}:
                raise ControllerError("receipt_anchor_keys_invalid")
            if not isinstance(anchor.get("line"), int):
                raise ControllerError("receipt_anchor_line_invalid")
            if not isinstance(anchor.get("matches"), list):
                raise ControllerError("receipt_anchor_matches_invalid")
            if len(str(anchor.get("snippet", ""))) > 1_200:
                raise ControllerError("receipt_anchor_snippet_too_large")
        return path

    @classmethod
    def validate_receipt(cls, receipt: dict) -> dict:
        allowed_top = {
            "task_id",
            "mode",
            "status",
            "production_write",
            "crm_write",
            "db_write",
            "ua0009_published",
            "sources",
            "db",
            "errors",
            "UA0006_CONTAINER_STATUS",
        }
        if set(receipt) - allowed_top:
            raise ControllerError("receipt_top_level_keys_invalid")
        if receipt.get("task_id") != "task_037":
            raise ControllerError("receipt_task_invalid")
        if receipt.get("mode") != "READ_ONLY_DISCOVERY":
            raise ControllerError("receipt_mode_invalid")
        status = receipt.get("status")
        if status not in {"PASS", "BLOCKED"}:
            raise ControllerError("receipt_status_invalid")
        for field in (
            "production_write",
            "crm_write",
            "db_write",
            "ua0009_published",
        ):
            if receipt.get(field) is not False:
                raise ControllerError("receipt_safety_field_invalid:" + field)

        sources = receipt.get("sources")
        if not isinstance(sources, list) or len(sources) > len(REMOTE_SOURCES):
            raise ControllerError("receipt_sources_invalid")
        source_paths = [cls._validate_source_entry(item) for item in sources]
        if len(source_paths) != len(set(source_paths)):
            raise ControllerError("receipt_source_duplicate")

        errors = receipt.get("errors")
        if not isinstance(errors, list) or len(errors) > 50:
            raise ControllerError("receipt_errors_invalid")
        if any(not isinstance(item, str) or len(item) > 240 for item in errors):
            raise ControllerError("receipt_error_entry_invalid")

        database = receipt.get("db")
        if not isinstance(database, dict):
            raise ControllerError("receipt_db_invalid")
        if len(json.dumps(database, ensure_ascii=False)) > 80_000:
            raise ControllerError("receipt_db_too_large")

        if status == "PASS":
            if set(source_paths) != set(REMOTE_SOURCES):
                raise ControllerError("receipt_sources_incomplete")
            if errors:
                raise ControllerError("pass_receipt_has_errors")
            if receipt.get("UA0006_CONTAINER_STATUS") not in {
                "ALREADY_CORRECT",
                "NEEDS_EXACT_UPDATE",
            }:
                raise ControllerError("receipt_container_status_invalid")
            if database.get("path") != REMOTE_DB_PATH:
                raise ControllerError("receipt_db_path_invalid")
            if database.get("quick_check_ok") is not True:
                raise ControllerError("receipt_quick_check_invalid")
            if database.get("identity_stable") is not True:
                raise ControllerError("receipt_db_identity_invalid")
            before = database.get("sha256_before")
            after = database.get("sha256_after")
            if (
                not isinstance(before, str)
                or not HEX64_RE.fullmatch(before)
                or before != after
            ):
                raise ControllerError("receipt_db_hash_invalid")
            if database.get("candidate_count") != 1:
                raise ControllerError("receipt_candidate_count_invalid")
            if database.get("ua0006_row_count") != 1:
                raise ControllerError("receipt_row_count_invalid")
            for field in (
                "matched_table",
                "matched_id_column",
                "matched_container_column",
            ):
                value = database.get(field)
                if not isinstance(value, str) or not value or len(value) > 120:
                    raise ControllerError("receipt_match_metadata_invalid")
        else:
            if not errors:
                raise ControllerError("blocked_receipt_without_error")
            if "UA0006_CONTAINER_STATUS" in receipt:
                raise ControllerError("blocked_receipt_has_container_status")

        if _contains_sensitive(receipt):
            raise ControllerError("receipt_sensitive_data_detected")
        return receipt

    @staticmethod
    def _atomic_text(path: pathlib.Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix="." + path.name + ".",
            suffix=".tmp",
            delete=False,
        )
        temp_path = pathlib.Path(handle.name)
        try:
            with handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _write_relay(self, receipt: dict) -> None:
        evidence = (
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        )
        self._atomic_text(EVIDENCE_PATH_LOCAL, evidence)
        report = (
            "# TASK 039 read-only discovery relay\n\n"
            f"status: {receipt['status']}\n"
            "production_write: false\n"
            "crm_write: false\n"
            "db_write: false\n"
            "ua0009_published: false\n"
            "container_status: %s\n"
            "errors: %s\n"
            % (
                receipt.get("UA0006_CONTAINER_STATUS", "NONE"),
                ",".join(receipt.get("errors", [])) or "NONE",
            )
        )
        self._atomic_text(REPORT_PATH_LOCAL, report)

    def run(self) -> dict:
        self.validate_environment()
        local_hashes = self.verify_local_artifacts()
        self.verify_manifest(local_hashes)
        trigger = None
        try:
            self.api.delete_output(REMOTE_OUTPUT_PATH)
            trigger = self._create_trigger()
            receipt = self.validate_receipt(self._poll_receipt())
            self._write_relay(receipt)
            return receipt
        finally:
            if trigger is not None:
                try:
                    self.api.delete_trigger(trigger)
                except Exception:
                    pass
            try:
                self.api.delete_output(REMOTE_OUTPUT_PATH)
            except Exception:
                pass


def main() -> int:
    env = os.environ
    username = env.get("PYTHONANYWHERE_USERNAME", ALLOWED_USERNAME)
    host = env.get("PYTHONANYWHERE_HOST", ALLOWED_HOSTS[0])
    token = env.get("PYTHONANYWHERE_API_TOKEN", "")
    try:
        api = PythonAnywhereAPI(
            username=username,
            host=host,
            token=token,
        )
        controller = DiscoveryController(api, env=env)
        receipt = controller.run()
        print(
            json.dumps(
                {
                    "controller_status": "PASS",
                    "remote_discovery_status": receipt["status"],
                    "production_write": False,
                    "crm_write": False,
                    "db_write": False,
                },
                sort_keys=True,
            )
        )
        return 0
    except ControllerError as exc:
        print("DISCOVERY_CONTROLLER_BLOCKED:" + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
