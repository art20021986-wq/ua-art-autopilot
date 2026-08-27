#!/usr/bin/env python3
"""Gate A runner for the UA cards unified pipeline.

SAFETY (TASK 014 / TASK 017 / TASK 018):
- This runner performs Gate A validation ONLY. It never writes to
  production systems and never executes anything on PythonAnywhere.
- Banned synthetic placeholder IDs UA-0001..UA-0008 are rejected outright.
- If ANY card fails validation, the overall run is marked BLOCKED and the
  pipeline must NOT advance to AWAITING_GATE_B.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    ensure_dirs,
    load_json_cards,
    is_banned_synthetic,
    OUTPUT_DIR,
    REQUIRED_CARD_FIELDS,
    RUN_LOG_PATH,
    GateStatus,
    utc_now_iso,
    write_json,
)


def _cards_output_dir() -> Path:
    return OUTPUT_DIR / "cards"


def validate_card(card: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(card, dict):
        return {"card_id": "UNKNOWN", "passed": False, "errors": ["Card is not a JSON object"]}

    card_id = card.get("card_id") or card.get("_source_file", "UNKNOWN")
    errors: List[str] = []

    if "_load_error" in card:
        errors.append(f"JSON parse error: {card['_load_error']}")
        return {"card_id": card_id, "passed": False, "errors": errors}

    if not card.get("card_id"):
        errors.append("Missing card_id")

    if card.get("card_id") and is_banned_synthetic(card["card_id"]):
        errors.append(
            f"Banned synthetic placeholder id {card['card_id']} (UA-0001..UA-0008 forbidden)"
        )

    for field in REQUIRED_CARD_FIELDS:
        if field not in card:
            errors.append(f"Missing required field: {field}")

    payload = card.get("payload")
    if payload is not None and not isinstance(payload, dict):
        errors.append("payload must be an object")

    passed = len(errors) == 0
    return {"card_id": card_id, "passed": passed, "errors": errors}


def run() -> Dict[str, Any]:
    ensure_dirs()
    cards_output_dir = _cards_output_dir()
    cards_output_dir.mkdir(parents=True, exist_ok=True)

    cards = load_json_cards()
    results = [validate_card(card) for card in cards]

    for result in results:
        safe_name = str(result["card_id"]).replace("/", "_").replace("\\", "_")
        write_json(cards_output_dir / f"{safe_name}.json", result)

    total = len(results)
    failed = [r for r in results if not r["passed"]]

    if total == 0:
        gate_status = GateStatus.BLOCKED
        reason = "No cards discovered to process."
    elif failed:
        gate_status = GateStatus.BLOCKED
        reason = f"{len(failed)} of {total} card(s) failed Gate A validation."
    else:
        gate_status = GateStatus.AWAITING_GATE_B
        reason = f"All {total} card(s) passed Gate A validation."

    run_log = {
        "generated_at_utc": utc_now_iso(),
        "total_cards": total,
        "passed_cards": total - len(failed),
        "failed_cards": len(failed),
        "gate_status": gate_status,
        "reason": reason,
        "results": results,
        "production_touched": False,
        "pythonanywhere_executed": False,
    }
    write_json(RUN_LOG_PATH, run_log)
    return run_log


def main() -> int:
    run_log = run()
    print(f"Gate status: {run_log['gate_status']}")
    print(f"Reason: {run_log['reason']}")
    return 0 if run_log["gate_status"] == GateStatus.AWAITING_GATE_B else 1


if __name__ == "__main__":
    raise SystemExit(main())
