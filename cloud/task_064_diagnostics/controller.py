#!/usr/bin/env python3
"""GitHub-side controller for TASK 064 diagnostics repair."""
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
ALLOWED_HOSTS = ("www.pythonanywhere.com", "eu.pythonanywhere.com")
REMOTE_ROOT = "/home/Carix/autopilot_inbox/cloud/task_047_ferry_discovery"
REMOTE_SCRIPT = REMOTE_ROOT + "/task064_diag_remote.py"
REMOTE_OUTPUT = REMOTE_ROOT + "/task064_diag_receipt.json"
REMOTE_TEMP = REMOTE_OUTPUT + ".tmp"
EXACT_COMMAND = (
    "cd " + REMOTE_ROOT
    + " && (python3.10 task064_diag_remote.py > task064_diag_receipt.json.tmp; "
      "mv task064_diag_receipt.json.tmp task064_diag_receipt.json)"
)
HERE = pathlib.Path(__file__).resolve().parent
LOCAL_SCRIPT = HERE / "repair_remote.py"
EVIDENCE = HERE / "evidence" / "repair.json"
REPORT = HERE / "TASK_064_REPORT.md"
MAX_RESPONSE = 2_000_000
MAX_RECEIPT = 750_000
POLL_TIMEOUT = 900
HEX64 = re.compile(r"^[0-9a-f]{64}$")
CARD_ID = re.compile(r"^UA-[0-9]{4,}$")


class ControllerBlocked(RuntimeError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def multipart(filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = "----task064-" + uuid.uuid4().hex
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body = bytearray()
    body.extend(("--%s\r\n" % boundary).encode())
    body.extend((
        'Content-Disposition: form-data; name="content"; filename="%s"\r\n'
        "Content-Type: %s\r\n\r\n" % (filename, mime)
    ).encode())
    body.extend(data)
    body.extend(("\r\n--%s--\r\n" % boundary).encode())
    return bytes(body), "multipart/form-data; boundary=" + boundary


class API:
    def __init__(self) -> None:
        self.host = os.environ.get("PYTHONANYWHERE_HOST", "")
        self.username = os.environ.get("PYTHONANYWHERE_USERNAME", "")
        self.token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
        if self.host not in ALLOWED_HOSTS or self.username != USERNAME or not self.token:
            raise ControllerBlocked("pythonanywhere_configuration_invalid")

    @property
    def base(self) -> str:
        return "https://%s/api/v0/user/%s/" % (
            self.host, urllib.parse.quote(self.username)
        )

    def request(self, method: str, url: str, *, data=None, headers=None,
                allowed=(200,), label="request") -> tuple[int, bytes]:
        merged = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task064-diagnostics/1",
        }
        merged.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=merged, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
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
            raise ControllerBlocked("unexpected_http_status:%s:%d" % (label, status))
        return status, body

    def file_url(self, path: str) -> str:
        if path not in {REMOTE_SCRIPT, REMOTE_OUTPUT, REMOTE_TEMP}:
            raise ControllerBlocked("remote_path_not_allowed")
        return self.base + "files/path" + urllib.parse.quote(path, safe="/")

    def upload(self, data: bytes) -> None:
        body, content_type = multipart("task064_diag_remote.py", data)
        self.request(
            "POST", self.file_url(REMOTE_SCRIPT), data=body,
            headers={"Content-Type": content_type}, allowed=(200, 201), label="upload",
        )

    def read(self, path: str) -> bytes:
        status, body = self.request(
            "GET", self.file_url(path), allowed=(200, 404), label="read"
        )
        if status == 404:
            raise FileNotFoundError(path)
        return body

    def delete(self, path: str) -> None:
        self.request(
            "DELETE", self.file_url(path), allowed=(204, 404), label="delete"
        )

    @staticmethod
    def trigger_id(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) and identifier > 0 else None

    def create_trigger(self) -> tuple[str, int]:
        form = urllib.parse.urlencode({
            "command": EXACT_COMMAND,
            "description": "UA ART permanent diagnostics TASK 064",
            "enabled": "true",
        }).encode()
        status, body = self.request(
            "POST", self.base + "always_on/", data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409), label="always_on",
        )
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
        if identifier:
            return "always_on", identifier

        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({
            "command": EXACT_COMMAND,
            "description": "UA ART diagnostics TASK 064 fallback",
            "enabled": "true",
            "interval": "daily",
            "hour": run_at.hour,
            "minute": run_at.minute,
        }).encode()
        status, body = self.request(
            "POST", self.base + "schedule/", data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409), label="schedule",
        )
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerBlocked("no_remote_trigger_available")
        return "schedule", identifier

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        kind, identifier = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request(
            "DELETE", self.base + "%s/%d/" % (endpoint, identifier),
            allowed=(200, 202, 204, 404), label="delete_trigger",
        )


