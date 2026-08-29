#!/usr/bin/env python3
"""Owner-approved production Gate B controller for TASK 073 V5."""

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


CONTRACT = "CRM-UNIFIED-CATALOG-001-V1.0"
APPROVAL = "CRM-UNIFIED-CATALOG-001-V1.0-APPROVED"
HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_073"
FILES = {
    "patcher_v5.py": HERE / "patcher_v5.py",
    "gate_b_installer_v5.py": HERE / "gate_b_installer_v5.py",
    "gate_b_postcheck_v5.py": HERE / "gate_b_postcheck_v5.py",
}
RECEIPTS = {
    "shadow": REMOTE + "/shadow_receipt_v5.json",
    "install": REMOTE + "/install_receipt_v5.json",
    "postcheck": REMOTE + "/postcheck_receipt_v5.json",
    "rollback": REMOTE + "/rollback_receipt_v5.json",
}
COMMANDS = {
    "shadow": "cd %s && python3.10 gate_b_installer_v5.py --shadow" % REMOTE,
    "install": "cd %s && python3.10 gate_b_installer_v5.py --install" % REMOTE,
    "postcheck": "cd %s && python3.10 gate_b_postcheck_v5.py" % REMOTE,
    "rollback": "cd %s && python3.10 gate_b_installer_v5.py --rollback" % REMOTE,
}
EVIDENCE = HERE / "evidence" / "gate_b_v5.json"
REPORT = HERE / "GATE_B_V5_REPORT.md"
GATE_A_EVIDENCE = HERE / "evidence" / "gate_a_v5.json"
MAX_BYTES = 12_000_000
PRODUCTION_WORKFLOWS = {
    "task067-crm-online-guard-v1-3-deploy",
    "task068-ferry-vin-v1-1-deploy",
    "task064-emergency-crm-quiesce",
    "SEO Rehab Guard 068 production",
    "TASK073_GATE_B_V4",
    "TASK073_GATE_B_V5",
}


