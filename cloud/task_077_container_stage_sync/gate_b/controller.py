#!/usr/bin/env python3
"""Orchestrate the owner-approved TASK 077 production Gate B."""
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


CONTRACT = "CRM-CONTAINER-STAGE-SYNC-004-V1.0"
OWNER_TOKEN = "CRM-CONTAINER-STAGE-SYNC-004-V1.0-PRODUCTION-APPROVED"
HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_077_container_stage_sync/gate_b"
REMOTE_PATCHER = "/home/Carix/autopilot_inbox/cloud/task_077_container_stage_sync/patcher"
REMOTE_ENGINE = "/home/Carix/autopilot_inbox/cloud/task_076_eta_sync"
DIR_MARKER = REMOTE + "/directories_ready.txt"
FILES = {
    REMOTE + "/remote.py": HERE / "remote.py",
    REMOTE_PATCHER + "/live_patcher.py": HERE.parent / "patcher" / "live_patcher.py",
    REMOTE_PATCHER + "/eta_release_candidate.py": HERE.parent / "patcher" / "eta_release_candidate.py",
    REMOTE_ENGINE + "/eta_engine.py": HERE.parent.parent / "task_076_eta_sync" / "eta_engine.py",
}
RECEIPTS = {
    "shadow": REMOTE + "/gate_b_shadow_receipt.json",
    "apply": REMOTE + "/gate_b_apply_receipt.json",
    "postcheck": REMOTE + "/gate_b_postcheck_receipt.json",
    "rollback": REMOTE + "/gate_b_rollback_receipt.json",
}
COMMANDS = {
    "shadow": "cd %s && python3.10 remote.py shadow" % REMOTE,
    "apply": "cd %s && python3.10 remote.py apply" % REMOTE,
    "postcheck": "cd %s && python3.10 remote.py postcheck" % REMOTE,
    "rollback": "cd %s && python3.10 remote.py rollback" % REMOTE,
}
EVIDENCE = HERE.parent / "evidence" / "gate_b.json"
REPORT = HERE.parent / "GATE_B_REPORT.md"
MAX_BYTES = 20_000_000
KNOWN_PRODUCTION_WORKFLOWS = {
    "task067-crm-online-guard-v1-3-deploy",
    "task068-ferry-vin-v1-1-deploy",
    "task064-emergency-crm-quiesce",
    "SEO Rehab Guard 068 production",
    "task069-crm-container-production-gate-b",
    "task082-catalog-stage-production",
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
    conflicts = []
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ua-art-task077-conflict-guard/1",
    }
    try:
        for status in ("queued", "in_progress", "waiting", "pending"):
            url = (
                "https://api.github.com/repos/%s/actions/runs?status=%s&per_page=100"
                % (repository, status)
            )
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                value = json.loads(response.read(4_000_001).decode("utf-8"))
            for run in value.get("workflow_runs") or []:
                name = str(run.get("name") or "")
                folded = name.casefold()
                production_like = (
                    name in KNOWN_PRODUCTION_WORKFLOWS
                    or any(marker in folded for marker in (
                        "production", "deploy", "gate b", "gate-b", "gate_b",
                    ))
                )
                if str(run.get("id")) == current or not production_like:
                    continue
                conflicts.append({
                    "id": run.get("id"), "name": run.get("name"), "status": run.get("status"),
                })
    except Exception as exc:
        raise ControllerError("GITHUB_CONFLICT_GUARD_NETWORK:" + type(exc).__name__) from exc
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
            "User-Agent": "ua-art-task077-production-gate-b/1",
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
        allowed = set(FILES) | set(RECEIPTS.values()) | {
            REMOTE + "/gate_b_state.json", DIR_MARKER,
        }
        if path not in allowed:
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
        boundary = "----uaart-task077-" + uuid.uuid4().hex
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
        trigger = self.create_trigger(COMMANDS[key], "task077 " + key)
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

    def ensure_remote_directories(self) -> None:
        self.delete_file(DIR_MARKER)
        command = (
            "mkdir -p %s %s %s && printf TASK077_DIRS_READY > %s"
            % (REMOTE, REMOTE_PATCHER, REMOTE_ENGINE, DIR_MARKER)
        )
        trigger = self.create_trigger(command, "task077 prepare bounded inbox directories")
        try:
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                raw = self.read(DIR_MARKER, missing=True)
                if raw == b"TASK077_DIRS_READY":
                    return
                time.sleep(3)
            raise ControllerError("REMOTE_DIRECTORY_PREP_TIMEOUT")
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
    if database.get("quick_check") != "ok" or int(database.get("row_count") or 0) < 11:
        raise ControllerError("SHADOW_DATABASE")
    targets = database.get("targets") or {}
    if set(targets) != {"UA-0009", "UA-0010"}:
        raise ControllerError("SHADOW_TARGETS")
    if database.get("protected_ua0011", {}).get("auto_number") != "UA-0011":
        raise ControllerError("SHADOW_UA0011_PROTECTION")
    patch = value.get("patch_bundle") or {}
    if patch.get("function_transforms") != 8 or len(patch.get("compiled_files") or {}) != 5:
        raise ControllerError("SHADOW_PATCH_BUNDLE")


