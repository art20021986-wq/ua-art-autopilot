#!/usr/bin/env python3
"""GitHub-side controller for TASK 058 live read-only discovery.

The controller verifies the filtered safe-inbox sync manifest and exact
remote bytes, creates one temporary PythonAnywhere trigger for one exact
command, validates and relays one bounded receipt, then deletes both the
trigger and receipt in ``finally``. It has no production write endpoint.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
ALLOWED_USERNAME = "Carix"
ALLOWED_HOSTS = ("www.pythonanywhere.com", "eu.pythonanywhere.com")
REMOTE_ROOT = "/home/Carix/autopilot_inbox"
REMOTE_PACKAGE = REMOTE_ROOT + "/cloud/task_058_crm_ocr_sync"
REMOTE_MANIFEST_PATH = REMOTE_ROOT + "/_sync_manifest.json"
REMOTE_SCRIPT = REMOTE_PACKAGE + "/live_discovery.py"
REMOTE_ALLOWLIST = REMOTE_PACKAGE + "/allowlist.json"
REMOTE_RECEIPT = REMOTE_PACKAGE + "/task_058_live_discovery_receipt.json"
EXACT_COMMAND = (
    "python3.10 "
    + REMOTE_SCRIPT
    + " --allowlist-file "
    + REMOTE_ALLOWLIST
    + " --output "
    + REMOTE_RECEIPT
)

LOCAL_ARTIFACTS = {
    "cloud/task_058_crm_ocr_sync/live_discovery.py": PACKAGE_DIR / "live_discovery.py",
    "cloud/task_058_crm_ocr_sync/allowlist.json": PACKAGE_DIR / "allowlist.json",
}
EVIDENCE_PATH = PACKAGE_DIR / "evidence" / "task_058_live_discovery.json"
REPORT_PATH = PACKAGE_DIR / "TASK_058_CONTROLLER_REPORT.md"

MAX_HTTP_BYTES = 3_000_000
MAX_RECEIPT_BYTES = 2_000_000
MAX_MANIFEST_AGE_SECONDS = 3_600
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 600
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(
    r"(?<!\w)(?:\+\d{1,3}[ ()-]*)?(?:\d[ ()-]*){8,14}\d(?!\w)"
)
SECRET_VALUE_RE = re.compile(
    r"(?:sk-ant-[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{20,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|\b\d{8,12}:[A-Za-z0-9_-]{20,}\b|"
    r"AIza[0-9A-Za-z_-]{30,}|xox[baprs]-[0-9A-Za-z-]{20,}|"
    r"AKIA[0-9A-Z]{16}|eyJ[A-Za-z0-9_-]{20,}(?:\.[A-Za-z0-9_-]{10,}){1,2}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
)
GENERIC_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|token|secret|password|authorization)\b"
    r"\s*[:=]\s*['\"][^'\"\r\n]{8,}['\"]"
)

REQUIRED_SOURCE_PATHS = {
    "/home/Carix/ai.py",
    "/home/Carix/team_bot.py",
    "/home/Carix/db.py",
    "/home/Carix/cars_ui.py",
    "/home/Carix/start_safe.py",
    "/home/Carix/stranica.py",
}
OPTIONAL_SOURCE_PATHS = {
    "/home/Carix/avtoperedacha.py",
    "/home/Carix/run_all.py",
    "/home/Carix/yadro.py",
    "/home/Carix/konteyner.py",
    "/home/Carix/ai_filter.py",
    "/home/Carix/lock4_zhurnal.py",
}
ALLOWED_SOURCE_PATHS = REQUIRED_SOURCE_PATHS | OPTIONAL_SOURCE_PATHS
REQUIRED_SITE_PATHS = {
    f"/home/Carix/{root}/{name}"
    for root in ("video", "site")
    for name in (
        "index.html",
        "katalog.html",
        *(f"UA-{number:04d}.html" for number in range(1, 9)),
    )
}
OPTIONAL_SITE_PATHS = {
    f"/home/Carix/{root}/UA-{number:04d}.html"
    for root in ("video", "site")
    for number in (9, 10)
}
ALLOWED_SITE_PATHS = REQUIRED_SITE_PATHS | OPTIONAL_SITE_PATHS


def expected_allowlist() -> dict:
    """The remote audit scope is code, not user-controlled configuration."""
    return {
        "task_id": "task_058",
        "required_source_paths": [
            "/home/Carix/ai.py",
            "/home/Carix/team_bot.py",
            "/home/Carix/db.py",
            "/home/Carix/cars_ui.py",
            "/home/Carix/start_safe.py",
            "/home/Carix/stranica.py",
        ],
        "optional_source_paths": [
            "/home/Carix/avtoperedacha.py",
            "/home/Carix/run_all.py",
            "/home/Carix/yadro.py",
            "/home/Carix/konteyner.py",
            "/home/Carix/ai_filter.py",
            "/home/Carix/lock4_zhurnal.py",
        ],
        "db_path": "/home/Carix/crm.db",
        "required_site_paths": [
            f"/home/Carix/{root}/{name}"
            for root in ("video", "site")
            for name in (
                "index.html",
                "katalog.html",
                *(f"UA-{number:04d}.html" for number in range(1, 9)),
            )
        ],
        "optional_site_paths": [
            "/home/Carix/video/UA-0009.html",
            "/home/Carix/video/UA-0010.html",
            "/home/Carix/site/UA-0009.html",
            "/home/Carix/site/UA-0010.html",
        ],
        "log_paths": [],
    }


class ControllerError(RuntimeError):
    """Sanitized, fail-closed controller error."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    return sha256_bytes(path.read_bytes())


