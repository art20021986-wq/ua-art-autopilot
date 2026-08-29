#!/usr/bin/env python3
"""Separately owner-approved production controller for TASK 081."""

from __future__ import annotations

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


CONTRACT = "UA-0013-PUBLISH-REPAIR-001-V1.0"
APPROVAL = "UA-0013-PUBLISH-REPAIR-001-V1.0-PRODUCTION-APPROVED"
HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_081_publish_repair"
FILES = {
    "patcher_v2.py": HERE / "patcher_v2.py",
    "gate_b_installer_v2.py": HERE / "gate_b_installer_v2.py",
    "postcheck_v2.py": HERE / "postcheck_v2.py",
}
RECEIPTS = {
    "shadow": REMOTE + "/shadow_receipt_v2.json",
    "install": REMOTE + "/install_receipt_v2.json",
    "postcheck": REMOTE + "/postcheck_receipt_v2.json",
    "rollback": REMOTE + "/rollback_receipt_v2.json",
}
COMMANDS = {
    "shadow": "cd %s && (test -f shadow_receipt_v2.json || python3.10 gate_b_installer_v2.py --shadow)" % REMOTE,
    "install": "cd %s && (test -f install_receipt_v2.json || python3.10 gate_b_installer_v2.py --install)" % REMOTE,
    "postcheck": "cd %s && (test -f postcheck_receipt_v2.json || python3.10 postcheck_v2.py)" % REMOTE,
    "rollback": "cd %s && (test -f rollback_receipt_v2.json || python3.10 gate_b_installer_v2.py --rollback)" % REMOTE,
}
GATE_A_EVIDENCE = HERE / "evidence" / "gate_a_v2.json"
EVIDENCE = HERE / "evidence" / "gate_b_v2.json"
REPORT = HERE / "GATE_B_V2_REPORT.md"
MAX_BYTES = 15_000_000


