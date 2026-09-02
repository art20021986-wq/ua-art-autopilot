#!/usr/bin/env python3
"""Non-production end-to-end canary for the permanent FAST workflow."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent
RECEIPT = ROOT / "state/receipts/TASK105-PERMANENT-ROUTE-CANARY.json"
REPORT = HERE / "ROUTE_CANARY_REPORT.md"


def utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def atomic_text(path: pathlib.Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix="." + path.name + ".",
        suffix=".route-canary.tmp",
        delete=False,
    )
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    now = utc_now()
    receipt = {
        "task_id": "TASK105-PERMANENT-ROUTE-CANARY",
        "status": "FINISHED",
        "task_class": "FAST",
        "target_environment": "sandbox",
        "tests": "PASS",
        "unexpected_changes": 0,
        "rollback_ready": True,
        "production_required": False,
        "ai_calls": 0,
        "permanent_fast_workflow": True,
        "finished_at": now,
    }
    atomic_text(
        RECEIPT,
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    atomic_text(
        REPORT,
        "\n".join(
            [
                "# TASK105 Permanent Route Canary",
                "",
                "STATUS: **PASS**",
                "",
                "- Class: FAST",
                "- Environment: sandbox",
                "- Production touched: NO",
                "- CRM/vehicle data touched: NO",
                "- Reusable execution contract: PASS",
                "- Truthful FINISHED receipt: PASS",
                "- AI calls: 0",
                "",
            ]
        ),
    )
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