class ControllerBlocked(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
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
        "User-Agent": "ua-art-task073-conflict-guard-v5/1",
    }
    conflicts = []
    for status in ("queued", "in_progress", "waiting", "pending"):
        url = "https://api.github.com/repos/%s/actions/runs?status=%s&per_page=100" % (
            repository, status,
        )
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=30
            ) as response:
                value = json.loads(response.read(4_000_001).decode())
        except Exception as exc:
            raise ControllerBlocked("GITHUB_CONFLICT_NETWORK:" + type(exc).__name__)
        for run in value.get("workflow_runs") or []:
            if str(run.get("id")) == current:
                continue
            if run.get("name") in PRODUCTION_WORKFLOWS:
                conflicts.append({
                    "id": run.get("id"), "name": run.get("name"),
                    "status": run.get("status"),
                })
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

    def request(self, method, url, data=None, headers=None, allowed=(200,), timeout=90):
        request_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task073-gate-b-v5/1",
        }
        request_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = response.status
                body = response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
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
            raise ControllerBlocked("REMOTE_FILE_MISSING:" + pathlib.PurePosixPath(path).name)
        return body

    def delete_file(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(200, 202, 204, 404))

    def upload(self, path: str, data: bytes) -> None:
        boundary = "----uaart-task073-" + uuid.uuid4().hex
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
                allowed=(200, 201, 429, 500, 502, 503, 504), timeout=120,
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
        form = urllib.parse.urlencode({
            "command": command, "description": description, "enabled": "true",
        }).encode()
        status, body = self.request(
            "POST", BASE + "always_on/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
        if identifier:
            return "always_on", identifier
        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({
            "command": command, "description": description + " fallback",
            "enabled": "true", "interval": "daily",
            "hour": run_at.hour, "minute": run_at.minute,
        }).encode()
        status, body = self.request(
            "POST", BASE + "schedule/", form,
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
        self.request("DELETE", BASE + "%s/%d/" % (endpoint, identifier),
                     allowed=(200, 202, 204, 404))

    def run_remote(self, key: str, timeout=900) -> dict:
        receipt = RECEIPTS[key]
        self.delete_file(receipt)
        trigger = self.create_trigger(COMMANDS[key], "task073-v5 " + key)
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
        matches = [item for item in tasks if isinstance(item, dict)
                   and item.get("enabled") is not False
                   and str(item.get("command", "")).strip()
                   == "python3.10 /home/Carix/start_safe.py"]
        if len(matches) != 1:
            raise ControllerBlocked("PRODUCTION_LAUNCHER_COUNT:%d" % len(matches))
        return matches[0]

    def restart_bot(self) -> dict:
        task = self.launcher()
        identifier = int(task["id"])
        self.request("POST", BASE + "always_on/%d/restart/" % identifier,
                     b"", allowed=(200, 201, 202, 204))
        return {"status": "accepted", "launcher_id": identifier,
                "command": "python3.10 /home/Carix/start_safe.py"}


def validate_gate_a() -> dict:
    value = json.loads(GATE_A_EVIDENCE.read_text(encoding="utf-8"))
    if value.get("contract_id") != CONTRACT or value.get("status") != "PASS_READY_FOR_APPROVED_GATE_B":
        raise ControllerBlocked("GATE_A_NOT_PASS")
    if value.get("production_write") is not False or value.get("crm_db_write") is not False:
        raise ControllerBlocked("GATE_A_WRITE_SCOPE")
    return {"status": value["status"], "candidate_sha256": value["candidate_sha256"]}


def require_pass(value: dict, label: str) -> None:
    if value.get("contract_id") != CONTRACT or value.get("status") != "PASS":
        raise ControllerBlocked(label + "_FAIL:" + json.dumps(value.get("errors") or [])[:1500])


def validate_shadow(value: dict) -> None:
    require_pass(value, "SHADOW")
    if value.get("production_write") is not False or value.get("crm_db_write") is not False:
        raise ControllerBlocked("SHADOW_WRITE_SCOPE")
    if value.get("publisher_probe", {}).get("ok") is not True:
        raise ControllerBlocked("SHADOW_PUBLISHER_PROBE")
    before = value.get("before") or {}
    if before.get("database", {}).get("cards_count") != 11:
        raise ControllerBlocked("SHADOW_DATABASE")


def validate_install(value: dict) -> None:
    require_pass(value, "INSTALL")
    if value.get("production_write") is not True or value.get("crm_db_write") is not False:
        raise ControllerBlocked("INSTALL_WRITE_SCOPE")
    if value.get("publisher", {}).get("ok") is not True:
        raise ControllerBlocked("INSTALL_PUBLISHER")
    if not str(value.get("backup_root") or "").startswith(
        REMOTE + "/backups_v5/"
    ):
        raise ControllerBlocked("INSTALL_BACKUP_SCOPE")
    if value.get("before", {}).get("database") != value.get("after", {}).get("database"):
        raise ControllerBlocked("INSTALL_DATABASE_CHANGED")
    if value.get("before", {}).get("protected_pages_sha256") != value.get(
        "after", {}
    ).get("protected_pages_sha256"):
        raise ControllerBlocked("INSTALL_PROTECTED_CHANGED")


def validate_postcheck(value: dict) -> None:
    require_pass(value, "POSTCHECK")
    if value.get("production_write") is not False or value.get("crm_db_write") is not False:
        raise ControllerBlocked("POSTCHECK_WRITE_SCOPE")
    if not all((value.get("public") or {}).get("checks", {}).values()):
        raise ControllerBlocked("POSTCHECK_PUBLIC")
    if value.get("database", {}).get("cards_count") != 11:
        raise ControllerBlocked("POSTCHECK_DATABASE")


def report_markdown(value: dict) -> str:
    install = value.get("install") or {}
    final = value.get("postcheck_delayed") or value.get("postcheck") or {}
    return "\n".join([
        "# CRM-UNIFIED-CATALOG-001 v1.0 — Gate B V5",
        "",
        "Status: **%s**" % value.get("status", "BLOCKED"),
        "",
        "- Duplicate outer buttons removed: %s" % ("PASS" if value.get("status") == "PASS" else "not verified"),
        "- Container inner actions preserved: %s" % ("PASS" if value.get("status") == "PASS" else "not verified"),
        "- UA-0011 primary + diagnostics + catalog: %s" % final.get("status", "not verified"),
        "- Existing cards and database protected: %s" % ("PASS" if value.get("status") == "PASS" else "not verified"),
        "- Backup: `%s`" % install.get("backup_root", ""),
        "- Rollback: %s" % ("not needed" if value.get("status") == "PASS" else value.get("rollback")),
        "",
    ])


def main() -> int:
    value = {
        "contract_id": CONTRACT,
        "mode": "OWNER_APPROVED_PRODUCTION_GATE_B_V5",
        "status": "BLOCKED",
        "owner_approval": os.environ.get("TASK073_OWNER_APPROVAL", ""),
        "runtime_llm_tokens": 0,
        "started_at_utc": utc_now(),
        "errors": [],
        "rollback": None,
    }
    api = None
    install_value = None
    try:
        if value["owner_approval"] != APPROVAL:
            raise ControllerBlocked("OWNER_APPROVAL_MISSING")
        value["gate_a"] = validate_gate_a()
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
        validate_shadow(shadow)
        value["exclusive_before_install"] = require_exclusive_window()
        install_value = api.run_remote("install")
        value["install"] = install_value
        validate_install(install_value)
        value["restart"] = api.restart_bot()
        time.sleep(18)
        value["launcher_after_restart"] = api.launcher()
        immediate = api.run_remote("postcheck")
        value["postcheck"] = immediate
        validate_postcheck(immediate)
        time.sleep(65)
        delayed = api.run_remote("postcheck")
        value["postcheck_delayed"] = delayed
        validate_postcheck(delayed)
        value["status"] = "PASS"
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api is not None and install_value and install_value.get("status") == "PASS":
            try:
                rollback = api.run_remote("rollback")
                value["rollback"] = rollback
                require_pass(rollback, "ROLLBACK")
                value["rollback_restart"] = api.restart_bot()
                time.sleep(15)
                value["status"] = "ROLLED_BACK"
            except Exception as rollback_exc:
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
