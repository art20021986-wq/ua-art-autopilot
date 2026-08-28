#!/usr/bin/env python3
"""Post-restart concurrency and integrity check for task_064."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile


BASE = pathlib.Path("/home/Carix")
DB_PY = BASE / "db.py"
CRM_DB = BASE / "crm.db"
SAFE = BASE / "autopilot_inbox" / "cloud" / "task_064"
RECEIPT = SAFE / "postcheck_receipt.json"
MARKER = "CRM-DB-LOCK-EMERGENCY-001"
WORKERS = 4
ITERATIONS = 10


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_json(path: pathlib.Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def snapshot():
    connection = sqlite3.connect("file:/home/Carix/crm.db?mode=ro", uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        count = connection.execute("SELECT count(*) FROM cars").fetchone()[0]
        columns = {row[1] for row in connection.execute("PRAGMA table_info(cars)")}
        result = {"quick_check": quick, "cars_count": count}
        if "auto_number" in columns:
            rows = connection.execute(
                "SELECT * FROM cars WHERE auto_number IN ('UA-0009','UA0009')"
            ).fetchall()
            result["ua0009_rows"] = len(rows)
            result["ua0009_sha256"] = sha(
                json.dumps([dict(row) for row in rows], ensure_ascii=False,
                           sort_keys=True, default=str).encode("utf-8")
            )
        return result
    finally:
        connection.close()


def worker_code():
    return (
        "import sys\n"
        "sys.path.insert(0, '/home/Carix')\n"
        "import db\n"
        "for _ in range(%d):\n"
        "    with db.connect() as c:\n"
        "        c.execute('UPDATE cars SET updated_at=updated_at WHERE 0')\n"
        "print('TASK064_WORKER_PASS')\n" % ITERATIONS
    )


def concurrency_probe():
    code = worker_code()
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code],
            cwd=str(BASE),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(WORKERS)
    ]
    results = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=90)
        results.append({
            "returncode": process.returncode,
            "pass_marker": "TASK064_WORKER_PASS" in stdout,
            "stderr_tail": stderr[-500:],
        })
    return results


def main() -> int:
    receipt = {
        "task_id": "task_064",
        "contract_id": MARKER,
        "status": "FAIL",
        "llm_tokens": 0,
        "write_probe": "UPDATE_WHERE_FALSE_ONLY",
        "errors": [],
    }
    try:
        source = DB_PY.read_text(encoding="utf-8")
        if MARKER not in source:
            raise RuntimeError("HOTFIX_MARKER_MISSING")
        compile(source, str(DB_PY), "exec")
        before = snapshot()
        if before["quick_check"] != "ok":
            raise RuntimeError("QUICK_CHECK_BEFORE_FAILED")
        workers = concurrency_probe()
        receipt["workers"] = workers
        if len(workers) != WORKERS or any(
            item["returncode"] != 0 or not item["pass_marker"] for item in workers
        ):
            raise RuntimeError("CONCURRENCY_PROBE_FAILED")
        after = snapshot()
        receipt["readonly_before"] = before
        receipt["readonly_after"] = after
        receipt["operations"] = WORKERS * ITERATIONS
        receipt["journal_present_after"] = (BASE / "crm.db-journal").exists()
        if after["quick_check"] != "ok":
            raise RuntimeError("QUICK_CHECK_AFTER_FAILED")
        if before["cars_count"] != after["cars_count"]:
            raise RuntimeError("CARD_COUNT_CHANGED")
        if before.get("ua0009_sha256") != after.get("ua0009_sha256"):
            raise RuntimeError("UA0009_CHANGED")
        receipt["status"] = "PASS"
    except Exception as exc:
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc))
    atomic_json(RECEIPT, receipt)
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
