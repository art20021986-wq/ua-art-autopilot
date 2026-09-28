"""Task-scoped PythonAnywhere transport; importing this module has no effects.

Admission, installation policy, provider pause/recovery and final workflow receipts
belong to the caller and the hash-bound remote worker.  This layer only stages an
exact admitted byte set and starts the fixed worker command.  It has no console,
schedule, arbitrary-command, retry-after-uncertainty or credential-file path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import PurePosixPath
import re
import shlex
import time
from typing import Any, Callable, Mapping
import urllib.error
import urllib.parse
import urllib.request
import uuid


TASK_ID = "UA-ART-CRM-DELETE-RECOVERY-002-INSTALL"
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
STAGE_PARENT = "/home/Carix/uploads"
STAGE_PREFIX = "uaart-crm-delete-recovery-002-"
CONTEXT_SCHEMA = "ua-art-crm-delete-recovery-002-transport-v1"
RECEIPT_SCHEMA = "ua-art-crm-delete-recovery-002-remote-receipt-v1"
READY_SCHEMA = "ua-art-crm-delete-recovery-002-stage-ready-v1"
MAX_BYTES = 64 * 1024 * 1024
# The phase owner also uses the provider API.  Two actors at this interval stay
# below the shared forty-request/minute budget without a burst allowance.
MIN_REQUEST_INTERVAL = 3.2
SHA_RE = re.compile(r"[0-9a-f]{64}")
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
PATH_RE = re.compile(r"[A-Za-z0-9_./-]{1,240}")
OPERATIONS = frozenset({"backup", "execute", "rollback"})
WORKER_FILES = frozenset({"remote_worker.py", "lifecycle_controller.py",
                          "lifecycle_worker.py", "package_install.py", "watchdog.py"})
READ_SOURCE_PATHS = frozenset(
    "/home/Carix/" + name for name in (
        "cars_ui.py", "db.py", "run_all.py", "start_safe.py", "publication_fence.py",
        "ua_site_counters.py", "ua_crm_catalog_folders.py", "ua_stage_catalog_sync.py",
        "ua_additional_spec.py", "uaart_connection_monitor.py", "kadry_diagnostiki.py",
        "publikaciya.py", "publish_transaction_guard.py", "stranica.py",
        "ua_spec84_runtime.py", "ua_spec_permanent.py", "yadro.py")) | frozenset({
    "/var/www/www_uaart_com_ua_wsgi.py",
    "/home/Carix/autopilot_inbox/cloud/seo_rehab_guard_068/seo_rehab_guard_068_repair.py",
    "/home/Carix/uploads/ua0002_job/console-result.json",
    "/home/Carix/uploads/ua0002_job/plan.json",
})


class TransportError(RuntimeError):
    """An exact transport precondition or verified remote result failed."""


class RemoteOutcomeUncertain(TransportError):
    """Do not retry, release staged files, or infer a production outcome."""


class RemoteOperationFailed(TransportError):
    """Verified terminal remote failure; the paired receipt remains available."""
    def __init__(self, receipt):
        super().__init__("REMOTE_OPERATION_FAILED")
        self.receipt = receipt


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise TransportError(code)


def _relative(value: str) -> str:
    _require(isinstance(value, str) and bool(PATH_RE.fullmatch(value)), "STAGE_FILE_PATH")
    path = PurePosixPath(value)
    _require(bool(path.parts) and not path.is_absolute() and str(path) == value and
             all(part not in (".", "..") for part in path.parts), "STAGE_FILE_PATH")
    return value


def _digest(value: Any, code: str) -> str:
    _require(isinstance(value, str) and bool(SHA_RE.fullmatch(value)), code)
    return value


@dataclass(frozen=True)
class Payload:
    relative_path: str
    content: bytes = field(repr=False)
    sha256: str


@dataclass(frozen=True)
class TransportBundle:
    identity: Mapping[str, str]
    files: tuple[Payload, ...] = field(repr=False)
    parameters: Mapping[str, Any]
    operation: str


@dataclass(frozen=True)
class StageContext:
    remote_dir: str
    context_sha256: str
    context_bytes: bytes = field(repr=False)
    bootstrap_path: str
    bootstrap_bytes: bytes = field(repr=False)
    files: tuple[Payload, ...] = field(repr=False)
    operation: str

    @property
    def context(self) -> dict[str, Any]:
        return json.loads(self.context_bytes)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        # Never forward an authenticated API request to another URL.
        return None


class PythonAnywhereTransport:
    """Injected request/clock/sleep are test seams, never environment options.

    request(method, url, data=None, headers=None, allowed=(200,)) returns
    (status, bytes).  Production uses stdlib urllib with no redirects.  Both
    implementations pass through this class's size/status and identity checks.
    """

    def __init__(self, token: str, *, request: Callable | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        _require(isinstance(token, str) and 0 < len(token) <= 1024 and
                 not any(char in token for char in "\r\n\0"), "API_TOKEN_REQUIRED")
        self._token = token
        self._io = request or self._http
        self._clock, self._sleep = clock, sleep
        self._stages: dict[str, dict[str, Any]] = {}
        self.remote_fenced = True
        self._last_request_at: float | None = None

    def _http(self, method, url, data=None, headers=None, allowed=(200,)):
        actual = {"Authorization": "Token " + self._token,
                  "User-Agent": "ua-art-crm-delete-recovery-002/1"}
        actual.update(headers or {})
        request = urllib.request.Request(url, data=data, headers=actual, method=method)
        try:
            with urllib.request.build_opener(_NoRedirect).open(request, timeout=30) as response:
                return int(response.status), response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as error:
            return int(error.code), error.read(MAX_BYTES + 1)
        except Exception:
            # Deliberately omit exception text, request headers and chained causes.
            raise TransportError("API_NETWORK_ERROR") from None

    def _request(self, method, url, data=None, headers=None, allowed=(200,)):
        _require(url.startswith(BASE), "API_URL_SCOPE")
        if self._last_request_at is not None:
            remaining = MIN_REQUEST_INTERVAL - (self._clock() - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._clock()
        try:
            status, body = self._io(method, url, data=data, headers=headers, allowed=allowed)
        except TransportError:
            raise
        except Exception:
            raise TransportError("API_REQUEST_ERROR") from None
        _require(type(status) is int and isinstance(body, bytes), "API_RESPONSE_TYPE")
        _require(len(body) <= MAX_BYTES, "API_RESPONSE_TOO_LARGE")
        _require(status in allowed, "API_HTTP_STATUS_%d" % status)
        return status, body

    def read_source(self, remote_path: str, expected_sha256: str) -> bytes:
        """GET one explicitly listed dependency after the caller admits its hash."""
        _require(remote_path in READ_SOURCE_PATHS, "READ_SOURCE_SCOPE")
        _digest(expected_sha256, "READ_SOURCE_DIGEST")
        _, raw = self._request("GET", BASE + "files/path" + urllib.parse.quote(remote_path, safe="/"))
        _require(sha256(raw) == expected_sha256, "READ_SOURCE_HASH_MISMATCH")
        return raw

    def read_backup_file(self, package_sha256: str, transaction_id: str,
                         filename: str, expected_sha256: str) -> bytes:
        """Read only hash-bound code backup metadata/images; never database files."""
        _digest(package_sha256, "BACKUP_PACKAGE_DIGEST")
        _digest(expected_sha256, "BACKUP_FILE_DIGEST")
        _require(isinstance(transaction_id, str) and
                 re.fullmatch(r"tx-[A-Za-z0-9._-]{16,120}", transaction_id) is not None,
                 "BACKUP_TRANSACTION_ID")
        _require(isinstance(filename, str) and (filename in {
            "phase_backup_manifest.json", "backup_manifest.json", "wsgi.before"} or
            re.fullmatch(r"[0-9]+\.before", filename) is not None), "BACKUP_FILE_SCOPE")
        transaction_hash = sha256(transaction_id.encode())[:20]
        folder = "/home/Carix/ua_crm_installation_state/install-" + package_sha256[:20] + "-" + transaction_hash
        path = folder + "/" + filename
        _, raw = self._request("GET", BASE + "files/path" + urllib.parse.quote(path, safe="/"))
        _require(sha256(raw) == expected_sha256, "BACKUP_FILE_HASH_MISMATCH")
        return raw

    @staticmethod
    def _file_url(stage: StageContext, path: str) -> str:
        root = PurePosixPath(stage.remote_dir)
        candidate = PurePosixPath(path)
        _require(str(candidate) == path and ".." not in candidate.parts and
                 (root in candidate.parents or path == stage.bootstrap_path), "REMOTE_FILE_SCOPE")
        return BASE + "files/path" + urllib.parse.quote(path, safe="/")

    def _read(self, stage, path, *, missing=False):
        status, body = self._request("GET", self._file_url(stage, path), allowed=(200, 404))
        if status == 404:
            _require(missing, "REMOTE_FILE_MISSING")
            return None
        return body

    def _upload(self, stage, path, value):
        boundary = "----uaart-crm-recovery-" + uuid.uuid4().hex
        name = PurePosixPath(path).name
        prefix = ("--%s\r\nContent-Disposition: form-data; name=\"content\"; "
                  "filename=\"%s\"\r\nContent-Type: application/octet-stream\r\n\r\n" %
                  (boundary, name)).encode()
        body = prefix + value + ("\r\n--%s--\r\n" % boundary).encode()
        self._request("POST", self._file_url(stage, path), data=body,
                      headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
                      allowed=(200, 201))
        _require(self._read(stage, path) == value, "UPLOAD_READBACK_MISMATCH")

    def _delete_exact(self, stage, path, expected):
        current = self._read(stage, path, missing=True)
        if current is None:
            return
        _require(current == expected, "RELEASE_SOURCE_CHANGED")
        self._request("DELETE", self._file_url(stage, path), allowed=(200, 202, 204, 404))
        _require(self._read(stage, path, missing=True) is None, "RELEASE_DELETE_UNCONFIRMED")

    def _start(self, command, description):
        _require(self.remote_fenced, "PRIOR_TRIGGER_NOT_FENCED")
        self.remote_fenced = False  # Set before POST: a network error can hide a created task.
        form = urllib.parse.urlencode({"command": command, "description": description,
                                      "enabled": "true"}).encode()
        try:
            _, raw = self._request("POST", BASE + "always_on/", data=form,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                allowed=(200, 201, 202))
            value = json.loads(raw)
            identifier = value.get("id") if isinstance(value, dict) else None
            _require(type(identifier) is int and identifier > 0, "TRIGGER_ID_MISSING")
            return identifier
        except Exception:
            raise RemoteOutcomeUncertain("REMOTE_TRIGGER_CREATION_UNCONFIRMED") from None

    def _stop(self, identifier):
        detail = BASE + "always_on/%d/" % identifier
        try:
            self._request("DELETE", detail, allowed=(200, 202, 204, 404))
            for attempt in range(12):
                status, _ = self._request("GET", detail, allowed=(200, 404))
                if status == 404:
                    self.remote_fenced = True
                    return
                if attempt < 11:
                    self._sleep(1)
        except Exception:
            pass
        self.remote_fenced = False
        raise RemoteOutcomeUncertain("REMOTE_TRIGGER_STOP_UNCONFIRMED") from None

    def _poll(self, stage, path, timeout):
        _require(type(timeout) in (int, float) and math.isfinite(timeout) and
                 0 < timeout <= 1800, "POLL_TIMEOUT_RANGE")
        deadline = self._clock() + timeout
        # A bounded attempt count also protects against a broken injected clock.
        for attempt in range(math.ceil(timeout / 2) + 1):
            raw = self._read(stage, path, missing=True)
            if raw is not None:
                return raw
            remaining = deadline - self._clock()
            if remaining <= 0:
                break
            self._sleep(min(2, remaining))
        raise RemoteOutcomeUncertain("REMOTE_RESULT_TIMEOUT")

    @staticmethod
    def _bootstrap(stage_dir, context_sha, files):
        parents = {str(PurePosixPath(name).parent) for name in files}
        directories = sorted({str(parent) for name in parents for parent in
                              (PurePosixPath(name), *PurePosixPath(name).parents)
                              if str(parent) != "."}, key=lambda value: (value.count("/"), value))
        # Every substituted value is a validated path/digest rendered as a Python
        # literal.  This fixed program only makes its unique private stage.
        return ('''import hashlib, json, os, pathlib, sys
os.umask(0o077)
source = pathlib.Path(__file__)
if len(sys.argv) != 3 or sys.argv[1] != '--expected-script-sha256' or hashlib.sha256(source.read_bytes()).hexdigest() != sys.argv[2]:
    raise RuntimeError('BOOTSTRAP_SOURCE_BINDING')
parent = pathlib.Path(%r)
if parent.resolve(strict=True) != parent or not parent.is_dir() or parent.stat().st_uid != os.getuid():
    raise RuntimeError('STAGE_PARENT_BINDING')
stage = pathlib.Path(%r)
stage.mkdir(mode=0o700)
if stage.resolve(strict=True) != stage or stage.stat().st_mode & 0o777 != 0o700:
    raise RuntimeError('PRIVATE_STAGE_REQUIRED')
for relative in %r:
    (stage / relative).mkdir(mode=0o700)
source.chmod(0o600)
receipt = %r
raw = (json.dumps(receipt, sort_keys=True, separators=(',', ':')) + '\\n').encode()
fd = os.open(str(stage / 'stage-ready.json'), os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
with os.fdopen(fd, 'wb') as output:
    output.write(raw)
    output.flush()
    os.fsync(output.fileno())
directory = os.open(str(stage), os.O_RDONLY | os.O_DIRECTORY)
try:
    os.fsync(directory)
finally:
    os.close(directory)
''' % (STAGE_PARENT, stage_dir, directories, {
            "schema": READY_SCHEMA, "task_id": TASK_ID, "context_sha256": context_sha,
            "stage": stage_dir, "mode": 0o700, "status": "READY"})).encode()

    def claim_transport(self, bundle: TransportBundle, *, timeout=60) -> StageContext:
        _require(self.remote_fenced, "PRIOR_TRIGGER_NOT_FENCED")
        _require(type(timeout) in (int, float) and math.isfinite(timeout) and
                 0 < timeout <= 1800, "POLL_TIMEOUT_RANGE")
        _require(isinstance(bundle, TransportBundle), "TRANSPORT_BUNDLE_REQUIRED")
        _require(bundle.operation in OPERATIONS, "OPERATION_SCOPE")
        identity = dict(bundle.identity)
        _require(set(identity) == {"task_id", "workflow_run_id", "transaction_id",
                                  "request_sha256", "manifest_sha256"}, "IDENTITY_FIELDS")
        _require(identity["task_id"] == TASK_ID, "TASK_IDENTITY")
        _require(isinstance(identity["workflow_run_id"], str) and
                 re.fullmatch(r"[0-9]{1,30}", identity["workflow_run_id"]) is not None and
                 isinstance(identity["transaction_id"], str) and
                 re.fullmatch(r"tx-[A-Za-z0-9._-]{16,120}", identity["transaction_id"]) is not None,
                 "RUNTIME_IDENTITY")
        for key in ("request_sha256", "manifest_sha256"):
            _digest(identity[key], "ENVELOPE_DIGEST")
        files = tuple(bundle.files)
        _require(5 <= len(files) <= 250 and all(isinstance(item, Payload) for item in files),
                 "PAYLOAD_SET")
        hashes, total = {}, 0
        reserved = {"context.json", "stage-ready.json", "watchdog-context.json", "watchdog-ready.json",
                    "watchdog-result.json", "watchdog-outcome.json", "watchdog-terminal.json",
                    "phase-journal.json", "phase.lock"}
        reserved.update("%s-%s.json" % (kind, operation)
                        for kind in ("result", "completed") for operation in OPERATIONS)
        for item in files:
            name = _relative(item.relative_path)
            _require(name not in hashes and PurePosixPath(name).name not in reserved and
                     not PurePosixPath(name).name.startswith(("result-", "completed-")) and
                     not any(str(parent) in reserved for parent in PurePosixPath(name).parents),
                     "PAYLOAD_PATH_CONFLICT")
            _require(isinstance(item.content, bytes) and len(item.content) <= 8 * 1024 * 1024,
                     "PAYLOAD_BYTES_REQUIRED")
            _require(_digest(item.sha256, "PAYLOAD_DIGEST") == sha256(item.content), "PAYLOAD_HASH_MISMATCH")
            hashes[name] = item.sha256
            total += len(item.content)
        _require(total <= MAX_BYTES and WORKER_FILES.issubset(hashes), "PAYLOAD_SCOPE_OR_SIZE")
        _require(not any(any(str(parent) in hashes for parent in PurePosixPath(name).parents)
                         for name in hashes), "PAYLOAD_PARENT_CONFLICT")
        parameters = dict(bundle.parameters)
        _require(set(parameters) == {"plan_path", "plan_sha256", "installation_policy_sha256",
                                     "backup_manifest_sha256"}, "PARAMETER_FIELDS")
        plan_relative = _relative(parameters["plan_path"])
        _require(plan_relative in hashes and parameters["plan_sha256"] == hashes[plan_relative], "PLAN_BINDING")
        _digest(parameters["installation_policy_sha256"], "INSTALLATION_POLICY_DIGEST")
        if bundle.operation == "backup":
            _require(parameters["backup_manifest_sha256"] is None, "BACKUP_OPERATION_BINDING")
        else:
            _digest(parameters["backup_manifest_sha256"], "BACKUP_MANIFEST_DIGEST")
        stage_dir = STAGE_PARENT + "/" + STAGE_PREFIX + uuid.uuid4().hex
        parameters["plan_path"] = stage_dir + "/" + plan_relative
        value = dict(identity, schema=CONTEXT_SCHEMA, stage=stage_dir, files=hashes,
                     parameters=parameters, operation=bundle.operation)
        raw = canonical(value)
        context_sha = sha256(raw)
        bootstrap = self._bootstrap(stage_dir, context_sha, hashes)
        stage = StageContext(stage_dir, context_sha, raw, stage_dir + ".py", bootstrap,
                             files, bundle.operation)
        self._stages[context_sha] = {"stage": stage, "phase": "CLAIMING"}
        _require(self._read(stage, stage.bootstrap_path, missing=True) is None and
                 self._read(stage, stage_dir + "/stage-ready.json", missing=True) is None,
                 "STAGE_ALREADY_EXISTS")
        self._upload(stage, stage.bootstrap_path, bootstrap)
        command = shlex.join(["python3.10", "-I", "-B", stage.bootstrap_path,
                              "--expected-script-sha256", sha256(bootstrap)])
        identifier = self._start(command, TASK_ID + " prepare")
        try:
            ready = self._poll(stage, stage_dir + "/stage-ready.json", timeout)
        finally:
            self._stop(identifier)
        expected_ready = canonical({"schema": READY_SCHEMA, "task_id": TASK_ID,
            "context_sha256": context_sha, "stage": stage_dir, "mode": 0o700, "status": "READY"})
        _require(ready == expected_ready and
                 self._read(stage, stage_dir + "/stage-ready.json") == ready,
                 "PRIVATE_STAGE_READBACK")
        for item in files:
            destination = stage_dir + "/" + item.relative_path
            _require(self._read(stage, destination, missing=True) is None, "STAGED_FILE_ALREADY_EXISTS")
            self._upload(stage, destination, item.content)
        self._upload(stage, stage_dir + "/context.json", raw)
        self._stages[context_sha]["phase"] = "CLAIMED"
        return stage

    def _state(self, stage):
        _require(isinstance(stage, StageContext), "OWNED_STAGE_REQUIRED")
        state = self._stages.get(stage.context_sha256)
        _require(state is not None and state["stage"] is stage, "OWNED_STAGE_REQUIRED")
        return state

    def run(self, stage: StageContext, operation: str | None = None, *, timeout=900):
        state = self._state(stage)
        operation = operation or stage.operation
        _require(state["phase"] == "CLAIMED" and operation == stage.operation, "STAGE_OPERATION_STATE")
        _require(self.remote_fenced, "PRIOR_TRIGGER_NOT_FENCED")
        _require(type(timeout) in (int, float) and math.isfinite(timeout) and
                 0 < timeout <= 1800, "POLL_TIMEOUT_RANGE")
        # A second full read-back binds execution to the exact admitted closure.
        _require(self._read(stage, stage.remote_dir + "/context.json") == stage.context_bytes,
                 "CONTEXT_READBACK_MISMATCH")
        for item in stage.files:
            _require(self._read(stage, stage.remote_dir + "/" + item.relative_path) == item.content,
                     "STAGED_SOURCE_DRIFT")
        result_path = stage.remote_dir + "/result-" + operation + ".json"
        completed_path = stage.remote_dir + "/completed-" + operation + ".json"
        _require(self._read(stage, result_path, missing=True) is None and
                 self._read(stage, completed_path, missing=True) is None, "PREEXISTING_REMOTE_RESULT")
        command = shlex.join(["python3.10", "-I", "-B", stage.remote_dir + "/remote_worker.py",
            "--context", stage.remote_dir + "/context.json", "--context-sha256",
            stage.context_sha256, "--operation", operation])
        state["phase"] = "STARTING"
        identifier = self._start(command, TASK_ID + " " + operation)
        state["trigger_id"] = identifier
        try:
            raw = self._poll(stage, result_path, timeout)
            _require(self._read(stage, result_path) == raw and
                     self._read(stage, completed_path) == raw, "REMOTE_RECEIPT_PAIR_MISMATCH")
            value = json.loads(raw)
            _require(isinstance(value, dict) and canonical(value) == raw, "REMOTE_RECEIPT_CANONICAL")
            expected = {key: stage.context[key] for key in
                        ("task_id", "workflow_run_id", "transaction_id", "request_sha256", "manifest_sha256")}
            expected.update(schema=RECEIPT_SCHEMA, context_sha256=stage.context_sha256, operation=operation)
            _require(all(value.get(key) == wanted for key, wanted in expected.items()), "REMOTE_RECEIPT_IDENTITY")
            _require(value.get("status") in ("PASS", "FAIL") and value.get("safe_to_stop") is True,
                     "REMOTE_RECEIPT_NOT_TERMINAL")
        except TransportError as error:
            # Terminating an uncertain owner can also terminate its recovery
            # watchdog.  Keep the task and all staged evidence intact.
            raise RemoteOutcomeUncertain(str(error)) from None
        except (ValueError, UnicodeDecodeError, TypeError):
            raise RemoteOutcomeUncertain("REMOTE_RECEIPT_PARSE") from None
        state["phase"] = "TERMINAL_UNFENCED"
        self._stop(identifier)
        _require(self._read(stage, result_path) == raw and self._read(stage, completed_path) == raw,
                 "REMOTE_RECEIPT_POST_STOP_DRIFT")
        state["phase"] = "VERIFIED"
        state["receipt"] = raw
        if value["status"] != "PASS":
            raise RemoteOperationFailed(value)
        return value

    def release_transport(self, stage: StageContext):
        state = self._state(stage)
        _require(self.remote_fenced and state["phase"] in ("CLAIMED", "VERIFIED"),
                 "RELEASE_REQUIRES_CONFIRMED_STOP_AND_OUTCOME")
        # Retain context, payloads and receipts inside the private stage as audit
        # evidence; remove only the two executable entrypoints, by exact content.
        worker = next(item for item in stage.files if item.relative_path == "remote_worker.py")
        self._delete_exact(stage, stage.remote_dir + "/remote_worker.py", worker.content)
        self._delete_exact(stage, stage.bootstrap_path, stage.bootstrap_bytes)
        state["phase"] = "RELEASED"