def strict_json(data: bytes) -> dict:
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ControllerBlocked("duplicate_receipt_key")
            result[key] = value
        return result

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ControllerBlocked("invalid_receipt_json") from exc
    if not isinstance(value, dict):
        raise ControllerBlocked("receipt_not_object")
    return value


def validate(receipt: dict) -> dict:
    required = {
        "mode", "status", "generated_at_utc", "production_write",
        "production_files_changed", "crm_write", "db_write", "service_reload",
        "rollback_attempted", "rollback_completed", "backup_root",
        "crm_sha256_before", "crm_sha256_after", "generator_sha256_before",
        "generator_sha256_after", "yadro_sha256", "card_ids", "cards",
        "changed_paths", "errors",
    }
    if set(receipt) != required:
        raise ControllerBlocked("receipt_keys_invalid")
    if receipt["mode"] != "TASK_064_DIAGNOSTICS_PERMANENT_ATOMIC_REPAIR":
        raise ControllerBlocked("receipt_mode_invalid")
    if receipt["status"] != "PASS" or receipt["errors"] != []:
        raise ControllerBlocked("repair_not_passed:" + str(receipt.get("errors")))
    for field in ("crm_write", "db_write", "service_reload", "rollback_attempted", "rollback_completed"):
        if receipt[field] is not False:
            raise ControllerBlocked("safety_field_invalid:" + field)
    if not isinstance(receipt["production_write"], bool):
        raise ControllerBlocked("production_write_type_invalid")
    count = receipt["production_files_changed"]
    if not isinstance(count, int) or count < 0 or count != len(receipt["changed_paths"]):
        raise ControllerBlocked("changed_count_invalid")
    if receipt["production_write"] != (count > 0):
        raise ControllerBlocked("production_write_count_mismatch")
    for field in (
        "crm_sha256_before", "crm_sha256_after", "generator_sha256_before",
        "generator_sha256_after", "yadro_sha256",
    ):
        if not isinstance(receipt[field], str) or not HEX64.fullmatch(receipt[field]):
            raise ControllerBlocked("receipt_hash_invalid:" + field)
    if receipt["crm_sha256_before"] != receipt["crm_sha256_after"]:
        raise ControllerBlocked("crm_hash_changed")
    if not isinstance(receipt["backup_root"], str) or not receipt["backup_root"].startswith(
        "/home/Carix/autopilot_inbox/cloud/task_064_diagnostics/backups/"
    ):
        raise ControllerBlocked("backup_root_invalid")
    identifiers = receipt["card_ids"]
    if (not isinstance(identifiers, list) or not identifiers
            or len(identifiers) > 100 or len(set(identifiers)) != len(identifiers)):
        raise ControllerBlocked("card_ids_invalid")
    if any(not isinstance(value, str) or not CARD_ID.fullmatch(value) for value in identifiers):
        raise ControllerBlocked("card_id_invalid")
    cards = receipt["cards"]
    if not isinstance(cards, list) or len(cards) != len(identifiers):
        raise ControllerBlocked("card_results_invalid")
    seen = set()
    for item in cards:
        if not isinstance(item, dict) or set(item) != {"id", "roots", "empty_state"}:
            raise ControllerBlocked("card_result_shape_invalid")
        if item["id"] not in identifiers or item["id"] in seen:
            raise ControllerBlocked("card_result_id_invalid")
        seen.add(item["id"])
        roots = item["roots"]
        if not isinstance(roots, dict) or set(roots) != {"video", "site"}:
            raise ControllerBlocked("card_roots_invalid")
        for result in roots.values():
            if not isinstance(result, dict) or set(result) != {
                "card_sha256", "diag_sha256", "diag_links",
            }:
                raise ControllerBlocked("root_result_invalid")
            if result["diag_links"] != 1:
                raise ControllerBlocked("diagnostics_link_count_invalid")
            for key in ("card_sha256", "diag_sha256"):
                if not isinstance(result[key], str) or not HEX64.fullmatch(result[key]):
                    raise ControllerBlocked("card_hash_invalid")
    if seen != set(identifiers):
        raise ControllerBlocked("card_result_set_invalid")
    if not isinstance(receipt["changed_paths"], list) or any(
        not isinstance(path, str) or path.startswith("/") or ".." in pathlib.PurePosixPath(path).parts
        for path in receipt["changed_paths"]
    ):
        raise ControllerBlocked("changed_paths_invalid")
    return receipt


