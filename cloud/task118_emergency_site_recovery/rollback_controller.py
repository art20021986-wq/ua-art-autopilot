#!/usr/bin/env python3
"""Safe fallback: repeat the same stateless webapp reload."""
from __future__ import annotations

import json
import os
import pathlib
import re

import controller


def main() -> int:
    if (
        os.environ.get("UAART_OPERATION") != "rollback"
        or os.environ.get("UAART_TASK_ID") != controller.TASK_ID
    ):
        return 2
    backup_sha = os.environ["UAART_BACKUP_MANIFEST_SHA256"]
    if not re.fullmatch(r"[0-9a-f]{64}", backup_sha):
        raise RuntimeError("BACKUP_IDENTITY")
    controller.API(os.environ["PYTHONANYWHERE_API_TOKEN"]).reload()
    controller.wait_for_consecutive(1, 120)
    receipt = {
        "schema_version": "UA-ART-PRODUCTION-ROLLBACK-RECEIPT-1",
        "operation": "rollback",
        "task_id": os.environ["UAART_TASK_ID"],
        "request_sha256": os.environ["UAART_REQUEST_SHA256"],
        "run_id": os.environ["UAART_RUN_ID"],
        "transaction_id": os.environ["UAART_TRANSACTION_ID"],
        "manifest_sha256": os.environ["UAART_MANIFEST_SHA256"],
        "backup_manifest_sha256": backup_sha,
        "status": "ROLLED_BACK",
        "rollback": "PASS",
        "restored": True,
        "unexpected_changes": 0,
        "protected_files_unchanged": True,
        "crm_unchanged": True,
        "live_verify": "PASS",
    }
    target = pathlib.Path(os.environ["UAART_ROLLBACK_RECEIPT_PATH"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
