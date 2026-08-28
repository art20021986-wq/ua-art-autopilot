#!/usr/bin/env python3
"""GitHub-side controller for the explicitly approved TASK 063 Gate B."""
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

from gate_a_controller import GateAController
from gate_b_remote import (
    ALLOWED_PATHS,
    FIXED_BACKUP_PARENT,
    FIXED_CANDIDATE_ROOT,
    FIXED_SOURCE_ROOT,
    MODE,
    OWNER_APPROVAL,
    PYTHON_PATHS,
    TASK,
    VIDEO_PATHS,
)

ALLOWED_USERNAME = "Carix"
ALLOWED_HOSTS = ("www.pythonanywhere.com", "eu.pythonanywhere.com")
REMOTE_ROOT = "/home/Carix/autopilot_inbox/cloud/task_047_ferry_discovery"
REMOTE_SCRIPT = REMOTE_ROOT + "/gate_b_remote.py"
REMOTE_MANIFEST = REMOTE_ROOT + "/ferry_gate_b_manifest.json"
REMOTE_OUTPUT = REMOTE_ROOT + "/ferry_gate_b_receipt.json"
HERE = pathlib.Path(__file__).resolve().parent
LOCAL_SCRIPT = HERE / "gate_b_remote.py"
GATE_A_EVIDENCE = HERE / "evidence" / "ferry_gate_a.json"
GATE_B_EVIDENCE = HERE / "evidence" / "ferry_gate_b.json"
GATE_B_REPORT = HERE / "FERRY_GATE_B_REPORT.md"

# This one-shot production approval is tied to the exact Gate A artifact that
# the owner reviewed, not merely to any future structurally valid Gate A run.
APPROVED_GATE_A_EVIDENCE_SHA256 = (
    "1182ecdac7f510983a7da813c34a3cccc4c23c07c5939346a1771a2f425ec2c1"
)
APPROVED_GATE_A_GENERATED_AT = "2026-08-28T07:42:13Z"
APPROVED_CRM_SHA256 = "065a7b53f6e5d97e8b43690306750e33fac3534dccbf713fe66b464eeb824b0f"
APPROVED_FILES = {
    "video/index.html": (
        "f8c64fec851d025f37f3efb35d539aaf1c361be7f6a2102d2b2ac5dbd4649985",
        "545bae287315336804a01cb0467abb376298c8463e16a8ae05d916757cde42ba", 30750,
    ),
    "video/katalog.html": (
        "743ce2a2d0bd35f475006cb0991f52982b6540670d62544654d2caf4d387c61a",
        "6711e2b02f269680b0c3ecc76371b9aa79830f9a0466b7e51b517ef547627899", 29540,
    ),
    "video/info.html": (
        "d7e2589542991a1628835df919ce60ef0c7a29a8130cbf3915553517e62559a1",
        "dbd759eb4aca9ee413d72c88d32dac9c3c626b657587479f6ab55c167fef600f", 24173,
    ),
    "video/podbor.html": (
        "00d4f473812bcebef1d760465e0a2ed18cc010b152ea1eae340773e0527324a5",
        "00d4f473812bcebef1d760465e0a2ed18cc010b152ea1eae340773e0527324a5", 33310,
    ),
    "video/UA-0001.html": (
        "2c1f40123210389453c192098f893b5fafb4bd53aeea92855f35456f7a982a09",
        "48d66ed286aa88a494322971d99e93b933af8bc7560961e6f3e32188475748b1", 37506,
    ),
    "video/UA-0002.html": (
        "85438938624cb2cb1e39d994542236d740eb418a738603ed2290149aa1c3a0f0",
        "f020306b5487b281f5ab56c279e41bfcf6fe49598e70b9b40231257a426bb220", 38733,
    ),
    "video/UA-0003.html": (
        "3513b36bd1a823e64b478ea082153d928f85194b5723e0f789ad8203b412dec7",
        "e9d4c91f1ed17472f968a1280fe04c5a75ac92144ca61ce6946ef98d45608466", 36354,
    ),
    "video/UA-0004.html": (
        "30c705dca405f88dc09549b7408b256d105a879d7ef4e4183279e54c117a9865",
        "a4095c1b4e1cda025b2e9ca59000e896c6cfe03ca6443ec993ef03161e8142e0", 36684,
    ),
    "video/UA-0005.html": (
        "5fb42943ddb7f1fe681d08927e1c2c17cd48e6284abf1543ecbb0e90c9e13fbc",
        "b30174921834a714f33278bb90a4708a89eab9b72f3f8a55e0be85dea62f8923", 35622,
    ),
    "video/UA-0006.html": (
        "1afd8295f78a45bb26a1df1f50b67c8d996ec26b828891c63caf88e08683a9f8",
        "62d267321d0b75bc9b6f9027748b25cd16bfea2897a6e641f9ab0cd40c139165", 40565,
    ),
    "video/UA-0007.html": (
        "35b27dafe0ac62e909d033074a1d7bfcf3d56f10db2ded7b4d10aa9854f7805f",
        "23d2f4bfe481f6e9bbb4371598b58e06304455112ad904d8bdf2f8c37c037c51", 37328,
    ),
    "video/UA-0008.html": (
        "d3df03714bd0dc2a420eef88c16eb89f530d7dc38ec5dfb7e325dd3199659d9e",
        "f3192e949b0c86f1274e1ff34c426d33c17ab089a9f66a487ec562d71f28a736", 38373,
    ),
    "video/UA-0009.html": (
        "c00fe8edaad664b605abe05271b72d08f5fac6ad507bdf51e22c98fdc46a103a",
        "03b83759f304706e4b6a61070616348493a24b1e21134bdee9589c4f527fb48d", 35918,
    ),
    "video/UA-0010.html": (
        "236b2934c0f404fd9d1ef5ae8f851d3625b7f303e7746a3f4ac886edccbb9951",
        "fb2d459583df51ef3ae8ddd0d5a4fd26d70f8f0d020591c16826b62bc14488b9", 36917,
    ),
    "stranica.py": (
        "16b3432f2bc0d703a5f33eeb2303077cfcf054f28ded4ccd3268e76c188530e1",
        "1522350ae821ffcde9393d10ac9707830a4592c2adcdf4ad0f666841f14b3656", 136789,
    ),
    "yadro.py": (
        "e25befedb73683e6c045e3cdbd624097ccfa8276c615cf1ac9297efcd67360f6",
        "71d981508c157dad7d683430d8d0965af8d3b5946331cbda06b2a0179a7a657c", 84974,
    ),
}

