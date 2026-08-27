"""Read-only verification of a Gate A receipt. Does not execute Gate A and
does not touch production."""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

VALID_STATUSES = ("GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", "BLOCKED")


def verify_receipt(receipt_path):
    with open(receipt_path, "r") as fh:
        receipt = json.load(fh)
    if receipt.get("production_write") != "NO":
        return False, "production_write_not_declared_no"
    if receipt.get("status") not in VALID_STATUSES:
        return False, f"unexpected_status:{receipt.get('status')}"
    if receipt.get("status") == "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL" and receipt.get("unmet_predicates"):
        return False, "pass_status_with_unmet_predicates"
    return True, "ok"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: verify_gate_a.py <receipt.json>")
        sys.exit(2)
    ok, reason = verify_receipt(sys.argv[1])
    print(json.dumps({"ok": ok, "reason": reason}))
    sys.exit(0 if ok else 1)
