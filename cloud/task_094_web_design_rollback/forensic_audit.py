#!/usr/bin/env python3
"""
TASK 094 Phase A — read-only forensic audit.

Zero-LLM, deterministic. Must be executed with real access to the PythonAnywhere
account (via the Files API using PYTHONANYWHERE_API_TOKEN, or via a console/bash
session with filesystem access). This script performs NO writes.

It enumerates:
  - current production presentation files
  - the TASK 093 pre-write backup
  - all TASK 086 backup directories it can find
and computes SHA-256 + size + mtime for each, writing audit_report.json.

This script does not decide which preimage is "approved" -- that decision is a
human/ChatGPT-Codex review step performed on audit_report.json, per the fail-closed
rule in the task.
"""
import hashlib
import json
import os
import sys
import time

PRODUCTION_TARGETS = [
    "/home/Carix/video/index.html",
    "/home/Carix/video/katalog.html",
]

BACKUP_ROOTS = [
    "/home/Carix/backups/task_093_home_counters",
    "/home/Carix/backups/task_086_catalog_stage",
    "/home/Carix/backups",  # fallback: scanned for any task_086_* / task_093_* dirs
]

KNOWN_TASK_093_BACKUP = (
    "/home/Carix/backups/task_093_home_counters/20260830T010212Z_7e621e5028"
)


def sha256_of(path):
    if not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def describe(path):
    if not os.path.exists(path):
        return {"path": path, "exists": False}
    st = os.stat(path)
    return {
        "path": path,
        "exists": True,
        "is_file": os.path.isfile(path),
        "size_bytes": st.st_size,
        "mtime_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)),
        "sha256": sha256_of(path) if os.path.isfile(path) else None,
    }


def find_task_086_backups(roots):
    found = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            full = os.path.join(root, entry)
            if "086" in entry:
                found.append(full)
    return found


def main():
    report = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase": "A_FORENSIC_AUDIT",
        "read_only": True,
        "production_current": [describe(p) for p in PRODUCTION_TARGETS],
        "task_093_backup": describe(KNOWN_TASK_093_BACKUP),
        "task_086_backups": [],
    }

    task_086_candidates = find_task_086_backups(BACKUP_ROOTS)
    for cand in task_086_candidates:
        if os.path.isdir(cand):
            entry = {"backup_dir": cand, "files": []}
            for root, _dirs, files in os.walk(cand):
                for fn in files:
                    entry["files"].append(describe(os.path.join(root, fn)))
            report["task_086_backups"].append(entry)
        else:
            report["task_086_backups"].append(describe(cand))

    report["note"] = (
        "This report is read-only forensic data. Selection of the approved preimage "
        "must be performed by a human/ChatGPT-Codex reviewer comparing these hashes "
        "against known-good acceptance records. No hash here is asserted as approved."
    )

    with open("audit_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
