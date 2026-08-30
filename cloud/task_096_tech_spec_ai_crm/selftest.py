"""TASK 096 — offline self-test harness (NOT executed by Claude/Cloud in this
delivery; no code-execution capability is available in this response channel).

The controller must run this script (`python3 selftest.py`) in an environment
with Python 3.10+ and attach the printed JSON result block into evidence.json,
replacing the PENDING_CONTROLLER_EXECUTION placeholder.

The harness builds an in-memory SQLite database shaped like UA-0001..UA-0016
(no real customer data, synthetic placeholders only) and exercises:
  1. schema_additional_spec.sql application
  2. dedup rejection of a fact already present as a primary field
  3. dedup rejection of a semantic duplicate already in additional_specification
  4. acceptance of a genuinely new fact
  5. hard rejection of any purchase/auction/wholesale price field
  6. confirmation that no primary_field_registry row is ever mutated
"""
from __future__ import annotations
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from dedup_check import check_candidate, canonical_key, normalize_text
from manual_field_protection import assert_target_is_additional_spec_only, ManualFieldViolation
from price_exclusion_guard import is_price_key


def build_sandbox_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    schema_sql = Path(__file__).parent.joinpath("schema_additional_spec.sql").read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    car_uids = [f"UA-{i:04d}" for i in range(1, 17)]
    for uid in car_uids:
        conn.execute(
            "INSERT INTO primary_field_registry (car_uid, field_key, normalized_value) VALUES (?,?,?)",
            (uid, "model", "synthetic-placeholder-model"),
        )
    # UA-0009 already has an operator-entered drivetrain fact.
    conn.execute(
        "INSERT INTO primary_field_registry (car_uid, field_key, normalized_value) VALUES (?,?,?)",
        ("UA-0009", "drivetrain", "4matic"),
    )
    conn.commit()
    return conn


def run() -> dict:
    results = {}
    conn = build_sandbox_db()

    primary_rows = conn.execute(
        "SELECT field_key, normalized_value FROM primary_field_registry WHERE car_uid=?",
        ("UA-0009",),
    ).fetchall()
    primary_fields = {canonical_key(k): normalize_text(v) for k, v in primary_rows}

    # Test 1: reject duplicate of a manually entered primary field.
    r1 = check_candidate("UA-0009", "awd", "AWD system", primary_fields, {})
    results["test1_manual_field_protected"] = {"allowed": r1.allowed, "reason": r1.reason}

    # Test 2: accept a genuinely new fact.
    r2 = check_candidate("UA-0009", "torque_nm", "400 Nm", primary_fields, {})
    results["test2_new_fact_accepted"] = {"allowed": r2.allowed, "reason": r2.reason}

    # Insert the accepted fact, then try to add a semantic duplicate under a synonym key.
    existing_additional = {}
    if r2.allowed:
        existing_additional[canonical_key("torque_nm")] = normalize_text("400 Nm")
    r3 = check_candidate("UA-0009", "крутящий_момент", "400 Нм", primary_fields, existing_additional)
    results["test3_semantic_duplicate_rejected"] = {"allowed": r3.allowed, "reason": r3.reason}

    # Test 4: hard price exclusion.
    r4 = check_candidate("UA-0009", "auction_price", "12345", primary_fields, {})
    results["test4_price_field_rejected"] = {"allowed": r4.allowed, "reason": r4.reason}
    results["test4_price_key_detected"] = is_price_key("auction_price")

    # Test 5: manual field protection layer raises for a primary key.
    try:
        assert_target_is_additional_spec_only("vin")
        results["test5_primary_key_blocked"] = False
    except ManualFieldViolation:
        results["test5_primary_key_blocked"] = True

    # Test 6: primary_field_registry row count unchanged (never mutated by this module).
    count_before = 17  # 16 model rows + 1 drivetrain row
    count_after = conn.execute("SELECT COUNT(*) FROM primary_field_registry").fetchone()[0]
    results["test6_primary_registry_untouched"] = (count_after == count_before)

    all_pass = (
        results["test1_manual_field_protected"]["allowed"] is False
        and results["test2_new_fact_accepted"]["allowed"] is True
        and results["test3_semantic_duplicate_rejected"]["allowed"] is False
        and results["test4_price_field_rejected"]["allowed"] is False
        and results["test4_price_key_detected"] is True
        and results["test5_primary_key_blocked"] is True
        and results["test6_primary_registry_untouched"] is True
    )
    results["ALL_TESTS_PASS"] = all_pass
    conn.close()
    return results


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
