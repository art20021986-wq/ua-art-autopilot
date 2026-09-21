#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt
import json
import os
import subprocess
import tempfile

OUTPUT = "/home/Carix/uploads/seo_daily_storage_probe_20260921.json"
TOTAL_BYTES = 37580963840
TARGETS = ["/tmp", "/home/Carix", "/var/www"]


def du_bytes(path: str) -> int:
    completed = subprocess.run(
        ["du", "-s", "-B", "1", path],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        raise RuntimeError("DU_FAILED:" + path)
    first = completed.stdout.strip().split(None, 1)[0]
    return int(first)


def atomic_json(path: str, value: dict) -> None:
    directory = os.path.dirname(path)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=directory, prefix=".seo_storage_", suffix=".tmp", delete=False
    )
    temporary = handle.name
    try:
        with handle:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            if os.path.exists(temporary):
                os.unlink(temporary)
        except OSError:
            pass


def main() -> int:
    components = {path: du_bytes(path) for path in TARGETS}
    used = sum(components.values())
    if used < 0 or used >= TOTAL_BYTES:
        raise RuntimeError("STORAGE_RANGE")
    value = {
        "task_id": "SEO-DAILY-PODBOR-CANONICAL-20260921",
        "target_environment": "production",
        "read_only": True,
        "measured_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "measurement": "target-side read-only du bytes with authenticated 35 GiB account quota baseline verified 2026-09-20",
        "total_bytes": TOTAL_BYTES,
        "used_bytes": used,
        "free_bytes": TOTAL_BYTES - used,
        "used_measurement": {
            "command": "du -s -B 1 /tmp /home/Carix /var/www",
            "components_bytes": components,
            "source": "PythonAnywhere production scheduled task",
        },
        "quota_baseline": {
            "total_bytes": TOTAL_BYTES,
            "source": "state/storage/UA-ART-UA0022-PUBLISH-REPAIR-003.json",
            "verified_at": "2026-09-20T04:52:10Z"
        }
    }
    atomic_json(OUTPUT, value)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
