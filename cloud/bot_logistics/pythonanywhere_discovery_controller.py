#!/usr/bin/env python3
"""pythonanywhere_discovery_controller.py -- TASK 039 GitHub-side controller.

Standard library only. This module is NOT executed by this Claude worker; it
is prepared for a future GitHub Actions job to run the single, already-
reviewed read-only PythonAnywhere discovery command described in TASK 037/039
and relay its safe receipt back into this repository.

Safety properties enforced here:
  * Only PythonAnywhere account 'Carix' and host www.pythonanywhere.com or
    eu.pythonanywhere.com are accepted.
  * PYTHONANYWHERE_API_TOKEN is read from the environment and never printed
    or written to any local file.
  * Local discovery script + test files must compile and pass before any
    remote action is attempted.
  * The remote _sync_manifest.json must show status PASS,
    executed_remote_code=false, production_touched=false, and must bind the
    exact discovery-script SHA-256 this controller computed locally.
  * Only the one exact, fixed, read-only command is ever requested to run.
  * Any always-on-task / scheduled-task trigger created is deleted in
    'finally', along with the one exact remote output file.
  * The controller never calls any endpoint that would write/upload files,
    restart a web app, run Gate B, or otherwise touch Production/CRM.
  * The remote receipt JSON is parsed with duplicate-key rejection and
    validated field-by-field. BLOCKED receipts are relayed as BLOCKED, never
    silently upgraded to PASS.
"""
import hashlib
import json
import os
import subprocess
import sys
import time

ALLOWED_USERNAME = "Carix"
ALLOWED_HOSTS = ("www.pythonanywhere.com", "eu.pythonanywhere.com")

BOT_LOGISTICS_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOVERY_SCRIPT_LOCAL = os.path.join(BOT_LOGISTICS_DIR, "bot_logistics_discovery.py")

REMOTE_DISCOVERY_SCRIPT = "/home/Carix/autopilot_inbox/cloud/bot_logistics/bot_logistics_discovery.py"
REMOTE_MANIFEST_PATH = "/home/Carix/autopilot_inbox/_sync_manifest.json"
REMOTE_OUTPUT_PATH = "/home/Carix/autopilot_inbox/cloud/bot_logistics/task037_discovery_output.json"
REMOTE_DB_PATH = "/home/Carix/crm.db"

REMOTE_SOURCES = (
    "/home/Carix/cars_ui.py",
    "/home/Carix/team_bot.py",
    "/home/Carix/avtoperedacha.py",
    "/home/Carix/db.py",
    "/home/Carix/run_all.py",
    "/home/Carix/start_safe.py",
)

EXACT_COMMAND = (
    "python3.10 {script} --db {db} "
    "--source {s0} --source {s1} --source {s2} --source {s3} --source {s4} --source {s5}"
).format(
    script=REMOTE_DISCOVERY_SCRIPT,
    db=REMOTE_DB_PATH,
    s0=REMOTE_SOURCES[0], s1=REMOTE_SOURCES[1], s2=REMOTE_SOURCES[2],
    s3=REMOTE_SOURCES[3], s4=REMOTE_SOURCES[4], s5=REMOTE_SOURCES[5],
)

EVIDENCE_PATH_LOCAL = os.path.join(BOT_LOGISTICS_DIR, "evidence", "task_037_discovery.json")
REPORT_PATH_LOCAL = os.path.join(BOT_LOGISTICS_DIR, "TASK_039_DISCOVERY_CONTROLLER_REPORT.md")

MAX_RECEIPT_AGE_SECONDS = 900
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 300

# Method names that would constitute a production/CRM write if ever called.
# The controller must never call any of these on the injected api object.
FORBIDDEN_API_METHODS = (
    "write_file", "upload_file", "reload_webapp", "restart_webapp",
    "execute_console_command", "run_gate_b", "delete_crm_row", "update_crm_row",
)

