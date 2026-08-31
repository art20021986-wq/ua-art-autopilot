#!/usr/bin/env python3
"""Owner-authorized production controller for TASK099."""
from __future__ import annotations

import argparse
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
from typing import Any


CONTRACT = "UA-ART-16-SITE-CRM-COMPLETION-099-V1"
APPROVAL = "UA_ART_TASK099_SITE_CRM_PRODUCTION_APPROVED"
ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence"
LIVE_AUDIT = EVIDENCE / "live_audit.json"
TASK096_EVIDENCE = ROOT / "cloud/task_096_tech_spec_ai_crm/data_enrichment/evidence.json"
OUTPUT = EVIDENCE / "production_gate.json"
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_099_site_crm_repair"
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
FILES = {
    "task099_remote.py": HERE / "task099_remote.py",
    "task099_patches.py": HERE / "task099_patches.py",
    "ua_additional_spec.py": HERE / "ua_additional_spec.py",
}
MAX_BYTES = 20_000_000


class Blocked(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.is_file():
        raise Blocked("MISSING_EVIDENCE:" + path.name)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Blocked("INVALID_EVIDENCE:" + path.name)
    return value


def active_production_conflicts() -> list[dict[str, Any]]:
    token = os.environ.get("GITHUB_TOKEN", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    current = str(os.environ.get("GITHUB_RUN_ID", ""))
    if not token or not repository or not current:
        raise Blocked("GITHUB_CONFLICT_GUARD_MISSING")
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ua-art-task099-conflict-guard/1",
    }
    conflicts = []
    for status in ("queued", "in_progress", "waiting", "pending"):
        request = urllib.request.Request(
            "https://api.github.com/repos/%s/actions/runs?status=%s&per_page=100" % (repository, status),
            headers=headers, method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                payload = json.loads(response.read(5_000_001).decode())
        except Exception as exc:
            raise Blocked("GITHUB_CONFLICT_NETWORK:" + type(exc).__name__) from exc
        for run in payload.get("workflow_runs") or []:
            if str(run.get("id")) == current:
                continue
            name = str(run.get("name") or "")
            lowered = name.casefold()
            if any(marker in lowered for marker in ("production", "deploy", "gate b", "gate_b", "quiesce")):
                conflicts.append({"id": run.get("id"), "name": name, "status": run.get("status")})
    return conflicts


def validate_prerequisites() -> dict[str, Any]:
    audit = read_json(LIVE_AUDIT)
    if audit.get("contract_id") != CONTRACT or audit.get("status") != "PASS_READ_ONLY":
        raise Blocked("TASK099_READ_ONLY_AUDIT_NOT_PASS")
    database = audit.get("database") or {}
    if database.get("quick_check") != "ok" or database.get("ids") != ["UA-%04d" % n for n in range(1, 17)]:
        raise Blocked("TASK099_CRM_REGISTRY")
    if sorted(database.get("published_ids") or []) != ["UA-%04d" % n for n in range(1, 17)]:
        raise Blocked("TASK099_PUBLISHED_16")
    if database.get("additional_table_counts"):
        raise Blocked("TASK099_ADDITIONAL_TABLES_ALREADY_EXIST")
    files = audit.get("files") or {}
    expected = {}
    for name in ("cars_ui.py", "master_card.py", "publikaciya.py"):
        digest = (files.get(name) or {}).get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise Blocked("TASK099_SOURCE_HASH_MISSING:" + name)
        expected[name] = digest

    task096 = read_json(TASK096_EVIDENCE)
    if task096.get("status") not in ("PASS", "PASS_WITH_WARNINGS"):
        raise Blocked("TASK096_EVIDENCE_NOT_PASS")
    canary = task096.get("canary") or {}
    batch = task096.get("batch") or {}
    if canary.get("status") != "PASS" or int(canary.get("ua0015_additional_rows") or 0) < 8:
        raise Blocked("TASK096_DATA_CANARY")
    ids = ["UA-%04d" % n for n in range(1, 17)]
    if batch.get("status") != "PASS" or sorted(set(batch.get("processed_uids") or [])) != ids:
        raise Blocked("TASK096_DATA_BATCH")
    for key in (
        "production_touched", "live_crm_write", "main_fields_changed", "public_path_write",
        "bot_code_changed", "services_restarted", "autopublication", "purchase_price_extracted",
        "purchase_price_logged", "purchase_price_uploaded", "production_authorized",
    ):
        if task096.get(key) is not False:
            raise Blocked("TASK096_SCOPE_FLAG:" + key)
    return {
        "contract_id": CONTRACT, "status": "PASS", "source_sha256": expected,
        "audit_finished_at_utc": audit.get("finished_at_utc"),
        "task096_run_id": task096.get("recovery_workflow_run_id"),
        "task096_canary_rows": canary.get("ua0015_additional_rows"),
        "task096_processed_uids": batch.get("processed_uids"),
    }


class API:
    def __init__(self) -> None:
        token = (os.environ.get("PYTHONANYWHERE_API_TOKEN") or "").strip()
        if not token:
            raise Blocked("PYTHONANYWHERE_TOKEN_MISSING")
        self.token = token

    def request(self, method, url, data=None, headers=None, allowed=(200,), timeout=120):
        actual = {"Authorization": "Token " + self.token, "User-Agent": "ua-art-task099/1"}
        actual.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=actual, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status, body = int(response.status), response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, body = int(exc.code), exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise Blocked("PYTHONANYWHERE_NETWORK:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES:
            raise Blocked("PYTHONANYWHERE_RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise Blocked("PYTHONANYWHERE_HTTP_%d:%s" % (status, urllib.parse.urlsplit(url).path))
        return status, body

    @staticmethod
    def file_url(path: str) -> str:
        if not path.startswith(REMOTE + "/"):
            raise Blocked("REMOTE_PATH_SCOPE")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, missing=False):
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise Blocked("REMOTE_FILE_MISSING:" + pathlib.PurePosixPath(path).name)
        return body

    def delete(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(200, 202, 204, 404))

    def upload(self, path: str, data: bytes) -> None:
        boundary = "----uaart-task099-" + uuid.uuid4().hex
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
                allowed=(200, 201, 429, 500, 502, 503, 504), timeout=150,
            )
            if status in (200, 201):
                if self.read(path) != data:
                    raise Blocked("UPLOAD_READBACK:" + filename)
                return
            time.sleep(min(attempt * 3, 12))
        raise Blocked("UPLOAD_FAILED:" + filename)

    @staticmethod
    def object_id(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode())
        except Exception:
            return None
        if isinstance(value, list) and value:
            value = value[0]
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) else None

    def trigger(self, mode: str):
        command = "cd %s && python3.10 task099_remote.py %s" % (REMOTE, mode)
        description = "TASK099 %s %s" % (mode, os.environ.get("GITHUB_RUN_ID", ""))
        form = urllib.parse.urlencode({"command": command, "description": description, "enabled": "true"}).encode()
        status, body = self.request(
            "POST", BASE + "always_on/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self.object_id(body) if status in (200, 201, 202) else None
        if identifier:
            return "always_on", identifier
        at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({
            "command": command, "description": description + " fallback", "enabled": "true",
            "interval": "daily", "hour": at.hour, "minute": at.minute,
        }).encode()
        status, body = self.request(
            "POST", BASE + "schedule/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202),
        )
        identifier = self.object_id(body)
        if not identifier:
            raise Blocked("REMOTE_TRIGGER_MISSING")
        return "schedule", identifier

    def delete_trigger(self, trigger) -> None:
        kind, identifier = trigger
        self.request("DELETE", BASE + "%s/%d/" % (kind, identifier), allowed=(200, 202, 204, 404))

    def run(self, mode: str, timeout: int = 1800) -> dict[str, Any]:
        receipt = REMOTE + "/" + mode + "_receipt.json"
        self.delete(receipt)
        trigger = self.trigger(mode)
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                raw = self.read(receipt, missing=True)
                if raw:
                    return json.loads(raw.decode("utf-8"))
                time.sleep(5)
            raise Blocked("REMOTE_RECEIPT_TIMEOUT:" + mode)
        finally:
            self.delete_trigger(trigger)

    def launcher(self) -> dict[str, Any]:
        _, body = self.request("GET", BASE + "always_on/")
        value = json.loads(body.decode())
        tasks = value.get("results") or value.get("objects") or value.get("tasks") or [] if isinstance(value, dict) else value
        matches = [item for item in tasks if isinstance(item, dict) and item.get("enabled") is not False
                   and str(item.get("command") or "").strip() == "python3.10 /home/Carix/start_safe.py"]
        if len(matches) != 1:
            raise Blocked("PRODUCTION_LAUNCHER_COUNT:%d" % len(matches))
        return matches[0]

    def restart(self) -> dict[str, Any]:
        launcher = self.launcher()
        identifier = int(launcher["id"])
        self.request("POST", BASE + "always_on/%d/restart/" % identifier, b"", allowed=(200, 201, 202, 204))
        return {"status": "accepted", "launcher_id": identifier,
                "command": "python3.10 /home/Carix/start_safe.py"}


def require_pass(value: dict[str, Any], mode: str) -> None:
    if value.get("contract_id") != CONTRACT or value.get("status") != "PASS" or value.get("mode") != mode:
        raise Blocked(mode + "_FAIL:" + json.dumps(value.get("errors") or [], ensure_ascii=False)[:1000])


def upload_payload(api: API, expected: dict[str, Any]) -> None:
    for name, path in FILES.items():
        compile(path.read_text(encoding="utf-8"), name, "exec")
        api.upload(REMOTE + "/" + name, path.read_bytes())
    api.upload(REMOTE + "/expected_live.json", (json.dumps(expected, ensure_ascii=False, indent=2) + "\n").encode())


def perform_rollback(api: API, value: dict[str, Any]) -> None:
    try:
        result = api.run("rollback")
        require_pass(result, "ROLLBACK")
        value["rollback"] = result
        value["rollback_restart"] = api.restart()
        time.sleep(18)
        value["status"] = "ROLLED_BACK"
    except Exception as exc:
        value.setdefault("errors", []).append("ROLLBACK_" + type(exc).__name__ + ":" + str(exc))
        value["status"] = "BLOCKED"


def run_production() -> int:
    value = {
        "contract_id": CONTRACT, "status": "BLOCKED", "mode": "OWNER_APPROVED_PRODUCTION",
        "started_at_utc": utc_now(), "errors": [], "issue_35_closed": False,
        "github_comment_published": False,
    }
    api = None
    installed = False
    try:
        if os.environ.get("TASK099_OWNER_APPROVAL") != APPROVAL:
            raise Blocked("OWNER_APPROVAL_MISSING")
        conflicts = active_production_conflicts()
        if conflicts:
            raise Blocked("PARALLEL_PRODUCTION_GATE:" + json.dumps(conflicts))
        expected = validate_prerequisites()
        value["prerequisites"] = expected
        api = API()
        upload_payload(api, expected)
        shadow = api.run("shadow")
        require_pass(shadow, "SHADOW")
        if shadow.get("production_write") is not False or shadow.get("live_crm_write") is not False:
            raise Blocked("SHADOW_SCOPE")
        value["shadow"] = shadow
        conflicts = active_production_conflicts()
        if conflicts:
            raise Blocked("PARALLEL_PRODUCTION_GATE_BEFORE_INSTALL:" + json.dumps(conflicts))
        install = api.run("install", timeout=2400)
        value["install"] = install
        require_pass(install, "INSTALL")
        installed = True
        if install.get("main_fields_changed") is not False or install.get("media_changed") is not False:
            raise Blocked("INSTALL_PROTECTED_SCOPE")
        value["restart"] = api.restart()
        time.sleep(18)
        value["launcher_after_restart"] = api.launcher()
        immediate = api.run("postcheck")
        require_pass(immediate, "POSTCHECK")
        value["postcheck_immediate"] = immediate
        time.sleep(35)
        delayed = api.run("postcheck")
        require_pass(delayed, "POSTCHECK")
        value["postcheck_delayed"] = delayed
        value["status"] = "PASS_READY_FOR_BROWSER_GATE"
    except Exception as exc:
        value["errors"].append(type(exc).__name__ + ":" + str(exc)[:1600])
        if api is not None and installed:
            perform_rollback(api, value)
    value["finished_at_utc"] = utc_now()
    atomic_json(OUTPUT, value)
    print(json.dumps({"status": value["status"], "errors": value["errors"]}, ensure_ascii=False))
    return 0 if value["status"] == "PASS_READY_FOR_BROWSER_GATE" else 1


def run_rollback() -> int:
    value = read_json(OUTPUT)
    api = API()
    upload_payload(api, validate_prerequisites_after_install(value))
    perform_rollback(api, value)
    value["finished_at_utc"] = utc_now()
    atomic_json(OUTPUT, value)
    print(json.dumps({"status": value["status"], "errors": value.get("errors")}, ensure_ascii=False))
    return 0 if value["status"] == "ROLLED_BACK" else 1


def validate_prerequisites_after_install(value: dict[str, Any]) -> dict[str, Any]:
    expected = value.get("prerequisites")
    if not isinstance(expected, dict) or expected.get("contract_id") != CONTRACT:
        raise Blocked("ROLLBACK_PREREQUISITE_MISSING")
    return expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    return run_rollback() if args.rollback else run_production()


if __name__ == "__main__":
    raise SystemExit(main())
