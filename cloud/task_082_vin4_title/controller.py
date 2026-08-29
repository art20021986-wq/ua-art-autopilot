#!/usr/bin/env python3
"""Controller for the CRM VIN4 title production transaction."""
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


HERE = pathlib.Path(__file__).resolve().parent
CONTRACT = "CRM-VIN4-TITLE-001-V1.0"
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
ROOT = "/home/Carix"
REMOTE = ROOT + "/autopilot_inbox/cloud/task_082_vin4_title"
REMOTE_SCRIPT = REMOTE + "/repair_remote.py"
SOURCE = ROOT + "/cars_ui.py"
DATABASE = ROOT + "/crm.db"
LOCAL_SCRIPT = HERE / "repair_remote.py"
EVIDENCE = HERE / "evidence" / "deploy.json"
STATUS = HERE / "STATUS.md"
MAX_BYTES = 100_000_000


class ControllerError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=path.parent,
        prefix="." + path.name + ".", suffix=".tmp", delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class API:
    def __init__(self) -> None:
        token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "").strip()
        if not token:
            raise ControllerError("PYTHONANYWHERE_API_TOKEN_MISSING")
        self.token = token

    def request(self, method: str, url: str, data=None, headers=None, allowed=(200,), timeout=90):
        request_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task082-vin4-title/1",
        }
        request_headers.update(headers or {})
        last = None
        for attempt in range(1, 6):
            request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    status = response.status
                    body = response.read(MAX_BYTES + 1)
            except urllib.error.HTTPError as exc:
                status = exc.code
                body = exc.read(MAX_BYTES + 1)
            except Exception as exc:
                last = exc
                if attempt < 5:
                    time.sleep(min(2 ** attempt, 15))
                    continue
                raise ControllerError("NETWORK_ERROR:" + type(exc).__name__) from exc
            if len(body) > MAX_BYTES:
                raise ControllerError("RESPONSE_TOO_LARGE")
            if status in allowed:
                return status, body
            if status in (429, 500, 502, 503, 504) and attempt < 5:
                time.sleep(min(2 ** attempt, 15))
                continue
            raise ControllerError("HTTP_%d" % status)
        raise ControllerError("REQUEST_EXHAUSTED:" + type(last).__name__)

    @staticmethod
    def file_url(path: str) -> str:
        if not path.startswith(ROOT + "/"):
            raise ControllerError("PATH_SCOPE")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, *, missing=False) -> bytes | None:
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_FILE_MISSING:" + pathlib.PurePosixPath(path).name)
        return body

    def delete(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(204, 404))

    def upload(self, path: str, payload: bytes) -> None:
        boundary = "----uaart-vin4-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = bytearray()
        body.extend(("--%s\r\n" % boundary).encode())
        body.extend((
            'Content-Disposition: form-data; name="content"; filename="%s"\r\n'
            "Content-Type: %s\r\n\r\n" % (filename, mime)
        ).encode())
        body.extend(payload)
        body.extend(("\r\n--%s--\r\n" % boundary).encode())
        self.request(
            "POST", self.file_url(path), bytes(body),
            {"Content-Type": "multipart/form-data; boundary=" + boundary},
            allowed=(200, 201),
        )

    @staticmethod
    def objects(body: bytes) -> list:
        value = json.loads(body.decode("utf-8"))
        if isinstance(value, dict):
            return value.get("tasks") or value.get("objects") or value.get("results") or []
        return value if isinstance(value, list) else []

    @staticmethod
    def identifier(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        result = value.get("id") if isinstance(value, dict) else None
        return result if isinstance(result, int) and result > 0 else None

    def create_trigger(self, command: str, description: str) -> tuple[str, int]:
        form = urllib.parse.urlencode({
            "command": command,
            "description": description,
            "enabled": "true",
        }).encode()
        status, body = self.request(
            "POST", BASE + "always_on/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self.identifier(body) if status in (200, 201, 202) else None
        if identifier:
            return "always_on", identifier

        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({
            "command": command,
            "description": description + " fallback",
            "enabled": "true",
            "interval": "daily",
            "hour": run_at.hour,
            "minute": run_at.minute,
        }).encode()
        status, body = self.request(
            "POST", BASE + "schedule/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self.identifier(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerError("NO_REMOTE_TRIGGER_AVAILABLE")
        return "schedule", identifier

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        kind, identifier = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request(
            "DELETE", BASE + "%s/%d/" % (endpoint, identifier),
            allowed=(200, 202, 204, 404),
        )

    def run_remote(self, command: str, description: str, receipt_path: str) -> dict:
        self.delete(receipt_path)
        last_error = None
        for lane in range(1, 3):
            trigger = self.create_trigger(command, "%s lane %d" % (description, lane))
            try:
                deadline = time.monotonic() + 240
                while time.monotonic() < deadline:
                    raw = self.read(receipt_path, missing=True)
                    if raw:
                        return json.loads(raw.decode("utf-8"))
                    time.sleep(5)
                last_error = "REMOTE_RECEIPT_TIMEOUT_LANE_%d" % lane
            finally:
                self.delete_trigger(trigger)
            # A late first lane and a second lane are safe: deployment IDs are
            # deterministic and the remote installer is idempotent.
        raise ControllerError(last_error or "REMOTE_RECEIPT_TIMEOUT")

    def launcher(self) -> tuple[int, dict]:
        _, body = self.request("GET", BASE + "always_on/")
        matches = [
            item for item in self.objects(body)
            if isinstance(item, dict)
            and item.get("enabled") is not False
            and str(item.get("command", "")).strip() == "python3.10 /home/Carix/start_safe.py"
        ]
        if len(matches) != 1:
            raise ControllerError("PRODUCTION_LAUNCHER_NOT_UNIQUE")
        identifier = matches[0].get("id")
        if not isinstance(identifier, int):
            raise ControllerError("PRODUCTION_LAUNCHER_ID_INVALID")
        safe = {
            "id": identifier,
            "enabled": matches[0].get("enabled", True),
            "command": matches[0].get("command"),
            "status": matches[0].get("status"),
        }
        return identifier, safe

    def restart_launcher(self) -> dict:
        identifier, before = self.launcher()
        for attempt in range(1, 4):
            try:
                self.request(
                    "POST", BASE + "always_on/%d/restart/" % identifier,
                    b"", allowed=(200, 201, 202, 204),
                )
                _, after = self.launcher()
                return {"attempt": attempt, "before": before, "after": after, "accepted": True}
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(attempt * 5)
        raise ControllerError("RESTART_EXHAUSTED")


def validate_receipt(value: dict, source_before: bytes, database_before: bytes) -> None:
    if value.get("contract") != CONTRACT:
        raise ControllerError("RECEIPT_CONTRACT_INVALID")
    if value.get("status") not in ("PASS_DEPLOYED", "PASS_ALREADY_INSTALLED"):
        raise ControllerError("INSTALL_FAILED:" + ";".join(value.get("errors") or []))
    if value.get("source_before_sha256") != sha(source_before):
        raise ControllerError("SOURCE_PREIMAGE_RACE")
    if value.get("database_before", {}).get("sha256") != sha(database_before):
        raise ControllerError("DATABASE_PREIMAGE_RACE")
    if value.get("database_after", {}).get("sha256") != sha(database_before):
        raise ControllerError("DATABASE_CHANGED")
    if value.get("database_after", {}).get("current_count") != 13:
        raise ControllerError("CURRENT_CARD_COUNT_INVALID")
    if value.get("database_after", {}).get("valid_current_count") != 13:
        raise ControllerError("CURRENT_VIN_COUNT_INVALID")
    if value.get("db_write") is not False or value.get("media_write") is not False or value.get("site_write") is not False:
        raise ControllerError("WRITE_SCOPE_INVALID")
    if value.get("llm_tokens") != 0:
        raise ControllerError("LLM_SCOPE_INVALID")
    tests = value.get("tests") or {}
    if not tests or not all(tests.values()):
        raise ControllerError("TEST_CONTRACT_INVALID")
    expected = ["cars_ui.py"] if value["status"] == "PASS_DEPLOYED" else []
    if value.get("changed_files") != expected:
        raise ControllerError("CHANGED_FILE_SET_INVALID")


def source_postcheck(payload: bytes, expected_sha: str) -> dict:
    text = payload.decode("utf-8")
    compile(text, SOURCE, "exec")
    checks = {
        "sha": sha(payload) == expected_sha,
        "helper_once": text.count("def _ua082_title_html(card):") == 1,
        "render_hook_once": text.count("L.append(_ua082_title_html(card))") == 1,
        "list_hook_once": text.count("lines.append(_ua082_title_html(card))") == 1,
        "button_hook_once": text.count("InlineKeyboardButton(_ua082_title_button(card)") == 1,
    }
    if not all(checks.values()):
        raise ControllerError("SOURCE_POSTCHECK_FAILED")
    return checks


def main() -> int:
    deployment_id = "vin4-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    receipt_path = REMOTE + "/receipts/" + deployment_id + ".json"
    rollback_receipt_path = REMOTE + "/receipts/" + deployment_id + ".rollback.json"
    evidence = {
        "contract": CONTRACT,
        "deployment_id": deployment_id,
        "started_at_utc": utc_now(),
        "status": "FAIL",
        "production_touched": False,
        "restart": None,
        "rollback": None,
        "errors": [],
    }
    api = None
    source_before = b""
    database_before = b""
    receipt = None
    try:
        api = API()
        local = LOCAL_SCRIPT.read_bytes()
        compile(local.decode("utf-8"), str(LOCAL_SCRIPT), "exec")
        source_before = api.read(SOURCE)
        database_before = api.read(DATABASE)
        api.upload(REMOTE_SCRIPT, local)
        if api.read(REMOTE_SCRIPT) != local:
            raise ControllerError("REMOTE_SCRIPT_READBACK_MISMATCH")

        command = "cd %s && python3.10 repair_remote.py --deploy %s" % (REMOTE, deployment_id)
        receipt = api.run_remote(command, "task082 VIN4 title deploy", receipt_path)
        evidence["install"] = receipt
        validate_receipt(receipt, source_before, database_before)
        evidence["production_touched"] = bool(receipt.get("production_touched"))
        evidence["restart"] = api.restart_launcher()

        expected = receipt["source_after_sha256"]
        time.sleep(10)
        immediate_source = api.read(SOURCE)
        immediate_db = api.read(DATABASE)
        if sha(immediate_db) != sha(database_before):
            raise ControllerError("IMMEDIATE_DATABASE_CHANGED")
        immediate = source_postcheck(immediate_source, expected)

        time.sleep(20)
        delayed_source = api.read(SOURCE)
        delayed_db = api.read(DATABASE)
        if sha(delayed_db) != sha(database_before):
            raise ControllerError("DELAYED_DATABASE_CHANGED")
        delayed = source_postcheck(delayed_source, expected)
        _, launcher = api.launcher()
        evidence.update({
            "status": "PASS",
            "finished_at_utc": utc_now(),
            "immediate_postcheck": immediate,
            "delayed_postcheck": delayed,
            "launcher_health": launcher,
            "source_sha256": expected,
            "database_sha256": sha(database_before),
            "production_touched": evidence["production_touched"],
        })
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api is not None and receipt and receipt.get("production_touched"):
            try:
                command = "cd %s && python3.10 repair_remote.py --rollback %s" % (REMOTE, deployment_id)
                rollback = api.run_remote(command, "task082 VIN4 title rollback", rollback_receipt_path)
                evidence["rollback"] = rollback
                if rollback.get("status") != "PASS":
                    raise ControllerError("ROLLBACK_REMOTE_FAILED")
                evidence["restart_after_rollback"] = api.restart_launcher()
                restored = api.read(SOURCE)
                if source_before and restored != source_before:
                    raise ControllerError("ROLLBACK_SOURCE_MISMATCH")
                if database_before and api.read(DATABASE) != database_before:
                    raise ControllerError("ROLLBACK_DATABASE_MISMATCH")
                evidence["production_touched"] = False
            except Exception as rollback_exc:
                evidence["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )

    atomic_text(EVIDENCE, json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    install = evidence.get("install") or {}
    examples = (install.get("database_after") or {}).get("examples") or []
    lines = [
        "# CRM-VIN4-TITLE-001", "",
        "STATUS: **%s**" % evidence["status"], "",
        "- Current cards verified: %s/13" % (install.get("database_after") or {}).get("valid_current_count", 0),
        "- Future-card renderer: %s" % ("PASS" if (install.get("tests") or {}).get("future_vin4") else "NOT VERIFIED"),
        "- Production file set: %s" % (", ".join(install.get("changed_files") or []) or "already installed"),
        "- Bot launcher restart: %s" % ("PASS" if evidence.get("restart") else "NOT VERIFIED"),
        "- Immediate + delayed postcheck: %s" % ("PASS" if evidence["status"] == "PASS" else "FAIL"),
        "- CRM/media/site writes: 0; LLM tokens: 0",
        "- Backup: `%s`" % install.get("backup_path", ""),
        "- Sanitized VIN4 examples: %s" % json.dumps(examples, ensure_ascii=False),
        "- Errors: %s" % ("; ".join(evidence["errors"]) if evidence["errors"] else "none"),
        "",
    ]
    atomic_text(STATUS, "\n".join(lines))
    print(json.dumps({"status": evidence["status"], "errors": evidence["errors"]}, ensure_ascii=False))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
