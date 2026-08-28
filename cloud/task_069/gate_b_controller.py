#!/usr/bin/env python3
"""Orchestrate approved production Gate B for TASK 069."""
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


CONTRACT = "CRM-CONTAINER-KYIV-DAYS-001-V1.0"
HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_069"
FILES = {
    "task069_gate_b_installer.py": HERE / "gate_b_installer.py",
    "task069_gate_b_postcheck.py": HERE / "gate_b_postcheck.py",
}
RECEIPTS = {
    "shadow": REMOTE + "/gate_b_shadow_receipt.json",
    "install": REMOTE + "/gate_b_install_receipt.json",
    "postcheck": REMOTE + "/gate_b_postcheck_receipt.json",
    "rollback": REMOTE + "/gate_b_rollback_receipt.json",
}
COMMANDS = {
    "shadow": "cd %s && python3.10 task069_gate_b_installer.py --shadow" % REMOTE,
    "install": "cd %s && python3.10 task069_gate_b_installer.py" % REMOTE,
    "postcheck": "cd %s && python3.10 task069_gate_b_postcheck.py" % REMOTE,
    "rollback": "cd %s && python3.10 task069_gate_b_installer.py --rollback" % REMOTE,
}
EVIDENCE = HERE / "evidence" / "gate_b.json"
REPORT = HERE / "GATE_B_REPORT.md"
MAX_BYTES = 12_000_000
CONFLICTING_WORKFLOWS = {
    "task067-crm-online-guard-v1-3-deploy",
    "task068-ferry-vin-v1-1-deploy",
    "task064-emergency-crm-quiesce",
    "SEO Rehab Guard 068 production",
}


class ControllerError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def active_production_conflicts() -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    current = str(os.environ.get("GITHUB_RUN_ID", ""))
    if not token or not repository or not current:
        raise ControllerError("GITHUB_CONFLICT_GUARD_MISSING")
    url = "https://api.github.com/repos/%s/actions/runs?per_page=100" % repository
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ua-art-task069-conflict-guard/1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            value = json.loads(response.read(4_000_001).decode("utf-8"))
    except Exception as exc:
        raise ControllerError("GITHUB_CONFLICT_GUARD_NETWORK:" + type(exc).__name__) from exc
    conflicts = []
    for run in value.get("workflow_runs") or []:
        if str(run.get("id")) == current:
            continue
        if run.get("name") not in CONFLICTING_WORKFLOWS:
            continue
        if run.get("status") not in ("queued", "in_progress", "waiting", "pending"):
            continue
        conflicts.append({
            "id": run.get("id"), "name": run.get("name"), "status": run.get("status"),
        })
    return conflicts


def require_no_production_conflicts() -> dict:
    conflicts = active_production_conflicts()
    if conflicts:
        raise ControllerError("PARALLEL_PRODUCTION_GATE:" + json.dumps(conflicts, sort_keys=True))
    return {"status": "PASS", "active_conflicts": 0}


