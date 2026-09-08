#!/usr/bin/env python3
"""PythonAnywhere controller for TASK120-PUBLISH-UA-0017-UA-0018."""
from __future__ import annotations

import datetime as dt
import concurrent.futures
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
from typing import Any, Mapping


HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REMOTE_SCRIPT_LOCAL = HERE / "remote_installer.py"
TASK_ID = "TASK120-PUBLISH-UA-0017-UA-0018"
CONTRACT_ID = "UA-ART-PUBLISH-17-18-001-V1.0"
CRITICAL_CONTRACT = "UA-ART-CRITICAL-ADAPTER-V1.0"
REMOTE_DIR = "/home/Carix/autopilot_inbox/cloud/task_068_ferry_vin"
REMOTE_SCRIPT = REMOTE_DIR + "/task120_publish_17_18.py"
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REQUEST_REL = "tasks/requests/%s.json" % TASK_ID
MANIFEST_REL = "tasks/manifests/%s.json" % TASK_ID
RECEIPT_REL = "state/receipts/%s.json" % TASK_ID
BACKUP_RECEIPT_REL = "state/receipts/%s-BACKUP.json" % TASK_ID
ROLLBACK_RECEIPT_REL = "state/receipts/%s-ROLLBACK.json" % TASK_ID
EVIDENCE_REL = "cloud/task120_publish_ua0017_ua0018/evidence.json"
CONTROLLER_REL = "cloud/task120_publish_ua0017_ua0018/controller.py"
BACKUP_CONTROLLER_REL = "cloud/task120_publish_ua0017_ua0018/backup_controller.py"
ROLLBACK_CONTROLLER_REL = "cloud/task120_publish_ua0017_ua0018/rollback_controller.py"
EXPECTED_IDS = tuple("UA-%04d" % value for value in range(1, 19))
EXPECTED_TARGETS = {
    "UA-0017": {
        "id": 26, "auto_number": "UA-0017", "vin": "WAUZZZ4GXGN069684",
        "brand": "Audi", "model": "A6", "year": "2015", "fuel": "diesel",
        "engine_cc": 2967, "gearbox": "автомат", "drive": "полный",
        "mileage_km": 118000, "color": "серебристый", "price_uah": 23000,
        "review_status": "approved_owner", "status": "ge_waiting",
        "photo_count": 39, "video_count": 0,
    },
    "UA-0018": {
        "id": 28, "auto_number": "UA-0018", "vin": "KNAG541BBPA224823",
        "brand": "Kia", "model": "K5", "year": "2023", "fuel": "газ",
        "engine_cc": 1999, "gearbox": "Автомат", "drive": "передний",
        "mileage_km": 110000, "color": "Темный графит", "price_uah": 19900,
        "review_status": "approved_owner", "status": "ge_to_kyiv",
        "photo_count": 36, "video_count": 1,
    },
}
EXPECTED_RUNTIME = {
    "publikaciya.py": "fb7fa77277ebc3330c85ab3744c85ac7f084074a314866a5bf388a283f2622c0",
    "publish_transaction_guard.py": "ce6bd00338fbdc38b91f9554ea7baab3b8e921ffe6c1035aa4aba0186e2b549d",
    "catalog_design_guard.py": "51127bbc2be949e1d37f7b6995c0e5a7a32a497c8436139322ce5b0fea308d60",
    "stranica.py": "42aa5fc9db162e59fcf36b7ee9b2002360205827023786a65cf2205ab16066cc",
    "master_card.py": "f64e0b82b11bfd6089509510e5b131a91b03d40bed97b16075ab2ec60da380ce",
    "yadro.py": "1e92a22a3fc485ea2cfe3d00a50586e872b3f6e4f628923b2ab9744534406992",
    "ua_additional_spec.py": "a04bb9fe565379a02e2c4e1b7c055821ecd63fb3e7c84138e5fe949ac032d259",
    "vin_spec_service.py": "247943e514f34dc37265791bf56fd36e58bcbaa8b2064285544733b1afc42bae",
    "catalog_design_golden.html": "34fb82b9ec1bc66b76fccbbaad9b440d01ea4d60fe5c195954e88251442ecdd0",
}
MAX_BYTES = 64 * 1024 * 1024
SHA_RE = re.compile(r"[0-9a-f]{64}")
RUNTIME_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


class ControllerError(RuntimeError):
    pass


class RemoteStopUnconfirmed(ControllerError):
    pass


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _atomic_json(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False)
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


def _repo_path(relative: str) -> pathlib.Path:
    pure = pathlib.PurePosixPath(relative)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts or str(pure) != relative:
        raise ControllerError("REPO_PATH_SCOPE")
    root = ROOT.resolve()
    path = (root / pathlib.Path(*pure.parts)).resolve()
    if not path.is_relative_to(root):
        raise ControllerError("REPO_PATH_SCOPE")
    return path


def _required_value(environment: Mapping[str, str], name: str) -> str:
    value = str(environment.get(name, ""))
    if not value or len(value) > 256 or any(char in value for char in "\r\n\0"):
        raise ControllerError("RUNTIME_BINDING_INVALID:" + name)
    return value


