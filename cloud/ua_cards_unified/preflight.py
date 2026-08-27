#!/usr/bin/env python3
"""Read-only preflight/audit utility for the UA cards unified pipeline.

This utility performs NO writes to source/input card data and NO writes to
production or PythonAnywhere. It inspects the local environment and the
local input directory only, and writes its own report to a local output
file (output/preflight_report.json), which is not production data.

Exit codes:
  0 -> preflight PASS (safe to proceed to runner.py)
  1 -> preflight FAIL (do not run runner.py)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    ensure_dirs,
    load_json_cards,
    is_banned_synthetic,
    FORBIDDEN_ENV_MARKERS,
    PREFLIGHT_REPORT_PATH,
    REQUIRED_CARD_FIELDS,
    utc_now_iso,
    write_json,
)


def check_env_markers():
    findings = []
    for marker in FORBIDDEN_ENV_MARKERS:
        if os.environ.get(marker):
            findings.append(f"Forbidden environment marker present: {marker}")
    return findings


def check_input_cards():
    findings = []
    cards = load_json_cards()
    if not cards:
        findings.append("No input cards found under data/input_cards/ (nothing to process).")
        return findings, cards
    seen_ids = set()
    for card in cards:
        source = card.get("_source_file", "unknown") if isinstance(card, dict) else "unknown"
        if not isinstance(card, dict):
            findings.append(f"Card file does not contain a JSON object: {source}")
            continue
        if "_load_error" in card:
            findings.append(f"Card file failed to parse as JSON: {source} ({card['_load_error']})")
            continue
        card_id = card.get("card_id")
        if not card_id:
            findings.append(f"Card missing card_id: {source}")
            continue
        if is_banned_synthetic(card_id):
            findings.append(
                f"BANNED synthetic placeholder id detected ({card_id}) in {source}. "
                "UA-0001..UA-0008 must never be processed."
            )
        if card_id in seen_ids:
            findings.append(f"Duplicate card_id detected: {card_id} ({source})")
        seen_ids.add(card_id)
        for field in REQUIRED_CARD_FIELDS:
            if field not in card:
                findings.append(f"Card {card_id} missing required field '{field}' ({source})")
    return findings, cards


def check_no_network_config():
    """Scan this package's own source for accidental production/network wiring."""
    findings = []
    suspicious_names = ["api_url", "webhook", "production_url", "prod_endpoint"]
    for path in Path(__file__).resolve().parent.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lowered = text.lower()
        for name in suspicious_names:
            if name in lowered:
                findings.append(
                    f"Possible network/production reference '{name}' found in {path.name}; verify manually."
                )
    return findings


def run_preflight() -> dict:
    ensure_dirs()
    env_findings = check_env_markers()
    card_findings, cards = check_input_cards()
    network_findings = check_no_network_config()

    all_findings = env_findings + card_findings + network_findings
    blocking = list(env_findings) + list(network_findings) + [
        f for f in card_findings
        if ("BANNED" in f or "missing" in f or "failed to parse" in f
            or "Duplicate" in f or "does not contain" in f)
    ]

    status = "FAIL" if blocking else "PASS"

    report = {
        "generated_at_utc": utc_now_iso(),
        "status": status,
        "cards_discovered": len(cards),
        "findings": all_findings,
        "blocking_findings": blocking,
        "gate": "GATE_A_PREFLIGHT",
        "production_touched": False,
        "pythonanywhere_executed": False,
    }
    write_json(PREFLIGHT_REPORT_PATH, report)
    return report


def main() -> int:
    report = run_preflight()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
