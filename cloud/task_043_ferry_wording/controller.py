"""TASK 043 — PythonAnywhere orchestration controller.

This controller never performs a real network call inside this repository.
It is written for dependency injection so it can be unit-tested offline
with a FakeAPI, and independently audited by Codex before being wired to
a real `pythonanywhere.com` API client. It only ever issues the exact
read-only discovery and isolated Gate A commands; it refuses any command
containing a reload/restart/Gate B/publish/vacuum/attach token.

Standard library only. Never prints PYTHONANYWHERE_API_TOKEN.
"""

import json
import os
import time

ALLOWED_ACCOUNT = "Carix"
ALLOWED_HOSTS = {"www.pythonanywhere.com", "eu.pythonanywhere.com"}
FORBIDDEN_COMMAND_TOKENS = [
    "reload", "restart", "gate_b", "gateb", "publish", "vacuum", "attach",
]
SECRET_SCAN_TERMS = [
    "token", "password", "secret", "api_key", "api-key", "authorization",
    "private_key", "credential",
]


class ControllerError(Exception):
    pass


class SafeInboxManifestError(ControllerError):
    pass


class ReceiptError(ControllerError):
    pass


def verify_manifest(manifest, expected_hashes):
    """Bind the safe-inbox sync manifest to exact expected script hashes."""
    for rel_path, expected_sha in expected_hashes.items():
        actual = manifest.get(rel_path)
        if actual != expected_sha:
            raise SafeInboxManifestError("hash mismatch for %s" % rel_path)
    return True


def assert_command_allowed(command):
    lowered = command.lower()
    for token in FORBIDDEN_COMMAND_TOKENS:
        if token in lowered:
            raise ControllerError("forbidden command token %r in %r" % (token, command))


def scan_for_secrets(text):
    lowered = text.lower()
    return [term for term in SECRET_SCAN_TERMS if term in lowered]


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: %s" % key)
        result[key] = value
    return result


class PAController:
    def __init__(self, account, host, api_client, token=None):
        if account != ALLOWED_ACCOUNT:
            raise ControllerError("account %r not allowed" % account)
        if host not in ALLOWED_HOSTS:
            raise ControllerError("host %r not allowed" % host)
        self.account = account
        self.host = host
        self.api_client = api_client
        self.token = token if token is not None else os.environ.get("PYTHONANYWHERE_API_TOKEN")
        if not self.token:
            raise ControllerError("PYTHONANYWHERE_API_TOKEN not set")

    def run_discovery(self, command, receipt_path, timeout_seconds=60, poll_interval=1):
        assert_command_allowed(command)
        trigger_id = self.api_client.run_command(command)
        try:
            deadline = time.time() + timeout_seconds
            while time.time() < deadline:
                if self.api_client.file_exists(receipt_path):
                    raw = self.api_client.read_file(receipt_path)
                    return self._validate_receipt(raw)
                time.sleep(poll_interval)
            raise ControllerError("timeout waiting for receipt at %s" % receipt_path)
        finally:
            self.api_client.cleanup(trigger_id)

    def run_gate_a(self, command, receipt_path, timeout_seconds=120, poll_interval=1):
        return self.run_discovery(command, receipt_path, timeout_seconds, poll_interval)

    def _validate_receipt(self, raw_text):
        secrets_found = scan_for_secrets(raw_text)
        if secrets_found:
            raise ControllerError("secret-like tokens found in receipt: %s" % secrets_found)
        try:
            decoder = json.JSONDecoder(object_pairs_hook=_no_duplicate_keys)
            data = decoder.decode(raw_text)
        except ValueError as exc:
            raise ReceiptError("malformed JSON receipt: %s" % exc)
        for flag in ("production_touched", "crm_touched", "gate_b_executed"):
            if flag in data and str(data[flag]).upper() != "NO":
                raise ControllerError("unsafe flag %s=%s" % (flag, data[flag]))
        return data