class ControllerBlocked(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix="." + path.name + ".",
        suffix=".tmp",
        delete=False,
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


def active_production_conflicts() -> list:
    token = os.environ.get("GITHUB_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    current = str(os.environ.get("GITHUB_RUN_ID", ""))
    if not token or not repository or not current:
        raise ControllerBlocked("GITHUB_CONFLICT_GUARD_MISSING")
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ua-art-task081-conflict-guard-v2/1",
    }
    conflicts = []
    for status in ("queued", "in_progress", "waiting", "pending"):
        url = "https://api.github.com/repos/%s/actions/runs?status=%s&per_page=100" % (
            repository,
            status,
        )
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                payload = json.loads(response.read(5_000_001).decode())
        except Exception as exc:
            raise ControllerBlocked("GITHUB_CONFLICT_NETWORK:" + type(exc).__name__)
        for run in payload.get("workflow_runs") or []:
            if str(run.get("id")) == current:
                continue
            name = str(run.get("name") or "")
            lowered = name.lower()
            if any(marker in lowered for marker in ("gate_b", "gate-b", "deploy", "production", "quiesce")):
                conflicts.append(
                    {"id": run.get("id"), "name": name, "status": run.get("status")}
                )
    return conflicts


def require_exclusive_window() -> dict:
    conflicts = active_production_conflicts()
    if conflicts:
        raise ControllerBlocked("PARALLEL_PRODUCTION_GATE:" + json.dumps(conflicts))
    return {"status": "PASS", "active_conflicts": 0}


class API:
    def __init__(self):
        token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
        if not token:
            raise ControllerBlocked("PYTHONANYWHERE_TOKEN_MISSING")
        self.token = token

    def request(self, method, url, data=None, headers=None, allowed=(200,), timeout=100):
        request_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task081-gate-b-v2/1",
        }
        request_headers.update(headers or {})
        request = urllib.request.Request(
            url, data=data, headers=request_headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = int(response.status)
                body = response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            body = exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerBlocked("NETWORK:" + type(exc).__name__)
        if len(body) > MAX_BYTES:
            raise ControllerBlocked("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise ControllerBlocked("HTTP_%d:%s" % (status, url.rsplit("/", 2)[-2]))
        return status, body

    @staticmethod
    def file_url(path: str) -> str:
        if not path.startswith(REMOTE + "/"):
            raise ControllerBlocked("REMOTE_PATH_NOT_ALLOWED")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, missing=False):
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerBlocked(
                "REMOTE_FILE_MISSING:" + pathlib.PurePosixPath(path).name
            )
        return body

    def delete_file(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(200, 202, 204, 404))

    def upload(self, path: str, data: bytes) -> None:
        boundary = "----uaart-task081-" + uuid.uuid4().hex
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
        body.extend(data)
        body.extend(("\r\n--%s--\r\n" % boundary).encode())
        for attempt in range(1, 6):
            status, _ = self.request(
                "POST",
                self.file_url(path),
                bytes(body),
                {"Content-Type": "multipart/form-data; boundary=" + boundary},
                allowed=(200, 201, 429, 500, 502, 503, 504),
                timeout=130,
            )
            if status in (200, 201):
                return
            time.sleep(min(2 * attempt, 10))
        raise ControllerBlocked("UPLOAD_FAILED:" + filename)

    @staticmethod
    def objects(body: bytes):
        value = json.loads(body.decode())
        if isinstance(value, dict):
            return value.get("tasks") or value.get("objects") or value.get("results") or []
        return value

    @staticmethod
    def trigger_id(body: bytes):
        try:
            value = json.loads(body.decode())
        except Exception:
            return None
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) and identifier > 0 else None

    def create_trigger(self, command: str, description: str):
        form = urllib.parse.urlencode(
            {"command": command, "description": description, "enabled": "true"}
        ).encode()
        status, body = self.request(
            "POST",
            BASE + "always_on/",
            form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
        if identifier:
            return "always_on", identifier
        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode(
            {
                "command": command,
                "description": description + " fallback",
                "enabled": "true",
                "interval": "daily",
                "hour": run_at.hour,
                "minute": run_at.minute,
            }
        ).encode()
        status, body = self.request(
            "POST",
            BASE + "schedule/",
            form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerBlocked("NO_REMOTE_TRIGGER")
        return "schedule", identifier

    def delete_trigger(self, trigger) -> None:
        kind, identifier = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request(
            "DELETE",
            BASE + "%s/%d/" % (endpoint, identifier),
            allowed=(200, 202, 204, 404),
        )

    def run_remote(self, key: str, timeout=1200) -> dict:
        receipt = RECEIPTS[key]
        self.delete_file(receipt)
        trigger = self.create_trigger(COMMANDS[key], "task081-v2 " + key)
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                raw = self.read(receipt, missing=True)
                if raw:
                    return json.loads(raw.decode("utf-8"))
                time.sleep(5)
            raise ControllerBlocked("RECEIPT_TIMEOUT:" + key)
        finally:
            self.delete_trigger(trigger)

    def launcher(self) -> dict:
        _, body = self.request("GET", BASE + "always_on/")
        tasks = self.objects(body)
        matches = [
            item
            for item in tasks
            if isinstance(item, dict)
            and item.get("enabled") is not False
            and str(item.get("command", "")).strip()
            == "python3.10 /home/Carix/start_safe.py"
        ]
        if len(matches) != 1:
            raise ControllerBlocked("PRODUCTION_LAUNCHER_COUNT:%d" % len(matches))
        return matches[0]

    def restart_bot(self) -> dict:
        task = self.launcher()
        identifier = int(task["id"])
        self.request(
            "POST",
            BASE + "always_on/%d/restart/" % identifier,
            b"",
            allowed=(200, 201, 202, 204),
        )
        return {
            "status": "accepted",
            "launcher_id": identifier,
            "command": "python3.10 /home/Carix/start_safe.py",
        }


def validate_gate_a() -> dict:
    value = json.loads(GATE_A_EVIDENCE.read_text(encoding="utf-8"))
    if value.get("task_id") != "UA-0013-PUBLISH-REPAIR-001":
        raise ControllerBlocked("GATE_A_TASK")
    if value.get("status") != "PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL":
        raise ControllerBlocked("GATE_A_NOT_PASS")
    if value.get("production_touched") is not False:
        raise ControllerBlocked("GATE_A_WRITE_SCOPE")
    if value.get("stage") != {
        "catalog_category": "more",
        "owner_label": "На пароме",
        "status": "sea_loaded",
    }:
        raise ControllerBlocked("GATE_A_STAGE")
    if "UA-0013" not in (value.get("missing_published_numbers") or []):
        raise ControllerBlocked("GATE_A_CANARY_GAP")
    return {
        "status": value["status"],
        "candidate_sha256": value["candidate_sha256"],
        "stage": value["stage"],
        "missing_published_numbers": value["missing_published_numbers"],
    }


def require_pass(value: dict, label: str) -> None:
    if value.get("contract_id") != CONTRACT or value.get("status") != "PASS":
        raise ControllerBlocked(
            label + "_FAIL:" + json.dumps(value.get("errors") or [], ensure_ascii=False)[:2000]
        )


def validate_shadow(value: dict, gate_a: dict) -> None:
    require_pass(value, "SHADOW")
    if value.get("production_write") is not False or value.get("crm_db_write") is not False:
        raise ControllerBlocked("SHADOW_WRITE_SCOPE")
    before = value.get("before") or {}
    targets = before.get("repair_targets") or []
    if "UA-0013" not in targets or not (1 <= len(targets) <= 5):
        raise ControllerBlocked("SHADOW_REPAIR_TARGETS")
    if value.get("candidate_sha256") != gate_a.get("candidate_sha256"):
        raise ControllerBlocked("SHADOW_CANDIDATE_DRIFT")
    if not all(item.get("ok") is True for item in value.get("publisher_probe", {}).get("results", [])):
        raise ControllerBlocked("SHADOW_PUBLISHER_PROBE")


def validate_install(value: dict, gate_a: dict) -> None:
    require_pass(value, "INSTALL")
    if value.get("production_write") is not True or value.get("crm_db_write") is not False:
        raise ControllerBlocked("INSTALL_WRITE_SCOPE")
    if value.get("candidate_sha256") != gate_a.get("candidate_sha256"):
        raise ControllerBlocked("INSTALL_CANDIDATE_DRIFT")
    if not all(item.get("ok") is True for item in value.get("publisher", {}).get("results", [])):
        raise ControllerBlocked("INSTALL_PUBLISHER")
    if not str(value.get("backup_root") or "").startswith(REMOTE + "/backups_v2/"):
        raise ControllerBlocked("INSTALL_BACKUP_SCOPE")
    before = value.get("before") or {}
    after = value.get("after") or {}
    if before.get("database") != after.get("database"):
        raise ControllerBlocked("INSTALL_DATABASE_CHANGED")
    if before.get("protected_pages_sha256") != after.get("protected_pages_sha256"):
        raise ControllerBlocked("INSTALL_PROTECTED_CHANGED")


def validate_postcheck(value: dict, expected_targets: list[str]) -> None:
    require_pass(value, "POSTCHECK")
    if value.get("production_write") is not False or value.get("crm_db_write") is not False:
        raise ControllerBlocked("POSTCHECK_WRITE_SCOPE")
    if value.get("repaired_numbers") != expected_targets:
        raise ControllerBlocked("POSTCHECK_TARGETS")
    if "UA-0013" not in value.get("public", {}):
        raise ControllerBlocked("POSTCHECK_CANARY_PUBLIC")


def report_markdown(value: dict) -> str:
    install = value.get("install") or {}
    delayed = value.get("postcheck_delayed") or {}
    targets = (install.get("before") or {}).get("repair_targets") or []
    return "\n".join(
        [
            "# UA-0013-PUBLISH-REPAIR-001 v1.0 — Gate B",
            "",
            "Status: **%s**" % value.get("status", "BLOCKED"),
            "",
            "- Correct UA-0013 stage: `sea_loaded` → `На пароме`",
            "- Repaired cards: `%s`" % ", ".join(targets),
            "- Public delayed verification: `%s`" % delayed.get("status", "not run"),
            "- Backup: `%s`" % install.get("backup_root", ""),
            "- Rollback: `%s`" % (
                "not needed" if value.get("status") == "PASS" else value.get("rollback")
            ),
            "",
        ]
    )


def main() -> int:
    value = {
        "contract_id": CONTRACT,
        "mode": "OWNER_APPROVED_PRODUCTION_GATE_B_V2",
        "status": "BLOCKED",
        "owner_approval": os.environ.get("TASK081_OWNER_APPROVAL", ""),
        "started_at_utc": utc_now(),
        "errors": [],
        "rollback": None,
    }
    api = None
    install_value = None
    try:
        if value["owner_approval"] != APPROVAL:
            raise ControllerBlocked("OWNER_APPROVAL_MISSING")
        gate_a = validate_gate_a()
        value["gate_a"] = gate_a
        value["exclusive_before_shadow"] = require_exclusive_window()
        api = API()
        for name, path in FILES.items():
            data = path.read_bytes()
            compile(data.decode("utf-8"), name, "exec")
            api.upload(REMOTE + "/" + name, data)
            if api.read(REMOTE + "/" + name) != data:
                raise ControllerBlocked("UPLOAD_READBACK:" + name)

        shadow = api.run_remote("shadow")
        value["shadow"] = shadow
        validate_shadow(shadow, gate_a)
        value["exclusive_before_install"] = require_exclusive_window()
        install_value = api.run_remote("install")
        value["install"] = install_value
        validate_install(install_value, gate_a)

        value["restart"] = api.restart_bot()
        time.sleep(20)
        value["launcher_after_restart"] = api.launcher()
        immediate = api.run_remote("postcheck")
        value["postcheck"] = immediate
        targets = (install_value.get("before") or {}).get("repair_targets") or []
        validate_postcheck(immediate, targets)
        time.sleep(65)
        delayed = api.run_remote("postcheck")
        value["postcheck_delayed"] = delayed
        validate_postcheck(delayed, targets)
        value["status"] = "PASS"
    except Exception as exc:  # noqa: BLE001
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api is not None and install_value and install_value.get("status") == "PASS":
            try:
                rollback = api.run_remote("rollback")
                value["rollback"] = rollback
                require_pass(rollback, "ROLLBACK")
                value["rollback_restart"] = api.restart_bot()
                time.sleep(18)
                value["status"] = "ROLLED_BACK"
            except Exception as rollback_exc:  # noqa: BLE001
                value["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )
                value["status"] = "BLOCKED"
        elif install_value and install_value.get("status") == "ROLLED_BACK":
            value["rollback"] = install_value.get("rollback")
            value["status"] = "ROLLED_BACK"
    value["finished_at_utc"] = utc_now()
    atomic_text(EVIDENCE, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    atomic_text(REPORT, report_markdown(value))
    print(json.dumps({"status": value["status"], "errors": value["errors"]}, ensure_ascii=False))
    return 0 if value["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