def required(
    environment: Mapping[str, str],
    operation: str = "execute",
) -> tuple[dict[str, str], dict[str, Any]]:
    """Validate the immutable CRITICAL workflow envelope before any network call."""
    if operation not in {"execute", "backup", "rollback"}:
        raise ControllerError("OPERATION_INVALID")
    names = (
        "PYTHONANYWHERE_API_TOKEN", "UAART_OPERATION", "UAART_REQUEST_PATH",
        "UAART_REQUEST_SHA256", "UAART_TASK_ID", "UAART_TASK_CLASS",
        "UAART_RUN_ID", "UAART_TRANSACTION_ID", "UAART_MANIFEST_SHA256",
        "UAART_RECEIPT_PATH",
    )
    values = {name: _required_value(environment, name) for name in names}
    if values["UAART_OPERATION"] != operation:
        raise ControllerError("OPERATION_IDENTITY")
    if values["UAART_TASK_ID"] != TASK_ID or values["UAART_TASK_CLASS"].upper() != "CRITICAL":
        raise ControllerError("TASK_IDENTITY")
    if not RUNTIME_ID_RE.fullmatch(values["UAART_RUN_ID"]):
        raise ControllerError("RUN_IDENTITY")
    if not RUNTIME_ID_RE.fullmatch(values["UAART_TRANSACTION_ID"]):
        raise ControllerError("TRANSACTION_IDENTITY")
    for name in ("UAART_REQUEST_SHA256", "UAART_MANIFEST_SHA256"):
        if not SHA_RE.fullmatch(values[name]):
            raise ControllerError(name + "_INVALID")

    expected_receipts = {
        "execute": ("receipt_path", RECEIPT_REL, None),
        "backup": ("backup_receipt_path", BACKUP_RECEIPT_REL, "UAART_BACKUP_RECEIPT_PATH"),
        "rollback": ("rollback_receipt_path", ROLLBACK_RECEIPT_REL, "UAART_ROLLBACK_RECEIPT_PATH"),
    }
    receipt_field, receipt_rel, alias = expected_receipts[operation]
    if values["UAART_RECEIPT_PATH"] != receipt_rel:
        raise ControllerError("RECEIPT_IDENTITY")
    if alias:
        values[alias] = _required_value(environment, alias)
        if values[alias] != receipt_rel or values[alias] != values["UAART_RECEIPT_PATH"]:
            raise ControllerError("RECEIPT_ALIAS_IDENTITY")
    if operation in {"execute", "rollback"}:
        values["UAART_BACKUP_MANIFEST_SHA256"] = _required_value(
            environment, "UAART_BACKUP_MANIFEST_SHA256"
        )
        if not SHA_RE.fullmatch(values["UAART_BACKUP_MANIFEST_SHA256"]):
            raise ControllerError("BACKUP_IDENTITY")

    if values["UAART_REQUEST_PATH"] != REQUEST_REL:
        raise ControllerError("REQUEST_PATH_IDENTITY")
    request_path = _repo_path(values["UAART_REQUEST_PATH"])
    if request_path.is_symlink() or not request_path.is_file():
        raise ControllerError("REQUEST_FILE_IDENTITY")
    request_bytes = request_path.read_bytes()
    if _sha(request_bytes) != values["UAART_REQUEST_SHA256"]:
        raise ControllerError("REQUEST_IDENTITY")
    try:
        request = json.loads(request_bytes.decode("utf-8"))
    except Exception as exc:
        raise ControllerError("REQUEST_PARSE") from exc
    if (
        not isinstance(request, dict)
        or request.get("task_id") != TASK_ID
        or request.get("production_required") is not True
        or str(request.get("requested_min_class") or "").upper() != "CRITICAL"
    ):
        raise ControllerError("REQUEST_SCOPE")
    critical = request.get("critical") or {}
    execution = request.get("execution") or {}
    if not isinstance(critical, dict) or not isinstance(execution, dict):
        raise ControllerError("REQUEST_CONTRACT")
    if critical.get("manifest_path") != MANIFEST_REL:
        raise ControllerError("MANIFEST_PATH_IDENTITY")
    manifest_path = _repo_path(MANIFEST_REL)
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ControllerError("MANIFEST_FILE_IDENTITY")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ControllerError("MANIFEST_PARSE") from exc
    manifest_sha = _sha(_canonical(manifest))
    if (
        manifest_sha != values["UAART_MANIFEST_SHA256"]
        or critical.get("manifest_sha256") != manifest_sha
    ):
        raise ControllerError("MANIFEST_IDENTITY")
    if (
        not isinstance(manifest, dict)
        or manifest.get("task_id") != TASK_ID
        or str(manifest.get("task_class") or "").upper() != "CRITICAL"
        or manifest.get("contract_id") != CRITICAL_CONTRACT
        or manifest.get("production_write") is not True
        or manifest.get("explicit_crm_vehicle_approval") is not True
    ):
        raise ControllerError("MANIFEST_SCOPE")
    expected_execution = {
        "controller_path": CONTROLLER_REL,
        "backup_controller_path": BACKUP_CONTROLLER_REL,
        "rollback_controller_path": ROLLBACK_CONTROLLER_REL,
        receipt_field: receipt_rel,
    }
    for key, expected in expected_execution.items():
        if execution.get(key) != expected:
            raise ControllerError("EXECUTION_IDENTITY:" + key)
    return values, request


def receipt_target(values: Mapping[str, str]) -> pathlib.Path:
    path = _repo_path(str(values["UAART_RECEIPT_PATH"]))
    if path.is_symlink():
        raise ControllerError("RECEIPT_TARGET_SYMLINK")
    return path


