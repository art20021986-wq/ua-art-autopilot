#!/usr/bin/env python3
"""Independent verifier for a Gate A receipt.json.

Exits nonzero unless every evidence entry has passed == true and the
top-level status equals GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL. Never
writes anything; never touches production."""

from __future__ import annotations

import json
import sys

REQUIRED_EVIDENCE_KEYS = [
    "required_inputs_present",
    "backup_archive_verified",
    "site_inventory_unchanged",
    "ua0009_not_public",
    "sqlite_quick_check",
    "protected_inputs_unchanged",
]


def verify(receipt: dict) -> list:
    problems = []
    if receipt.get("PRODUCTION_WRITE") != "NO":
        problems.append("PRODUCTION_WRITE_not_NO")
    evidence = receipt.get("evidence", {})
    for key in REQUIRED_EVIDENCE_KEYS:
        entry = evidence.get(key)
        if entry is None:
            problems.append(f"missing_evidence:{key}")
            continue
        if entry.get("passed") is not True:
            problems.append(f"not_passed:{key}:{entry.get('reasons')}")
    if receipt.get("status") != "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL":
        problems.append(f"status_not_pass:{receipt.get('status')}")
    return problems


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_gate_a.py <receipt.json>")
        return 2
    with open(sys.argv[1], "r") as f:
        receipt = json.load(f)
    problems = verify(receipt)
    if problems:
        print(json.dumps({"result": "BLOCKED", "problems": problems}, indent=2))
        return 1
    print(json.dumps({"result": "PASS"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
