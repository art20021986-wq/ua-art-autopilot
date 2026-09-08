#!/usr/bin/env python3
"""Owner-approved, one-shot controller for exactly one CRM button: «В Корее»."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import mimetypes
import os
import pathlib
import re
import shlex
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Mapping

import patcher


TASK_ID = "TASK121-KOREA-BUTTON"
CONTRACT = "UA-ART-CRM-KOREA-BUTTON-001-V1.0"
HERE = pathlib.Path(__file__).resolve().parent


def find_root() -> pathlib.Path:
    for candidate in (HERE, *HERE.parents):
        if (candidate / "CLAUDE.md").is_file() and (candidate / "state").is_dir():
            return candidate
    return HERE.parents[1]


ROOT = find_root()
REQUEST_REL = "tasks/requests/TASK121-KOREA-BUTTON.json"
APPROVAL_REL = "tasks/approvals/TASK121-KOREA-BUTTON.json"
HALT_REL = "state/AUTOPILOT_HALT.json"
GATE_A_REL = "cloud/task121_korea_button_manual/gate_a.json"
EVIDENCE_REL = "cloud/task121_korea_button_manual/evidence.json"
RECEIPT_REL = "state/receipts/TASK121-KOREA-BUTTON.json"
REMOTE_DIR = "/home/Carix/autopilot_inbox/cloud/task_068_ferry_vin"
REMOTE_INSTALLER = REMOTE_DIR + "/task121_korea_installer.py"
REMOTE_PATCHER = REMOTE_DIR + "/task121_korea_patcher.py"
REMOTE_RECEIPT = REMOTE_DIR + "/task121_korea_receipt.json"
REMOTE_STATE = REMOTE_DIR + "/task121_korea_state.json"
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
TARGETS = {
    "cars_ui.py": "/home/Carix/cars_ui.py",
    "konteyner.py": "/home/Carix/konteyner.py",
    "cars_schema.py": "/home/Carix/cars_schema.py",
}
EXPECTED_BEFORE = {
    "cars_ui.py": "2b1ef0bcfa700b7c87ccfb164b69b8ca173d460481936225e41344096c92062f",
    "konteyner.py": "72c03a1b8ab14279b2a2adbc681e112594d88c766d2aae7cc40e08b8aa004230",
    "cars_schema.py": "87f20a57248c3483ccb09955431cd840bb57bfdef6d2705e5fc048c201e14496",
}
MAX_BYTES = 8 * 1024 * 1024


class ControllerError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_hash(path: pathlib.Path) -> str:
    return sha(path.read_bytes())


def hash_value(value: str, code: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value or ""):
        raise ControllerError(code)
    return value


def nonce_value(value: str) -> str:
    if not re.fullmatch(r"task121-[0-9]{6,20}-[0-9a-f]{12}", value or ""):
        raise ControllerError("RUN_NONCE")
    return value


def atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load_json(path: pathlib.Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ControllerError(code) from exc
    if not isinstance(value, dict):
        raise ControllerError(code)
    return value


def required(environment: Mapping[str, str]) -> dict[str, str]:
    names = (
        "PYTHONANYWHERE_API_TOKEN",
        "UAART_REQUEST_SHA256",
        "UAART_APPROVAL_SHA256",
        "UAART_HALT_SHA256",
        "UAART_RUN_NONCE",
        "GITHUB_RUN_ID",
        "GITHUB_SHA",
    )
    values = {name: str(environment.get(name, "")).strip() for name in names}
    missing = [name for name in names if not values[name]]
    if missing:
        raise ControllerError("MISSING_ENV:" + ",".join(missing))
    nonce_value(values["UAART_RUN_NONCE"])
    hash_value(values["UAART_REQUEST_SHA256"], "REQUEST_SHA")
    hash_value(values["UAART_APPROVAL_SHA256"], "APPROVAL_SHA")
    hash_value(values["UAART_HALT_SHA256"], "HALT_SHA")
    if not re.fullmatch(r"[0-9a-f]{40}", values["GITHUB_SHA"]):
        raise ControllerError("GITHUB_SHA")

    request_path = ROOT / REQUEST_REL
    approval_path = ROOT / APPROVAL_REL
    halt_path = ROOT / HALT_REL
    if read_hash(request_path) != values["UAART_REQUEST_SHA256"]:
        raise ControllerError("REQUEST_IDENTITY")
    if read_hash(approval_path) != values["UAART_APPROVAL_SHA256"]:
        raise ControllerError("APPROVAL_IDENTITY")
    if read_hash(halt_path) != values["UAART_HALT_SHA256"]:
        raise ControllerError("GLOBAL_HALT_DRIFT")

    request = load_json(request_path, "REQUEST_PARSE")
    approval = load_json(approval_path, "APPROVAL_PARSE")
    halt = load_json(halt_path, "HALT_PARSE")
    if (
        request.get("task_id") != TASK_ID
        or request.get("task_class") != "CRITICAL"
        or request.get("production_required") is not True
        or request.get("button")
        != {"code": "kr_bought", "label": "В Корее", "count": 1}
        or request.get("keep_hidden")
        != ["sea_loaded", "sea_transit", "ua_handed"]
        or request.get("global_halt_policy") != "PRESERVE_UNCHANGED"
    ):
        raise ControllerError("REQUEST_SCOPE")
    if (
        approval.get("task_id") != TASK_ID
        or approval.get("approval_status") != "APPROVED"
        or approval.get("production_authorized") is not True
        or approval.get("button")
        != {"code": "kr_bought", "label": "В Корее", "count": 1}
        or approval.get("keep_hidden")
        != ["sea_loaded", "sea_transit", "ua_handed"]
        or approval.get("global_halt_must_remain") is not True
    ):
        raise ControllerError("OWNER_APPROVAL_SCOPE")
    if halt.get("status") != "EMERGENCY_HALT":
        raise ControllerError("GLOBAL_HALT_MISSING")
    return values


class API:
    def __init__(self, token: str, run_nonce: str) -> None:
        self.token = token
        self.run_nonce = run_nonce

    def request(
        self,
        method: str,
        url: str,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        allowed: tuple[int, ...] = (200,),
    ) -> tuple[int, bytes]:
        actual = {
            "Authorization": "Token " + self.token,
            "User-Agent": "ua-art-task121/1",
        }
        actual.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=actual, method=method)
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                status = int(response.status)
                body = response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            body = exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES or status not in allowed:
            raise ControllerError("HTTP_%d" % status)
        return status, body

    @staticmethod
    def file_url(path: str) -> str:
        allowed_exact = set(TARGETS.values()) | {
            REMOTE_INSTALLER,
            REMOTE_PATCHER,
            REMOTE_RECEIPT,
            REMOTE_STATE,
        }
        if path not in allowed_exact:
            raise ControllerError("REMOTE_FILE_SCOPE")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, missing: bool = False) -> bytes | None:
        status, body = self.request(
            "GET", self.file_url(path), allowed=(200, 404)
        )
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_MISSING:" + pathlib.PurePosixPath(path).name)
        return body

    def delete_file(self, path: str) -> None:
        self.request(
            "DELETE", self.file_url(path), allowed=(200, 202, 204, 404)
        )
        for _ in range(6):
            if self.read(path, missing=True) is None:
                return
            time.sleep(1)
        raise ControllerError("REMOTE_DELETE_READBACK")

    def upload(self, path: str, value: bytes) -> None:
        if path not in (REMOTE_INSTALLER, REMOTE_PATCHER):
            raise ControllerError("REMOTE_UPLOAD_SCOPE")
        boundary = "----uaart-task121-" + uuid.uuid4().hex
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
        body.extend(value)
        body.extend(("\r\n--%s--\r\n" % boundary).encode())
        self.request(
            "POST",
            self.file_url(path),
            bytes(body),
            {"Content-Type": "multipart/form-data; boundary=" + boundary},
            allowed=(200, 201),
        )
        if self.read(path) != value:
            raise ControllerError("UPLOAD_READBACK")

    @staticmethod
    def object_id(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None
        identifier = value.get("id") if isinstance(value, dict) else None
        if isinstance(identifier, int):
            return identifier
        if isinstance(identifier, str) and identifier.isdigit():
            return int(identifier)
        return None

    @staticmethod
    def objects(body: bytes) -> list[dict[str, Any]]:
        value = json.loads(body.decode("utf-8"))
        raw = (
            value.get("results")
            or value.get("objects")
            or value.get("tasks")
            or []
            if isinstance(value, dict)
            else value
        )
        if not isinstance(raw, list):
            raise ControllerError("TASK_LIST_INVALID")
        return [item for item in raw if isinstance(item, dict)]

    def create_trigger(self, command: str) -> tuple[str, int]:
        description = TASK_ID + " " + self.run_nonce
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
        identifier = self.object_id(body) if status in (200, 201, 202) else None
        if identifier is not None:
            return "always_on", identifier

        at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode(
            {
                "command": command,
                "description": description + " fallback",
                "enabled": "true",
                "interval": "daily",
                "hour": at.hour,
                "minute": at.minute,
            }
        ).encode()
        _, body = self.request(
            "POST",
            BASE + "schedule/",
            form,
            {"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202),
        )
        identifier = self.object_id(body)
        if identifier is None:
            raise ControllerError("NO_TRIGGER")
        return "schedule", identifier

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        kind, identifier = trigger
        self.request(
            "DELETE",
            BASE + "%s/%d/" % (kind, identifier),
            allowed=(200, 202, 204, 404),
        )

    def run_remote(
        self,
        mode: str,
        *,
        backup_sha: str = "",
        patcher_sha: str = "",
        after_hashes: Mapping[str, str] | None = None,
        timeout: int = 900,
    ) -> dict[str, Any]:
        if mode not in ("backup", "install", "verify", "rollback"):
            raise ControllerError("REMOTE_MODE")
        self.delete_file(REMOTE_RECEIPT)
        parts = [
            "cd",
            REMOTE_DIR,
            "&&",
            "python3.10",
            pathlib.PurePosixPath(REMOTE_INSTALLER).name,
            "--mode",
            mode,
            "--run-nonce",
            self.run_nonce,
        ]
        if backup_sha:
            parts.extend(["--backup-manifest-sha256", hash_value(backup_sha, "BACKUP_SHA")])
        if patcher_sha:
            parts.extend(["--patcher-sha256", hash_value(patcher_sha, "PATCHER_SHA")])
        if after_hashes:
            for name, option in (
                ("cars_ui.py", "--expected-after-cars-ui"),
                ("konteyner.py", "--expected-after-konteyner"),
                ("cars_schema.py", "--expected-after-cars-schema"),
            ):
                parts.extend([option, hash_value(str(after_hashes[name]), "AFTER_SHA")])
        command = " ".join(
            token if token == "&&" else shlex.quote(token) for token in parts
        )
        # PythonAnywhere always-on tasks restart short-lived commands.  Keep the
        # first completed process alive long enough for the controller to read
        # its receipt and delete the trigger, so a successful mode cannot run
        # for a second time against its own postimage.
        command += "; task121_rc=$?; sleep 180; exit $task121_rc"
        trigger = self.create_trigger(command)
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                raw = self.read(REMOTE_RECEIPT, missing=True)
                if raw:
                    try:
                        value = json.loads(raw.decode("utf-8"))
                    except Exception as exc:
                        raise ControllerError("REMOTE_RECEIPT_PARSE") from exc
                    if (
                        not isinstance(value, dict)
                        or value.get("task_id") != TASK_ID
                        or value.get("run_nonce") != self.run_nonce
                        or value.get("mode") != mode.upper()
                    ):
                        raise ControllerError("REMOTE_RECEIPT_IDENTITY")
                    return value
                time.sleep(5)
            raise ControllerError("REMOTE_TIMEOUT:" + mode)
        finally:
            self.delete_trigger(trigger)

    def bot_task(self) -> dict[str, Any]:
        _, body = self.request("GET", BASE + "always_on/")
        matches = [
            item
            for item in self.objects(body)
            if item.get("enabled") is not False
            and str(item.get("command") or "").strip()
            == "python3.10 /home/Carix/start_safe.py"
        ]
        if len(matches) != 1:
            raise ControllerError("BOT_TASK_NOT_UNIQUE")
        return matches[0]

    def restart(self) -> dict[str, Any]:
        before = self.bot_task()
        identifier = int(before["id"])
        self.request(
            "POST",
            BASE + "always_on/%d/restart/" % identifier,
            b"",
            allowed=(200, 201, 202, 204),
        )
        for _ in range(8):
            after = self.bot_task()
            if int(after["id"]) == identifier and after.get("enabled") is not False:
                return {
                    "status": "PASS",
                    "task_id": identifier,
                    "command": "python3.10 /home/Carix/start_safe.py",
                    "instances": 1,
                    "enabled": True,
                }
            time.sleep(2)
        raise ControllerError("BOT_TASK_POST_RESTART")


def fresh_sources(api: API) -> dict[str, bytes]:
    values: dict[str, bytes] = {}
    for name, path in TARGETS.items():
        payload = api.read(path)
        if not isinstance(payload, bytes) or not payload or len(payload) > MAX_BYTES:
            raise ControllerError("SOURCE_READ:" + name)
        values[name] = payload
    return values


def assert_preimages(values: Mapping[str, bytes]) -> None:
    for name, expected in EXPECTED_BEFORE.items():
        if sha(values[name]) != expected:
            raise ControllerError("LIVE_PREIMAGE_MISMATCH:" + name)


def candidates(values: Mapping[str, bytes]) -> tuple[dict[str, bytes], dict[str, Any]]:
    result = {
        "cars_ui.py": patcher.patch_cars_ui(values["cars_ui.py"].decode("utf-8")).encode("utf-8"),
        "konteyner.py": patcher.patch_konteyner(values["konteyner.py"].decode("utf-8")).encode("utf-8"),
        "cars_schema.py": patcher.patch_schema(values["cars_schema.py"].decode("utf-8")).encode("utf-8"),
    }
    for name in result:
        if result[name] == values[name]:
            raise ControllerError("NO_CHANGE:" + name)
    proof = patcher.verify(
        result["cars_ui.py"].decode("utf-8"),
        result["konteyner.py"].decode("utf-8"),
        result["cars_schema.py"].decode("utf-8"),
    )
    return result, proof


def validate_remote(value: Mapping[str, Any], mode: str, run_nonce: str) -> None:
    if (
        value.get("task_id") != TASK_ID
        or value.get("contract_id") != CONTRACT
        or value.get("run_nonce") != run_nonce
        or value.get("status") != "PASS"
        or value.get("mode") != mode.upper()
        or value.get("unexpected_changes") != 0
    ):
        raise ControllerError("REMOTE_%s_FAIL:%s" % (mode.upper(), value.get("error")))


def probe(values: Mapping[str, str]) -> dict[str, Any]:
    api = API(values["PYTHONANYWHERE_API_TOKEN"], values["UAART_RUN_NONCE"])
    before = fresh_sources(api)
    assert_preimages(before)
    after, proof = candidates(before)
    files = {
        name: {
            "production_path": TARGETS[name],
            "before_sha256": sha(before[name]),
            "after_sha256": sha(after[name]),
            "before_bytes": len(before[name]),
            "after_bytes": len(after[name]),
        }
        for name in TARGETS
    }
    gate = {
        "schema_version": "UA-ART-TASK121-GATE-A-1",
        "task_id": TASK_ID,
        "contract_id": CONTRACT,
        "run_nonce": values["UAART_RUN_NONCE"],
        "status": "PASS",
        "mode": "GET_ONLY",
        "production_touched": False,
        "request_sha256": values["UAART_REQUEST_SHA256"],
        "approval_sha256": values["UAART_APPROVAL_SHA256"],
        "global_halt_sha256": values["UAART_HALT_SHA256"],
        "source_commit": values["GITHUB_SHA"],
        "patcher_sha256": read_hash(HERE / "patcher.py"),
        "remote_installer_sha256": read_hash(HERE / "remote_installer.py"),
        "files": files,
        "proof": proof,
        "checked_at": now(),
    }
    atomic_json(ROOT / GATE_A_REL, gate)
    return gate


def load_gate(values: Mapping[str, str]) -> dict[str, Any]:
    gate = load_json(ROOT / GATE_A_REL, "GATE_A_PARSE")
    if (
        gate.get("task_id") != TASK_ID
        or gate.get("contract_id") != CONTRACT
        or gate.get("run_nonce") != values["UAART_RUN_NONCE"]
        or gate.get("status") != "PASS"
        or gate.get("mode") != "GET_ONLY"
        or gate.get("production_touched") is not False
        or gate.get("request_sha256") != values["UAART_REQUEST_SHA256"]
        or gate.get("approval_sha256") != values["UAART_APPROVAL_SHA256"]
        or gate.get("global_halt_sha256") != values["UAART_HALT_SHA256"]
        or gate.get("source_commit") != values["GITHUB_SHA"]
        or gate.get("patcher_sha256") != read_hash(HERE / "patcher.py")
        or gate.get("remote_installer_sha256") != read_hash(HERE / "remote_installer.py")
    ):
        raise ControllerError("GATE_A_IDENTITY")
    proof = gate.get("proof") or {}
    if (
        proof.get("button_code") != "kr_bought"
        or proof.get("button_label") != "В Корее"
        or proof.get("button_count_added") != 1
        or proof.get("hidden_codes") != ["sea_loaded", "sea_transit", "ua_handed"]
        or proof.get("primary_menu") != "PASS"
        or proof.get("fallback_menu") != "PASS"
        or proof.get("callback") != "ENABLED"
    ):
        raise ControllerError("GATE_A_PROOF")
    files = gate.get("files")
    if not isinstance(files, dict) or set(files) != set(TARGETS):
        raise ControllerError("GATE_A_FILES")
    for name in TARGETS:
        meta = files.get(name) or {}
        if meta.get("before_sha256") != EXPECTED_BEFORE[name]:
            raise ControllerError("GATE_A_PREIMAGE:" + name)
        hash_value(str(meta.get("after_sha256") or ""), "GATE_A_AFTER:" + name)
    return gate


def upload_runtime(api: API) -> tuple[str, str]:
    installer = (HERE / "remote_installer.py").read_bytes()
    patcher_raw = (HERE / "patcher.py").read_bytes()
    compile(installer.decode("utf-8"), "remote_installer.py", "exec")
    compile(patcher_raw.decode("utf-8"), "patcher.py", "exec")
    api.upload(REMOTE_INSTALLER, installer)
    api.upload(REMOTE_PATCHER, patcher_raw)
    return sha(installer), sha(patcher_raw)


def recover_current(api: API, run_nonce: str) -> dict[str, Any]:
    raw = api.read(REMOTE_STATE, missing=True)
    if raw is None:
        return {"status": "NOT_REQUIRED", "reason": "NO_TASK121_STATE"}
    try:
        state = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ControllerError("RECOVERY_STATE_PARSE") from exc
    if state.get("task_id") != TASK_ID or state.get("run_nonce") != run_nonce:
        return {"status": "NOT_REQUIRED", "reason": "DIFFERENT_RUN_STATE"}
    backup_sha = hash_value(
        str(state.get("backup_manifest_sha256") or ""), "RECOVERY_BACKUP_SHA"
    )
    status = state.get("status")
    if status == "ROLLED_BACK":
        restored = fresh_sources(api)
        assert_preimages(restored)
        return {"status": "PASS", "mode": "ALREADY_ROLLED_BACK"}
    if status not in ("BACKED_UP", "INSTALLED", "VERIFIED"):
        raise ControllerError("RECOVERY_STATE_STATUS")
    upload_runtime(api)
    result = api.run_remote("rollback", backup_sha=backup_sha)
    validate_remote(result, "rollback", run_nonce)
    restart = api.restart()
    restored = fresh_sources(api)
    assert_preimages(restored)
    return {"status": "PASS", "mode": "ROLLBACK", "remote": result, "restart": restart}


def apply(values: Mapping[str, str]) -> dict[str, Any]:
    gate = load_gate(values)
    api = API(values["PYTHONANYWHERE_API_TOKEN"], values["UAART_RUN_NONCE"])
    evidence: dict[str, Any] = {
        "schema_version": "UA-ART-TASK121-EVIDENCE-1",
        "task_id": TASK_ID,
        "contract_id": CONTRACT,
        "run_nonce": values["UAART_RUN_NONCE"],
        "status": "FAIL",
        "started_at": now(),
        "source_commit": values["GITHUB_SHA"],
        "global_halt_before_sha256": read_hash(ROOT / HALT_REL),
        "gate_a": gate,
        "errors": [],
    }
    backup_sha = ""
    try:
        live_before = fresh_sources(api)
        assert_preimages(live_before)
        live_candidates, proof = candidates(live_before)
        after_hashes = {name: sha(value) for name, value in live_candidates.items()}
        gate_after = {
            name: str(gate["files"][name]["after_sha256"]) for name in TARGETS
        }
        if after_hashes != gate_after:
            raise ControllerError("LIVE_DRIFT_AFTER_GATE_A")

        installer_sha, patcher_sha = upload_runtime(api)
        if installer_sha != gate["remote_installer_sha256"]:
            raise ControllerError("INSTALLER_GATE_BINDING")
        if patcher_sha != gate["patcher_sha256"]:
            raise ControllerError("PATCHER_GATE_BINDING")

        backed_up = api.run_remote("backup")
        validate_remote(backed_up, "backup", values["UAART_RUN_NONCE"])
        backup_sha = hash_value(
            str(backed_up.get("backup_manifest_sha256") or ""), "BACKUP_SHA"
        )
        evidence["backup"] = backed_up

        installed = api.run_remote(
            "install",
            backup_sha=backup_sha,
            patcher_sha=patcher_sha,
            after_hashes=after_hashes,
        )
        validate_remote(installed, "install", values["UAART_RUN_NONCE"])
        if installed.get("proof") != proof:
            raise ControllerError("INSTALL_PROOF_DRIFT")
        evidence["install"] = installed
        evidence["restart"] = api.restart()
        time.sleep(12)

        verified = api.run_remote(
            "verify",
            backup_sha=backup_sha,
            patcher_sha=patcher_sha,
            after_hashes=after_hashes,
        )
        validate_remote(verified, "verify", values["UAART_RUN_NONCE"])
        if verified.get("proof") != proof:
            raise ControllerError("VERIFY_PROOF_DRIFT")
        evidence["verify"] = verified

        live_after = fresh_sources(api)
        actual_after = {name: sha(value) for name, value in live_after.items()}
        if actual_after != after_hashes:
            raise ControllerError("FINAL_LIVE_HASH_DRIFT")
        final_proof = patcher.verify(
            live_after["cars_ui.py"].decode("utf-8"),
            live_after["konteyner.py"].decode("utf-8"),
            live_after["cars_schema.py"].decode("utf-8"),
        )
        if final_proof != proof:
            raise ControllerError("FINAL_LIVE_PROOF_DRIFT")
        if read_hash(ROOT / HALT_REL) != values["UAART_HALT_SHA256"]:
            raise ControllerError("GLOBAL_HALT_CHANGED")

        receipt = {
            "schema_version": "UA-ART-TASK121-RECEIPT-1",
            "task_id": TASK_ID,
            "contract_id": CONTRACT,
            "run_nonce": values["UAART_RUN_NONCE"],
            "run_id": values["GITHUB_RUN_ID"],
            "source_commit": values["GITHUB_SHA"],
            "status": "FINISHED",
            "task_class": "CRITICAL",
            "target_environment": "production",
            "production": "PASS",
            "tests": "PASS",
            "live_verify": "PASS",
            "backup_manifest_sha256": backup_sha,
            "rollback_ready": True,
            "changed_files": list(TARGETS.values()),
            "before_sha256": {name: sha(live_before[name]) for name in TARGETS},
            "after_sha256": actual_after,
            "button": {"code": "kr_bought", "label": "В Корее", "count": 1},
            "button_working": True,
            "hidden_codes": ["sea_loaded", "sea_transit", "ua_handed"],
            "other_removed_buttons_restored": False,
            "primary_menu": "PASS",
            "fallback_menu": "PASS",
            "callback": "ENABLED",
            "restart": evidence["restart"],
            "cards_unchanged": True,
            "crm_vehicle_data_unchanged": True,
            "media_unchanged": True,
            "website_unchanged": True,
            "global_halt_preserved": True,
            "global_halt_sha256": values["UAART_HALT_SHA256"],
            "unexpected_changes": 0,
            "finished_at": now(),
        }
        atomic_json(ROOT / RECEIPT_REL, receipt)
        evidence.update(
            {
                "status": "PASS",
                "receipt": receipt,
                "global_halt_after_sha256": read_hash(ROOT / HALT_REL),
                "finished_at": now(),
            }
        )
        atomic_json(ROOT / EVIDENCE_REL, evidence)
        return receipt
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        try:
            evidence["rollback"] = recover_current(api, values["UAART_RUN_NONCE"])
        except Exception as rollback_exc:
            evidence["errors"].append(
                "ROLLBACK_" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
            )
        evidence["global_halt_after_sha256"] = read_hash(ROOT / HALT_REL)
        evidence["finished_at"] = now()
        atomic_json(ROOT / EVIDENCE_REL, evidence)
        failure = {
            "schema_version": "UA-ART-TASK121-RECEIPT-1",
            "task_id": TASK_ID,
            "run_nonce": values["UAART_RUN_NONCE"],
            "run_id": values["GITHUB_RUN_ID"],
            "status": "FAILED",
            "production": "ROLLED_BACK"
            if (evidence.get("rollback") or {}).get("status") == "PASS"
            else "UNKNOWN_FAIL_CLOSED",
            "errors": evidence["errors"],
            "global_halt_preserved": evidence["global_halt_after_sha256"]
            == values["UAART_HALT_SHA256"],
            "finished_at": now(),
        }
        atomic_json(ROOT / RECEIPT_REL, failure)
        raise


def emergency_rollback(values: Mapping[str, str]) -> dict[str, Any]:
    api = API(values["PYTHONANYWHERE_API_TOKEN"], values["UAART_RUN_NONCE"])
    result = recover_current(api, values["UAART_RUN_NONCE"])
    evidence = {
        "schema_version": "UA-ART-TASK121-EMERGENCY-ROLLBACK-1",
        "task_id": TASK_ID,
        "run_nonce": values["UAART_RUN_NONCE"],
        "result": result,
        "global_halt_preserved": read_hash(ROOT / HALT_REL)
        == values["UAART_HALT_SHA256"],
        "finished_at": now(),
    }
    atomic_json(ROOT / "cloud/task121_korea_button_manual/emergency_rollback.json", evidence)
    return evidence


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("probe", "apply", "rollback"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        values = required(os.environ)
        if args.mode == "probe":
            result = probe(values)
        elif args.mode == "apply":
            result = apply(values)
        else:
            result = emergency_rollback(values)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "task_id": TASK_ID,
                    "status": "FAIL",
                    "mode": args.mode.upper(),
                    "error": type(exc).__name__ + ":" + str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