class API:
    def __init__(self, token: str | None = None) -> None:
        self.token = (token or os.environ.get("PYTHONANYWHERE_API_TOKEN", "")).strip()
        if not self.token:
            raise ControllerError("PYTHONANYWHERE_API_TOKEN_MISSING")
        self.remote_fenced = True

    def request(self, method: str, url: str, data: bytes | None = None,
                headers: dict[str, str] | None = None,
                allowed: tuple[int, ...] = (200,)) -> tuple[int, bytes]:
        actual = {"Authorization": "Token " + self.token, "User-Agent": "ua-art-task120/1"}
        actual.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=actual, method=method)
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                status, body = int(response.status), response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, body = int(exc.code), exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK:" + type(exc).__name__) from exc
        if len(body) > MAX_BYTES:
            raise ControllerError("RESPONSE_TOO_LARGE")
        if status not in allowed:
            raise ControllerError("HTTP_%d:%s" % (status, urllib.parse.urlsplit(url).path))
        return status, body

    @staticmethod
    def file_url(path: str) -> str:
        candidate = pathlib.PurePosixPath(path)
        root = pathlib.PurePosixPath(REMOTE_DIR)
        if not candidate.is_absolute() or root not in candidate.parents or ".." in candidate.parts:
            raise ControllerError("REMOTE_PATH_SCOPE")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def read(self, path: str, missing: bool = False) -> bytes | None:
        status, body = self.request("GET", self.file_url(path), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_FILE_MISSING")
        return body

    def delete_file(self, path: str) -> None:
        self.request("DELETE", self.file_url(path), allowed=(200, 202, 204, 404))

    def upload(self, path: str, value: bytes) -> None:
        boundary = "----uaart-task120-" + uuid.uuid4().hex
        filename = pathlib.PurePosixPath(path).name
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body = bytearray()
        body.extend(("--%s\r\n" % boundary).encode())
        body.extend(('Content-Disposition: form-data; name="content"; filename="%s"\r\n'
                     "Content-Type: %s\r\n\r\n" % (filename, mime)).encode())
        body.extend(value)
        body.extend(("\r\n--%s--\r\n" % boundary).encode())
        self.request("POST", self.file_url(path), bytes(body),
                     {"Content-Type": "multipart/form-data; boundary=" + boundary},
                     allowed=(200, 201))
        if self.read(path) != value:
            raise ControllerError("UPLOAD_READBACK")

    def claim_transport(self, value: bytes) -> None:
        if self.read(REMOTE_SCRIPT, missing=True) is not None:
            raise ControllerError("REMOTE_TRANSPORT_PREEXISTING")
        self.upload(REMOTE_SCRIPT, value)

    def release_transport(self, expected: bytes) -> None:
        if not self.remote_fenced:
            raise RemoteStopUnconfirmed("REMOTE_TRIGGER_STOP_UNCONFIRMED")
        current = self.read(REMOTE_SCRIPT, missing=True)
        if current is None:
            return
        if current != expected:
            raise ControllerError("REMOTE_TRANSPORT_CHANGED")
        self.delete_file(REMOTE_SCRIPT)
        if self.read(REMOTE_SCRIPT, missing=True) is not None:
            raise ControllerError("REMOTE_TRANSPORT_DELETE_FAILED")

    @staticmethod
    def _id(body: bytes) -> int | None:
        """Extract an id from the documented object or common API wrappers."""
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception:
            return None

        def walk(item: Any) -> int | None:
            if isinstance(item, dict):
                for key in ("id", "task_id", "always_on_id"):
                    candidate = item.get(key)
                    if isinstance(candidate, int) and candidate > 0:
                        return candidate
                for child in item.values():
                    found = walk(child)
                    if found:
                        return found
            elif isinstance(item, list):
                for child in item:
                    found = walk(child)
                    if found:
                        return found
            return None

        return walk(value)

    def _find_always_on(self, command: str, description: str) -> list[int]:
        status, body = self.request(
            "GET", BASE + "always_on/", allowed=(200,)
        )
        try:
            value = json.loads(body.decode("utf-8"))
        except Exception as exc:
            raise ControllerError("MUTATING_ALWAYS_ON_LIST_INVALID") from exc
        rows = value.get("tasks") if isinstance(value, dict) else value
        if not isinstance(rows, list):
            rows = [value] if isinstance(value, dict) else []
        matches: list[int] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            identifier = self._id(json.dumps(row).encode("utf-8"))
            if (
                identifier
                and row.get("command") == command
                and row.get("description") == description
            ):
                matches.append(identifier)
        return sorted(set(matches))

    @staticmethod
    def _response_excerpt(body: bytes) -> str:
        return body.decode("utf-8", "replace").replace("\\r", " ").replace("\\n", " ")[:400]

    def trigger(
        self, command: str, description: str, *, allow_schedule: bool
    ) -> tuple[str, int]:
        form = urllib.parse.urlencode(
            {"command": command, "description": description, "enabled": "true"}
        ).encode()
        status, body = self.request(
            "POST", BASE + "always_on/", form,
            {"Content-Type": "application/x-www-form-urlencoded",
             "Accept": "application/json"},
            allowed=(200, 201, 202, 400, 403, 404, 409),
        )
        if status in (200, 201, 202):
            identifier = self._id(body)
            if identifier:
                return "always_on", identifier
            # Some successful API responses contain no top-level id. Resolve
            # the exact just-created task from the authoritative task list.
            matches = self._find_always_on(command, description)
            if len(matches) == 1:
                return "always_on", matches[0]
            if len(matches) > 1:
                raise ControllerError("MUTATING_ALWAYS_ON_AMBIGUOUS")
        if not allow_schedule:
            detail = self._response_excerpt(body)
            raise ControllerError(
                "MUTATING_ALWAYS_ON_UNAVAILABLE:%d:%s" % (status, detail)
            )
        when = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)
        form = urllib.parse.urlencode(
            {"command": command, "description": description + " fallback", "enabled": "true",
             "interval": "daily", "hour": when.hour, "minute": when.minute}
        ).encode()
        _, body = self.request(
            "POST", BASE + "schedule/", form,
            {"Content-Type": "application/x-www-form-urlencoded",
             "Accept": "application/json"},
            allowed=(200, 201, 202),
        )
        identifier = self._id(body)
        if not identifier:
            raise ControllerError("NO_REMOTE_TRIGGER")
        return "schedule", identifier

    def delete_trigger(self, trigger: tuple[str, int]) -> None:
        kind, identifier = trigger
        self.request("DELETE", BASE + "%s/%d/" % (kind, identifier),
                     allowed=(200, 202, 204, 404))
        if kind == "always_on":
            detail = BASE + "always_on/%d/" % identifier
            for attempt in range(12):
                status, _body = self.request("GET", detail, allowed=(200, 404))
                if status == 404:
                    return
                if attempt < 11:
                    time.sleep(1)
            raise ControllerError("STOP_UNCONFIRMED:%d" % identifier)

    def run(self, mode: str, script_sha: str, *, workflow_run_id: str,
            transaction_id: str, preflight: str = "", backup_manifest: str = "",
            backup_sha: str = "", timeout: int = 1200) -> dict[str, Any]:
        if not self.remote_fenced:
            raise RemoteStopUnconfirmed("REMOTE_TRIGGER_STOP_UNCONFIRMED")
        seed = "\0".join((
            TASK_ID, workflow_run_id, transaction_id, mode, script_sha,
            preflight, backup_manifest, backup_sha,
        )).encode("utf-8")
        run_id = "task120-" + _sha(seed)[:40]
        receipt = REMOTE_DIR + "/task120-receipt-" + run_id + ".json"
        completed = REMOTE_DIR + "/task120-completed-" + run_id + ".json"
        stale = self.read(receipt, missing=True)
        if stale is not None:
            durable = self.read(completed, missing=True)
            if durable != stale:
                raise ControllerError("REMOTE_STALE_RECEIPT_CONFLICT")
            parsed_stale = json.loads(stale.decode("utf-8"))
            if not isinstance(parsed_stale, dict) or parsed_stale.get("run_id") != run_id:
                raise ControllerError("REMOTE_STALE_RECEIPT_IDENTITY")
            self.delete_file(receipt)
            if self.read(receipt, missing=True) is not None:
                raise ControllerError("REMOTE_STALE_RECEIPT_DELETE_FAILED")
        pieces = [
            "cd", REMOTE_DIR, "&&", "python3.10", "-B", "task120_publish_17_18.py",
            "--mode", mode, "--run-id", run_id,
            "--expected-script-sha256", script_sha,
        ]
        if preflight:
            pieces += ["--expected-preflight-digest", preflight]
        if backup_manifest:
            if not re.fullmatch(r"[A-Za-z0-9_./-]+", backup_manifest):
                raise ControllerError("BACKUP_MANIFEST_SCOPE")
            pieces += ["--backup-manifest", backup_manifest]
        if backup_sha:
            if not SHA_RE.fullmatch(backup_sha):
                raise ControllerError("BACKUP_MANIFEST_SHA256")
            pieces += ["--backup-manifest-sha256", backup_sha]
        command = " ".join(pieces)
        trigger = self.trigger(
            command,
            TASK_ID + " " + mode,
            allow_schedule=False,
        )
        raw_receipt: bytes | None = None
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                raw = self.read(receipt, missing=True)
                if raw:
                    value = json.loads(raw.decode("utf-8"))
                    if not isinstance(value, dict) or value.get("run_id") != run_id:
                        raise ControllerError("REMOTE_RECEIPT_IDENTITY")
                    raw_receipt = raw
                    break
                time.sleep(3)
            if raw_receipt is None:
                raise ControllerError("REMOTE_TIMEOUT:" + mode)
        finally:
            try:
                self.delete_trigger(trigger)
            except Exception as exc:
                self.remote_fenced = False
                raise RemoteStopUnconfirmed(
                    "REMOTE_TRIGGER_STOP_UNCONFIRMED:" + type(exc).__name__
                ) from exc
            current_receipt = self.read(receipt, missing=True)
            current_completed = self.read(completed, missing=True)
            if raw_receipt is None:
                if current_receipt is None:
                    # Preserve the original REMOTE_TIMEOUT after a confirmed
                    # stop; a completed ledger, if any, remains replay-safe.
                    current_receipt = None
                elif current_completed != current_receipt:
                    raise ControllerError("REMOTE_TIMEOUT_RECEIPT_CONFLICT")
                else:
                    parsed_timeout = json.loads(current_receipt.decode("utf-8"))
                    if (
                        not isinstance(parsed_timeout, dict)
                        or parsed_timeout.get("run_id") != run_id
                    ):
                        raise ControllerError("REMOTE_TIMEOUT_RECEIPT_IDENTITY")
                    self.delete_file(receipt)
                    if self.read(receipt, missing=True) is not None:
                        raise ControllerError("REMOTE_TRANSPORT_RECEIPT_DELETE_FAILED")
                continue_cleanup = False
            elif current_receipt != raw_receipt or current_completed != raw_receipt:
                raise ControllerError("REMOTE_TRANSPORT_RECEIPT_PAIR_MISMATCH")
            else:
                continue_cleanup = True
            if continue_cleanup:
                self.delete_file(receipt)
                if self.read(receipt, missing=True) is not None:
                    raise ControllerError("REMOTE_TRANSPORT_RECEIPT_DELETE_FAILED")
        value = json.loads(raw_receipt.decode("utf-8"))
        if not isinstance(value, dict) or value.get("run_id") != run_id:
            raise ControllerError("REMOTE_RECEIPT_IDENTITY")
        return value