MAX_RESPONSE_BYTES = 2_000_000
MAX_RECEIPT_BYTES = 500_000
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 600
HEX64 = re.compile(r"^[0-9a-f]{64}$")
RECEIPT_KEYS = {
    "mode", "task", "status", "generated_at_utc", "manifest_sha256",
    "gate_a_generated_at_utc", "source_root", "candidate_root", "backup_root",
    "owner_approval", "production_write", "production_files_changed",
    "crm_write", "db_write", "service_reload", "gate_b_executed",
    "rollback_attempted", "rollback_completed", "crm_sha256_before",
    "crm_sha256_after", "files", "errors",
}
RECEIPT_FILE_KEYS = {
    "path", "source_sha256", "candidate_sha256", "before_sha256",
    "backup_sha256", "after_sha256", "action",
}


class ControllerBlocked(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_json(data: bytes, label: str) -> dict:
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ControllerBlocked("duplicate_json_key:" + label)
            result[key] = value
        return result

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ControllerBlocked("invalid_json:" + label) from exc
    if not isinstance(value, dict):
        raise ControllerBlocked("json_not_object:" + label)
    return value


def multipart(filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = "----ferry-gate-b-" + uuid.uuid4().hex
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    body = bytearray()
    body.extend((f"--{boundary}\r\n").encode())
    body.extend(
        (
            f'Content-Disposition: form-data; name="content"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode()
    )
    body.extend(data)
    body.extend((f"\r\n--{boundary}--\r\n").encode())
    return bytes(body), "multipart/form-data; boundary=" + boundary


class PythonAnywhereGateBAPI:
    def __init__(self, username: str, host: str, token: str, opener=urllib.request.urlopen):
        if username != ALLOWED_USERNAME:
            raise ControllerBlocked("invalid_username")
        if host not in ALLOWED_HOSTS:
            raise ControllerBlocked("invalid_host")
        if not token:
            raise ControllerBlocked("missing_api_token")
        self.username = username
        self.host = host
        self._token = token
        self._opener = opener

    @property
    def base(self) -> str:
        return f"https://{self.host}/api/v0/user/{urllib.parse.quote(self.username)}/"

    def _request(self, method: str, url: str, *, data=None, headers=None,
                 allowed=(200,), operation="request") -> tuple[int, bytes]:
        all_headers = {
            "Authorization": "Token " + self._token,
            "User-Agent": "ua-art-ferry-gate-b/1",
        }
        all_headers.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=all_headers, method=method)
        try:
            with self._opener(request, timeout=60) as response:
                status = getattr(response, "status", response.getcode())
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read(MAX_RESPONSE_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ControllerBlocked("network_error:" + operation) from exc
        if len(body) > MAX_RESPONSE_BYTES:
            raise ControllerBlocked("response_too_large:" + operation)
        if status not in allowed:
            raise ControllerBlocked(f"unexpected_http_status:{operation}:{status}")
        return status, body

    def _file_url(self, path: str) -> str:
        if path not in {REMOTE_SCRIPT, REMOTE_MANIFEST, REMOTE_OUTPUT}:
            raise ControllerBlocked("remote_file_path_not_allowed")
        return self.base + "files/path" + urllib.parse.quote(path, safe="/")

    def upload(self, remote_path: str, data: bytes) -> None:
        if remote_path not in {REMOTE_SCRIPT, REMOTE_MANIFEST}:
            raise ControllerBlocked("upload_path_not_allowed")
        body, content_type = multipart(pathlib.PurePosixPath(remote_path).name, data)
        self._request(
            "POST", self._file_url(remote_path), data=body,
            headers={"Content-Type": content_type}, allowed=(200, 201),
            operation="upload",
        )

    def read_file(self, path: str) -> bytes:
        status, body = self._request(
            "GET", self._file_url(path), allowed=(200, 404), operation="read_file"
        )
        if status == 404:
            raise FileNotFoundError(path)
        return body

    def delete_output(self) -> None:
        self._request(
            "DELETE", self._file_url(REMOTE_OUTPUT), allowed=(204, 404),
            operation="delete_output",
        )

    @staticmethod
    def _trigger_id(body: bytes) -> int | None:
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        identifier = value.get("id") if isinstance(value, dict) else None
        return identifier if isinstance(identifier, int) and identifier > 0 else None

    def create_trigger(self, manifest_sha256: str, script_sha256: str) -> tuple[str, int]:
        if not HEX64.fullmatch(manifest_sha256) or not HEX64.fullmatch(script_sha256):
            raise ControllerBlocked("remote_command_hash_invalid")
        command = (
            "cd " + REMOTE_ROOT
            + " && FERRY_GATE_B_MANIFEST_SHA256=" + manifest_sha256
            + " FERRY_GATE_B_SCRIPT_SHA256=" + script_sha256
            + " FERRY_GATE_B_APPROVED=" + OWNER_APPROVAL
            + " python3.10 gate_b_remote.py > " + REMOTE_OUTPUT
        )
        form = urllib.parse.urlencode(
            {
                "command": command,
                "description": "UA ART TASK 063 approved atomic Gate B",
                "enabled": "true",
            }
        ).encode()
        status, body = self._request(
            "POST", self.base + "always_on/", data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409), operation="create_always_on",
        )
        identifier = self._trigger_id(body) if status in (200, 201, 202) else None
        if identifier:
            return "always_on", identifier

        run_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode(
            {
                "command": command,
                "description": "UA ART TASK 063 Gate B fallback",
                "enabled": "true", "interval": "daily",
                "hour": run_at.hour, "minute": run_at.minute,
            }
        ).encode()
        status, body = self._request(
            "POST", self.base + "schedule/", data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            allowed=(200, 201, 202, 400, 403, 404, 409), operation="create_schedule",
        )
        identifier = self._trigger_id(body) if status in (200, 201, 202) else None
        if not identifier:
            raise ControllerBlocked("no_remote_trigger_available")
        return "schedule", identifier

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        kind, identifier = trigger
        if kind not in {"always_on", "schedule"} or not isinstance(identifier, int):
            raise ControllerBlocked("invalid_trigger")
        endpoint = "always_on" if kind == "always_on" else "schedule"
        self._request(
            "DELETE", self.base + f"{endpoint}/{identifier}/",
            allowed=(200, 202, 204, 404), operation="delete_trigger",
        )


class GateBController:
    def __init__(self, api, sleep=time.sleep, monotonic=time.monotonic,
                 poll_interval=POLL_INTERVAL_SECONDS, poll_timeout=POLL_TIMEOUT_SECONDS):
        self.api = api
        self.sleep = sleep
        self.monotonic = monotonic
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout

    @staticmethod
    def load_approved_gate_a() -> dict:
        data = GATE_A_EVIDENCE.read_bytes()
        if sha256_bytes(data) != APPROVED_GATE_A_EVIDENCE_SHA256:
            raise ControllerBlocked("approved_gate_a_evidence_hash_mismatch")
        receipt = strict_json(data, "approved_gate_a_evidence")
        try:
            GateAController.validate_receipt(receipt)
        except Exception as exc:
            raise ControllerBlocked("approved_gate_a_evidence_invalid") from exc
        if receipt.get("status") != "PASS_READY_FOR_GATE_B":
            raise ControllerBlocked("approved_gate_a_status_invalid")
        if receipt.get("generated_at_utc") != APPROVED_GATE_A_GENERATED_AT:
            raise ControllerBlocked("approved_gate_a_timestamp_mismatch")
        if receipt.get("crm", {}).get("sha256") != APPROVED_CRM_SHA256:
            raise ControllerBlocked("approved_crm_hash_mismatch")
        combined = receipt["candidates"] + receipt["generator_candidates"]
        seen = {}
        for item in combined:
            path = item["path"]
            actual = (item["source_sha256"], item["candidate_sha256"], item["candidate_size"])
            if path in seen or APPROVED_FILES.get(path) != actual:
                raise ControllerBlocked("approved_candidate_mismatch:" + path)
            seen[path] = actual
        if set(seen) != set(APPROVED_FILES) or set(seen) != set(ALLOWED_PATHS):
            raise ControllerBlocked("approved_candidate_set_mismatch")
        return receipt

    @staticmethod
    def deployment_id() -> str:
        run_id = os.environ.get("GITHUB_RUN_ID", "local")
        attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
        token = re.sub(r"[^a-z0-9-]", "-", (run_id + "-" + attempt).lower())[:40]
        return "task063-" + token.strip("-")

    @classmethod
    def build_manifest(cls, gate_a: dict) -> tuple[dict, bytes]:
        deployment_id = cls.deployment_id()
        by_path = {
            item["path"]: item
            for item in gate_a["candidates"] + gate_a["generator_candidates"]
        }
        manifest = {
            "task": TASK,
            "operation": "APPLY",
            "owner_approval": OWNER_APPROVAL,
            "deployment_id": deployment_id,
            "gate_a_generated_at_utc": gate_a["generated_at_utc"],
            "source_root": FIXED_SOURCE_ROOT,
            "candidate_root": FIXED_CANDIDATE_ROOT,
            "backup_root": FIXED_BACKUP_PARENT + "/" + deployment_id,
            "crm": {
                "path": "crm.db",
                "sha256": gate_a["crm"]["sha256"],
                "id_count": 10,
                "table": "cars",
                "id_column": "auto_number",
                "container_column": "sea_container",
            },
            "files": [
                {
                    "path": path,
                    "kind": "html" if path in VIDEO_PATHS else "python",
                    "source_sha256": by_path[path]["source_sha256"],
                    "candidate_sha256": by_path[path]["candidate_sha256"],
                    "candidate_size": by_path[path]["candidate_size"],
                }
                for path in ALLOWED_PATHS
            ],
        }
        data = (
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        return manifest, data

    def upload_and_verify(self, manifest_bytes: bytes) -> None:
        script = LOCAL_SCRIPT.read_bytes()
        compile(script.decode("utf-8"), str(LOCAL_SCRIPT), "exec")
        for remote, data in ((REMOTE_SCRIPT, script), (REMOTE_MANIFEST, manifest_bytes)):
            self.api.upload(remote, data)
            if sha256_bytes(self.api.read_file(remote)) != sha256_bytes(data):
                raise ControllerBlocked("uploaded_file_hash_mismatch")

    def poll_receipt(self) -> dict:
        deadline = self.monotonic() + self.poll_timeout
        while self.monotonic() < deadline:
            try:
                data = self.api.read_file(REMOTE_OUTPUT)
            except FileNotFoundError:
                data = b""
            if data:
                if len(data) > MAX_RECEIPT_BYTES:
                    raise ControllerBlocked("receipt_too_large")
                return strict_json(data, "gate_b_receipt")
            self.sleep(self.poll_interval)
        raise ControllerBlocked("receipt_timeout")

    @staticmethod
    def validate_receipt(receipt: dict, manifest: dict, manifest_sha256: str) -> dict:
        if set(receipt) != RECEIPT_KEYS:
            raise ControllerBlocked("gate_b_receipt_keys_invalid")
        if receipt.get("mode") != MODE or receipt.get("task") != TASK:
            raise ControllerBlocked("gate_b_receipt_identity_invalid")
        if receipt.get("status") not in {"PASS", "BLOCKED", "ROLLED_BACK"}:
            raise ControllerBlocked("gate_b_receipt_status_invalid")
        if receipt.get("manifest_sha256") != manifest_sha256:
            raise ControllerBlocked("gate_b_receipt_manifest_hash_invalid")
        for field, expected in (
            ("gate_a_generated_at_utc", manifest["gate_a_generated_at_utc"]),
            ("source_root", manifest["source_root"]),
            ("candidate_root", manifest["candidate_root"]),
            ("backup_root", manifest["backup_root"]),
            ("owner_approval", OWNER_APPROVAL),
        ):
            if receipt.get(field) != expected:
                raise ControllerBlocked("gate_b_receipt_field_invalid:" + field)
        if not isinstance(receipt.get("generated_at_utc"), str):
            raise ControllerBlocked("gate_b_receipt_timestamp_invalid")
        for field in ("production_write", "crm_write", "db_write", "service_reload",
                      "gate_b_executed", "rollback_attempted", "rollback_completed"):
            if not isinstance(receipt.get(field), bool):
                raise ControllerBlocked("gate_b_receipt_boolean_invalid:" + field)
        if receipt["crm_write"] or receipt["db_write"] or receipt["service_reload"]:
            raise ControllerBlocked("gate_b_receipt_safety_invalid")
        if receipt["gate_b_executed"] is not True:
            raise ControllerBlocked("gate_b_not_executed")
        if not isinstance(receipt.get("production_files_changed"), int):
            raise ControllerBlocked("gate_b_changed_count_invalid")
        if not isinstance(receipt.get("errors"), list):
            raise ControllerBlocked("gate_b_errors_invalid")
        if receipt["status"] != "PASS":
            return receipt
        if receipt["errors"] or receipt["rollback_attempted"] or receipt["rollback_completed"]:
            raise ControllerBlocked("gate_b_pass_safety_state_invalid")
        if (
            receipt.get("crm_sha256_before") != APPROVED_CRM_SHA256
            or receipt.get("crm_sha256_after") != APPROVED_CRM_SHA256
        ):
            raise ControllerBlocked("gate_b_crm_hash_invalid")

        files = receipt.get("files")
        if not isinstance(files, list) or len(files) != len(ALLOWED_PATHS):
            raise ControllerBlocked("gate_b_receipt_files_invalid")
        by_path = {}
        applied = 0
        for item in files:
            if not isinstance(item, dict) or set(item) != RECEIPT_FILE_KEYS:
                raise ControllerBlocked("gate_b_receipt_file_entry_invalid")
            path = item.get("path")
            if path in by_path or path not in APPROVED_FILES:
                raise ControllerBlocked("gate_b_receipt_file_path_invalid")
            source_sha, candidate_sha, _ = APPROVED_FILES[path]
            if item.get("source_sha256") != source_sha:
                raise ControllerBlocked("gate_b_receipt_source_hash_invalid:" + path)
            if item.get("candidate_sha256") != candidate_sha:
                raise ControllerBlocked("gate_b_receipt_candidate_hash_invalid:" + path)
            if item.get("before_sha256") not in {source_sha, candidate_sha}:
                raise ControllerBlocked("gate_b_receipt_before_hash_invalid:" + path)
            if item.get("backup_sha256") != item.get("before_sha256"):
                raise ControllerBlocked("gate_b_receipt_backup_hash_invalid:" + path)
            if item.get("after_sha256") != candidate_sha:
                raise ControllerBlocked("gate_b_receipt_after_hash_invalid:" + path)
            if item.get("action") not in {"APPLIED", "ALREADY_APPLIED"}:
                raise ControllerBlocked("gate_b_receipt_action_invalid:" + path)
            if item["action"] == "APPLIED":
                applied += 1
                if item["before_sha256"] == candidate_sha:
                    raise ControllerBlocked("gate_b_receipt_applied_state_invalid:" + path)
            by_path[path] = item
        if set(by_path) != set(ALLOWED_PATHS):
            raise ControllerBlocked("gate_b_receipt_file_set_invalid")
        if receipt["production_files_changed"] != applied:
            raise ControllerBlocked("gate_b_receipt_changed_count_mismatch")
        if receipt["production_write"] is not bool(applied):
            raise ControllerBlocked("gate_b_receipt_write_flag_mismatch")
        return receipt

    @staticmethod
    def atomic_write(path: pathlib.Path, text: str) -> None:
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

    @classmethod
    def relay(cls, receipt: dict) -> None:
        cls.atomic_write(
            GATE_B_EVIDENCE,
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        rows = "\n".join(
            "- `%s`: %s; `%s` → `%s`; backup `%s`" % (
                item["path"], item["action"], item["before_sha256"],
                item["after_sha256"], item["backup_sha256"],
            )
            for item in receipt.get("files", [])
        ) or "- No production file passed preflight."
        errors = "\n".join("- " + str(value) for value in receipt.get("errors", [])) or "- none"
        report = f'''# Ferry wording Gate B report

status: {receipt["status"]}
generated_at_utc: {receipt["generated_at_utc"]}
gate_a_generated_at_utc: {receipt["gate_a_generated_at_utc"]}
production_write: {str(receipt["production_write"]).lower()}
production_files_changed: {receipt["production_files_changed"]}
crm_write: false
db_write: false
service_reload: false
rollback_attempted: {str(receipt["rollback_attempted"]).lower()}
rollback_completed: {str(receipt["rollback_completed"]).lower()}
backup_root: `{receipt["backup_root"]}`

## Bounded production files

{rows}

## Errors

{errors}
'''
        cls.atomic_write(GATE_B_REPORT, report)

    def run(self) -> dict:
        gate_a = self.load_approved_gate_a()
        manifest, manifest_bytes = self.build_manifest(gate_a)
        manifest_sha = sha256_bytes(manifest_bytes)
        self.upload_and_verify(manifest_bytes)
        trigger = None
        try:
            self.api.delete_output()
            trigger = self.api.create_trigger(manifest_sha, sha256_bytes(LOCAL_SCRIPT.read_bytes()))
            receipt = self.validate_receipt(
                self.poll_receipt(), manifest, manifest_sha
            )
            self.relay(receipt)
            if receipt["status"] != "PASS":
                raise ControllerBlocked(
                    "remote_gate_b_" + receipt["status"].lower() + ":"
                    + ",".join(receipt.get("errors", []))
                )
            return receipt
        finally:
            if trigger is not None:
                try:
                    self.api.delete_trigger(trigger)
                except Exception:
                    pass
            try:
                self.api.delete_output()
            except Exception:
                pass


def main() -> int:
    try:
        api = PythonAnywhereGateBAPI(
            os.environ.get("PYTHONANYWHERE_USERNAME", ALLOWED_USERNAME),
            os.environ.get("PYTHONANYWHERE_HOST", ALLOWED_HOSTS[0]),
            os.environ.get("PYTHONANYWHERE_API_TOKEN", ""),
        )
        receipt = GateBController(api).run()
        print(json.dumps({
            "status": receipt["status"],
            "production_write": receipt["production_write"],
            "production_files_changed": receipt["production_files_changed"],
            "crm_write": False,
            "db_write": False,
            "service_reload": False,
        }, sort_keys=True))
        return 0
    except (ControllerBlocked, OSError, UnicodeError, SyntaxError) as exc:
        label = str(exc) if isinstance(exc, ControllerBlocked) else "local_controller_failure"
        print("FERRY_GATE_B_CONTROLLER_BLOCKED:" + label)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
