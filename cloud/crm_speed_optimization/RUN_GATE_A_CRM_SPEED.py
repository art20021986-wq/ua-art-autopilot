#!/usr/bin/env python3
"""No-argument launcher for CRM-SPEED-001 Gate A — round 2.

This launcher only creates a unique run directory under
/home/Carix/qa/crm_speed_task020/ and writes a JSON receipt plus a
Markdown report there. It never writes to production paths, never
imports/executes the copied application modules, and never installs
anything. Any BLOCKED evidence stops the run with a nonzero exit code.

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO (Claude/Cloud never runs this on PythonAnywhere;
only the owner-authorized controller may execute it there.)
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import crm_speed_gate_a as gate_a  # noqa: E402

QA_ROOT = "/home/Carix/qa/crm_speed_task020"


def _make_run_dir() -> str:
    stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    run_dir = os.path.join(QA_ROOT, f"run_{stamp}_{os.getpid()}")
    os.makedirs(run_dir, exist_ok=False)
    return run_dir


def main() -> int:
    try:
        run_dir = _make_run_dir()
    except OSError as exc:
        print(f"BLOCKED: cannot create run directory: {exc}")
        return 1

    writer = gate_a.SafeWriter(run_dir)
    lock = gate_a.CrossProcessLock(os.path.join(QA_ROOT, "gate_a.lock"))
    if not lock.acquire(timeout=0):
        print("BLOCKED: another Gate A run already holds the exclusive lock")
        return 1

    try:
        config = {"db_path": "/home/Carix/crm.db"}
        receipt = gate_a.build_receipt(run_dir, config)

        writer.write_text("receipt.json", json.dumps(receipt, indent=2, default=str))

        report_lines = [
            "# CRM-SPEED-001 Gate A run report (round 2)",
            "",
            f"STATUS: {receipt['status']}",
            "PRODUCTION_WRITE: NO",
            "",
            "## Evidence",
        ]
        for name, ev in receipt["evidence"].items():
            report_lines.append(f"- {name}: passed={ev['passed']} reasons={ev['reasons']}")
        writer.write_text("report.md", "\n".join(report_lines) + "\n")

        print(json.dumps({"status": receipt["status"], "run_dir": run_dir}, indent=2))
        return 0 if receipt["status"] != "BLOCKED" else 1
    finally:
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
