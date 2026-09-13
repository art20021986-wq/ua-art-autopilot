#!/usr/bin/env python3
"""Exact, backed-up Stage 2 source installation; full acceptance stays separate.

FINISHED here means installation and source/database read-only verification only.
This controller never creates TASK088-GE-PRICE-CRM-STAGE2.json as a receipt and
never calls a publisher, restarts the site, or claims Telegram acceptance.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
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

PARENT_ID = "TASK088-GE-PRICE-CRM-STAGE2"
TASK_ID = PARENT_ID + "-INSTALL"
STAGE1_ID = "TASK088-GE-PRICE-CRM-STAGE1"
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PACKAGE = "cloud/task_088_ge_price_crm_stage2"
REQUEST_REL = "tasks/requests/" + TASK_ID + ".json"
RECEIPT_REL = "state/receipts/" + TASK_ID + ".json"
BACKUP_RECEIPT_REL = "state/receipts/" + TASK_ID + "-BACKUP.json"
ROLLBACK_RECEIPT_REL = "state/receipts/" + TASK_ID + "-ROLLBACK.json"
EVIDENCE_REL = PACKAGE + "/installation_evidence.json"
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE_ROOT = "/home/Carix/autopilot_inbox/cloud/task_088_ge_price_crm_stage2/runs"
SOURCES = ("remote_installer.py", "patcher.py", "runtime.py")
TARGETS = frozenset(("production/operator-ui/cars_ui.py", "production/crm.db"))
BINDINGS = ("task_id", "run_id", "request_sha256", "transaction_id", "manifest_sha256")
MAX_BYTES = 8 * 1024 * 1024
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
SCOPE = "INSTALLATION_AND_SOURCE_DB_READONLY_VERIFY"


class ControllerError(RuntimeError):
    """Only fixed codes, never tokens or raw network bodies, leave the process."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ControllerError("HTTP_REDIRECT_REFUSED")


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()


def require_sha(value, code):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) or value == "0" * 64:
        raise ControllerError(code)
    return value


