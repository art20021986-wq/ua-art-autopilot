#!/usr/bin/env python3
"""Build and compile TASK 080 only in memory from fresh GET-only live files."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

from live_gate_a import MAX_SOURCE, REMOTE_ROOT, atomic_write, remote_get
from src.integration_patcher import PatchRefused, build_candidate


HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "evidence" / "candidate_gate_a.json"
REPORT = HERE / "CANDIDATE_GATE_A_REPORT.md"
TARGETS = ("cars_ui.py", "local_ocr.py", "ai_fast_schema.py", "ai_filter.py", "db.py")


def now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def main() -> int:
    result = {
        "task_id": "task_080",
        "contract_id": "CRM-PRICE-RECOGNITION-006-v1.0",
        "mode": "LIVE_GET_ONLY_IN_MEMORY_CANDIDATE",
        "started_at_utc": now(),
        "status": "FAIL_CLOSED",
        "http_methods": ["GET"],
        "production_write": False,
        "database_write": False,
        "site_write": False,
        "process_restart": False,
        "candidate_files_persisted": False,
        "errors": [],
    }
    try:
        if not os.environ.get("PYTHONANYWHERE_API_TOKEN", "").strip():
            raise RuntimeError("PYTHONANYWHERE_API_TOKEN_MISSING")
        files = {
            name: remote_get(REMOTE_ROOT + "/" + name, MAX_SOURCE).decode("utf-8")
            for name in TARGETS
        }
        _, candidate = build_candidate(files)
        result.update(candidate)
        result["status"] = "PASS_IN_MEMORY_CANDIDATE"
        result["release_status"] = "READY_FOR_SEPARATE_PRODUCTION_APPROVAL"
    except (PatchRefused, Exception) as exc:
        result["errors"].append("%s:%s" % (type(exc).__name__, exc))
        result["release_status"] = "FAIL_CLOSED_LIVE_DRIFT_OR_CANDIDATE_ERROR"
    result["finished_at_utc"] = now()
    atomic_write(EVIDENCE, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    lines = [
        "# TASK 080 — in-memory candidate Gate A",
        "",
        "- Status: `%s`" % result["status"],
        "- Release status: `%s`" % result["release_status"],
        "- Remote methods: `GET` only",
        "- Production/DB/site writes: `NO`",
        "- Process restart: `NO`",
        "- Candidate production files persisted: `NO`",
        "- Changed active blocks: `%d`" % len(result.get("changed_blocks", [])),
        "- Errors: `%s`" % ("; ".join(result["errors"]) if result["errors"] else "none"),
        "",
        "The candidate was compiled only in memory against fresh whole-file and active-block hashes.",
        "A later production Gate B still requires separate owner approval.",
        "",
    ]
    atomic_write(REPORT, "\n".join(lines))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS_IN_MEMORY_CANDIDATE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
