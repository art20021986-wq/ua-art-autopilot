#!/usr/bin/env python3
"""
RUN_GATE_A_TASK016.py
Exact no-argument restricted Gate A server entrypoint for TASK_016.
Python 3.10 stdlib only.

This is the ONLY script an operator should run on the PythonAnywhere
console/task runner to execute Gate A. It:

  1. Accepts no arguments.
  2. Verifies it is running from the safe inbox location.
  3. Ignores/rejects any environment variable that would broaden paths
     or actions (UA_CARDS_OVERRIDE_ROOT, UA_CARDS_ALLOW_PRODUCTION, etc).
  4. Invokes build_gate_a_manifest.py, then START_UA_CARDS_UNIFIED.py in
     the restricted GATE_A_SANDBOX_ONLY mode.
  5. Never exposes a production/apply option.
  6. Emits a machine-readable receipt to stdout and to the receipt root.
"""

import os
import sys
import json
import subprocess
from pathlib import Path

SAFE_INBOX_ROOT = Path("/home/Carix/autopilot_inbox/cloud/ua_cards_unified")

BLOCKED_ENV_OVERRIDES = [
    "UA_CARDS_OVERRIDE_ROOT",
    "UA_CARDS_ALLOW_PRODUCTION",
    "UA_CARDS_FORCE_GATE_B",
    "UA_CARDS_DISABLE_SAFETY",
]


def verify_location():
    here = Path(__file__).resolve().parent
    if here != SAFE_INBOX_ROOT.resolve():
        print(f"REFUSED: this launcher must run from {SAFE_INBOX_ROOT}, found {here}")
        sys.exit(3)


def verify_environment():
    for key in BLOCKED_ENV_OVERRIDES:
        if os.environ.get(key):
            print(f"REFUSED: environment override '{key}' is not permitted for Gate A.")
            sys.exit(4)


def main():
    if len(sys.argv) > 1:
        print("REFUSED: RUN_GATE_A_TASK016.py accepts no arguments.")
        sys.exit(2)

    verify_location()
    verify_environment()

    manifest_script = SAFE_INBOX_ROOT / "build_gate_a_manifest.py"
    launcher_script = SAFE_INBOX_ROOT / "START_UA_CARDS_UNIFIED.py"

    if not manifest_script.exists() or manifest_script.is_symlink():
        print("REFUSED: manifest builder missing or symlink.")
        sys.exit(5)
    if not launcher_script.exists() or launcher_script.is_symlink():
        print("REFUSED: launcher missing or symlink.")
        sys.exit(5)

    manifest_proc = subprocess.run(
        [sys.executable, str(manifest_script)],
        capture_output=True, text=True, timeout=120,
    )
    sys.stdout.write(manifest_proc.stdout)
    if manifest_proc.returncode != 0:
        print("BLOCKED: manifest build failed.")
        print(manifest_proc.stderr)
        sys.exit(manifest_proc.returncode)

    launch_proc = subprocess.run(
        [sys.executable, str(launcher_script), "GATE_A_SANDBOX_ONLY"],
        capture_output=True, text=True, timeout=1800,
    )
    sys.stdout.write(launch_proc.stdout)
    if launch_proc.returncode != 0:
        print("BLOCKED: Gate A run failed.")
        print(launch_proc.stderr)
        sys.exit(launch_proc.returncode)

    receipt = {
        "task": "task_016",
        "mode": "GATE_A_SANDBOX_ONLY",
        "gate_b": False,
        "production_write": False,
        "wsgi_reload": False,
        "ua_0009_publication": False,
        "result": "See progress.json and gate_a_receipt.json under the allowed report/receipt roots.",
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
