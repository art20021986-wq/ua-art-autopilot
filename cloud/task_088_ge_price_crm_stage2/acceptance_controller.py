#!/usr/bin/env python3
"""Fail-closed parent Stage 2 entrypoint while real Telegram checks are pending.

The obsolete parent requests must never invoke the Stage 1 or child installer.
An installation receipt is deliberately insufficient for parent acceptance.
No network calls, remote writes, or receipt creation are made here.
"""
import json

TASK_ID = "TASK088-GE-PRICE-CRM-STAGE2"

if __name__ == "__main__":
    print(json.dumps({"task_id": TASK_ID, "status": "BLOCKED",
                      "reason": "PARENT_ACCEPTANCE_REQUIRES_REAL_TELEGRAM_COMMIT_READBACK_AND_RESTORE",
                      "installation_task_id": TASK_ID + "-INSTALL", "stage3_allowed": False}))
    raise SystemExit(1)
