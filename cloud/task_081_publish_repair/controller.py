#!/usr/bin/env python3
"""Controller for TASK 081: orchestrates offline sandbox verification and
produces exactly one verdict string:

  PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL

or a precise fail-closed blocker.

This controller never touches production. If live evidence files are absent
(no live_probe.py run occurred against real credentials), it runs strictly
against the bundled synthetic sandbox fixtures and reports that fact clearly
in the verdict payload so no one can mistake fixture results for live proof.
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run_offline_tests():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(HERE / "tests"), "-q"],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0, proc.stdout + proc.stderr


def main():
    evidence_dir = HERE / "evidence"
    live_report = evidence_dir / "live_audit_report.json"
    live_available = live_report.exists()

    tests_ok, tests_output = run_offline_tests()

    verdict = {
        "live_audit_available": live_available,
        "offline_tests_pass": tests_ok,
        "tests_output_tail": tests_output[-4000:],
        "production_touched": False,
    }

    if not tests_ok:
        verdict["result"] = (
            "BLOCKER: offline sandbox/fixture tests failed. See tests_output_tail. "
            "No production action was attempted."
        )
        print(json.dumps(verdict, indent=2))
        sys.exit(1)

    if not live_available:
        verdict["result"] = (
            "BLOCKER: no live GET audit evidence present (live_probe.py has not been "
            "run against real PythonAnywhere credentials). Offline fixture tests pass, "
            "but Gate A requires real live evidence before any Gate B approval can be "
            "requested. Configure PYANYWHERE_API_TOKEN / PYANYWHERE_USERNAME as repo "
            "secrets and re-run gate_a_workflow.yml."
        )
        print(json.dumps(verdict, indent=2))
        sys.exit(2)

    verdict["result"] = "PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL"
    print(json.dumps(verdict, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