SECRET_PATTERNS_SRC = (
    "secret", "token", "password", "api_key", "apikey", "authorization",
    "private_key", "credential",
)


class ControllerError(Exception):
    pass


def _now():
    return time.time()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _no_duplicate_keys(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ControllerError("duplicate_key_in_receipt:%s" % k)
        d[k] = v
    return d


def parse_strict_json(text):
    try:
        return json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except ValueError as exc:
        raise ControllerError("malformed_json:%s" % exc)


def contains_secret_shape(text):
    lower = text.lower()
    return any(p in lower for p in SECRET_PATTERNS_SRC)


class GuardedAPI(object):
    """Wraps an injected transport object and refuses to call any forbidden
    (write-capable) method name, regardless of what the transport exposes."""

    def __init__(self, transport):
        self._transport = transport
        self.calls = []

    def __getattr__(self, name):
        if name in FORBIDDEN_API_METHODS:
            raise ControllerError("forbidden_api_method_blocked:%s" % name)
        attr = getattr(self._transport, name)

        def _wrapped(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return attr(*args, **kwargs)
        return _wrapped


class DiscoveryController(object):
    def __init__(self, transport, env=None, sleep=time.sleep, now=_now,
                 poll_interval=POLL_INTERVAL_SECONDS, timeout=POLL_TIMEOUT_SECONDS,
                 subprocess_runner=None):
        self.api = GuardedAPI(transport)
        self.env = env if env is not None else os.environ
        self.sleep = sleep
        self.now = now
        self.poll_interval = poll_interval
        self.timeout = timeout
        self._run_subprocess = subprocess_runner or self._default_subprocess_runner
        self._trigger_created = False

    @staticmethod
    def _default_subprocess_runner(cmd):
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def validate_environment(self):
        username = self.env.get("PYTHONANYWHERE_USERNAME", ALLOWED_USERNAME)
        host = self.env.get("PYTHONANYWHERE_HOST", ALLOWED_HOSTS[0])
        if username != ALLOWED_USERNAME:
            raise ControllerError("invalid_username")
        if host not in ALLOWED_HOSTS:
            raise ControllerError("invalid_host")
        token = self.env.get("PYTHONANYWHERE_API_TOKEN")
        if not token:
            raise ControllerError("missing_api_token")
        return token  # never logged, never returned in any report

    def verify_local_artifacts(self):
        rc, out, err = self._run_subprocess(
            [sys.executable, "-m", "py_compile",
             os.path.join(BOT_LOGISTICS_DIR, "bot_logistics_discovery.py")]
        )
        if rc != 0:
            raise ControllerError("local_compile_failed")
        rc, out, err = self._run_subprocess(
            [sys.executable, "-m", "unittest", "discover", "-s", BOT_LOGISTICS_DIR, "-p", "test*.py"]
        )
        if rc != 0:
            raise ControllerError("local_tests_failed")
        return sha256_file(DISCOVERY_SCRIPT_LOCAL)

    def verify_manifest(self, local_script_sha):
        content = self.api.read_file(REMOTE_MANIFEST_PATH)
        manifest = parse_strict_json(content)
        if manifest.get("status") != "PASS":
            raise ControllerError("manifest_not_pass")
        if manifest.get("executed_remote_code") is not False:
            raise ControllerError("manifest_executed_remote_code_not_false")
        if manifest.get("production_touched") is not False:
            raise ControllerError("manifest_production_touched_not_false")
        if manifest.get("discovery_script_sha256") != local_script_sha:
            raise ControllerError("manifest_sha_mismatch")
        generated_at = manifest.get("generated_at_epoch")
        if generated_at is None or (self.now() - float(generated_at)) > MAX_RECEIPT_AGE_SECONDS:
            raise ControllerError("manifest_stale")
        return manifest

    def _create_trigger(self):
        self.api.create_always_on_task(command=EXACT_COMMAND, output_redirect=REMOTE_OUTPUT_PATH)
        self._trigger_created = True
        try:
            self.api.create_scheduled_task_fallback(command=EXACT_COMMAND, output_redirect=REMOTE_OUTPUT_PATH)
        except Exception:
            pass  # fallback is best-effort; always-on task is primary

    def _cleanup_trigger(self):
        if self._trigger_created:
            try:
                self.api.delete_always_on_task()
            except Exception:
                pass
            try:
                self.api.delete_scheduled_task_fallback()
            except Exception:
                pass
        try:
            self.api.delete_file(REMOTE_OUTPUT_PATH)
        except Exception:
            pass

    def _poll_output(self):
        deadline = self.now() + self.timeout
        while self.now() < deadline:
            try:
                content = self.api.read_file(REMOTE_OUTPUT_PATH)
                if content:
                    return content
            except FileNotFoundError:
                pass
            except Exception:
                pass
            self.sleep(self.poll_interval)
        raise ControllerError("poll_timeout_no_output")

    def _validate_receipt(self, receipt):
        required_bool_false = (
            "production_write", "crm_write", "db_write", "ua0009_published",
        )
        if receipt.get("task_id") != "task_037":
            raise ControllerError("receipt_wrong_task_id")
        if receipt.get("mode") != "READ_ONLY_DISCOVERY":
            raise ControllerError("receipt_wrong_mode")
        if receipt.get("status") not in ("PASS", "BLOCKED"):
            raise ControllerError("receipt_invalid_status")
        for field in required_bool_false:
            if receipt.get(field) is not False:
                raise ControllerError("receipt_unsafe_field:%s" % field)
        sources = receipt.get("sources", [])
        if not isinstance(sources, list) or len(sources) > 6:
            raise ControllerError("receipt_sources_bound_violation")
        errors = receipt.get("errors", [])
        if not isinstance(errors, list) or len(errors) > 50:
            raise ControllerError("receipt_errors_bound_violation")
        status_field = receipt.get("UA0006_CONTAINER_STATUS")
        if status_field is not None and status_field not in ("ALREADY_CORRECT", "NEEDS_EXACT_UPDATE"):
            raise ControllerError("receipt_invalid_container_status")
        raw = json.dumps(receipt, sort_keys=True)
        if contains_secret_shape(raw):
            raise ControllerError("receipt_contains_secret_shape")
        return receipt

    def run(self):
        self.validate_environment()
        local_sha = self.verify_local_artifacts()
        self.verify_manifest(local_sha)
        try:
            self._create_trigger()
            raw = self._poll_output()
            receipt = parse_strict_json(raw)
            validated = self._validate_receipt(receipt)
            self._write_evidence(validated)
            self._write_report(validated)
            return validated
        finally:
            self._cleanup_trigger()

    def _write_evidence(self, receipt):
        os.makedirs(os.path.dirname(EVIDENCE_PATH_LOCAL), exist_ok=True)
        with open(EVIDENCE_PATH_LOCAL, "w", encoding="utf-8") as f:
            json.dump(receipt, f, ensure_ascii=False, sort_keys=True, indent=2)

    def _write_report(self, receipt):
        with open(REPORT_PATH_LOCAL, "w", encoding="utf-8") as f:
            f.write("# TASK 039 discovery controller relay report\n\n")
            f.write("status: %s\n\n" % receipt.get("status"))
            f.write("production_write: %s\n" % receipt.get("production_write"))
            f.write("crm_write: %s\n" % receipt.get("crm_write"))
            f.write("db_write: %s\n" % receipt.get("db_write"))
            f.write("ua0009_published: %s\n" % receipt.get("ua0009_published"))
            f.write("container_status: %s\n" % receipt.get("UA0006_CONTAINER_STATUS", "NONE"))
            f.write("errors: %s\n" % receipt.get("errors", []))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(
        "This controller is prepared for GitHub Actions execution only; "
        "it is not invoked directly by this Claude worker."
    )
