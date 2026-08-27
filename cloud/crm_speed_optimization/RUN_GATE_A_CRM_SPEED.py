#!/usr/bin/env python3
"""No-argument Gate A launcher artifact.

IMPORTANT: This script is delivered for independent controller/owner
execution on PythonAnywhere ONLY, after review and explicit approval. It is
NEVER executed automatically by Claude/Cloud or by this repository's own
automation. Running this file is a separate, owner-approved action outside
the scope of any cloud/ task.
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crm_speed_gate_a import DEFAULT_CONFIG  # noqa: E402


def main():
    run_id = time.strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(DEFAULT_CONFIG["run_root"], run_id)
    print("This launcher is a delivered artifact for controller/owner-run execution only.")
    print("Claude/Cloud automation does not execute Gate A against production.")
    print(json.dumps({"planned_run_dir": run_dir, "config": DEFAULT_CONFIG}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