def validate_apply(value: dict) -> None:
    require_pass(value, "APPLY")
    if value.get("runtime_llm_tokens") != 0:
        raise ControllerError("APPLY_LLM_TOKENS")
    if not str(value.get("backup_root") or "").startswith(
        "/home/Carix/autopilot_inbox/cloud/task_077_container_stage_sync/gate_b/backups/"
    ):
        raise ControllerError("APPLY_BACKUP_PATH")
    if value.get("production_write") is not True:
        raise ControllerError("APPLY_EXPECTED_WRITE_MISSING")
    if value.get("rollback") is not None:
        raise ControllerError("APPLY_UNEXPECTED_ROLLBACK")
    targets = value.get("database_after", {}).get("targets") or {}
    if set(targets) != {"UA-0009", "UA-0010"}:
        raise ControllerError("APPLY_TARGETS")
    for code, row in targets.items():
        if row.get("auto_number") != code or int(row.get("days_to_kyiv")) != 30:
            raise ControllerError("APPLY_TARGET_DAYS:" + code)
        if row.get("eta_manual") != "2026-09-28" or row.get("status") != "sea_loaded":
            raise ControllerError("APPLY_TARGET_ETA_STATUS:" + code)
    if value.get("database_before", {}).get("protected_rows_sha256") != value.get(
        "database_after", {}
    ).get("protected_rows_sha256"):
        raise ControllerError("APPLY_PROTECTED_ROWS")
    if value.get("database_after", {}).get("protected_ua0011") != value.get(
        "database_before", {}
    ).get("protected_ua0011"):
        raise ControllerError("APPLY_UA0011_CHANGED")


def validate_postcheck(value: dict, protected_sha256: str) -> None:
    require_pass(value, "POSTCHECK")
    if value.get("production_write") is not False or value.get("crm_db_write") is not False:
        raise ControllerError("POSTCHECK_WRITE_SCOPE")
    if value.get("runtime_llm_tokens") != 0:
        raise ControllerError("POSTCHECK_LLM_TOKENS")
    targets = value.get("targets") or {}
    if set(targets) != {"UA-0009", "UA-0010"}:
        raise ControllerError("POSTCHECK_TARGETS")
    for code, row in targets.items():
        if int(row.get("days_to_kyiv")) != 30 or row.get("eta_manual") != "2026-09-28":
            raise ControllerError("POSTCHECK_ETA:" + code)
        if row.get("status") != "sea_loaded":
            raise ControllerError("POSTCHECK_STATUS:" + code)
    if value.get("protected_rows_sha256") != protected_sha256:
        raise ControllerError("POSTCHECK_PROTECTED_ROWS")
    if value.get("protected_ua0011", {}).get("auto_number") != "UA-0011":
        raise ControllerError("POSTCHECK_UA0011")
    if int(value.get("source_count") or 0) != 7:
        raise ControllerError("POSTCHECK_SOURCE_COUNT")
    for code, surfaces in (value.get("public") or {}).items():
        if code not in targets:
            raise ControllerError("POSTCHECK_PUBLIC_CODE")
        for surface in ("video", "site"):
            item = surfaces.get(surface) or {}
            if not (item.get("status") == 200 and item.get("code_present")
                    and item.get("days_30") and item.get("eta_2026_09_28")):
                raise ControllerError("POSTCHECK_PUBLIC:%s:%s" % (code, surface))