def _strict_object(text: str, label: str) -> dict:
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ControllerError("DUPLICATE_JSON_KEY:" + label)
            result[key] = value
        return result

    try:
        value = json.loads(text, object_pairs_hook=no_duplicates)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise ControllerError("INVALID_JSON:" + label) from exc
    if not isinstance(value, dict):
        raise ControllerError("JSON_NOT_OBJECT:" + label)
    return value


def _parse_utc(value: object, label: str) -> dt.datetime:
    if not isinstance(value, str):
        raise ControllerError("TIME_MISSING:" + label)
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ControllerError("TIME_INVALID:" + label) from exc
    if parsed.tzinfo is None:
        raise ControllerError("TIME_NAIVE:" + label)
    return parsed.astimezone(dt.timezone.utc)


def _sensitive_value(value: object) -> bool:
    """Inspect JSON string values only.

    Numeric metadata such as ``mtime_ns`` is intentionally ignored; treating
    every long JSON number as a phone number would make every valid receipt a
    false positive. Keys are fixed by the receipt schema and are not evidence.
    """
    if isinstance(value, str):
        return bool(
            SECRET_VALUE_RE.search(value)
            or GENERIC_SECRET_ASSIGNMENT_RE.search(value)
            or EMAIL_RE.search(value)
            or PHONE_RE.search(value)
            or VIN_RE.search(value)
        )
    if isinstance(value, list):
        return any(_sensitive_value(item) for item in value)
    if isinstance(value, dict):
        return any(_sensitive_value(item) for item in value.values())
    return False


