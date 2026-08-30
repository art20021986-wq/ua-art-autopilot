#!/usr/bin/env python3
"""
TASK 093 — Homepage stage counter fix (OFFLINE PACKAGE ONLY).

This script is NOT executed against UA ART production by Claude/Cloud.
It is a deterministic, testable package intended for controller or
owner-supervised Gate A/Gate B execution.

It never connects to a live CRM/database. It reads a read-only JSON
snapshot of published CRM rows (provided as input file), recomputes
stage counters, backs up target homepage files, and atomically writes
only the stage counter / CTA total fields. On any mismatch it performs
an automatic rollback from backup.

Usage (offline / test fixtures only):
    python task_093_homepage_counter_fix.py \
        --snapshot published_rows.json \
        --homepage-a homepage_copy_a.json \
        --homepage-b homepage_copy_b.json

Expected snapshot JSON schema:
[
  {"id": "UA-0001", "stage": "kyiv", "published": true},
  {"id": "UA-0011", "stage": "ferry", "published": true},
  ...
]

Stages recognized: "kyiv", "georgia", "ferry", "korea".

Homepage JSON schema (target files):
{
  "stage_counters": {"kyiv": 0, "georgia": 0, "ferry": 0, "korea": 0},
  "cta_total": 0,
  "other_fields": "...unchanged..."
}
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time

STAGES = ("kyiv", "georgia", "ferry", "korea")


class CounterFixError(Exception):
    pass


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_json_atomic(path, data):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_task093_", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def backup_file(path):
    if not os.path.exists(path):
        raise CounterFixError(f"Target homepage file does not exist: {path}")
    backup_path = f"{path}.bak.{int(time.time())}"
    shutil.copy2(path, backup_path)
    return backup_path


def restore_backup(path, backup_path):
    shutil.copy2(backup_path, path)


def compute_counters(published_rows):
    """Recompute unique published counts per stage and total.

    Deduplicates by id to avoid double counting.
    """
    seen_ids = set()
    counters = {stage: 0 for stage in STAGES}
    for row in published_rows:
        if not row.get("published"):
            continue
        row_id = row.get("id")
        if row_id is None or row_id in seen_ids:
            continue
        stage = row.get("stage")
        if stage not in STAGES:
            continue
        seen_ids.add(row_id)
        counters[stage] += 1
    total = sum(counters.values())
    return counters, total


def apply_fix_to_homepage(homepage_path, counters, total):
    """Backup, atomically update, verify, and roll back on mismatch.

    Returns (status, backup_path).
    status is one of: "PASS", "ROLLED_BACK"
    """
    original_data = load_json(homepage_path)
    backup_path = backup_file(homepage_path)

    updated_data = json.loads(json.dumps(original_data))  # deep copy
    updated_data["stage_counters"] = dict(counters)
    updated_data["cta_total"] = total

    try:
        dump_json_atomic(homepage_path, updated_data)

        verify_data = load_json(homepage_path)
        if verify_data.get("stage_counters") != counters:
            raise CounterFixError("Stage counter mismatch after write")
        if verify_data.get("cta_total") != total:
            raise CounterFixError("CTA total mismatch after write")

        # Ensure no other fields were altered.
        for key in original_data:
            if key in ("stage_counters", "cta_total"):
                continue
            if verify_data.get(key) != original_data.get(key):
                raise CounterFixError(f"Unexpected field mutated: {key}")

        return "PASS", backup_path
    except Exception:
        restore_backup(homepage_path, backup_path)
        return "ROLLED_BACK", backup_path


def run(snapshot_path, homepage_paths):
    published_rows = load_json(snapshot_path)
    counters, total = compute_counters(published_rows)

    results = []
    all_pass = True
    for homepage_path in homepage_paths:
        status, backup_path = apply_fix_to_homepage(homepage_path, counters, total)
        results.append(
            {"file": homepage_path, "status": status, "backup": backup_path}
        )
        if status != "PASS":
            all_pass = False

    return {
        "counters": counters,
        "total": total,
        "results": results,
        "overall": "PASS" if all_pass else "ROLLED_BACK",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--homepage-a", required=True)
    parser.add_argument("--homepage-b", required=True)
    args = parser.parse_args()

    result = run(args.snapshot, [args.homepage_a, args.homepage_b])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["overall"] == "PASS" else 1)


if __name__ == "__main__":
    main()