def validate_receipt(value: dict[str, Any], mode: str, script_sha: str) -> None:
    if value.get("schema") != "ua-art-task120-remote-receipt-v1":
        raise ControllerError("REMOTE_RECEIPT_SCHEMA")
    if value.get("task_id") != TASK_ID or value.get("contract_id") != CONTRACT_ID:
        raise ControllerError("REMOTE_CONTRACT")
    if value.get("mode") != mode.upper() or value.get("script_sha256") != script_sha:
        raise ControllerError("REMOTE_MODE_OR_SCRIPT")
    if value.get("production_root") != "/home/Carix":
        raise ControllerError("REMOTE_PRODUCTION_ROOT")
    if value.get("status") != "PASS":
        raise ControllerError("REMOTE_%s_FAILED:%s" % (mode.upper(), ";".join(value.get("errors") or [])))


def validate_probe(value: dict[str, Any]) -> None:
    observation = value.get("observation") or {}
    if value.get("read_only") is not True:
        raise ControllerError("PROBE_NOT_READ_ONLY")
    if not re.fullmatch(r"[0-9a-f]{64}", str(observation.get("preflight_digest") or "")):
        raise ControllerError("PROBE_DIGEST")
    runtime = observation.get("runtime") or {}
    if set(runtime) != set(EXPECTED_RUNTIME):
        raise ControllerError("RUNTIME_KEY_SET")
    for name, expected in EXPECTED_RUNTIME.items():
        if runtime.get(name) != expected:
            raise ControllerError("RUNTIME_DRIFT:" + name)
    targets = observation.get("targets") or {}
    if set(targets) != {"UA-0017", "UA-0018"}:
        raise ControllerError("PROBE_TARGET_SET")
    flag_pairs = set()
    for uid, expected in EXPECTED_TARGETS.items():
        actual = targets[uid]
        for key, wanted in expected.items():
            if key == "vin":
                if actual.get("vin_sha256") != _sha(wanted.encode("utf-8")):
                    raise ControllerError("PROBE_TARGET_BINDING:" + uid + ":vin")
            elif actual.get(key) != wanted:
                raise ControllerError("PROBE_TARGET_BINDING:" + uid + ":" + key)
        if not SHA_RE.fullmatch(str(actual.get("row_digest") or "")):
            raise ControllerError("PROBE_TARGET_DIGEST:" + uid)
        flag_pairs.add((actual.get("published"), actual.get("publish_pending")))
    if len(flag_pairs) != 1 or next(iter(flag_pairs)) not in {(0, 0), (1, 0)}:
        raise ControllerError("PROBE_TARGET_PUBLICATION_STATE")
    states = observation.get("spec_states") or {}
    expected_counts = {"UA-0017": 18, "UA-0018": 12}
    for uid, count in expected_counts.items():
        if (states.get(uid) or {}).get("state") not in {"EMPTY", "EXACT"}:
            raise ControllerError("PROBE_SPEC_STATE:" + uid)
        if (states.get(uid) or {}).get("state") == "EXACT" and states[uid].get("count") != count:
            raise ControllerError("PROBE_SPEC_COUNT:" + uid)
    media_plan = observation.get("media_plan") or {}
    expected_media = {
        "UA-0017": {"foto": 39, "video": 0},
        "UA-0018": {"foto": 36, "video": 1},
    }
    if set(media_plan) != set(expected_media):
        raise ControllerError("PROBE_MEDIA_TARGET_SET")
    for uid, counts in expected_media.items():
        item = media_plan.get(uid) or {}
        rows = item.get("rows") or []
        if item.get("counts") != counts or len(rows) != sum(counts.values()):
            raise ControllerError("PROBE_MEDIA_COUNT:" + uid)
        if any(not SHA_RE.fullmatch(str(row.get("file_id_sha256") or "")) for row in rows):
            raise ControllerError("PROBE_MEDIA_BINDING:" + uid)


