#!/usr/bin/env python3
"""Upload, install, restart and verify UA-CARDS-STAGE-ANCHOR-001 V1.1."""
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


HERE = pathlib.Path(__file__).resolve().parent
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_047_ferry_discovery"
STATE_ROOT = "/home/Carix/autopilot_inbox/cloud/task_066_stage_anchor"
FILES = {
    "task066_stage_repair.py": HERE / "repair_remote.py",
    "task066_stage_postcheck.py": HERE / "postcheck_remote.py",
}
INSTALL_RECEIPT = STATE_ROOT + "/install_receipt.json"
SOURCE_RECEIPT = STATE_ROOT + "/source_install_receipt.json"
POSTCHECK_RECEIPT = STATE_ROOT + "/postcheck_receipt.json"
ROLLBACK_RECEIPT = STATE_ROOT + "/rollback_receipt.json"
INSTALL_COMMAND = "cd %s && python3.10 task066_stage_repair.py" % REMOTE
SOURCE_COMMAND = "cd %s && python3.10 task066_stage_repair.py --sources-only" % REMOTE
POSTCHECK_COMMAND = "cd %s && python3.10 task066_stage_postcheck.py" % REMOTE
ROLLBACK_COMMAND = "cd %s && python3.10 task066_stage_repair.py --rollback" % REMOTE
EVIDENCE = HERE / "evidence" / "deploy.json"
REPORT = HERE / "TASK_066_REPORT.md"
CONTRACT = "UA-CARDS-STAGE-ANCHOR-001-V1.1"
MAX_BYTES = 5_000_000


