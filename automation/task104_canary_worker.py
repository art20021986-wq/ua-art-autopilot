#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib

import task104_self_recovery_core as core

SCENARIOS = {
    "TIMEOUT": ("SANDBOX", "TimeoutError"),
    "HTTP412": ("SANDBOX", "PYTHONANYWHERE_HTTP_412"),
    "HTTP429": ("CANARY", "PYTHONANYWHERE_HTTP_429"),
    "HTTP502": ("CANARY", "PYTHONANYWHERE_HTTP_502"),
    "CONNECTION_RESET": ("EXECUTE", "Connection reset"),
    "RUNNER_LOST": ("EXECUTE", "RUNNER_LOST"),
    "WORKFLOW_CANCELLED": ("POSTCHECK", "WORKFLOW_CANCELLED"),
    "LOST_EVENT": ("POSTCHECK", "LOST_WORKFLOW_EVENT"),
    "DATABASE_LOCKED": ("SANDBOX", "database is locked"),
    "ATTRIBUTE_ERROR": ("CANARY", "AttributeError in executor"),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycle", type=int, required=True)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    parser.add_argument("--attempt", type=int, required=True)
    args = parser.parse_args()
    core.require_approval()
    if args.attempt == 1:
        # Deliberate workflow-level failure. Recovery must happen without owner input.
        print("TASK104_INTENTIONAL_FAILURE cycle=%d scenario=%s" % (args.cycle, args.scenario))
        return 42
    stage, message = SCENARIOS[args.scenario]
    result = core.run_one_canary(args.cycle, stage, message)
    result.update({
        "scenario": args.scenario,
        "workflow_attempt": args.attempt,
        "production_touched": False,
        "task096_v8_touched": False,
    })
    out = pathlib.Path("cloud/task104_self_recovery/state/integration_receipt_%02d.json" % args.cycle)
    core.atomic_json(out, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "PASS" and result.get("business_status") == "BUSINESS_COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
