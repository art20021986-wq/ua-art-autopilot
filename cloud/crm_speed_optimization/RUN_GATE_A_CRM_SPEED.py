#!/usr/bin/env python3
"""No-argument Gate A launcher artifact.

IMPORTANT: This script is delivered for independent controller/owner
execution on PythonAnywhere ONLY, after review and explicit approval. It
is NEVER executed automatically by Claude/Cloud or by this repository's
own automation. Running this file is a separate, owner-approved action
outside the scope of any cloud/ task.

The no-argument code path uses only DEFAULT_CONFIG (bounded, fixed paths
already present in the canonical specification), never imports or
executes production application modules, and performs no installation,
restart, publication, or production mutation of any kind. It returns 0
only for GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL and nonzero for any
BLOCKED or internal failure outcome.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import crm_speed_gate_a  # noqa: E402
from crm_speed_gate_a import DEFAULT_CONFIG  # noqa: E402


def main(orchestrate=None, config=None):
    """orchestrate and config are injectable so tests never execute the
    real DEFAULT_CONFIG production path and never touch /home/Carix or
    the network. The no-argument invocation (__main__ below) always uses
    the real canonical orchestrate_gate_a and DEFAULT_CONFIG."""
    orchestrate_fn = orchestrate or crm_speed_gate_a.orchestrate_gate_a
    cfg = config if config is not None else DEFAULT_CONFIG
    try:
        receipt = orchestrate_fn(cfg)
    except Exception as exc:
        print(json.dumps({"status": "INTERNAL_ERROR", "reason": type(exc).__name__}))
        return 1
    status = receipt.get("status", "UNKNOWN")
    summary = {
        "status": status,
        "run_id": receipt.get("run_id"),
        "unmet_predicate_count": len(receipt.get("unmet_predicates") or []),
        "phase_count": len(receipt.get("phases") or []),
        "production_write": receipt.get("production_write", "NO"),
    }
    print(json.dumps(summary, indent=2, default=str))
    if status == "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL":
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
