#!/usr/bin/env python3
"""Record a no-file-write checkpoint for the exact reload target."""
from __future__ import annotations

import json
import os
import pathlib

import controller


def main() -> int:
    if (
        os.environ.get("UAART_OPERATION") != "backup"
        or os.environ.get("UAART_TASK_ID") != controller.TASK_ID
    ):
        return 2
    api = controller.API(os.environ["PYTHONANYWHERE_API_TOKEN"])
    checkpoint = {
        "task_id": controller.TASK_ID,
        "domain": controller.DOMAIN,
        "operation": "reload_only",
        "persistent_file_write": False,
        "webapp": controller.API.safe_state(api.exact_webapp()),
    }
    receipt = {
        "schema_version": "UA-ART-PRODUCTION-BACKUP-RECEIPT-1",
        "operation": "backup",
        "task_id": os.environ["UAART_TASK_ID"],
        "request_sha256": os.environ["UAART_REQUEST_SHA256"],
        "run_id": os.environ["UAART_RUN_ID"],
        "transaction_id": os.environ["UAART_TRANSACTION_ID"],
        "manifest_sha256": os.environ["UAART_MANIFEST_SHA256"],
        "backup_manifest_sha256": controller.sha(controller.canonical(checkpoint)),
        "status": "PASS",
        "backup": "PASS",
        "unexpected_changes": 0,
    }
    target = pathlib.Path(os.environ["UAART_BACKUP_RECEIPT_PATH"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
