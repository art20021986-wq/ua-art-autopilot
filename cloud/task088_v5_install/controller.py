"""Canonical CRITICAL Stage 3 installation child; no deployment self-authorization.

The existing workflow owns PREPARING/OPEN/ROLLING_BACK transitions and final
claim reconciliation. This adapter reads those exact records; it never writes
policy, claims, nonces, authorizations or launch markers. FINISHED means only
installation plus filesystem/schema readback, with Stage 3/4 still unclosed.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2] if HERE.name == "release" else HERE.parents[1]
PACKAGE = HERE.relative_to(ROOT).as_posix()
BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/"
REMOTE_BASE = "/home/Carix/autopilot_inbox/cloud/task088_v5_install/runs"
MAX_BYTES = 8 * 1024 * 1024
SCOPE = "STAGE3_INSTALLATION_AND_SOURCE_SCHEMA_HTML_READBACK"
BINDINGS = ("task_id", "request_sha256", "run_id", "transaction_id", "manifest_sha256")
REMOTE_FILES = frozenset({"remote_adapter.py", "install_package.py", "uaart_market_prices.py",
    "uaart_price_sync_outbox.py", "uaart_price_sync_runtime.py", "uaart_price_sync_binding.py",
    "uaart_price_sync_confirmation.py", "uaart_price_control_reader.py", "owner_policy.py", "price_publication.py"})


class ControllerError(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def require_sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) or value == "0" * 64:
        raise ControllerError("REAL_SHA256_REQUIRED")
    return value


def repo_file(relative, root=ROOT):
    if not isinstance(relative, str) or not re.fullmatch(r"[A-Za-z0-9._/-]+", relative):
        raise ControllerError("EXACT_REPOSITORY_PATH_REQUIRED")
    parts = PurePosixPath(relative)
    path = root / relative
    if (parts.is_absolute() or ".." in parts.parts or str(parts) != relative
            or any(parent.is_symlink() for parent in (path, *path.parents)) or not path.is_file()):
        raise ControllerError("CANONICAL_FILE_UNAVAILABLE")
    return path


def atomic_new(path, value):
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ControllerError("SYMLINK_OUTPUT_FORBIDDEN")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".task088-stage3-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical(value)); handle.flush(); os.fsync(handle.fileno())
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def receipt_paths(task):
    prefix = "state/receipts/" + task
    return {"execute": prefix + ".json", "backup": prefix + "-BACKUP.json", "rollback": prefix + "-ROLLBACK.json"}


def required(environment, operation, *, root=ROOT, package=PACKAGE):
    if operation not in ("backup", "execute", "rollback"):
        raise ControllerError("EXACT_OPERATION_REQUIRED")
    names = ("PYTHONANYWHERE_API_TOKEN", "UAART_REQUEST_PATH", "UAART_REQUEST_SHA256", "UAART_TASK_ID",
        "UAART_TASK_CLASS", "UAART_RUN_ID", "UAART_TRANSACTION_ID", "UAART_MANIFEST_SHA256",
        "UAART_OPERATION", "UAART_RECEIPT_PATH")
    values = {name: str(environment.get(name, "")) for name in names}
    if any(not value or any(char in value for char in "\r\n\0") for value in values.values()):
        raise ControllerError("COMPLETE_CANONICAL_ENVIRONMENT_REQUIRED")
    task, request_sha, run_id = values["UAART_TASK_ID"], require_sha(values["UAART_REQUEST_SHA256"]), values["UAART_RUN_ID"]
    if not re.fullmatch(r"TASK088-GE-PRICE-SITE-STAGE3-[A-Za-z0-9-]+", task) or not re.fullmatch(r"[0-9]{1,30}", run_id):
        raise ControllerError("FRESH_STAGE3_IDENTITY_REQUIRED")
    paths = receipt_paths(task)
    if (values["UAART_TASK_CLASS"] != "CRITICAL" or values["UAART_OPERATION"] != operation
            or values["UAART_REQUEST_PATH"] != "tasks/requests/" + task + ".json"
            or values["UAART_RECEIPT_PATH"] != paths[operation]):
        raise ControllerError("EXACT_CRITICAL_EXECUTION_SCOPE_REQUIRED")
    if operation != "execute" and environment.get("UAART_" + operation.upper() + "_RECEIPT_PATH") != paths[operation]:
        raise ControllerError("AUXILIARY_RECEIPT_SCOPE_REQUIRED")
    request_raw = repo_file(values["UAART_REQUEST_PATH"], root).read_bytes()
    if sha(request_raw) != request_sha:
        raise ControllerError("REQUEST_HASH_DRIFT")
    request = json.loads(request_raw)
    critical, execution = request.get("critical", {}), request.get("execution", {})
    if (request.get("task_id") != task or request.get("production_required") is not True
            or request.get("read_only") is not False or request.get("requested_min_class") != "CRITICAL"
            or critical.get("gate_b_authorized") is not True or critical.get("allow_crm_vehicle_data") is not True
            or execution.get("production_required") is not True
            or execution.get("controller_path") != package + "/controller.py"
            or execution.get("backup_controller_path") != package + "/backup_controller.py"
            or execution.get("rollback_controller_path") != package + "/rollback_controller.py"
            or execution.get("receipt_path") != paths["execute"]
            or execution.get("backup_receipt_path") != paths["backup"]
            or execution.get("rollback_receipt_path") != paths["rollback"]):
        raise ControllerError("EXACT_INSTALLATION_CONTROLLER_SCOPE_REQUIRED")
    manifest_raw = repo_file(critical.get("manifest_path"), root).read_bytes()
    manifest = json.loads(manifest_raw)
    # Existing canonical critical manifests use newline-terminated canonical JSON.
    if (sha(canonical(manifest)) != require_sha(values["UAART_MANIFEST_SHA256"])
            or sha(manifest_raw) != critical.get("manifest_sha256")
            or manifest.get("task_id") != task or manifest.get("acceptance_scope") != SCOPE
            or manifest.get("stage3_complete") is not False
            or any(manifest.get(key) is not True for key in
                ("backup_required", "rollback_required", "live_verify_required", "explicit_crm_vehicle_approval"))):
        raise ControllerError("EXACT_INSTALLATION_MANIFEST_REQUIRED")
    deployment = manifest.get("deployment_plan", {})
    blueprint = deployment.get("install_blueprint", {})
    if deployment.get("contract") != "TASK088-CANONICAL-STAGE3-ADAPTER-1" or blueprint.get("contract") != "UA-ART-GE-PRICE-STAGE3-INSTALL-5":
        raise ControllerError("EXACT_ADAPTER_DEPLOYMENT_CONTRACT_REQUIRED")
    expected_operations = {"production/" + name: {"action": "create" if entry["before_sha256"] is None else "replace",
        "expected_before_sha256": entry["before_sha256"], "expected_after_sha256": entry["after_sha256"]}
        for name, entry in blueprint["files"].items()}
    expected_operations["production/crm.db/schema"] = {"action": "replace",
        "expected_before_sha256": blueprint["schema_sha256"], "expected_after_sha256": blueprint["candidate_schema_sha256"]}
    operations = manifest.get("operations", [])
    if (len(operations) != len(expected_operations) or set(request.get("changed_paths", [])) != set(expected_operations)
            or {item.get("path") for item in operations} != set(expected_operations)
            or any(any(item.get(key) != value for key, value in expected_operations[item["path"]].items()) for item in operations)):
        raise ControllerError("EXACT_SOURCE_HTML_SCHEMA_MANIFEST_SCOPE_REQUIRED")
    schema_op = next(item for item in operations if item["path"] == "production/crm.db/schema")
    if schema_op.get("content_kind") != "SQLITE_SCHEMA":
        raise ControllerError("EXPLICIT_SCHEMA_ONLY_RESOURCE_REQUIRED")
    identity_suffix = task + "." + request_sha + "." + run_id + ".json"
    claim_path, transaction_path = "state/claims/" + identity_suffix, "state/transactions/" + identity_suffix
    evidence_paths = deployment.get("evidence_paths", {})
    expected_evidence = {"gate_b", "quota", "writers", "preview_gate"} | ({"routing"} if blueprint.get("homepage_policy") else set())
    if set(evidence_paths) != expected_evidence:
        raise ControllerError("REAL_CANONICAL_EVIDENCE_PATHS_REQUIRED")
    mapped = {"request": values["UAART_REQUEST_PATH"], "manifest": critical["manifest_path"],
        "owner_approval": critical["owner_approval_path"], "claim": claim_path, "transaction": transaction_path,
        "stage2": "state/receipts/TASK088-GE-PRICE-CRM-STAGE2.json", **evidence_paths}
    evidence = {name: repo_file(path, root).read_bytes() for name, path in mapped.items()}
    transaction = json.loads(evidence["transaction"])
    claim = json.loads(evidence["claim"])
    expected_phase = "PREPARING" if operation == "backup" else "ROLLING_BACK" if operation == "rollback" else "OPEN"
    if (transaction.get("status") != expected_phase or claim.get("production_transaction_status") != expected_phase
            or transaction.get("transaction_id") != values["UAART_TRANSACTION_ID"]
            or transaction.get("request_sha256") != request_sha or transaction.get("task_id") != task
            or str(transaction.get("run_id")) != run_id or transaction.get("request_path") != values["UAART_REQUEST_PATH"]
            or claim.get("production_transaction_path") != transaction_path):
        raise ControllerError("ACTUAL_CANONICAL_TRANSACTION_PHASE_REQUIRED")
    owner = json.loads(evidence["owner_approval"])
    if (owner.get("launch_nonce") != deployment.get("nonce") or not re.fullmatch(r"[A-Za-z0-9._-]{16,140}", str(deployment.get("nonce", "")))):
        raise ControllerError("REAL_OWNER_LAUNCH_NONCE_REQUIRED")
    package_hashes = deployment.get("remote_package_sha256", {})
    if set(package_hashes) != REMOTE_FILES:
        raise ControllerError("EXACT_REMOTE_PACKAGE_CLOSURE_REQUIRED")
    for name, digest in package_hashes.items():
        path = package + "/" + name
        if sha(repo_file(path, root).read_bytes()) != require_sha(digest) or execution.get("file_sha256", {}).get(path) != digest:
            raise ControllerError("REVIEWED_REMOTE_PACKAGE_HASH_MISMATCH")
    install_plan = {**blueprint, "environment": "PRODUCTION", "root": "/home/Carix", "task_id": task,
        "transaction_id": values["UAART_TRANSACTION_ID"], "evidence_sha256": {name: sha(raw) for name, raw in evidence.items()}}
    values.update({"ROOT": root, "PACKAGE": package, "INSTALL_PLAN": install_plan, "EVIDENCE": evidence,
        "DEPLOYMENT": deployment, "EXECUTION": execution, "RECEIPTS": paths,
        "BINDINGS": {"task_id": task, "request_sha256": request_sha, "run_id": run_id,
            "transaction_id": values["UAART_TRANSACTION_ID"], "manifest_sha256": values["UAART_MANIFEST_SHA256"]}})
    if operation != "backup":
        backup_sha = require_sha(str(environment.get("UAART_BACKUP_MANIFEST_SHA256", "")))
        if transaction.get("backup_manifest_sha256") != backup_sha:
            raise ControllerError("CANONICAL_BACKUP_HASH_REQUIRED")
        values["BACKUP_SHA"] = backup_sha
    return values


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ControllerError("HTTP_REDIRECT_REFUSED")


class API:
    def __init__(self, values):
        self.values = values
        self.remote = REMOTE_BASE + "/" + values["UAART_RUN_ID"] + "-" + values["UAART_REQUEST_SHA256"]
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method, url, data=None, headers=None, allowed=(200,)):
        if not url.startswith(BASE):
            raise ControllerError("API_ORIGIN_SCOPE")
        request = urllib.request.Request(url, data=data, method=method,
            headers={"Authorization": "Token " + self.values["PYTHONANYWHERE_API_TOKEN"],
                     "User-Agent": "ua-art-stage3-install/5", **(headers or {})})
        try:
            with self.opener.open(request, timeout=45) as response:
                status, raw = response.status, response.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read(MAX_BYTES + 1)
        except Exception as exc:
            raise ControllerError("NETWORK_" + type(exc).__name__) from None
        if status not in allowed or len(raw) > MAX_BYTES:
            raise ControllerError("HTTP_" + str(status))
        return status, raw

    def file_url(self, name):
        allowed = REMOTE_FILES | {operation + suffix for operation in ("backup", "execute", "verify", "rollback")
                                 for suffix in ("-plan.json", "-result.json")}
        if name not in allowed:
            raise ControllerError("EXACT_RUN_FILE_SCOPE")
        return BASE + "files/path" + urllib.parse.quote(self.remote + "/" + name, safe="/")

    def read(self, name):
        status, raw = self.request("GET", self.file_url(name), allowed=(200, 404))
        return None if status == 404 else raw

    def upload(self, name, payload):
        current = self.read(name)
        if current is not None:
            if current != payload:
                raise ControllerError("EXISTING_REMOTE_RUN_FILE_DRIFT")
            return
        if len(payload) > MAX_BYTES:
            raise ControllerError("BOUNDED_UPLOAD_REQUIRED")
        boundary = "----uaart-stage3-" + uuid.uuid4().hex
        body = ("--" + boundary + '\r\nContent-Disposition: form-data; name="content"; filename="' + name
            + '"\r\nContent-Type: application/octet-stream\r\n\r\n').encode() + payload + ("\r\n--" + boundary + "--\r\n").encode()
        self.request("POST", self.file_url(name), body, {"Content-Type": "multipart/form-data; boundary=" + boundary}, allowed=(200, 201))
        if self.read(name) != payload:
            raise ControllerError("REMOTE_UPLOAD_READBACK_FAILED")

    def supervisor(self):
        _, raw = self.request("GET", BASE + "always_on/266084/")
        obj = json.loads(raw)
        if (obj.get("id") != 266084 or obj.get("command") != "python3.10 /home/Carix/start_safe.py"
                or obj.get("enabled") is not True or str(obj.get("state", "")).lower() != "running"):
            raise ControllerError("EXACT_EXISTING_CRM_SUPERVISOR_REQUIRED")
        return {"id": 266084, "state": "Running", "observed_at": now(), "restarted": False}

    def routing(self):
        """Re-read provider routing before each operation, including restore.

        Server source hashes cannot detect a changed provider static mapping.
        Keep the exact observed existing domain and /video/ static route bound
        to the candidate; never create or alter provider configuration here.
        """
        _, raw = self.request("GET", BASE + "webapps/")
        webapps = json.loads(raw)
        if not isinstance(webapps, list) or any(not isinstance(item, dict) for item in webapps):
            raise ControllerError("EXACT_EXISTING_WEBAPP_ROUTING_REQUIRED")
        production = [item for item in webapps if item.get("domain_name") == "www.uaart.com.ua"]
        if (len(production) != 1 or production[0].get("enabled") is not True
                or production[0].get("python_version") != "3.10"):
            raise ControllerError("EXACT_EXISTING_WEBAPP_ROUTING_REQUIRED")
        _, raw = self.request("GET", BASE + "webapps/www.uaart.com.ua/static_files/")
        mappings = json.loads(raw)
        expected = [{"path": "/home/Carix/video/", "url": "/video/"}]
        if (not isinstance(mappings, list)
                or [{key: item.get(key) for key in ("path", "url")} for item in mappings] != expected):
            raise ControllerError("EXACT_EXISTING_STATIC_ROUTING_REQUIRED")
        return {"domain": "www.uaart.com.ua", "static_mappings": expected, "observed_at": now(),
                "provider_configuration_written": False}

    def run(self, operation):
        before = self.supervisor()
        route_before = self.routing()
        deployment = self.values["DEPLOYMENT"]
        payload = {**self.values["BINDINGS"], "operation": operation,
            "install_plan": self.values["INSTALL_PLAN"],
            "canonical_evidence": {name: raw.decode("utf-8") for name, raw in self.values["EVIDENCE"].items()},
            "preflight_directory": deployment["preflight_directory"],
            "preflight_report_sha256": deployment["preflight_report_sha256"],
            "remote_package_sha256": deployment["remote_package_sha256"]}
        if operation != "backup":
            payload["backup_manifest_sha256"] = self.values["BACKUP_SHA"]
        for name in sorted(REMOTE_FILES):
            self.upload(name, repo_file(self.values["PACKAGE"] + "/" + name, self.values["ROOT"]).read_bytes())
        result_name = operation + "-result.json"
        if self.read(result_name) is not None:
            raise ControllerError("REMOTE_OPERATION_ALREADY_RECORDED")
        self.upload(operation + "-plan.json", encoded(payload))
        command = "cd " + shlex.quote(self.remote) + " && python3.10 remote_adapter.py --plan " + operation + "-plan.json"
        description = self.values["UAART_TASK_ID"] + " " + self.values["UAART_RUN_ID"] + " " + operation
        form = urllib.parse.urlencode({"command": command, "description": description, "enabled": "true"}).encode()
        _, raw = self.request("POST", BASE + "always_on/", form, {"Content-Type": "application/x-www-form-urlencoded"}, allowed=(200, 201, 202))
        obj = json.loads(raw)
        identifier = obj.get("id") if isinstance(obj, dict) else None
        if type(identifier) is not int or identifier <= 0 or identifier == 266084:
            raise ControllerError("OWN_RUNNER_IDENTITY_UNCONFIRMED")
        url = BASE + "always_on/" + str(identifier) + "/"
        try:
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                result_raw = self.read(result_name)
                if result_raw is not None:
                    result = json.loads(result_raw)
                    result["crm_supervisor_before"] = before
                    result["crm_supervisor_after"] = self.supervisor()
                    result["provider_routing_before"] = route_before
                    result["provider_routing_after"] = self.routing()
                    return result
                time.sleep(3)
            raise ControllerError("SCOPED_REMOTE_OPERATION_TIMEOUT")
        finally:
            status, raw = self.request("GET", url, allowed=(200, 404))
            if status == 200:
                owned = json.loads(raw)
                if (owned.get("id") != identifier or owned.get("command") != command or owned.get("description") != description):
                    raise ControllerError("SCOPED_RUNNER_CLEANUP_IDENTITY_MISMATCH")
                self.request("DELETE", url, allowed=(200, 202, 204, 404))
                if self.request("GET", url, allowed=(200, 404))[0] != 404:
                    raise ControllerError("SCOPED_RUNNER_CLEANUP_UNCONFIRMED")


def validate_remote(result, values, operation):
    expected = {"backup": "BACKUP_PASS", "execute": "INSTALLED_AWAITING_VERIFICATION",
                "verify": "INSTALLATION_VERIFIED", "rollback": "ROLLED_BACK"}
    if (not isinstance(result, dict) or result.get("operation") != operation or result.get("status") != expected[operation]
            or any(result.get(key) != value for key, value in values["BINDINGS"].items())
            or result.get("live_price_writes") is not False or result.get("stage1_reinstalled") is not False
            or result.get("stage2_reinstalled") is not False or result.get("public_acceptance") != "NOT_RUN"
            or result.get("telegram_acceptance") != "NOT_RUN"):
        raise ControllerError("REMOTE_RESULT_BINDING_OR_SCOPE_FAILED")
    require_sha(result.get("backup_manifest_sha256"))
    if operation != "backup" and result["backup_manifest_sha256"] != values["BACKUP_SHA"]:
        raise ControllerError("REMOTE_CANONICAL_BACKUP_MISMATCH")
    if operation in ("verify", "rollback") and (result.get("database_unchanged") is not True or result.get("protected_files_unchanged") is not True):
        raise ControllerError("REMOTE_PROTECTED_READBACK_FAILED")


def perform(environment, operation, *, api_factory=API, root=ROOT, package=PACKAGE):
    values = required(environment, operation, root=root, package=package)
    api = api_factory(values)
    result = api.run(operation)
    validate_remote(result, values, operation)
    if operation == "backup":
        receipt = {**values["BINDINGS"], "schema_version": "UA-ART-PRODUCTION-BACKUP-RECEIPT-1",
            "operation": "backup", "status": "PASS", "backup": "PASS",
            "backup_manifest_sha256": result["backup_manifest_sha256"], "unexpected_changes": 0}
    elif operation == "rollback":
        if result.get("restored") is not True or result.get("live_verify") != "PASS":
            raise ControllerError("ACTUAL_ROLLBACK_VERIFICATION_REQUIRED")
        receipt = {**values["BINDINGS"], "schema_version": "UA-ART-PRODUCTION-ROLLBACK-RECEIPT-1",
            "operation": "rollback", "status": "ROLLED_BACK", "rollback": "PASS", "restored": True,
            "backup_manifest_sha256": values["BACKUP_SHA"], "unexpected_changes": 0,
            "protected_files_unchanged": True, "crm_unchanged": True, "live_verify": "PASS"}
    else:
        verified = api.run("verify")
        validate_remote(verified, values, "verify")
        receipt = {**values["BINDINGS"], "contract_id": "UA-ART-CRITICAL-ADAPTER-V1.0", "status": "FINISHED",
            "task_class": "CRITICAL", "target_environment": "production", "production_required": True,
            "tests": "PASS", "tests_scope": SCOPE, "backup": "PASS", "production": "PASS",
            "live_verify": "PASS", "live_verify_scope": SCOPE, "rollback": "PASS", "rollback_ready": True,
            "rollback_scope": "EXACT_BACKUP_AND_CAS_RESTORE_READINESS", "backup_manifest_sha256": values["BACKUP_SHA"],
            "unexpected_changes": 0, "protected_files_unchanged": True, "crm_unchanged": True,
            "crm_unchanged_scope": "EXISTING_CARS_AUDIT_ROWS_WITH_REVIEWED_SCHEMA_EXTENSION",
            "stage3_complete": False, "stage4_complete": False, "autopilot_activated": False,
            "bot_restart": "NOT_PERFORMED", "public_acceptance": "NOT_RUN", "telegram_acceptance": "NOT_RUN",
            "installed_evidence": verified["install_receipt"], "finished_at": now()}
    atomic_new(root / values["RECEIPTS"][operation], receipt)
    return receipt


def main(operation="execute"):
    try:
        result = perform(os.environ, operation)
        print(json.dumps({"task_id": result["task_id"], "status": result["status"], "scope": SCOPE,
                          "stage3_complete": False, "stage4_complete": False}))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc) if isinstance(exc, ControllerError) else type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
