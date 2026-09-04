#!/usr/bin/env python3
"""Read-only production filesystem capacity probe for TASK109."""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import tempfile


TARGET = "/home/Carix"
OUTPUT = "/home/Carix/autopilot_inbox/cloud/task_068_ferry_vin/task109_storage_probe.json"


def main() -> int:
    usage = shutil.disk_usage(TARGET)
    value = {
        "target_environment": "production",
        "read_only": True,
        "measured_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "total_bytes": int(usage.total),
        "used_bytes": int(usage.used),
        "free_bytes": int(usage.free),
        "measurement": "shutil.disk_usage:/home/Carix",
        "task_id": "TASK109-CONTAINER-TRACK-INLINE",
    }
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=os.path.dirname(OUTPUT),
        prefix=".task109-storage-", suffix=".tmp", delete=False,
    )
    temporary = handle.name
    try:
        with handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, OUTPUT)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
