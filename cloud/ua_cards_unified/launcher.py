#!/usr/bin/env python3
"""No-argument restricted launcher for the UA cards unified pipeline.

Restrictions (Gate A only, TASK 017 / TASK 018):
  - MUST be invoked with zero CLI arguments. Any argument aborts execution
    before anything else runs.
  - Runs, in strict order: preflight.py -> runner.py -> manifest_builder.py.
  - Never touches production. Never executes anything on PythonAnywhere.
  - Stops immediately (non-zero exit) if any stage fails, without
    proceeding to the next stage (except manifest is still built after a
    failed runner stage, purely to record the BLOCKED state locally).
  - Accepts no environment overrides for target hosts/URLs; there are none
    in this pipeline by design (Gate A is entirely local/file-based).
  - Never performs Gate B (production application). Gate B is a separate,
    explicitly owner-approved action outside this launcher's scope.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import preflight  # noqa: E402
import runner  # noqa: E402
import manifest_builder  # noqa: E402


def main(argv) -> int:
    if len(argv) > 1:
        print(
            "REJECTED: this launcher accepts no arguments. "
            "Restricted no-argument execution only.",
            file=sys.stderr,
        )
        return 2

    print("=== STAGE 1/3: preflight (read-only) ===")
    pre_report = preflight.run_preflight()
    print(f"Preflight status: {pre_report['status']}")
    if pre_report["status"] != "PASS":
        print("ABORT: preflight failed. Fix findings before re-running.", file=sys.stderr)
        for finding in pre_report["blocking_findings"]:
            print(f" - {finding}", file=sys.stderr)
        return 1

    print("=== STAGE 2/3: runner (Gate A validation) ===")
    run_log = runner.run()
    print(f"Runner gate_status: {run_log['gate_status']}")
    if run_log["gate_status"] != "AWAITING_GATE_B":
        print(f"ABORT: {run_log['reason']}", file=sys.stderr)
        # Build manifest anyway so the BLOCKED state is recorded locally.
        manifest_builder.build_manifest()
        return 1

    print("=== STAGE 3/3: manifest builder ===")
    manifest = manifest_builder.build_manifest()
    print(f"Final gate_status: {manifest['gate_status']}")

    if manifest["gate_status"] == "AWAITING_GATE_B":
        print(
            "Pipeline is AWAITING_GATE_B. Gate B requires explicit OWNER "
            "approval and is NOT performed by this launcher."
        )
        return 0

    print("ABORT: manifest builder reported BLOCKED.", file=sys.stderr)
    for reason in manifest["blocking_reasons"]:
        print(f" - {reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
