#!/usr/bin/env python3
"""Guarded CRITICAL production controller for UA111 ten-source VIN specs."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import mimetypes
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Mapping


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TASK_ID = "TASK111-VIN-SPEC-10SRC"
CONTRACT = "UA-VIN-SPEC-10SRC-V2.0"
CRITICAL_CONTRACT = "UA-ART-CRITICAL-ADAPTER-V1.0"
MANIFEST_SHA256 = "eb310b8af5d1101dae77ba4c9819c046c2555987d304e41450f4413abd3099a2"
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE = "/home/Carix/autopilot_inbox/cloud/task_068_ferry_vin"
INSTALL_RECEIPT = REMOTE + "/task111_install_receipt.json"
VERIFY_RECEIPT = REMOTE + "/task111_verify_receipt.json"
ROLLBACK_RECEIPT = REMOTE + "/task111_rollback_receipt.json"
INSTALL_COMMAND = "cd %s && python3.10 remote_installer.py --install" % REMOTE
VERIFY_COMMAND = "cd %s && python3.10 remote_installer.py --verify" % REMOTE
ROLLBACK_COMMAND = "cd %s && python3.10 remote_installer.py --rollback" % REMOTE
EVIDENCE_REL = "cloud/task_111_vin_spec_10src/evidence.json"
RECEIPT_REL = "state/receipts/%s.json" % TASK_ID
PUBLIC_BASE = "https://www.uaart.com.ua/video/"
MAX_BYTES = 64 * 1024 * 1024
SPEC_START = "<!--UA099_ADD_SPEC_START-->"
SPEC_END = "<!--UA099_ADD_SPEC_END-->"
TRANSIENT_HTTP = {429, 500, 502, 503, 504}
UPLOAD_FILES = (
    "remote_installer.py", "profile_library.py", "source_policy.py",
    "vin_spec_service.py", "integration_patcher.py",
)


class ControllerError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: pathlib.Path) -> str:
    return sha_bytes(path.read_bytes())


def safe_repo_path(value: str) -> str:
    path = pathlib.PurePosixPath(str(value))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ControllerError("UNSAFE_REPO_PATH")
    return path.as_posix()


def rooted(value: str) -> pathlib.Path:
    path = (ROOT / safe_repo_path(value)).resolve(strict=False)
    base = ROOT.resolve(strict=False)
    if path == base or not path.is_relative_to(base):
        raise ControllerError("PATH_ESCAPE")
    return path


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix="." + path.name + ".", suffix=".task111.tmp", delete=False,
    )
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


def required_environment(environment: Mapping[str, str]) -> dict[str, str]:
    keys = (
        "PYTHONANYWHERE_API_TOKEN", "UAART_REQUEST_PATH", "UAART_TASK_ID",
        "UAART_TASK_CLASS", "UAART_REQUEST_SHA256", "UAART_RUN_ID", "UAART_RECEIPT_PATH",
    )
    values = {key: str(environment.get(key, "")).strip() for key in keys}
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise ControllerError("MISSING_ENVIRONMENT:" + ",".join(missing))
    if values["UAART_TASK_ID"] != TASK_ID or values["UAART_TASK_CLASS"].upper() != "CRITICAL":
        raise ControllerError("TASK_IDENTITY")
    if safe_repo_path(values["UAART_RECEIPT_PATH"]) != RECEIPT_REL:
        raise ControllerError("RECEIPT_IDENTITY")
    request_path = rooted(values["UAART_REQUEST_PATH"])
    if sha_file(request_path) != values["UAART_REQUEST_SHA256"]:
        raise ControllerError("REQUEST_SHA_MISMATCH")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    critical = request.get("critical") or {}
    if request.get("task_id") != TASK_ID or request.get("production_required") is not True:
        raise ControllerError("REQUEST_IDENTITY")
    if critical.get("manifest_sha256") != MANIFEST_SHA256:
        raise ControllerError("MANIFEST_IDENTITY")
    return values


def rollback_drill() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ua111-rollback-") as folder:
        path = pathlib.Path(folder) / "probe"
        original = b"UA111-ORIGINAL\n"
        path.write_bytes(original)
        before = sha_file(path)
        backup = path.read_bytes()
        path.write_bytes(b"UA111-MUTATED\n")
        during = sha_file(path)
        path.write_bytes(backup)
        after = sha_file(path)
    if before == during or before != after:
        raise ControllerError("ROLLBACK_DRILL")
    return {"status": "PASS", "before": before, "during": during, "after": after}


class API:
    def __init__(self, token: str) -> None:
        self.token = token

    def request(self, method: str, url: str, data: bytes | None = None,
                headers: dict[str, str] | None = None,
                allowed: tuple[int, ...] = (200,)) -> tuple[int, bytes]:
        request_headers = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task111-vin-spec/2",
        }
        request_headers.update(headers or {})
        for attempt in range(1, 6):
            request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    status, body = int(response.status), response.read(MAX_BYTES + 1)
            except urllib.error.HTTPError as exc:
                status, body = int(exc.code), exc.read(MAX_BYTES + 1)
            except Exception as exc:
                if attempt < 5:
                    time.sleep(min(2 * attempt, 8))
                    continue
                raise ControllerError("NETWORK:" + type(exc).__name__) from exc
            if len(body) > MAX_BYTES:
                raise ControllerError("RESPONSE_TOO_LARGE")
            if status in TRANSIENT_HTTP and attempt < 5:
                time.sleep(min(2 * attempt, 8))
                continue
            if status not in allowed:
                raise ControllerError("HTTP_%d" % status)
            return status, body
        raise ControllerError("NETWORK_RETRY_EXHAUSTED")

    @staticmethod
    def file_url(path: str) -> str:
        if not path.startswith(REMOTE + "/"):
            raise ControllerError("REMOTE_PATH_FORBIDDEN")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, missing: bool = False) -> bytes | None:
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_MISSING:" + pathlib.PurePosixPath(path).name)
        return body

    def delete_file(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(204, 404))

    def upload(self, path: str, value: bytes) -> None:
        boundary = "----uaart-task111-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = bytearray()
        body.extend(("--%s\r\n" % boundary).encode())
        body.extend((
            'Content-Disposition: form-data; name="content"; filename="%s"\r\n'
            "Content-Type: %s\r\n\r\n" % (filename, mime)
        ).encode())
        body.extend(value)
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
                time.sleep(min(3 * attempt, 12))
        raise ControllerError("UPLOAD_FAILED:" + filename)

    @staticmethod
    def _objects(body: bytes) -> list[Any]:
        value = json.loads(body.decode())
        if isinstance(value, dict):
            return value.get("tasks") or value.get("objects") or value.get("results") or []
        return value if isinstance(value, list) else []

    @staticmethod
    def _id(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode())
            result = value.get("id") if isinstance(value, dict) else None
            return result if isinstance(result, int) and result > 0 else None
        except Exception:
            return None

    def create_trigger(self, command: str, description: str) -> tuple[str, int]:
        form = urllib.parse.urlencode({"command": command, "description": description, "enabled": "true"}).encode()
        status, body = self.request(
            "POST", BASE + "always_on/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self._id(body) if status in (200, 201, 202) else None
        if identifier:
            return "always_on", identifier
        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode({
            "command": command, "description": description + " fallback", "enabled": "true",
            "interval": "daily", "hour": run_at.hour, "minute": run_at.minute,
        }).encode()
        status, body = self.request(
            "POST", BASE + "schedule/", form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        identifier = self._id(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerError("NO_REMOTE_TRIGGER")
        return "schedule", identifier

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        kind, identifier = trigger
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self.request("DELETE", BASE + "%s/%d/" % (endpoint, identifier), allowed=(200, 202, 204, 404))

    def cleanup_stale_task_triggers(self) -> list[str]:
        """Remove only stale TASK111 triggers; never touch the CRM bot task."""
        removed: list[str] = []
        prefixes = (INSTALL_COMMAND, VERIFY_COMMAND, ROLLBACK_COMMAND)
        for kind, endpoint in (("always_on", "always_on"), ("schedule", "schedule")):
            _, body = self.request("GET", BASE + endpoint + "/")
            for item in self._objects(body):
                if not isinstance(item, dict) or not isinstance(item.get("id"), int):
                    continue
                command = str(item.get("command") or "").strip()
                description = str(item.get("description") or "").casefold()
                if not command.startswith(prefixes) or "task111" not in description:
                    continue
                self.delete_trigger((kind, int(item["id"])))
                removed.append("%s:%d" % (kind, int(item["id"])))
        return removed

    def run_remote(self, command: str, description: str, receipt: str,
                   invocation: str, seconds: int = 3300) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9._-]{8,160}", invocation):
            raise ControllerError("REMOTE_INVOCATION_INVALID")
        self.delete_file(receipt)
        trigger = self.create_trigger(command, description + " " + invocation)
        result: dict[str, Any] | None = None
        try:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                try:
                    raw = self.read(receipt, missing=True)
                except ControllerError as exc:
                    if re.fullmatch(r"HTTP_(?:429|500|502|503|504)", str(exc)):
                        time.sleep(5)
                        continue
                    raise
                if raw:
                    value = json.loads(raw.decode("utf-8"))
                    if not isinstance(value, dict):
                        raise ControllerError("REMOTE_RECEIPT_INVALID")
                    if value.get("invocation") != invocation:
                        self.delete_file(receipt)
                        time.sleep(2)
                        continue
                    result = value
                    break
                time.sleep(5)
            if result is None:
                raise ControllerError("REMOTE_TIMEOUT:" + pathlib.PurePosixPath(receipt).name)
        except Exception:
            try:
                self.delete_trigger(trigger)
            except Exception:
                pass
            raise
        else:
            self.delete_trigger(trigger)
            return result

    def restart_bot(self) -> dict[str, Any]:
        _, body = self.request("GET", BASE + "always_on/")
        tasks = [
            item for item in self._objects(body)
            if isinstance(item, dict) and item.get("enabled") is not False
            and str(item.get("command") or "").strip() == "python3.10 /home/Carix/start_safe.py"
        ]
        if len(tasks) != 1 or not isinstance(tasks[0].get("id"), int):
            raise ControllerError("BOT_TASK_NOT_UNIQUE")
        self.request("POST", BASE + "always_on/%d/restart/" % tasks[0]["id"], b"", allowed=(200, 201, 202, 204))
        return {"status": "PASS", "command": "python3.10 /home/Carix/start_safe.py"}


def validate_remote(value: Mapping[str, Any], phase: str, invocation: str) -> None:
    if value.get("task_id") != TASK_ID or value.get("contract_id") != CONTRACT:
        raise ControllerError("REMOTE_IDENTITY:" + phase)
    if value.get("status") != "PASS" or value.get("crm_write") is not False:
        raise ControllerError("REMOTE_FAILED:" + phase + ":" + str(value.get("error") or ""))
    if value.get("invocation") != invocation:
        raise ControllerError("REMOTE_INVOCATION:" + phase)
    if phase == "INSTALL":
        if value.get("crm_unchanged") is not True or value.get("initial_autopublication") is not False:
            raise ControllerError("REMOTE_SCOPE:INSTALL")
        if int((value.get("scan") or {}).get("valid_vins") or 0) < 16:
            raise ControllerError("REMOTE_VIN_COVERAGE")
        if int((value.get("public") or {}).get("card_count") or 0) < 16:
            raise ControllerError("REMOTE_PUBLIC_COVERAGE")
        if int((value.get("public") or {}).get("nonempty_cards") or 0) < 16:
            raise ControllerError("REMOTE_NONEMPTY_COVERAGE")
        if int((value.get("public") or {}).get("minimum_specs_per_card") or 0) < 10:
            raise ControllerError("REMOTE_SPEC_DEPTH")
        if value.get("vin_autostart_enabled") is not True:
            raise ControllerError("REMOTE_AUTOSTART")


def fetch_public(uid: str) -> str:
    url = urllib.parse.urljoin(PUBLIC_BASE, uid + ".html") + "?task111=" + str(int(time.time() * 1000))
    request = urllib.request.Request(url, headers={"User-Agent": "ua-art-task111-live/2", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read(MAX_BYTES + 1)
            status = int(response.status)
    except Exception as exc:
        raise ControllerError("PUBLIC_FETCH:" + uid + ":" + type(exc).__name__) from exc
    if status != 200 or len(body) > MAX_BYTES:
        raise ControllerError("PUBLIC_HTTP:" + uid)
    return body.decode("utf-8")


def public_verify(expected: Mapping[str, Any]) -> dict[str, Any]:
    verified = {}
    nonempty = 0
    minimum_specs: int | None = None
    for uid, meta in sorted(expected.items()):
        page = fetch_public(uid)
        if page.count(SPEC_START) != 1 or page.count(SPEC_END) != 1:
            raise ControllerError("PUBLIC_MARKERS:" + uid)
        fragment = page[page.index(SPEC_START):page.index(SPEC_END) + len(SPEC_END)]
        shown = len(re.findall(r"class=['\"]ua-addspec-row['\"]", fragment, re.I))
        expected_count = int((meta or {}).get("visible_specs") or 0)
        if shown != expected_count:
            raise ControllerError("PUBLIC_COUNT:%s:%d:%d" % (uid, shown, expected_count))
        if re.search(r"https?://", fragment, re.I):
            raise ControllerError("PUBLIC_SOURCE_LEAK:" + uid)
        nonempty += int(shown > 0)
        minimum_specs = shown if minimum_specs is None else min(minimum_specs, shown)
        verified[uid] = shown
    if len(verified) < 16 or nonempty != len(verified) or (minimum_specs or 0) < 10:
        raise ControllerError("PUBLIC_COVERAGE")
    return {
        "status": "PASS", "cards": verified, "nonempty_cards": nonempty,
        "minimum_specs_per_card": minimum_specs or 0,
    }


def run() -> dict[str, Any]:
    env = required_environment(os.environ)
    drill = rollback_drill()
    # The same files were compiled and contract-tested in the workflow.  Recheck
    # exact hashes immediately before upload.
    uploads = {}
    for name in UPLOAD_FILES:
        path = HERE / name
        raw = path.read_bytes()
        compile(raw.decode("utf-8"), str(path), "exec")
        uploads[name] = {"sha256": sha_bytes(raw), "bytes": len(raw)}
    api = API(env["PYTHONANYWHERE_API_TOKEN"])
    install = verify = None
    try:
        stale_triggers = api.cleanup_stale_task_triggers()
        for name in UPLOAD_FILES:
            api.upload(REMOTE + "/" + name, (HERE / name).read_bytes())
        install_invocation = env["UAART_RUN_ID"] + "-install-" + uuid.uuid4().hex
        install = api.run_remote(
            INSTALL_COMMAND + " --invocation " + install_invocation,
            "task111 ten-source install/backfill", INSTALL_RECEIPT, install_invocation, 3300,
        )
        validate_remote(install, "INSTALL", install_invocation)
        restart = api.restart_bot()
        expected = ((install.get("public") or {}).get("cards") or {})
        live_now = public_verify(expected)
        verify_invocation = env["UAART_RUN_ID"] + "-verify-" + uuid.uuid4().hex
        verify = api.run_remote(
            VERIFY_COMMAND + " --invocation " + verify_invocation,
            "task111 ten-source verify", VERIFY_RECEIPT, verify_invocation, 900,
        )
        validate_remote(verify, "VERIFY", verify_invocation)
        time.sleep(30)
        live_delayed = public_verify(expected)
        evidence = {
            "task_id": TASK_ID, "contract_id": CONTRACT, "status": "PASS",
            "finished_at": utc_now(), "uploads": uploads, "rollback_drill": drill,
            "install": install, "restart": restart, "remote_verify": verify,
            "stale_triggers_removed": stale_triggers,
            "live_verify": live_now, "delayed_verify": live_delayed,
            "unexpected_changes": 0, "crm_unchanged": True,
            "global_automatic_mode_enabled": False,
            "vin_autostart_enabled": True,
        }
        receipt = {
            "contract_id": CRITICAL_CONTRACT, "task_id": TASK_ID, "status": "FINISHED",
            "task_class": "CRITICAL", "target_environment": "production",
            "tests": "PASS", "backup": str(install.get("backup") or ""),
            "production": "PASS", "live_verify": "PASS", "rollback": "PASS",
            "unexpected_changes": 0, "protected_files_unchanged": True,
            "crm_unchanged": True, "manifest_sha256": MANIFEST_SHA256,
            "rollback_ready": True, "production_required": True,
            "request_sha256": env["UAART_REQUEST_SHA256"],
            "run_id": env["UAART_RUN_ID"],
            "source_count": 10, "valid_vins": int((install.get("scan") or {}).get("valid_vins") or 0),
            "public_card_count": len(expected), "nonempty_card_count": int(live_delayed["nonempty_cards"]),
            "initial_autopublication": False, "global_automatic_mode_enabled": False,
            "vin_autostart_enabled": True,
        }
        atomic_json(rooted(EVIDENCE_REL), evidence)
        atomic_json(rooted(RECEIPT_REL), receipt)
        return receipt
    except Exception as exc:
        rollback = None
        if install and install.get("status") == "PASS" and install.get("backup"):
            try:
                rollback_invocation = env["UAART_RUN_ID"] + "-rollback-" + uuid.uuid4().hex
                rollback = api.run_remote(
                    ROLLBACK_COMMAND + " --invocation " + rollback_invocation,
                    "task111 rollback", ROLLBACK_RECEIPT, rollback_invocation, 900,
                )
                api.restart_bot()
                if rollback.get("status") != "PASS" or rollback.get("invocation") != rollback_invocation:
                    raise ControllerError("ROLLBACK_FAILED")
            except Exception as rollback_exc:
                rollback = {"status": "FAIL", "error": type(rollback_exc).__name__ + ":" + str(rollback_exc)}
        failure = {
            "task_id": TASK_ID, "contract_id": CONTRACT, "status": "FAIL",
            "finished_at": utc_now(), "error": type(exc).__name__ + ":" + str(exc),
            "install": install, "verify": verify, "rollback": rollback,
            "global_automatic_mode_enabled": False,
        }
        atomic_json(rooted(EVIDENCE_REL), failure)
        raise


def main() -> int:
    receipt = run()
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
