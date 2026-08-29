"""GET-only PythonAnywhere live audit controller for TASK 073.

This module never performs write operations against production and never
fabricates evidence. If live credentials are not present in the execution
environment, it fails closed with an explicit BLOCKED status instead of
guessing or inventing SHA values, file contents, or schema.
"""

import os

REQUIRED_ENV_VARS = ["PA_API_HOST", "PA_API_TOKEN", "PA_USERNAME"]


class AuditBlockedError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def check_credentials_available():
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        return "MISSING_CREDENTIALS:" + ",".join(missing)
    return None


def run_get_only_audit(output_dir: str) -> dict:
    """Attempt a GET-only PythonAnywhere Files/Consoles API audit.

    Fails closed with an explicit BLOCKED reason if live credentials are
    not present in this execution environment. Never fabricates evidence,
    SHA values, or file contents. Never performs any write call.
    """
    missing_reason = check_credentials_available()
    if missing_reason:
        return {
            "status": "BLOCKED",
            "reason": missing_reason,
            "note": (
                "No live PythonAnywhere GET-only access was available in "
                "this execution environment. No production or CRM data was "
                "read, guessed, or fabricated."
            ),
        }
    os.makedirs(output_dir, exist_ok=True)
    return {
        "status": "NOT_IMPLEMENTED_WITHOUT_LIVE_CREDENTIALS",
        "note": (
            "Credentials were present but real GET-only API calls are not "
            "wired in this offline delivery. Implement PythonAnywhere Files "
            "API GET calls here before relying on this path for Gate A."
        ),
    }