class API:
    def __init__(self) -> None:
        token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
        if not token:
            raise ControllerError("PYTHONANYWHERE_TOKEN_MISSING")
        self.token = token

    def request(self, method, url, data=None, headers=None, allowed=(200,), timeout=90):
        request_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task069-production-gate-b/1",
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
            raise ControllerError("NETWORK:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES:
            raise ControllerError("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise ControllerError("HTTP_%d" % status)
        return status, body

    def file_url(self, path: str) -> str:
        if not path.startswith(REMOTE + "/"):
            raise ControllerError("REMOTE_PATH_NOT_ALLOWED")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, *, missing: bool = False) -> bytes | None:
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_FILE_MISSING:" + pathlib.PurePosixPath(path).name)
        return body

    def delete_file(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(200, 202, 204, 404))

    def upload(self, path: str, data: bytes) -> None:
        boundary = "----uaart-task069-" + uuid.uuid4().hex
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
                allowed=(200, 201, 429, 500, 502, 503, 504),
            )
            if status in (200, 201):
                return
            time.sleep(min(attempt * 2, 10))
        raise ControllerError("UPLOAD_FAILED:" + filename)

    @staticmethod
    def objects(body: bytes) -> list:
        value = json.loads(body.decode("utf-8"))
        if isinstance(value, dict):
            return value.get("tasks") or value.get("objects") or value.get("results") or []
        return value

    @staticmethod
    def trigger_id(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) and identifier > 0 else None

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
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
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
        identifier = self.trigger_id(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerError("NO_REMOTE_TRIGGER")
        return "schedule", identifier

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        kind, identifier = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request(
            "DELETE", BASE + "%s/%d/" % (endpoint, identifier),
            allowed=(200, 202, 204, 404),
        )

    def run_remote(self, key: str, timeout: int = 900) -> dict:
        receipt = RECEIPTS[key]
        self.delete_file(receipt)
        trigger = self.create_trigger(COMMANDS[key], "task069 " + key)
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                raw = self.read(receipt, missing=True)
                if raw:
                    return json.loads(raw.decode("utf-8"))
                time.sleep(5)
            raise ControllerError("RECEIPT_TIMEOUT:" + key)
        finally:
            self.delete_trigger(trigger)

    def restart_bot(self) -> dict:
        _, body = self.request("GET", BASE + "always_on/")
        tasks = self.objects(body)
        matches = [
            item for item in tasks
            if isinstance(item, dict)
            and item.get("enabled") is not False
            and str(item.get("command", "")).strip() == "python3.10 /home/Carix/start_safe.py"
        ]
        if len(matches) != 1:
            raise ControllerError("PRODUCTION_LAUNCHER_COUNT:%d" % len(matches))
        identifier = int(matches[0]["id"])
        self.request(
            "POST", BASE + "always_on/%d/restart/" % identifier,
            b"", allowed=(200, 201, 202, 204),
        )
        return {
            "status": "accepted",
            "launcher_id": identifier,
            "command": "python3.10 /home/Carix/start_safe.py",
        }


def require_pass(value: dict, key: str) -> None:
    if value.get("contract_id") != CONTRACT or value.get("status") != "PASS":
        raise ControllerError(
            "%s_FAIL:%s" % (key, json.dumps(value.get("errors") or [], ensure_ascii=False)[:1000])
        )


def validate_shadow(value: dict) -> None:
    require_pass(value, "SHADOW")
    if value.get("production_write") is not False or value.get("crm_db_write") is not False:
        raise ControllerError("SHADOW_WRITE_SCOPE")
    if value.get("runtime_llm_tokens") != 0:
        raise ControllerError("SHADOW_LLM_TOKENS")
    database = value.get("database") or {}
    if database.get("quick_check") != "ok" or len(database.get("card_ids") or []) < 11:
        raise ControllerError("SHADOW_DATABASE")
    if database.get("target", {}).get("auto_number") != "UA-0011":
        raise ControllerError("SHADOW_TARGET")
    if database.get("target", {}).get("sea_container") not in (None, "ONEYSELGF1046602"):
        raise ControllerError("SHADOW_TARGET_CONTAINER_CONFLICT")


def validate_install(value: dict) -> None:
    require_pass(value, "INSTALL")
    if value.get("runtime_llm_tokens") != 0:
        raise ControllerError("INSTALL_LLM_TOKENS")
    if not str(value.get("backup_root") or "").startswith(
        "/home/Carix/autopilot_inbox/cloud/task_069/backups/"
    ):
        raise ControllerError("INSTALL_BACKUP_PATH")
    if value.get("production_write") is not True:
        raise ControllerError("INSTALL_EXPECTED_WRITE_MISSING")
    if value.get("database_after", {}).get("target", {}).get("sea_container") != "ONEYSELGF1046602":
        raise ControllerError("INSTALL_TARGET_READBACK")
    if value.get("database_before", {}).get("protected_rows_sha256") != value.get(
        "database_after", {}
    ).get("protected_rows_sha256"):
        raise ControllerError("INSTALL_PROTECTED_ROWS")


def validate_postcheck(value: dict) -> None:
    require_pass(value, "POSTCHECK")
    if value.get("production_write") is not False or value.get("crm_db_write") is not False:
        raise ControllerError("POSTCHECK_WRITE_SCOPE")
    if value.get("runtime_llm_tokens") != 0:
        raise ControllerError("POSTCHECK_LLM_TOKENS")
    if value.get("database", {}).get("target", {}).get("sea_container") != "ONEYSELGF1046602":
        raise ControllerError("POSTCHECK_TARGET")
    if value.get("ua_0009_protected") is not True or value.get("all_cards_protected") is not True:
        raise ControllerError("POSTCHECK_CARD_PROTECTION")
    bots = value.get("bots") or {}
    if not bots.get("tokens_distinct") or any(
        not bots.get("bots", {}).get(name, {}).get("ok") for name in ("client", "crm")
    ):
        raise ControllerError("POSTCHECK_BOTS")


def report_markdown(value: dict) -> str:
    install = value.get("install") or {}
    final = value.get("postcheck_delayed") or value.get("postcheck") or {}
    lines = [
        "# CRM-CONTAINER-KYIV-DAYS-001 v1.0 — Gate B",
        "",
        "STATUS: **%s**" % value.get("status", "FAIL"),
        "",
        "- Production patch: %s" % ("PASS" if install.get("status") == "PASS" else "NOT APPLIED"),
        "- UA-0011 container: `%s`" % final.get("database", {}).get("target", {}).get("sea_container", "—"),
        "- Button `⏱ Количество дней до Киева`: %s" % (
            "PASS" if final.get("candidate", {}).get("button_label_occurrences") == 2 else "NOT VERIFIED"
        ),
        "- UA-0009 and all current cards protected: %s (count: %s)" % (
            "PASS" if final.get("all_cards_protected") else "NOT VERIFIED",
            len(final.get("database", {}).get("card_ids") or []),
        ),
        "- SQLite quick_check: `%s`" % final.get("database", {}).get("quick_check", "—"),
        "- Backup: `%s`" % install.get("backup_root", ""),
        "- Runtime LLM tokens: 0",
        "- Rollback: %s" % (
            "not needed" if value.get("status") == "PASS" else json.dumps(value.get("rollback"), ensure_ascii=False)
        ),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    result = {
        "contract_id": CONTRACT,
        "mode": "APPROVED_PRODUCTION_GATE_B",
        "status": "FAIL",
        "started_at_utc": utc_now(),
        "owner_approval": "УТВЕРЖДАЮ CRM-CONTAINER-KYIV-DAYS-001 v1.0. РАЗРЕШАЮ PRODUCTION GATE B",
        "runtime_llm_tokens": 0,
        "errors": [],
        "rollback": None,
    }
    api = None
    install = None
    try:
        api = API()
        for name, path in FILES.items():
            data = path.read_bytes()
            compile(data.decode("utf-8"), name, "exec")
            api.upload(REMOTE + "/" + name, data)
            if api.read(REMOTE + "/" + name) != data:
                raise ControllerError("UPLOAD_READBACK:" + name)

        result["conflict_guard_before_shadow"] = require_no_production_conflicts()
        shadow = api.run_remote("shadow")
        result["shadow"] = shadow
        validate_shadow(shadow)

        result["conflict_guard_before_install"] = require_no_production_conflicts()
        install = api.run_remote("install")
        result["install"] = install
        validate_install(install)
        result["restart"] = api.restart_bot()
        time.sleep(15)

        postcheck = api.run_remote("postcheck")
        result["postcheck"] = postcheck
        validate_postcheck(postcheck)
        time.sleep(30)
        delayed = api.run_remote("postcheck")
        result["postcheck_delayed"] = delayed
        validate_postcheck(delayed)
        result["status"] = "PASS"
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api is not None and install and install.get("status") == "PASS" and install.get("production_write"):
            try:
                rollback = api.run_remote("rollback")
                result["rollback"] = rollback
                require_pass(rollback, "ROLLBACK")
                result["rollback_restart"] = api.restart_bot()
                time.sleep(12)
                rollback_shadow = api.run_remote("shadow")
                result["rollback_shadow"] = rollback_shadow
                validate_shadow(rollback_shadow)
                if rollback_shadow.get("database", {}).get("rows_sha256") != install.get(
                    "database_before", {}
                ).get("rows_sha256"):
                    raise ControllerError("ROLLBACK_DATABASE_NOT_EXACT")
                if rollback_shadow.get("candidate", {}).get("source_sha256") != install.get(
                    "candidate", {}
                ).get("source_sha256"):
                    raise ControllerError("ROLLBACK_SOURCE_NOT_EXACT")
                result["status"] = "ROLLED_BACK"
            except Exception as rollback_exc:
                result["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )
                result["status"] = "BLOCKED"
    result["finished_at_utc"] = utc_now()
    atomic_text(EVIDENCE, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    atomic_text(REPORT, report_markdown(result))
    print(json.dumps({"status": result["status"], "errors": result["errors"]}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