def atomic_new(path, value):
    """Receipts are outputs: preserve an existing receipt instead of replacing it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".stage2-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical(value)); handle.flush(); os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        pathlib.Path(temporary).unlink(missing_ok=True)


def repo_file(relative):
    if not isinstance(relative, str) or not re.fullmatch(r"[A-Za-z0-9._/-]+", relative):
        raise ControllerError("REPO_PATH")
    rel = pathlib.PurePosixPath(relative)
    path = ROOT / relative
    if (rel.is_absolute() or ".." in rel.parts or str(rel) != relative
            or path.resolve() != path.absolute() or not path.is_file()):
        raise ControllerError("REPO_PATH")
    return path


def bindings(values):
    return {key: values["UAART_" + key.upper()] for key in BINDINGS}


def validate_deployment(plan):
    if not isinstance(plan, dict) or plan.get("readiness") != "READY":
        raise ControllerError("LIVE_PREFLIGHT_NOT_READY")
    fixed = {"source_path": "/home/Carix/cars_ui.py", "db_path": "/home/Carix/crm.db",
             "db_module_path": "/home/Carix/db.py", "parser_path": "/home/Carix/price_parser.py",
             "utils_path": "/home/Carix/cars_schema.py",
             "stage1_receipt_path": "/home/Carix/autopilot_inbox/cloud/task_088_ge_price_crm_stage1/receipt.json"}
    if any(plan.get(key) != value for key, value in fixed.items()):
        raise ControllerError("DEPLOYMENT_PATH_SCOPE")
    if not isinstance(plan.get("nonce"), str) or not re.fullmatch(r"[A-Za-z0-9._-]{16,140}", plan["nonce"]):
        raise ControllerError("DEPLOYMENT_NONCE_REQUIRED")
    for key in ("expected_source_sha256", "expected_candidate_sha256", "expected_stage1_receipt_sha256"):
        require_sha(plan.get(key), "DEPLOYMENT_" + key.upper())
    dependencies = plan.get("expected_dependency_sha256")
    if not isinstance(dependencies, dict) or not dependencies:
        raise ControllerError("LIVE_DEPENDENCY_HASHES_REQUIRED")
    absent = plan.get("expected_absent_dependency_paths", [])
    if (not isinstance(absent, list) or len(absent) != len(set(absent))
            or any(path != fixed["parser_path"] for path in absent)
            or set(absent) & set(dependencies)):
        raise ControllerError("ABSENT_DEPENDENCY_SCOPE")
    required_paths = {fixed[key] for key in ("db_module_path", "utils_path")}
    if fixed["parser_path"] not in absent:
        required_paths.add(fixed["parser_path"])
    if not required_paths.issubset(dependencies):
        raise ControllerError("LIVE_DEPENDENCY_HASHES_INCOMPLETE")
    for path, digest in dependencies.items():
        pure = pathlib.PurePosixPath(path)
        if pure.parent != pathlib.PurePosixPath("/home/Carix") or pure.suffix != ".py":
            raise ControllerError("LIVE_DEPENDENCY_SCOPE")
        require_sha(digest, "LIVE_DEPENDENCY_SHA")
    process = plan.get("exact_process")
    if not isinstance(process, dict):
        raise ControllerError("EXACT_CRM_PROCESS_REQUIRED")
    if "command_argv" in process:
        if (process.get("command_argv") != ["python3.10", "/home/Carix/start_safe.py"]
                or process.get("supervisor_id") != 266084):
            raise ControllerError("EXACT_CRM_COMMAND_SCOPE")
        if process.get("verification_mode") not in (None, "authenticated_supervisor"):
            raise ControllerError("PROCESS_VERIFICATION_MODE")
    else:
        if (type(process.get("pid")) is not int or process["pid"] <= 1
                or not re.fullmatch(r"[1-9][0-9]*", str(process.get("start_ticks", "")))):
            raise ControllerError("EXACT_CRM_PROCESS_REQUIRED")
        require_sha(process.get("cmdline_sha256"), "EXACT_CRM_PROCESS_SHA")
    quota = plan.get("quota")
    if not isinstance(quota, dict) or quota.get("target_environment") != "production" or quota.get("read_only") is not True:
        raise ControllerError("TARGET_QUOTA_REQUIRED")
    if any(type(quota.get(key)) is not int for key in ("total_bytes", "used_bytes", "free_bytes")):
        raise ControllerError("TARGET_QUOTA_BYTES")
    total, used, free = (quota[key] for key in ("total_bytes", "used_bytes", "free_bytes"))
    if total <= 0 or used < 0 or used >= total * 0.8 or free != total - used:
        raise ControllerError("TARGET_QUOTA_NOT_SAFE")
    return dict(plan)


def required(environment, operation):
    receipts = {"backup": BACKUP_RECEIPT_REL, "execute": RECEIPT_REL, "rollback": ROLLBACK_RECEIPT_REL}
    if operation not in receipts:
        raise ControllerError("OPERATION")
    names = ("PYTHONANYWHERE_API_TOKEN", "UAART_REQUEST_PATH", "UAART_REQUEST_SHA256",
             "UAART_TASK_ID", "UAART_TASK_CLASS", "UAART_RUN_ID", "UAART_RECEIPT_PATH",
             "UAART_TRANSACTION_ID", "UAART_MANIFEST_SHA256", "UAART_OPERATION")
    values = {name: str(environment.get(name, "")).strip() for name in names}
    if any(not value or any(char in value for char in "\r\n\0") for value in values.values()):
        raise ControllerError("MISSING_ENVIRONMENT")
    if (values["UAART_TASK_ID"] != TASK_ID or values["UAART_TASK_CLASS"] != "CRITICAL"
            or values["UAART_OPERATION"] != operation or values["UAART_RECEIPT_PATH"] != receipts[operation]
            or values["UAART_REQUEST_PATH"] != REQUEST_REL):
        raise ControllerError("INSTALLATION_IDENTITY")
    if operation != "execute" and environment.get("UAART_" + operation.upper() + "_RECEIPT_PATH") != receipts[operation]:
        raise ControllerError("AUXILIARY_RECEIPT_IDENTITY")
    if not re.fullmatch(r"[0-9]{1,30}", values["UAART_RUN_ID"]) or not re.fullmatch(r"[A-Za-z0-9._-]{1,180}", values["UAART_TRANSACTION_ID"]):
        raise ControllerError("RUN_IDENTITY")
    for key in ("UAART_REQUEST_SHA256", "UAART_MANIFEST_SHA256"):
        require_sha(values[key], "SHA_IDENTITY")
    raw = repo_file(REQUEST_REL).read_bytes()
    request = json.loads(raw)
    if sha(raw) != values["UAART_REQUEST_SHA256"] or request.get("task_id") != TASK_ID:
        raise ControllerError("REQUEST_IDENTITY")
    execution, critical = request.get("execution", {}), request.get("critical", {})
    if (request.get("production_required") is not True or execution.get("production_required") is not True
            or request.get("read_only") is not False or set(request.get("changed_paths", [])) != TARGETS
            or critical.get("gate_b_authorized") is not True or critical.get("allow_crm_vehicle_data") is not True):
        raise ControllerError("PROTECTED_INSTALLATION_SCOPE")
    expected = {"controller_path": PACKAGE + "/controller.py", "receipt_path": RECEIPT_REL,
                "backup_receipt_path": BACKUP_RECEIPT_REL, "rollback_receipt_path": ROLLBACK_RECEIPT_REL}
    if any(execution.get(key) != value for key, value in expected.items()):
        raise ControllerError("EXECUTION_IDENTITY")
    manifest = json.loads(repo_file(critical.get("manifest_path")).read_bytes())
    if (sha(canonical(manifest)) != values["UAART_MANIFEST_SHA256"]
            or critical.get("manifest_sha256") != values["UAART_MANIFEST_SHA256"]
            or manifest.get("task_id") != TASK_ID or manifest.get("parent_task_id") != PARENT_ID):
        raise ControllerError("MANIFEST_IDENTITY")
    if manifest.get("acceptance_scope") != SCOPE or manifest.get("stage3_allowed") is not False:
        raise ControllerError("INSTALLATION_ACCEPTANCE_SCOPE")
    operations = manifest.get("operations", [])
    if (len(operations) != 2 or {item.get("path") for item in operations} != TARGETS
            or any(item.get("action") != ("replace" if item.get("path").endswith("cars_ui.py") else "noop") for item in operations)):
        raise ControllerError("INSTALLATION_OPERATIONS")
    if any(manifest.get(key) is not True for key in ("backup_required", "rollback_required", "live_verify_required", "explicit_crm_vehicle_approval")):
        raise ControllerError("MANIFEST_PROTECTIONS")
    stage1 = json.loads(repo_file("state/receipts/" + STAGE1_ID + ".json").read_bytes())
    if stage1.get("task_id") != STAGE1_ID or stage1.get("status") != "FINISHED" or stage1.get("live_verify") != "PASS":
        raise ControllerError("STAGE1_PREREQUISITE")
    deployment = validate_deployment(manifest.get("deployment_plan"))
    source_operation = next(item for item in operations if item["path"].endswith("cars_ui.py"))
    if (source_operation.get("expected_before_sha256") != deployment["expected_source_sha256"]
            or source_operation.get("expected_after_sha256") != deployment["expected_candidate_sha256"]):
        raise ControllerError("APPROVED_SOURCE_HASH_BINDING")
    approval_raw = repo_file(critical.get("owner_approval_path")).read_bytes()
    approval = json.loads(approval_raw)
    if (sha(approval_raw) != require_sha(critical.get("owner_approval_sha256"), "OWNER_APPROVAL_PIN")
            or approval.get("launch_nonce") != deployment["nonce"]
            or approval.get("task_id") != TASK_ID or approval.get("production_allowed") is not True):
        raise ControllerError("OWNER_APPROVAL_IDENTITY")
    storage = request.get("storage_probe", {})
    probe_raw = repo_file(storage.get("evidence_path")).read_bytes()
    if sha(probe_raw) != require_sha(storage.get("evidence_sha256"), "STORAGE_PIN") or json.loads(probe_raw) != deployment["quota"]:
        raise ControllerError("STORAGE_MANIFEST_BINDING")
    # Rollback remains possible even if the pre-install measurement has aged.
    if operation != "rollback":
        stamp = dt.datetime.fromisoformat(str(deployment["quota"].get("measured_at", "")).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ControllerError("STORAGE_TIMEZONE")
        age = (dt.datetime.now(dt.timezone.utc) - stamp).total_seconds()
        if not -120 <= age <= 1800:
            raise ControllerError("STORAGE_STALE")
        if deployment["quota"]["free_bytes"] < int(request.get("storage_required_bytes", 0)):
            raise ControllerError("STORAGE_INSUFFICIENT")
    if operation != "backup":
        values["UAART_BACKUP_MANIFEST_SHA256"] = require_sha(
            str(environment.get("UAART_BACKUP_MANIFEST_SHA256", "")), "BACKUP_IDENTITY")
    values["DEPLOYMENT"] = deployment
    values["EXECUTION"] = execution
    return values


class API:
    """Writes only this run's inbox; manages only a positively identified own task."""
    def __init__(self, values):
        self.values = values
        self.remote = REMOTE_ROOT + "/" + values["UAART_RUN_ID"] + "-" + values["UAART_REQUEST_SHA256"]
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, url, data=None, headers=None, allowed=(200,)):
        if not url.startswith(BASE):
            raise ControllerError("API_ORIGIN")
        request = urllib.request.Request(url, data=data, method=method,
            headers={"Authorization": "Token " + self.values["PYTHONANYWHERE_API_TOKEN"],
                     "User-Agent": "ua-art-stage2-install/1", **(headers or {})})
        try:
            with self.opener.open(request, timeout=45) as response:
                status, body = response.status, response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, body = exc.code, exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK_" + type(exc).__name__) from None
        if status not in allowed or len(body) > MAX_BYTES:
            raise ControllerError("HTTP_" + str(status))
        return status, body

    def file_url(self, name):
        allowed = set(SOURCES) | {op + suffix for op in ("backup", "execute", "verify", "rollback")
                                  for suffix in ("-plan.json", "-result.json")}
        if name not in allowed:
            raise ControllerError("REMOTE_FILE_SCOPE")
        return BASE + "files/path" + urllib.parse.quote(self.remote + "/" + name, safe="/")

    def read(self, name, missing=False):
        status, body = self.request("GET", self.file_url(name), allowed=(200, 404))
        if status == 404:
            if missing:
                return None
            raise ControllerError("REMOTE_MISSING")
        return body

    def upload_new_or_identical(self, name, payload):
        if len(payload) > MAX_UPLOAD_BYTES:
            raise ControllerError("UPLOAD_BUDGET")
        existing = self.read(name, missing=True)
        if existing is not None:
            if existing != payload:
                raise ControllerError("REMOTE_IMMUTABLE_FILE_DRIFT")
            return
        boundary = "----uaart-stage2-" + uuid.uuid4().hex
        body = ("--" + boundary + '\r\nContent-Disposition: form-data; name="content"; filename="'
                + name + '"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
        body += payload + ("\r\n--" + boundary + "--\r\n").encode()
        self.request("POST", self.file_url(name), body,
                     {"Content-Type": "multipart/form-data; boundary=" + boundary}, allowed=(200, 201))
        if self.read(name) != payload:
            raise ControllerError("UPLOAD_READBACK")

    def supervisor_observation(self):
        """Observe the approved service without claiming cross-container PID access."""
        _, payload = self.request("GET", BASE + "always_on/266084/")
        obj = json.loads(payload)
        if (not isinstance(obj, dict) or obj.get("id") != 266084
                or obj.get("command") != "python3.10 /home/Carix/start_safe.py"
                or obj.get("enabled") is not True):
            raise ControllerError("SUPERVISOR_IDENTITY")
        state = obj.get("state")
        if not isinstance(state, str) or state.lower() != "running":
            raise ControllerError("SUPERVISOR_NOT_RUNNING")
        return {"source": "PYTHONANYWHERE_AUTHENTICATED_API", "supervisor_id": 266084,
                "command": obj["command"], "enabled": True, "status": "Running",
                "observed_at": now()}

    def run(self, operation, *, backup_manifest_sha256=None):
        if operation not in ("backup", "execute", "verify", "rollback"):
            raise ControllerError("REMOTE_OPERATION")
        plan = dict(self.values["DEPLOYMENT"])
        plan.update(bindings(self.values))
        plan.update({"parent_task_id": PARENT_ID, "operation": operation,
                     "remote_source_sha256": sha(repo_file(PACKAGE + "/remote_installer.py").read_bytes()),
                     "remote_package_sha256": {name: sha(repo_file(PACKAGE + "/" + name).read_bytes()) for name in SOURCES}})
        if backup_manifest_sha256 is not None:
            plan["backup_manifest_sha256"] = require_sha(backup_manifest_sha256, "REMOTE_BACKUP_SHA")
        supervisor_mode = plan["exact_process"].get("verification_mode") == "authenticated_supervisor"
        if supervisor_mode and operation != "rollback":
            plan["exact_process"] = {**plan["exact_process"],
                                     "observed_evidence": self.supervisor_observation()}
        for name in SOURCES:
            expected = self.values["EXECUTION"].get("file_sha256", {}).get(PACKAGE + "/" + name)
            payload = repo_file(PACKAGE + "/" + name).read_bytes()
            if sha(payload) != require_sha(expected, "PACKAGE_PIN_REQUIRED"):
                raise ControllerError("PACKAGE_PIN_MISMATCH")
            self.upload_new_or_identical(name, payload)
        result_name = operation + "-result.json"
        if self.read(result_name, missing=True) is not None:
            raise ControllerError("REMOTE_OPERATION_ALREADY_HAS_RESULT")
        self.upload_new_or_identical(operation + "-plan.json", canonical(plan))
        command = "cd " + shlex.quote(self.remote) + " && python3.10 remote_installer.py --operation " + operation + " --plan " + operation + "-plan.json"
        description = TASK_ID + " " + self.values["UAART_RUN_ID"] + " " + operation
        form = urllib.parse.urlencode({"command": command, "description": description, "enabled": "true"}).encode()
        _, body = self.request("POST", BASE + "always_on/", form,
                               {"Content-Type": "application/x-www-form-urlencoded"}, allowed=(200, 201, 202))
        obj = json.loads(body)
        identifier = obj.get("id") if isinstance(obj, dict) else None
        if type(identifier) is not int or identifier <= 0:
            raise ControllerError("TRIGGER_IDENTITY_UNCONFIRMED")
        trigger_url = BASE + "always_on/" + str(identifier) + "/"
        try:
            end = time.monotonic() + 300
            while time.monotonic() < end:
                payload = self.read(result_name, missing=True)
                if payload is not None:
                    result = json.loads(payload)
                    if not isinstance(result, dict):
                        raise ControllerError("REMOTE_RESULT_TYPE")
                    if supervisor_mode and operation != "rollback":
                        result["supervisor_post_observation"] = self.supervisor_observation()
                        result["os_pid_inspection"] = "NO_OS_PID_INSPECTION"
                    return result
                time.sleep(3)
            raise ControllerError("REMOTE_TIMEOUT")
        finally:
            # Never delete an unverified task or any existing CRM/site supervisor.
            status, body = self.request("GET", trigger_url, allowed=(200, 404))
            if status == 200:
                owned = json.loads(body)
                if (not isinstance(owned, dict) or owned.get("id") != identifier
                        or owned.get("command") != command or owned.get("description") != description):
                    raise ControllerError("TRIGGER_CLEANUP_IDENTITY")
                self.request("DELETE", trigger_url, allowed=(200, 202, 204, 404))
                check, _ = self.request("GET", trigger_url, allowed=(200, 404))
                if check != 404:
                    raise ControllerError("TRIGGER_CLEANUP_UNCONFIRMED")


def validate_remote(result, values, operation, *, expected_backup=None):
    if (not isinstance(result, dict) or any(result.get(key) != value for key, value in bindings(values).items())
            or result.get("operation") != operation):
        raise ControllerError("REMOTE_RESULT_BINDING")
    if expected_backup is not None and result.get("backup_manifest_sha256") != expected_backup:
        raise ControllerError("REMOTE_BACKUP_BINDING")
    expected_status = {"backup": "BACKUP_PASS", "execute": "INSTALLED_AWAITING_VERIFICATION",
                       "verify": "INSTALLATION_VERIFIED", "rollback": "ROLLED_BACK"}
    if result.get("status") != expected_status[operation]:
        raise ControllerError("REMOTE_OPERATION_FAILED")
    if result.get("nonce") != values["DEPLOYMENT"]["nonce"]:
        raise ControllerError("REMOTE_NONCE_BINDING")
    if result.get("live_price_writes") is not False:
        raise ControllerError("UNEXPECTED_LIVE_PRICE_WRITE")
    if result.get("telegram_ui_acceptance") != "NOT_PERFORMED":
        raise ControllerError("UNEXPECTED_ACCEPTANCE_SCOPE")
    if (result.get("site_write") is not False or result.get("migration") is not False
            or result.get("parent_stage2_receipt_created") is not False):
        raise ControllerError("REMOTE_PROTECTED_SCOPE")
    if operation in ("verify", "rollback"):
        if result.get("protected_sources_unchanged") is not True or result.get("database_unchanged") is not True:
            raise ControllerError("REMOTE_PROTECTED_INTEGRITY")


def backup(environment, api_factory=API):
    values = required(environment, "backup")
    result = api_factory(values).run("backup")
    validate_remote(result, values, "backup")
    if result.get("shadow_handler_acceptance") != "NOT_PERFORMED":
        raise ControllerError("UNEXPECTED_SHADOW_ACCEPTANCE_CLAIM")
    if result.get("candidate_sha256") != values["DEPLOYMENT"]["expected_candidate_sha256"]:
        raise ControllerError("BACKUP_CANDIDATE_HASH_BINDING")
    backup_sha = require_sha(result.get("backup_manifest_sha256"), "BACKUP_MANIFEST_REQUIRED")
    receipt = {**bindings(values), "schema_version": "UA-ART-PRODUCTION-BACKUP-RECEIPT-1",
               "operation": "backup", "status": "PASS", "backup": "PASS",
               "backup_manifest_sha256": backup_sha, "unexpected_changes": 0}
    atomic_new(ROOT / BACKUP_RECEIPT_REL, receipt)
    return receipt


def execute(environment, api_factory=API):
    values = required(environment, "execute")
    evidence = {**bindings(values), "status": "FAIL", "started_at": now(),
                "stage2_acceptance": "PENDING_TELEGRAM_CHECKS", "tests_scope": SCOPE}
    try:
        api = api_factory(values)
        backup_sha = values["UAART_BACKUP_MANIFEST_SHA256"]
        installed = api.run("execute", backup_manifest_sha256=backup_sha)
        evidence["installation"] = installed
        validate_remote(installed, values, "execute", expected_backup=backup_sha)
        verified = api.run("verify", backup_manifest_sha256=backup_sha)
        evidence["verification"] = verified
        validate_remote(verified, values, "verify", expected_backup=backup_sha)
        if verified.get("source_installed") is not True or verified.get("rollback_ready") is not True:
            raise ControllerError("INSTALLED_SOURCE_AND_ROLLBACK_NOT_VERIFIED")
        if verified.get("installed_sha256") != values["DEPLOYMENT"]["expected_candidate_sha256"]:
            raise ControllerError("INSTALLED_CANDIDATE_HASH_BINDING")
        receipt = {**bindings(values), "contract_id": "UA-ART-CRITICAL-ADAPTER-V1.0",
                   "parent_task_id": PARENT_ID, "status": "FINISHED", "task_class": "CRITICAL",
                   "target_environment": "production", "production_required": True,
                   "tests": "PASS", "tests_scope": SCOPE, "backup": "PASS",
                   "production": "PASS", "live_verify": "PASS", "live_verify_scope": SCOPE,
                   "rollback": "PASS", "rollback_scope": "BACKUP_AND_RESTORE_READINESS_VERIFIED",
                   "rollback_ready": True, "backup_manifest_sha256": backup_sha,
                   "unexpected_changes": 0, "protected_files_unchanged": True,
                   "crm_unchanged": True, "crm_unchanged_scope": "DATABASE_SCHEMA_AND_VEHICLE_VALUES_EXCLUDING_APPROVED_UI_SOURCE_REPLACEMENT",
                   "stage2_acceptance": "PENDING_TELEGRAM_CHECKS", "telegram_ui": "NOT_PERFORMED",
                   "bot_restart": "NOT_PERFORMED", "code_activation": "PENDING_PROCESS_VERIFICATION",
                   "stage3_allowed": False, "finished_at": now()}
        atomic_new(ROOT / RECEIPT_REL, receipt)
        evidence["status"] = "PASS"
    except Exception as exc:
        evidence["error"] = str(exc) if isinstance(exc, ControllerError) else type(exc).__name__
        raise
    finally:
        evidence["finished_at"] = now()
        atomic_new(ROOT / EVIDENCE_REL, evidence)
    return receipt


def rollback(environment, api_factory=API):
    values = required(environment, "rollback")
    backup_sha = values["UAART_BACKUP_MANIFEST_SHA256"]
    result = api_factory(values).run("rollback", backup_manifest_sha256=backup_sha)
    validate_remote(result, values, "rollback", expected_backup=backup_sha)
    if result.get("restored") is not True:
        raise ControllerError("ROLLBACK_RESTORE_NOT_PROVEN")
    receipt = {**bindings(values), "schema_version": "UA-ART-PRODUCTION-ROLLBACK-RECEIPT-1",
               "operation": "rollback", "status": "ROLLED_BACK", "rollback": "PASS",
               "backup_manifest_sha256": backup_sha, "restored": True, "unexpected_changes": 0,
               "protected_files_unchanged": True, "crm_unchanged": True, "live_verify": "PASS"}
    atomic_new(ROOT / ROLLBACK_RECEIPT_REL, receipt)
    return receipt


if __name__ == "__main__":
    try:
        result = execute(os.environ)
        print(json.dumps({"task_id": TASK_ID, "status": result["status"], "tests_scope": SCOPE,
                          "stage2_acceptance": "PENDING_TELEGRAM_CHECKS", "stage3_allowed": False}))
    except Exception as exc:
        print(json.dumps({"task_id": TASK_ID, "status": "FAIL",
                          "error": str(exc) if isinstance(exc, ControllerError) else type(exc).__name__}))
        raise SystemExit(1)
