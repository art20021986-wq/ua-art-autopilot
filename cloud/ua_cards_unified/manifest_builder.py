#!/usr/bin/env python3
"""Manifest builder for the UA cards unified pipeline (Gate A only).

Builds output/manifest.json summarizing the preflight + runner results.
Refuses to mark the pipeline AWAITING_GATE_B unless:
  - preflight report exists and status == PASS
  - run_log exists, has at least 1 card, and zero failed cards
  - runner itself already reported AWAITING_GATE_B
This utility does not touch production or PythonAnywhere, and it never
triggers Gate B (production application) by itself.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    ensure_dirs,
    GateStatus,
    MANIFEST_PATH,
    PREFLIGHT_REPORT_PATH,
    RUN_LOG_PATH,
    utc_now_iso,
    write_json,
)


def _load(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_manifest() -> Dict[str, Any]:
    ensure_dirs()
    preflight = _load(PREFLIGHT_REPORT_PATH)
    run_log = _load(RUN_LOG_PATH)

    blocking_reasons = []

    if preflight is None:
        blocking_reasons.append("preflight_report.json missing; run preflight.py first.")
    elif preflight.get("status") != "PASS":
        blocking_reasons.append("preflight status is not PASS.")

    if run_log is None:
        blocking_reasons.append("run_log.json missing; run runner.py first.")
    else:
        if run_log.get("total_cards", 0) == 0:
            blocking_reasons.append("No cards were processed.")
        if run_log.get("failed_cards", 0) > 0:
            blocking_reasons.append(f"{run_log['failed_cards']} card(s) failed validation.")
        if run_log.get("gate_status") != GateStatus.AWAITING_GATE_B:
            blocking_reasons.append("runner did not report AWAITING_GATE_B.")

    gate_status = GateStatus.BLOCKED if blocking_reasons else GateStatus.AWAITING_GATE_B

    manifest = {
        "generated_at_utc": utc_now_iso(),
        "gate_status": gate_status,
        "blocking_reasons": blocking_reasons,
        "preflight_summary": {
            "status": (preflight or {}).get("status"),
            "cards_discovered": (preflight or {}).get("cards_discovered"),
        },
        "run_summary": {
            "total_cards": (run_log or {}).get("total_cards"),
            "passed_cards": (run_log or {}).get("passed_cards"),
            "failed_cards": (run_log or {}).get("failed_cards"),
        },
        "production_touched": False,
        "pythonanywhere_executed": False,
        "note": (
            "AWAITING_GATE_B here means the pipeline is ready for a SEPARATE, "
            "OWNER-approved Gate B step. This manifest builder never triggers "
            "Gate B itself and never writes to production."
        ),
    }

    write_json(MANIFEST_PATH, manifest)
    return manifest


def main() -> int:
    manifest = build_manifest()
    print(f"Manifest gate_status: {manifest['gate_status']}")
    if manifest["blocking_reasons"]:
        for reason in manifest["blocking_reasons"]:
            print(f" - {reason}")
    return 0 if manifest["gate_status"] == GateStatus.AWAITING_GATE_B else 1


if __name__ == "__main__":
    raise SystemExit(main())