def atomic_text(path: pathlib.Path, text: str) -> None:
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


def write_evidence(receipt: dict) -> None:
    atomic_text(EVIDENCE, json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    rows = "\n".join(
        "- `%s`: video PASS, site PASS, diagnostics links 1/1, empty state: %s"
        % (item["id"], "YES" if item["empty_state"] else "NO")
        for item in receipt["cards"]
    )
    report = """# TASK 064 — permanent diagnostics repair

status: PASS
generated_at_utc: %(time)s
published_cards: %(count)d
production_files_changed: %(changed)d
crm_write: false
db_write: false
service_reload: false
rollback_attempted: false
backup_root: `%(backup)s`
generator_sha256: `%(before)s` → `%(after)s`

## Card matrix

%(rows)s

The canonical generator now treats diagnostics as mandatory even with no
materials. Card writes and etalon writes can no longer overwrite `*-diag.html`.
Every current card has exactly one diagnostics link in both `/video` and `/site`.
""" % {
        "time": receipt["generated_at_utc"],
        "count": len(receipt["card_ids"]),
        "changed": receipt["production_files_changed"],
        "backup": receipt["backup_root"],
        "before": receipt["generator_sha256_before"],
        "after": receipt["generator_sha256_after"],
        "rows": rows,
    }
    atomic_text(REPORT, report)


def run() -> dict:
    script = LOCAL_SCRIPT.read_bytes()
    compile(script.decode("utf-8"), str(LOCAL_SCRIPT), "exec")
    api = API()
    api.upload(script)
    if sha256(api.read(REMOTE_SCRIPT)) != sha256(script):
        raise ControllerBlocked("uploaded_script_hash_mismatch")
    for path in (REMOTE_OUTPUT, REMOTE_TEMP):
        api.delete(path)
    trigger = None
    try:
        trigger = api.create_trigger()
        deadline = time.monotonic() + POLL_TIMEOUT
        while time.monotonic() < deadline:
            try:
                data = api.read(REMOTE_OUTPUT)
            except FileNotFoundError:
                data = b""
            if data:
                if len(data) > MAX_RECEIPT:
                    raise ControllerBlocked("receipt_too_large")
                receipt = validate(strict_json(data))
                write_evidence(receipt)
                return receipt
            time.sleep(5)
        raise ControllerBlocked("receipt_timeout")
    finally:
        if trigger is not None:
            api.delete_trigger(trigger)


def main() -> int:
    receipt = run()
    print("TASK064_REMOTE_PASS cards=%d changed=%d" % (
        len(receipt["card_ids"]), receipt["production_files_changed"]
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