def report_markdown(value: dict) -> str:
    install = value.get("apply") or {}
    final = value.get("postcheck_delayed") or value.get("postcheck") or {}
    lines = [
        "# CRM-CONTAINER-STAGE-SYNC-004 v1.0 — Gate B",
        "",
        "STATUS: **%s**" % value.get("status", "FAIL"),
        "",
        "- Production patch: %s" % ("PASS" if install.get("status") == "PASS" else "NOT APPLIED"),
        "- UA-0009 / UA-0010: days=30, ETA=2026-09-28, status=sea_loaded: %s" % (
            "PASS" if final.get("status") == "PASS" else "NOT VERIFIED"
        ),
        "- UA-0011 protected under the newer Korea-stage amendment: %s" % (
            "PASS" if final.get("protected_ua0011", {}).get("auto_number") == "UA-0011"
            else "NOT VERIFIED"
        ),
        "- `/video`, `/site`, diagnostics and catalogs: %s" % (
            "PASS" if final.get("status") == "PASS" else "NOT VERIFIED"
        ),
        "- SQLite quick_check: `%s`" % final.get("quick_check", "—"),
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
        "owner_approval": "Продакшн в работу.",
        "runtime_llm_tokens": 0,
        "errors": [],
        "rollback": None,
    }
    api = None
    applied = None
    try:
        if os.environ.get("APPROVAL_TOKEN") != OWNER_TOKEN:
            raise ControllerError("OWNER_TOKEN_MISMATCH")
        api = API()
        api.ensure_remote_directories()
        for remote_path, path in FILES.items():
            data = path.read_bytes()
            compile(data.decode("utf-8"), str(path), "exec")
            api.upload(remote_path, data)
            if api.read(remote_path) != data:
                raise ControllerError("UPLOAD_READBACK:" + pathlib.PurePosixPath(remote_path).name)

        result["conflict_guard_before_shadow"] = require_no_production_conflicts()
        shadow = api.run_remote("shadow")
        result["shadow"] = shadow
        validate_shadow(shadow)

        result["conflict_guard_before_apply"] = require_no_production_conflicts()
        applied = api.run_remote("apply", timeout=1200)
        result["apply"] = applied
        validate_apply(applied)
        result["restart"] = api.restart_bot()
        time.sleep(15)

        postcheck = api.run_remote("postcheck")
        result["postcheck"] = postcheck
        protected = applied["database_after"]["protected_rows_sha256"]
        validate_postcheck(postcheck, protected)
        time.sleep(65)
        delayed = api.run_remote("postcheck")
        result["postcheck_delayed"] = delayed
        validate_postcheck(delayed, protected)
        result["status"] = "PASS"
    except Exception as exc:
        result["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api is not None and applied and applied.get("status") == "PASS" and applied.get("production_write"):
            try:
                rollback = api.run_remote("rollback")
                result["rollback"] = rollback
                require_pass(rollback, "ROLLBACK")
                result["rollback_restart"] = api.restart_bot()
                time.sleep(12)
                rollback_shadow = api.run_remote("shadow")
                result["rollback_shadow"] = rollback_shadow
                validate_shadow(rollback_shadow)
                result["status"] = "ROLLED_BACK"
            except Exception as rollback_exc:
                result["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )
                result["status"] = "BLOCKED"
        elif applied and applied.get("status") == "ROLLED_BACK":
            result["rollback"] = applied.get("rollback")
            try:
                result["rollback_restart"] = api.restart_bot() if api else None
            except Exception as restart_exc:
                result["errors"].append("ROLLBACK_RESTART:" + str(restart_exc))
            result["status"] = "ROLLED_BACK"
    result["finished_at_utc"] = utc_now()
    atomic_text(EVIDENCE, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    atomic_text(REPORT, report_markdown(result))
    print(json.dumps({"status": result["status"], "errors": result["errors"]}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