class PythonAnywhereAPI:
    """Minimal API transport with exact endpoint and path allowlists."""

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
            raise ControllerError("USERNAME_INVALID")
        if host not in ALLOWED_HOSTS:
            raise ControllerError("HOST_INVALID")
        if not token:
            raise ControllerError("API_TOKEN_MISSING")
        self.username = username
        self.host = host
        self._token = token
        self._opener = opener
        self.timeout = timeout

    @property
    def base_url(self) -> str:
        return (
            "https://"
            + self.host
            + "/api/v0/user/"
            + urllib.parse.quote(self.username, safe="")
            + "/"
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        form: dict | None = None,
        allowed_statuses: tuple[int, ...] = (200,),
        operation: str,
    ) -> tuple[int, bytes]:
        data = None
        headers = {
            "Authorization": "Token " + self._token,
            "User-Agent": "ua-art-task058-readonly/1",
        }
        if form is not None:
            data = urllib.parse.urlencode(form).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._opener(request, timeout=self.timeout) as response:
                status = getattr(response, "status", response.getcode())
                body = response.read(MAX_HTTP_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read(MAX_HTTP_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ControllerError("NETWORK_ERROR:" + operation) from exc
        if len(body) > MAX_HTTP_BYTES:
            raise ControllerError("RESPONSE_OVERSIZE:" + operation)
        if status not in allowed_statuses:
            raise ControllerError("HTTP_STATUS_%s:%s" % (operation, status))
        return status, body

    def _file_url(self, path: str) -> str:
        if path not in {
            REMOTE_MANIFEST_PATH,
            REMOTE_SCRIPT,
            REMOTE_ALLOWLIST,
            REMOTE_RECEIPT,
        }:
            raise ControllerError("REMOTE_FILE_PATH_NOT_ALLOWED")
        return self.base_url + "files/path" + urllib.parse.quote(path, safe="/")

    def read_file(self, path: str) -> str:
        status, body = self._request(
            "GET",
            self._file_url(path),
            allowed_statuses=(200, 404),
            operation="READ_FILE",
        )
        if status == 404:
            raise FileNotFoundError(path)
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ControllerError("REMOTE_FILE_NOT_UTF8") from exc

    def delete_receipt(self) -> None:
        self._request(
            "DELETE",
            self._file_url(REMOTE_RECEIPT),
            allowed_statuses=(204, 404),
            operation="DELETE_RECEIPT",
        )

    @staticmethod
    def _task_id(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        task_id = value.get("id") if isinstance(value, dict) else None
        return task_id if isinstance(task_id, int) and task_id > 0 else None

    def create_trigger(self) -> tuple[str, int]:
        status, body = self._request(
            "POST",
            self.base_url + "always_on/",
            form={
                "command": EXACT_COMMAND,
                "description": "UA ART TASK 058 read-only discovery",
                "enabled": "true",
            },
            allowed_statuses=(200, 201, 202, 400, 403, 404, 409),
            operation="CREATE_ALWAYS_ON",
        )
        if status in (200, 201, 202):
            task_id = self._task_id(body)
            if task_id:
                return "always_on", task_id

        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        status, body = self._request(
            "POST",
            self.base_url + "schedule/",
            form={
                "command": EXACT_COMMAND,
                "description": "UA ART TASK 058 read-only discovery fallback",
                "enabled": "true",
                "interval": "daily",
                "hour": run_at.hour,
                "minute": run_at.minute,
            },
            allowed_statuses=(200, 201, 202, 400, 403, 404, 409),
            operation="CREATE_SCHEDULE",
        )
        if status in (200, 201, 202):
            task_id = self._task_id(body)
            if task_id:
                return "schedule", task_id
        raise ControllerError("NO_TEMPORARY_TRIGGER_AVAILABLE")

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        kind, task_id = trigger
        if kind not in {"always_on", "schedule"} or not isinstance(task_id, int):
            raise ControllerError("TRIGGER_ID_INVALID")
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self._request(
            "DELETE",
            self.base_url + endpoint + "/" + str(task_id) + "/",
            allowed_statuses=(200, 202, 204, 404),
            operation="DELETE_TRIGGER",
        )


class ReadOnlyController:
    def __init__(
        self,
        api: PythonAnywhereAPI,
        *,
        sleep=time.sleep,
        monotonic=time.monotonic,
        utc_now=lambda: dt.datetime.now(dt.timezone.utc),
        poll_interval: int = POLL_INTERVAL_SECONDS,
        poll_timeout: int = POLL_TIMEOUT_SECONDS,
    ):
        self.api = api
        self.sleep = sleep
        self.monotonic = monotonic
        self.utc_now = utc_now
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout

    def verify_local_artifacts(self) -> dict[str, str]:
        hashes = {}
        for rel, path in LOCAL_ARTIFACTS.items():
            if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
                raise ControllerError("LOCAL_ARTIFACT_INVALID:" + rel)
            if path.suffix == ".py":
                try:
                    compile(path.read_text(encoding="utf-8"), rel, "exec")
                except (UnicodeDecodeError, SyntaxError) as exc:
                    raise ControllerError("LOCAL_PYTHON_INVALID:" + rel) from exc
            hashes[rel] = sha256_file(path)
        allowlist = _strict_object(
            LOCAL_ARTIFACTS["cloud/task_058_crm_ocr_sync/allowlist.json"].read_text(
                encoding="utf-8"
            ),
            "LOCAL_ALLOWLIST",
        )
        if allowlist != expected_allowlist():
            raise ControllerError("LOCAL_ALLOWLIST_SCOPE_INVALID")
        return hashes

    def verify_sync_manifest(self, local_hashes: dict[str, str]) -> None:
        manifest = _strict_object(
            self.api.read_file(REMOTE_MANIFEST_PATH), "SYNC_MANIFEST"
        )
        if manifest.get("status") != "PASS" or manifest.get("remote_root") != REMOTE_ROOT:
            raise ControllerError("SYNC_MANIFEST_STATUS_INVALID")
        for key in (
            "production_touched",
            "crm_touched",
            "executed_remote_code",
            "webapp_reloaded",
        ):
            if manifest.get(key) is not False:
                raise ControllerError("SYNC_MANIFEST_SAFETY_INVALID:" + key)
        generated = _parse_utc(manifest.get("generated_at_utc"), "SYNC_MANIFEST")
        age = (self.utc_now() - generated).total_seconds()
        if age < -300 or age > MAX_MANIFEST_AGE_SECONDS:
            raise ControllerError("SYNC_MANIFEST_STALE")
        entries = manifest.get("files")
        if not isinstance(entries, list) or not 1 <= len(entries) <= 30:
            raise ControllerError("SYNC_MANIFEST_FILES_INVALID")
        by_source = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise ControllerError("SYNC_MANIFEST_ENTRY_INVALID")
            source = entry.get("source")
            if not isinstance(source, str) or source in by_source:
                raise ControllerError("SYNC_MANIFEST_SOURCE_INVALID")
            by_source[source] = entry
        for rel, expected_hash in local_hashes.items():
            entry = by_source.get(rel)
            if entry is None:
                raise ControllerError("SYNC_MANIFEST_REQUIRED_FILE_MISSING:" + rel)
            if entry.get("remote") != REMOTE_ROOT + "/" + rel:
                raise ControllerError("SYNC_MANIFEST_REMOTE_PATH_MISMATCH:" + rel)
            if entry.get("sha256") != expected_hash or entry.get("http_status") not in (200, 201):
                raise ControllerError("SYNC_MANIFEST_HASH_OR_STATUS_MISMATCH:" + rel)
        for rel, remote_path in (
            ("cloud/task_058_crm_ocr_sync/live_discovery.py", REMOTE_SCRIPT),
            ("cloud/task_058_crm_ocr_sync/allowlist.json", REMOTE_ALLOWLIST),
        ):
            remote_bytes = self.api.read_file(remote_path).encode("utf-8")
            if sha256_bytes(remote_bytes) != local_hashes[rel]:
                raise ControllerError("REMOTE_ARTIFACT_HASH_MISMATCH:" + rel)

    def poll_receipt(self) -> dict:
        deadline = self.monotonic() + self.poll_timeout
        last_malformed = None
        stable_malformed = 0
        while self.monotonic() < deadline:
            try:
                raw = self.api.read_file(REMOTE_RECEIPT)
            except FileNotFoundError:
                raw = ""
            if raw:
                if len(raw.encode("utf-8")) > MAX_RECEIPT_BYTES:
                    raise ControllerError("RECEIPT_OVERSIZE")
                try:
                    return self.validate_receipt(raw)
                except ControllerError:
                    if raw == last_malformed:
                        stable_malformed += 1
                    else:
                        last_malformed = raw
                        stable_malformed = 1
                    if stable_malformed >= 2:
                        raise
            self.sleep(self.poll_interval)
        raise ControllerError("RECEIPT_TIMEOUT")

    @staticmethod
    def _validate_hash_snapshot(snapshot: object) -> dict:
        if not isinstance(snapshot, dict) or len(snapshot) > 40:
            raise ControllerError("SITE_SNAPSHOT_INVALID")
        for path, value in snapshot.items():
            if path not in ALLOWED_SITE_PATHS:
                raise ControllerError("SITE_PATH_INVALID")
            if value is None:
                continue
            if not isinstance(value, dict) or set(value) != {"sha256", "size", "mtime_ns"}:
                raise ControllerError("SITE_ENTRY_INVALID")
            if not HEX64_RE.fullmatch(str(value.get("sha256", ""))):
                raise ControllerError("SITE_HASH_INVALID")
            if not isinstance(value.get("size"), int) or value["size"] < 0:
                raise ControllerError("SITE_SIZE_INVALID")
            if not isinstance(value.get("mtime_ns"), int) or value["mtime_ns"] < 0:
                raise ControllerError("SITE_MTIME_INVALID")
        return snapshot

    @classmethod
    def validate_receipt(cls, raw: str) -> dict:
        receipt = _strict_object(raw, "DISCOVERY_RECEIPT")
        if _sensitive_value(receipt):
            raise ControllerError("RECEIPT_SENSITIVE_CONTENT")
        allowed_top = {
            "task_id",
            "mode",
            "status",
            "generated_at_utc",
            "started_at_utc",
            "production_write",
            "crm_write",
            "db_write",
            "site_rebuilt",
            "service_reloaded",
            "ocr_fix_installed",
            "gate_b_executed",
            "ua0009_published",
            "ua0010_published",
            "sources",
            "source_hashes_after",
            "source_identity_stable",
            "database",
            "site_before",
            "site_after",
            "site_identity_stable",
            "logs",
            "completeness",
            "ua0009_status",
            "ua0009_evidence",
            "ua0010_status",
            "ua0010_evidence",
            "errors",
        }
        if set(receipt) - allowed_top:
            raise ControllerError("RECEIPT_TOP_LEVEL_KEYS_INVALID")
        if receipt.get("task_id") != "task_058" or receipt.get("mode") != "READ_ONLY_LIVE_DISCOVERY":
            raise ControllerError("RECEIPT_ID_OR_MODE_INVALID")
        if receipt.get("status") not in {"PASS", "BLOCKED"}:
            raise ControllerError("RECEIPT_STATUS_INVALID")
        for key in (
            "production_write",
            "crm_write",
            "db_write",
            "site_rebuilt",
            "service_reloaded",
            "ocr_fix_installed",
            "gate_b_executed",
            "ua0009_published",
            "ua0010_published",
        ):
            if receipt.get(key) is not False:
                raise ControllerError("RECEIPT_SAFETY_INVALID:" + key)
        generated = _parse_utc(receipt.get("generated_at_utc"), "RECEIPT")
        now = dt.datetime.now(dt.timezone.utc)
        age = (now - generated).total_seconds()
        if age < -300 or age > 900:
            raise ControllerError("RECEIPT_STALE")
        errors = receipt.get("errors")
        if not isinstance(errors, list) or len(errors) > 80:
            raise ControllerError("RECEIPT_ERRORS_INVALID")
        if receipt.get("status") == "BLOCKED":
            if not errors:
                raise ControllerError("BLOCKED_RECEIPT_WITHOUT_REASON")
            return receipt

        sources = receipt.get("sources")
        if not isinstance(sources, list) or not 4 <= len(sources) <= len(ALLOWED_SOURCE_PATHS):
            raise ControllerError("RECEIPT_SOURCES_INVALID")
        seen = set()
        for entry in sources:
            if not isinstance(entry, dict):
                raise ControllerError("SOURCE_ENTRY_INVALID")
            path = entry.get("path")
            if path not in ALLOWED_SOURCE_PATHS or path in seen:
                raise ControllerError("SOURCE_PATH_INVALID")
            seen.add(path)
            if not HEX64_RE.fullmatch(str(entry.get("sha256", ""))):
                raise ControllerError("SOURCE_HASH_INVALID")
            anchors = entry.get("anchors")
            messages = entry.get("message_locations")
            if not isinstance(anchors, list) or len(anchors) > 160:
                raise ControllerError("SOURCE_ANCHORS_INVALID")
            if not isinstance(messages, list) or len(messages) > 20:
                raise ControllerError("SOURCE_MESSAGES_INVALID")
            imports = entry.get("imports")
            excerpts = entry.get("function_excerpts")
            if not isinstance(imports, list) or len(imports) > 120:
                raise ControllerError("SOURCE_IMPORTS_INVALID")
            for imported in imports:
                if not isinstance(imported, dict) or set(imported) != {
                    "module", "name", "as"
                }:
                    raise ControllerError("SOURCE_IMPORT_ENTRY_INVALID")
                for value in imported.values():
                    if value is not None and (
                        not isinstance(value, str) or len(value) > 200
                    ):
                        raise ControllerError("SOURCE_IMPORT_VALUE_INVALID")
            if not isinstance(excerpts, list) or len(excerpts) > 15:
                raise ControllerError("SOURCE_EXCERPTS_INVALID")
            excerpt_names = set()
            for excerpt in excerpts:
                if not isinstance(excerpt, dict) or set(excerpt) != {
                    "name", "line", "end_line", "calls", "source"
                }:
                    raise ControllerError("SOURCE_EXCERPT_ENTRY_INVALID")
                name = excerpt.get("name")
                # Nested helpers can legitimately reuse a short function name in
                # separate production functions.  Names are used only as a
                # completeness set; duplicate excerpts remain bounded by the
                # list-size and source-size limits above.
                if not isinstance(name, str) or not name:
                    raise ControllerError("SOURCE_EXCERPT_NAME_INVALID")
                excerpt_names.add(name)
                if not isinstance(excerpt.get("line"), int) or not isinstance(
                    excerpt.get("end_line"), int
                ):
                    raise ControllerError("SOURCE_EXCERPT_LINES_INVALID")
                calls = excerpt.get("calls")
                source = excerpt.get("source")
                if not isinstance(calls, list) or len(calls) > 200:
                    raise ControllerError("SOURCE_EXCERPT_CALLS_INVALID")
                if not isinstance(source, str) or len(source) > 30_000:
                    raise ControllerError("SOURCE_EXCERPT_SOURCE_INVALID")
            if path == "/home/Carix/team_bot.py" and not {
                "detect_kind", "intake", "run_ai_draft", "ai_save"
            }.issubset(excerpt_names):
                raise ControllerError("TEAM_BOT_TARGET_EXCERPTS_INCOMPLETE")
        if not REQUIRED_SOURCE_PATHS.issubset(seen):
            raise ControllerError("REQUIRED_SOURCE_PATH_MISSING")
        hashes_after = receipt.get("source_hashes_after")
        if not isinstance(hashes_after, dict) or set(hashes_after) != seen:
            raise ControllerError("SOURCE_HASH_SNAPSHOT_INVALID")
        for entry in sources:
            if hashes_after.get(entry["path"]) != entry["sha256"]:
                raise ControllerError("SOURCE_IDENTITY_MISMATCH")

        database = receipt.get("database")
        if not isinstance(database, dict) or database.get("path") != "/home/Carix/crm.db":
            raise ControllerError("DATABASE_EVIDENCE_INVALID")
        if database.get("open_uri_mode") != "ro" or database.get("query_only_value") != 1:
            raise ControllerError("DATABASE_NOT_READONLY")
        if database.get("quick_check") != "ok":
            raise ControllerError("DATABASE_QUICK_CHECK_FAILED")
        for field in ("sha256_before", "sha256_after"):
            if not HEX64_RE.fullmatch(str(database.get(field, ""))):
                raise ControllerError("DATABASE_HASH_INVALID")
        if database["sha256_before"] != database["sha256_after"]:
            raise ControllerError("DATABASE_IDENTITY_MISMATCH")
        if database.get("sidecars_before") != database.get("sidecars_after"):
            raise ControllerError("DATABASE_SIDECAR_IDENTITY_MISMATCH")

        site_before = cls._validate_hash_snapshot(receipt.get("site_before"))
        site_after = cls._validate_hash_snapshot(receipt.get("site_after"))
        if set(site_before) != ALLOWED_SITE_PATHS or set(site_after) != ALLOWED_SITE_PATHS:
            raise ControllerError("SITE_SCOPE_INCOMPLETE")
        if any(site_before.get(path) is None for path in REQUIRED_SITE_PATHS):
            raise ControllerError("REQUIRED_SITE_PATH_MISSING")
        if site_before != site_after:
            raise ControllerError("SITE_IDENTITY_MISMATCH")
        completeness = receipt.get("completeness")
        if not isinstance(completeness, dict):
            raise ControllerError("COMPLETENESS_INVALID")
        for key in (
            "required_sources_found",
            "target_functions_found",
            "required_site_found",
            "database_readonly_verified",
        ):
            if completeness.get(key) is not True:
                raise ControllerError("COMPLETENESS_REQUIRED_FALSE:" + key)
        if receipt.get("source_identity_stable") is not True:
            raise ControllerError("SOURCE_IDENTITY_CHANGED")
        if receipt.get("site_identity_stable") is not True:
            raise ControllerError("SITE_IDENTITY_CHANGED")
        if database.get("identity_stable") is not True:
            raise ControllerError("DATABASE_IDENTITY_CHANGED")
        if errors:
            raise ControllerError("PASS_RECEIPT_HAS_ERRORS")
        return receipt

    @staticmethod
    def _atomic_write(path: pathlib.Path, content: str) -> None:
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
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def write_relay(self, receipt: dict) -> None:
        evidence_text = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        self._atomic_write(EVIDENCE_PATH, evidence_text)
        completeness = receipt.get("completeness") or {}
        logs = receipt.get("logs") or {}
        counts = logs.get("counts") or {}
        report = (
            "# TASK 058 live read-only controller report\n\n"
            f"DISCOVERY_STATUS: {receipt.get('status')}\n"
            f"ROOT_CAUSE_CONFIRMED: {str(bool(completeness.get('root_cause_confirmed'))).upper()}\n"
            f"REQUIRED_SOURCES_FOUND: {completeness.get('required_sources_found')}\n"
            f"TARGET_FUNCTIONS_FOUND: {completeness.get('target_functions_found')}\n"
            f"REQUIRED_SITE_FOUND: {completeness.get('required_site_found')}\n"
            f"DATABASE_READONLY_VERIFIED: {completeness.get('database_readonly_verified')}\n"
            f"LOGS_SCANNED: {completeness.get('logs_scanned')}\n"
            f"DATABASE_LOCKED_COUNT: {counts.get('database_is_locked', 0)}\n"
            f"RESOURCE_UNAVAILABLE_COUNT: {counts.get('resource_temporarily_unavailable', 0)}\n"
            f"OCR_FAILURE_COUNT: {counts.get('ocr_failure', 0)}\n"
            f"REBUILD_FAILURE_COUNT: {counts.get('rebuild_failure', 0)}\n"
            f"UA0009_STATUS: {receipt.get('ua0009_status', 'UNKNOWN')}\n"
            f"UA0010_STATUS: {receipt.get('ua0010_status', 'UNKNOWN')}\n"
            f"ERRORS: {','.join(receipt.get('errors') or []) or 'NONE'}\n\n"
            "PRODUCTION_TOUCHED: NO\n"
            "CRM_TOUCHED: NO\n"
            "CRM_DB_WRITTEN: NO\n"
            "SITE_REBUILT: NO\n"
            "SERVICE_RELOADED: NO\n"
            "OCR_FIX_INSTALLED: NO\n"
            "GATE_B_EXECUTED: NO\n"
            "UA_0009_PUBLISHED: NO\n"
            "UA_0010_PUBLISHED: NO\n"
        )
        self._atomic_write(REPORT_PATH, report)

    def run(self) -> dict:
        local_hashes = self.verify_local_artifacts()
        self.verify_sync_manifest(local_hashes)
        trigger = None
        cleanup_errors = []
        receipt = None
        try:
            self.api.delete_receipt()
            trigger = self.api.create_trigger()
            receipt = self.poll_receipt()
            self.write_relay(receipt)
        finally:
            if trigger is not None:
                try:
                    self.api.delete_trigger(trigger)
                except Exception:
                    cleanup_errors.append("TRIGGER_CLEANUP_FAILED")
            try:
                self.api.delete_receipt()
            except Exception:
                cleanup_errors.append("RECEIPT_CLEANUP_FAILED")
        if cleanup_errors:
            raise ControllerError("+".join(cleanup_errors))
        if receipt is None:
            raise ControllerError("RECEIPT_MISSING_AFTER_RUN")
        return receipt


def main() -> int:
    try:
        api = PythonAnywhereAPI(
            username=os.environ.get("PYTHONANYWHERE_USERNAME", ALLOWED_USERNAME),
            host=os.environ.get("PYTHONANYWHERE_HOST", ALLOWED_HOSTS[0]),
            token=os.environ.get("PYTHONANYWHERE_API_TOKEN", ""),
        )
        receipt = ReadOnlyController(api).run()
        print(
            json.dumps(
                {
                    "controller_status": "PASS",
                    "discovery_status": receipt.get("status"),
                    "production_write": False,
                    "crm_write": False,
                    "db_write": False,
                },
                sort_keys=True,
            )
        )
        return 0
    except ControllerError as exc:
        print("TASK058_CONTROLLER_BLOCKED:" + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