def _public_get(
    url: str, maximum: int, *, range_bytes: bool = False, timeout: int = 15
) -> tuple[int, bytes, str]:
    headers = {
        "User-Agent": "ua-art-task120-public/1",
        "Cache-Control": "no-cache, no-store",
        "Pragma": "no-cache",
    }
    if range_bytes:
        headers["Range"] = "bytes=0-65535"
    separator = "&" if "?" in url else "?"
    request = urllib.request.Request(
        url + separator + "task120=" + str(time.time_ns()), headers=headers
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(maximum + 1)
        status = int(response.status)
        content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().casefold()
    if len(body) > maximum:
        raise ControllerError("PUBLIC_RESPONSE_TOO_LARGE")
    return status, body, content_type


def _jpeg_dimensions(value: bytes) -> tuple[int, int]:
    if len(value) < 12 or not value.startswith(b"\xff\xd8\xff") or not value.endswith(b"\xff\xd9"):
        raise ControllerError("PUBLIC_JPEG_STRUCTURE")
    offset = 2
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while offset + 4 <= len(value):
        if value[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(value) and value[offset] == 0xFF:
            offset += 1
        if offset >= len(value):
            break
        marker = value[offset]
        offset += 1
        if marker == 0x01 or 0xD0 <= marker <= 0xD9:
            continue
        if offset + 2 > len(value):
            break
        length = int.from_bytes(value[offset:offset + 2], "big")
        if length < 2 or offset + length > len(value):
            break
        if marker in sof and length >= 7:
            height = int.from_bytes(value[offset + 3:offset + 5], "big")
            width = int.from_bytes(value[offset + 5:offset + 7], "big")
            if 0 < width <= 32768 and 0 < height <= 32768:
                return width, height
            break
        if marker == 0xDA:
            break
        offset += length
    raise ControllerError("PUBLIC_JPEG_STRUCTURE")


def _target_media_paths() -> tuple[str, ...]:
    return tuple(
        ["video/foto/UA-0017/%03d.jpg" % index for index in range(1, 40)]
        + ["video/foto/UA-0018/%03d.jpg" % index for index in range(1, 37)]
        + ["video/UA-0018.mp4"]
    )


def _public_batch(
    relatives: set[str],
    html_paths: set[str],
    deadline: float,
    *,
    allow_404: bool,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Fetch a bounded public snapshot without an unbounded serial tail."""
    results: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    def fetch(relative: str) -> tuple[str, dict[str, Any]]:
        maximum = 16 * 1024 * 1024 if relative in html_paths else 20 * 1024 * 1024
        try:
            status, body, content_type = _public_get(
                "https://www.uaart.com.ua/" + relative, maximum
            )
        except urllib.error.HTTPError as exc:
            if not allow_404 or int(exc.code) != 404:
                raise
            status, body, content_type = 404, b"", ""
        metadata: dict[str, Any] = {
            "status": status, "sha256": _sha(body), "size": len(body),
            "content_type": content_type,
        }
        if status == 200 and relative not in html_paths:
            if relative.casefold().endswith(".jpg"):
                try:
                    width, height = _jpeg_dimensions(body)
                    metadata.update({"media_valid": True, "width": width, "height": height})
                except ControllerError:
                    metadata["media_valid"] = False
            elif relative.casefold().endswith(".mp4"):
                metadata["media_valid"] = len(body) >= 16 and body[4:8] == b"ftyp"
        return relative, metadata

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
    futures = {executor.submit(fetch, relative): relative for relative in sorted(relatives)}
    try:
        for future in concurrent.futures.as_completed(
            futures, timeout=max(0.1, deadline - time.monotonic())
        ):
            relative = futures[future]
            try:
                returned, metadata = future.result()
                if returned != relative:
                    raise ControllerError("PUBLIC_BATCH_RESULT_SCOPE")
                results[relative] = metadata
            except Exception as exc:
                errors.append(relative + ":HTTP:" + type(exc).__name__)
    except (TimeoutError, concurrent.futures.TimeoutError):
        errors.append("PUBLIC_BATCH_OVERALL_TIMEOUT")
    finally:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
    return results, errors


def public_verify(
    expected_media: Mapping[str, Mapping[str, Any]],
    expected_html: Mapping[str, Mapping[str, Any]],
    attempts: int = 9,
    overall_timeout: int = 300,
) -> dict[str, Any]:
    expected_paths = set(_target_media_paths())
    if set(expected_media) != expected_paths:
        raise ControllerError("PUBLIC_MEDIA_EXPECTATION_SCOPE")
    base = "https://www.uaart.com.ua/video/"
    html_urls = {
        "catalog": base + "katalog.html",
        "UA-0017": base + "UA-0017.html",
        "UA-0018": base + "UA-0018.html",
        "UA-0017-diag": base + "UA-0017-diag.html",
        "UA-0018-diag": base + "UA-0018-diag.html",
    }
    if set(expected_html) != set(html_urls):
        raise ControllerError("PUBLIC_HTML_EXPECTATION_SCOPE")
    for name, metadata in expected_html.items():
        if (
            not SHA_RE.fullmatch(str(metadata.get("sha256") or ""))
            or not isinstance(metadata.get("size"), int)
            or not 0 < int(metadata["size"]) <= 16 * 1024 * 1024
        ):
            raise ControllerError("PUBLIC_HTML_EXPECTATION:" + name)
    history: list[dict[str, Any]] = []
    consecutive = 0
    deadline = time.monotonic() + overall_timeout
    for attempt in range(1, attempts + 1):
        if time.monotonic() >= deadline:
            break
        errors: list[str] = []
        evidence: dict[str, Any] = {}
        html_values: dict[str, str] = {}
        for name, url in html_urls.items():
            try:
                status, body, content_type = _public_get(url, 16 * 1024 * 1024)
                text = body.decode("utf-8", "replace")
                html_values[name] = text
                evidence[name] = {
                    "status": status, "sha256": _sha(body), "size": len(body),
                    "content_type": content_type,
                }
                wanted = expected_html[name]
                if (
                    status != 200
                    or content_type != "text/html"
                    or "</html>" not in text.casefold()
                    or _sha(body) != wanted.get("sha256")
                    or len(body) != wanted.get("size")
                ):
                    errors.append(name + ":HTML_OR_HASH")
            except Exception as exc:
                errors.append(name + ":HTTP:" + type(exc).__name__)
        catalog = html_values.get("catalog", "")
        if catalog:
            ids = tuple(sorted(set(re.findall(r"UA-[0-9]{4}(?=\.html)", catalog, re.I))))
            card_counts = {
                uid: len(re.findall(
                    r"data-ua-card\s*=\s*['\"]" + re.escape(uid) + r"['\"]",
                    catalog,
                    re.I,
                ))
                for uid in EXPECTED_IDS
            }
            href_counts = {
                uid: len(re.findall(
                    r"href\s*=\s*['\"](?:[^'\"]*/)?" + re.escape(uid)
                    + r"\.html(?:\?[^'\"]*)?['\"]",
                    catalog,
                    re.I,
                ))
                for uid in EXPECTED_IDS
            }
            evidence["catalog"].update(
                {"unique_ids": list(ids), "semantic_card_counts": card_counts,
                 "href_counts": href_counts}
            )
            if (
                ids != EXPECTED_IDS
                or any(card_counts[uid] != 1 for uid in EXPECTED_IDS)
                or href_counts != {uid: 2 for uid in EXPECTED_IDS}
            ):
                errors.append("catalog:CONTRACT")
        for uid, vin, photos, specs, videos in (
            ("UA-0017", "WAUZZZ4GXGN069684", 39, 18, 0),
            ("UA-0018", "KNAG541BBPA224823", 36, 12, 1),
        ):
            text = html_values.get(uid, "")
            if text:
                refs = re.findall(
                    r"<img\b[^>]*\bsrc=['\"]foto/" + re.escape(uid)
                    + r"/([0-9]{3})\.jpg(?:\?[^'\"]*)?['\"]",
                    text,
                    re.I,
                )
                expected_refs = {"%03d" % index for index in range(1, photos + 1)}
                spec_rows = len(re.findall(
                    r"<div\b[^>]*class=['\"][^'\"]*\bua-addspec-row\b", text, re.I
                ))
                video_sources = len(re.findall(
                    r"<source\b[^>]*src=['\"]" + re.escape(uid) + r"\.mp4", text, re.I
                ))
                video_refs = re.findall(
                    r"(?:src|href)\s*=\s*['\"]([^'\"]*" + re.escape(uid)
                    + r"[^'\"]*\.mp4(?:\?[^'\"]*)?)['\"]", text, re.I
                )
                normalized_video_refs = {
                    reference.split("?", 1)[0].rsplit("/", 1)[-1].casefold()
                    for reference in video_refs
                }
                expected_video_names = {uid.casefold() + ".mp4"} if videos else set()
                evidence[uid].update(
                    {"photo_references": len(refs), "spec_rows": spec_rows,
                     "video_sources": video_sources}
                )
                lowered = text.casefold()
                if (
                    uid not in text
                    or vin not in text.upper()
                    or len(refs) != photos
                    or set(refs) != expected_refs
                    or spec_rows != specs
                    or "data-ua-additional-spec" not in lowered
                    or video_sources != videos
                    or normalized_video_refs != expected_video_names
                ):
                    errors.append(uid + ":CONTRACT")
            diag = html_values.get(uid + "-diag", "")
            if diag and (
                uid not in diag
                or not re.search(
                    r"href\s*=\s*['\"](?:[^'\"]*/)?" + re.escape(uid)
                    + r"\.html(?:\?[^'\"]*)?['\"]",
                    diag,
                    re.I,
                )
            ):
                errors.append(uid + ":DIAG_BINDING")
        for name, text in html_values.items():
            lowered = text.casefold()
            if any(marker in lowered for marker in (
                "carhistory.kr", "vindecoderz", "проверить vin", "перевірити vin"
            )):
                errors.append(name + ":VIN_AD")
        media_evidence: dict[str, Any] = {}
        fetched, fetch_errors = _public_batch(
            expected_paths, set(), deadline, allow_404=False
        )
        errors.extend(fetch_errors)
        for relative, actual in sorted(fetched.items()):
            kind = "mp4" if relative.endswith(".mp4") else "jpeg"
            media_evidence[relative] = actual
            expected_type = "video/mp4" if kind == "mp4" else "image/jpeg"
            valid = (
                actual.get("status") == 200
                and actual.get("content_type") == expected_type
                and actual.get("media_valid") is True
            )
            wanted = expected_media[relative]
            if (
                not valid
                or actual["sha256"] != wanted.get("sha256")
                or actual["size"] != wanted.get("size")
            ):
                errors.append(relative + ":CONTENT_OR_HASH")
        evidence["target_media"] = media_evidence
        snapshot = {
            "attempt": attempt,
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "evidence": evidence,
        }
        history.append(snapshot)
        consecutive = consecutive + 1 if not errors else 0
        if consecutive >= 3:
            return {
                "status": "PASS",
                "consecutive_passes": consecutive,
                "attempt": attempt,
                "history": history[-3:],
                "http_methods": ["GET"],
            }
        if attempt < attempts and time.monotonic() < deadline:
            time.sleep(5)
    return {
        "status": "FAIL",
        "consecutive_passes": consecutive,
        "attempt": len(history),
        "history": history[-3:],
        "errors": history[-1]["errors"] if history else ["OVERALL_TIMEOUT"],
        "http_methods": ["GET"],
    }


def public_preimage_verify(
    preimage: Mapping[str, Mapping[str, Any]],
    attempts: int = 9,
    overall_timeout: int = 300,
) -> dict[str, Any]:
    required_html = {
        "video/katalog.html", "video/UA-0016.html",
        "video/UA-0017.html", "video/UA-0017-diag.html",
        "video/UA-0018.html", "video/UA-0018-diag.html",
    }
    required = required_html | set(_target_media_paths())
    if set(preimage) != required:
        raise ControllerError("ROLLBACK_PUBLIC_PREIMAGE_INCOMPLETE")
    consecutive = 0
    history: list[dict[str, Any]] = []
    deadline = time.monotonic() + overall_timeout
    for attempt in range(1, attempts + 1):
        if time.monotonic() >= deadline:
            break
        errors: list[str] = []
        observed: dict[str, Any] = {}
        fetched, fetch_errors = _public_batch(
            required, required_html, deadline, allow_404=True
        )
        errors.extend(fetch_errors)
        for relative, actual in sorted(fetched.items()):
            expected = preimage[relative]
            observed[relative] = actual
            if expected.get("exists"):
                expected_type = (
                    "text/html" if relative in required_html
                    else "video/mp4" if relative.casefold().endswith(".mp4")
                    else "image/jpeg"
                )
                if (
                    actual.get("status") != 200
                    or actual.get("content_type") != expected_type
                    or actual.get("sha256") != expected.get("sha256")
                    or actual.get("size") != expected.get("size")
                ):
                    errors.append(relative + ":PREIMAGE_MISMATCH")
            elif actual.get("status") != 404:
                errors.append(relative + ":EXPECTED_404")
        history.append({"attempt": attempt, "errors": errors, "observed": observed})
        consecutive = consecutive + 1 if not errors else 0
        if consecutive >= 3:
            return {"status": "PASS", "consecutive_passes": consecutive,
                    "history": history[-3:], "http_methods": ["GET"]}
        if attempt < attempts and time.monotonic() < deadline:
            time.sleep(5)
    return {"status": "FAIL", "consecutive_passes": consecutive,
            "history": history[-3:], "http_methods": ["GET"]}


def _expected_public_html(verification: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    catalogs = verification.get("catalogs")
    pages = verification.get("pages")
    if not isinstance(catalogs, dict) or not isinstance(pages, dict):
        raise ControllerError("REMOTE_HTML_EVIDENCE")
    try:
        result = {
            "catalog": {
                "sha256": catalogs["video"]["sha256"],
                "size": catalogs["video"]["size"],
            }
        }
        for uid in ("UA-0017", "UA-0018"):
            item = pages["video/" + uid]
            result[uid] = {
                "sha256": item["primary"]["sha256"],
                "size": item["primary"]["size"],
            }
            result[uid + "-diag"] = {
                "sha256": item["diagnostic"]["sha256"],
                "size": item["diagnostic"]["size"],
            }
    except (KeyError, TypeError) as exc:
        raise ControllerError("REMOTE_HTML_EVIDENCE") from exc
    for name, metadata in result.items():
        if (
            not SHA_RE.fullmatch(str(metadata.get("sha256") or ""))
            or not isinstance(metadata.get("size"), int)
            or not 0 < int(metadata["size"]) <= 16 * 1024 * 1024
        ):
            raise ControllerError("REMOTE_HTML_EVIDENCE:" + name)
    return result


def execute(environment: Mapping[str, str]) -> dict[str, Any]:
    """Run the one-shot CRITICAL publication using backup A from the workflow."""
    values, _request = required(environment, "execute")
    evidence: dict[str, Any] = {
        "task_id": TASK_ID,
        "contract_id": CONTRACT_ID,
        "status": "FAIL",
        "started_at": _now(),
        "run_id": values["UAART_RUN_ID"],
        "transaction_id": values["UAART_TRANSACTION_ID"],
        "request_sha256": values["UAART_REQUEST_SHA256"],
        "manifest_sha256": values["UAART_MANIFEST_SHA256"],
        "backup_manifest_sha256": values["UAART_BACKUP_MANIFEST_SHA256"],
        "errors": [],
    }
    api: API | None = None
    script = b""
    script_sha = ""
    publication_started = False
    transport_claimed = False
    target = receipt_target(values)
    if target.exists():
        raise ControllerError("RECEIPT_PREEXISTING")
    try:
        script = REMOTE_SCRIPT_LOCAL.read_bytes()
        compile(script.decode("utf-8"), "remote_installer.py", "exec")
        script_sha = _sha(script)
        evidence["script_sha256"] = script_sha
        api = API(values["PYTHONANYWHERE_API_TOKEN"])
        api.claim_transport(script)
        transport_claimed = True

        # Backup A was created by backup_controller. The installer resolves
        # its immutable manifest by SHA, never by a substitute path.
        publication_started = True
        publish = api.run(
            "publish",
            script_sha,
            workflow_run_id=values["UAART_RUN_ID"],
            transaction_id=values["UAART_TRANSACTION_ID"],
            backup_sha=values["UAART_BACKUP_MANIFEST_SHA256"],
        )
        evidence["publish"] = publish
        validate_receipt(publish, "publish", script_sha)
        if publish.get("backup_manifest_sha256") != values["UAART_BACKUP_MANIFEST_SHA256"]:
            raise ControllerError("REMOTE_BACKUP_IDENTITY")
        verification = publish.get("verification") or {}
        if (
            verification.get("status") != "PASS"
            or verification.get("published_count") != 18
            or tuple(verification.get("published_ids") or ()) != EXPECTED_IDS
        ):
            raise ControllerError("REMOTE_FINAL_VERIFY")

        target_media = publish.get("target_media") or {}
        expected_public_media = target_media.get("files") if isinstance(target_media, dict) else None
        if not isinstance(expected_public_media, dict):
            raise ControllerError("REMOTE_MEDIA_EVIDENCE")
        expected_public_html = _expected_public_html(verification)
        public = public_verify(expected_public_media, expected_public_html)
        evidence["public"] = public
        if public.get("status") != "PASS":
            raise ControllerError("PUBLIC_VERIFY_FAILED")
        receipt = {
            "contract_id": CRITICAL_CONTRACT,
            "task_id": TASK_ID,
            "status": "FINISHED",
            "task_class": "CRITICAL",
            "target_environment": "production",
            "production_required": True,
            "production": "PASS",
            "tests": "PASS",
            "backup": str(publish.get("backup_manifest") or values["UAART_BACKUP_MANIFEST_SHA256"]),
            "backup_manifest_sha256": values["UAART_BACKUP_MANIFEST_SHA256"],
            "rollback": "PASS",
            "rollback_ready": True,
            "live_verify": "PASS",
            "request_sha256": values["UAART_REQUEST_SHA256"],
            "manifest_sha256": values["UAART_MANIFEST_SHA256"],
            "run_id": values["UAART_RUN_ID"],
            "transaction_id": values["UAART_TRANSACTION_ID"],
            "unexpected_changes": 0,
            "production_write": "EXACTLY_UA_0017_AND_UA_0018_PUBLICATION",
            "published_ids": list(EXPECTED_IDS),
            "newly_published_ids": ["UA-0017", "UA-0018"],
            "render_roots": ["site", "video"],
            "public_url_root": "https://www.uaart.com.ua/video/",
            "catalog_unique_ids": list(EXPECTED_IDS),
            "vin_advertisement_count": 0,
            "protected_files_unchanged": True,
            "crm_unchanged": True,
            "existing_media_unchanged": True,
            "target_media": publish.get("target_media"),
            "finished_at": _now(),
        }
        # Transport cleanup is pre-commit.  If either cleanup or the durable
        # receipt write fails, the exception enters the rollback branch below.
        api.release_transport(script)
        transport_claimed = False
        _atomic_json(target, receipt)
        evidence["status"] = "PASS"
        evidence["receipt_path"] = values["UAART_RECEIPT_PATH"]
    except Exception as exc:
        evidence["errors"].append(type(exc).__name__ + ":" + str(exc))
        stop_unconfirmed = isinstance(exc, RemoteStopUnconfirmed)
        if publication_started and api is not None and script_sha and not stop_unconfirmed:
            try:
                current = api.read(REMOTE_SCRIPT, missing=True)
                if current is None:
                    api.claim_transport(script)
                    transport_claimed = True
                elif current != script:
                    raise ControllerError("REMOTE_TRANSPORT_CHANGED")
                else:
                    transport_claimed = True
                rollback = api.run(
                    "rollback",
                    script_sha,
                    workflow_run_id=values["UAART_RUN_ID"],
                    transaction_id=values["UAART_TRANSACTION_ID"],
                    backup_sha=values["UAART_BACKUP_MANIFEST_SHA256"],
                )
                evidence["rollback"] = rollback
                validate_receipt(rollback, "rollback", script_sha)
                if rollback.get("backup_manifest_sha256") != values["UAART_BACKUP_MANIFEST_SHA256"]:
                    raise ControllerError("REMOTE_BACKUP_IDENTITY")
                proof = rollback.get("rollback") or {}
                if (
                    proof.get("status") != "PASS"
                    or (proof.get("web") or {}).get("status") != "PASS"
                    or (proof.get("media") or {}).get("status") != "PASS"
                    or (proof.get("flags") or {}).get("status") != "PASS"
                    or (proof.get("crm") or {}).get("status") != "UNCHANGED"
                    or (proof.get("spec") or {}).get("status") != "UNCHANGED"
                    or (proof.get("protected_media") or {}).get("status") != "UNCHANGED"
                    or (proof.get("prevalidation") or {}).get("status") != "PASS"
                ):
                    raise ControllerError("REMOTE_ROLLBACK_PROOF")
                rollback_public = public_preimage_verify(proof.get("public_preimage") or {})
                evidence["rollback_public"] = rollback_public
                if rollback_public.get("status") != "PASS":
                    raise ControllerError("PUBLIC_ROLLBACK_VERIFY")
            except Exception as rollback_exc:
                evidence["errors"].append(
                    "ROLLBACK_FAILED:" + type(rollback_exc).__name__ + ":" + str(rollback_exc)
                )
        elif stop_unconfirmed:
            evidence["errors"].append("ROLLBACK_SKIPPED:UNFENCED_REMOTE_TRIGGER")
    finally:
        if transport_claimed and api is not None:
            try:
                api.release_transport(script)
                transport_claimed = False
            except Exception as release_exc:
                evidence["errors"].append(
                    "TRANSPORT_RELEASE_FAILED:"
                    + type(release_exc).__name__ + ":" + str(release_exc)
                )
    evidence["finished_at"] = _now()
    _atomic_json(_repo_path(EVIDENCE_REL), evidence)
    return evidence


def main() -> int:
    value = execute(os.environ)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