class ControllerError(RuntimeError):
    pass


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
        token = os.environ.get("PYTHONANYWHERE_API_TOKEN", "")
        if not token:
            raise ControllerError("PYTHONANYWHERE_TOKEN_MISSING")
        self.token = token

    def request(self, method, url, data=None, headers=None, allowed=(200,)):
        request_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task066-stage-anchor/1",
        }
        request_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status = response.status
                body = response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK_ERROR:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES:
            raise ControllerError("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise ControllerError("HTTP_%d" % status)
        return status, body

    def file_url(self, path: str) -> str:
        if not (path.startswith(REMOTE + "/") or path.startswith(STATE_ROOT + "/")):
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
        self.request("DELETE", self.file_url(path), allowed=(204, 404))

    def upload(self, path: str, data: bytes) -> None:
        boundary = "----uaart-task066-" + uuid.uuid4().hex
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
            if attempt < 5:
                time.sleep(min(attempt * 3, 12))
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
            raise ControllerError("NO_REMOTE_TRIGGER_AVAILABLE")
        return "schedule", identifier

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        kind, identifier = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request(
            "DELETE", BASE + "%s/%d/" % (endpoint, identifier),
            allowed=(200, 202, 204, 404),
        )

    def run_remote(self, command: str, description: str, receipt_path: str,
                   seconds: int = 900) -> dict:
        self.delete_file(receipt_path)
        trigger = self.create_trigger(command, description)
        try:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                raw = self.read(receipt_path, missing=True)
                if raw:
                    return json.loads(raw.decode("utf-8"))
                time.sleep(5)
            raise ControllerError("REMOTE_RECEIPT_TIMEOUT:" + pathlib.PurePosixPath(receipt_path).name)
        finally:
            self.delete_trigger(trigger)

    def restart_bot(self) -> dict:
        _, body = self.request("GET", BASE + "always_on/")
        tasks = self.objects(body)
        matching = [
            item for item in tasks
            if isinstance(item, dict)
            and item.get("enabled") is not False
            and str(item.get("command", "")).strip() == "python3.10 /home/Carix/start_safe.py"
        ]
        if len(matching) != 1:
            raise ControllerError("PRODUCTION_BOT_TASK_NOT_UNIQUE")
        identifier = matching[0].get("id")
        self.request(
            "POST", BASE + "always_on/%d/restart/" % identifier,
            b"", allowed=(200, 201, 202, 204),
        )
        return {
            "configured": True,
            "enabled": True,
            "command": "python3.10 /home/Carix/start_safe.py",
            "restart_accepted": True,
        }


def validate_source_install(value: dict) -> None:
    if value.get("contract_id") != CONTRACT or value.get("status") != "PASS":
        raise ControllerError("SOURCE_INSTALL_FAILED:" + ";".join(value.get("errors", [])))
    if value.get("sources_only") is not True or value.get("llm_tokens") != 0:
        raise ControllerError("SOURCE_INSTALL_SCOPE_INVALID")
    for key in ("crm_write", "db_write", "media_write"):
        if value.get(key) is not False:
            raise ControllerError("SOURCE_INSTALL_WRITE_SCOPE_INVALID:" + key)
    expected = {"stranica.py", "yadro.py", "master_card.py", "cars_ui.py"}
    if set(value.get("source_sha256_after") or {}) != expected:
        raise ControllerError("SOURCE_INSTALL_SET_INVALID")
    changed = set(value.get("changed_paths") or [])
    if not changed.issubset(expected):
        raise ControllerError("SOURCE_INSTALL_CHANGED_PATH_INVALID")
    if value.get("production_files_changed") != len(changed):
        raise ControllerError("SOURCE_INSTALL_CHANGED_COUNT_INVALID")
    if value.get("master_final_fixtures") != {"korea": 1, "ferry": 2, "georgia": 3, "kyiv": 4}:
        raise ControllerError("SOURCE_INSTALL_MASTER_FIXTURES_INVALID")
    if not value.get("backup_root", "").startswith(STATE_ROOT + "/backups/"):
        raise ControllerError("SOURCE_INSTALL_BACKUP_INVALID")


def validate_install(value: dict) -> None:
    if value.get("contract_id") != CONTRACT or value.get("status") != "PASS":
        raise ControllerError("INSTALL_FAILED:" + ";".join(value.get("errors", [])))
    if value.get("sources_only") is not False:
        raise ControllerError("INSTALL_PHASE_INVALID")
    if value.get("llm_tokens") != 0:
        raise ControllerError("INSTALL_LLM_SCOPE_INVALID")
    for key in ("crm_write", "db_write", "media_write"):
        if value.get(key) is not False:
            raise ControllerError("INSTALL_WRITE_SCOPE_INVALID:" + key)
    ids = value.get("card_ids")
    if not isinstance(ids, list) or len(ids) != 10 or len(set(ids)) != 10 or "UA-0009" not in ids:
        raise ControllerError("INSTALL_CARD_SET_INVALID")
    cards = value.get("cards")
    if not isinstance(cards, list) or len(cards) != 10:
        raise ControllerError("INSTALL_CARD_RESULTS_INVALID")
    for card in cards:
        if card.get("id") not in ids or card.get("stage") not in (1, 2, 3, 4):
            raise ControllerError("INSTALL_CARD_RESULT_INVALID")
        roots = card.get("roots")
        if not isinstance(roots, dict) or set(roots) != {"video", "site"}:
            raise ControllerError("INSTALL_ROOTS_INVALID")
        for item in roots.values():
            if (item.get("stage_anchor_count") != 1 or item.get("stage_nodes") != 4
                    or item.get("current_nodes") != 1 or item.get("diagnostics_links") != 1):
                raise ControllerError("INSTALL_CARD_CONTRACT_INVALID")
    if value.get("db_before", {}).get("published_rows_sha256") != value.get("db_after", {}).get("published_rows_sha256"):
        raise ControllerError("INSTALL_CRM_CHANGED")
    if value.get("media_before") != value.get("media_after"):
        raise ControllerError("INSTALL_MEDIA_CHANGED")
    if value.get("fixtures") != {"korea": 1, "ferry": 2, "georgia": 3, "kyiv": 4}:
        raise ControllerError("INSTALL_FIXTURES_INVALID")
    if value.get("master_final_fixtures") != {"korea": 1, "ferry": 2, "georgia": 3, "kyiv": 4}:
        raise ControllerError("INSTALL_MASTER_FINAL_FIXTURES_INVALID")
    if not value.get("backup_root", "").startswith(STATE_ROOT + "/backups/"):
        raise ControllerError("INSTALL_BACKUP_INVALID")
    if value.get("production_files_changed") != len(value.get("changed_paths") or []):
        raise ControllerError("INSTALL_CHANGED_COUNT_INVALID")


def validate_postcheck(value: dict) -> None:
    if value.get("contract_id") != CONTRACT or value.get("status") != "PASS":
        raise ControllerError("POSTCHECK_FAILED:" + ";".join(value.get("errors", [])))
    if value.get("read_only") is not True or value.get("crm_write") is not False or value.get("media_write") is not False:
        raise ControllerError("POSTCHECK_SCOPE_INVALID")
    if value.get("card_count") != 10:
        raise ControllerError("POSTCHECK_CARD_COUNT_INVALID")
    distribution = value.get("stage_distribution") or {}
    if set(distribution) != {"1", "2", "3", "4"} or any(number <= 0 for number in distribution.values()):
        raise ControllerError("POSTCHECK_STAGE_COVERAGE_INVALID")
    ua0009 = value.get("ua0009") or {}
    if ua0009.get("id") != "UA-0009" or ua0009.get("stage") != 2:
        raise ControllerError("POSTCHECK_UA0009_INVALID")
    bots = (value.get("bot_health") or {}).get("bots") or {}
    if not (value.get("bot_health") or {}).get("tokens_distinct") or any(
        not bots.get(name, {}).get("ok") for name in ("client", "crm")
    ):
        raise ControllerError("POSTCHECK_BOTS_INVALID")
    if not (value.get("runtime") or {}).get("ok"):
        raise ControllerError("POSTCHECK_RUNTIME_INVALID")
    if value.get("master_final_fixtures") != {"korea": 1, "ferry": 2, "georgia": 3, "kyiv": 4}:
        raise ControllerError("POSTCHECK_MASTER_FINAL_FIXTURES_INVALID")


def main() -> int:
    evidence = {
        "contract_id": CONTRACT,
        "status": "FAIL",
        "llm_tokens": 0,
        "bot_restarted": False,
        "preinstall_bot_restarted": False,
        "rollback": None,
        "errors": [],
    }
    api = None
    install = None
    try:
        api = API()
        for name, local in FILES.items():
            data = local.read_bytes()
            compile(data.decode("utf-8"), name, "exec")
            api.upload(REMOTE + "/" + name, data)
            if api.read(REMOTE + "/" + name) != data:
                raise ControllerError("UPLOAD_READBACK_MISMATCH:" + name)

        # Phase 1 changes only generator/filter sources.  The long-lived bot is
        # then restarted so every concurrent writer has the new final filter in
        # memory before phase 2 touches any published card.
        source_install = api.run_remote(
            SOURCE_COMMAND,
            "task066 install final card writer sources only",
            SOURCE_RECEIPT,
        )
        evidence["source_install"] = source_install
        validate_source_install(source_install)
        evidence["preinstall_service_contract"] = api.restart_bot()
        evidence["preinstall_bot_restarted"] = True
        time.sleep(12)

        install = api.run_remote(
            INSTALL_COMMAND,
            "task066 install permanent card stages and CRM cleanup",
            INSTALL_RECEIPT,
        )
        evidence["install"] = install
        validate_install(install)
        evidence["service_contract"] = api.restart_bot()
        evidence["bot_restarted"] = True
        time.sleep(10)
        postcheck = api.run_remote(
            POSTCHECK_COMMAND,
            "task066 verify cards and both Telegram bots",
            POSTCHECK_RECEIPT,
        )
        evidence["postcheck"] = postcheck
        validate_postcheck(postcheck)
        # A second independent read is intentionally delayed.  The previous
        # regression appeared only after a background generator rewrote the
        # cards, so an immediate green check is no longer sufficient evidence.
        for _interval in range(3):
            time.sleep(30)
        delayed = api.run_remote(
            POSTCHECK_COMMAND,
            "task066 delayed permanence check after background writers",
            POSTCHECK_RECEIPT,
        )
        evidence["postcheck_delayed"] = delayed
        validate_postcheck(delayed)
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        if api is not None and install and install.get("status") == "PASS" and install.get("changed_paths"):
            try:
                rollback = api.run_remote(
                    ROLLBACK_COMMAND,
                    "task066 rollback failed stage anchor deployment",
                    ROLLBACK_RECEIPT,
                )
                evidence["rollback"] = rollback
                if rollback.get("status") != "PASS":
                    raise ControllerError("ROLLBACK_FAILED")
                api.restart_bot()
            except Exception as rollback_exc:
                evidence["errors"].append(
                    "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )

    atomic_text(EVIDENCE, json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    install_value = evidence.get("install") or {}
    post = evidence.get("postcheck") or {}
    delayed = evidence.get("postcheck_delayed") or {}
    report = "\n".join([
        "# UA-CARDS-STAGE-ANCHOR-001 V1.1", "",
        "STATUS: **%s**" % evidence["status"], "",
        "- Current cards: %s" % post.get("card_count", "not verified"),
        "- Stage coverage: %s" % json.dumps(post.get("stage_distribution", {}), sort_keys=True),
        "- UA-0009: %s" % ("PASS" if post.get("ua0009") else "NOT VERIFIED"),
        "- Both bots: %s" % ("PASS" if post.get("bot_health") else "NOT VERIFIED"),
        "- Two-phase source reload before card writes: %s" % ("PASS" if evidence.get("preinstall_bot_restarted") else "NOT RUN"),
        "- Delayed permanence check: %s" % ("PASS" if delayed.get("status") == "PASS" else "NOT VERIFIED"),
        "- CRM write: false; media write: false; LLM tokens: 0",
        "- Changed production files: %s" % install_value.get("production_files_changed", 0),
        "- Backup: `%s`" % install_value.get("backup_root", ""),
        "- Errors: %s" % ("; ".join(evidence["errors"]) if evidence["errors"] else "none"),
        "",
    ])
    atomic_text(REPORT, report)
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
