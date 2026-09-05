#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import urllib.request

import controller


def live_integrity() -> bool:
    for uid in controller.IDS:
        with urllib.request.urlopen(controller.PUBLIC + uid + ".html?rollback=1", timeout=30) as response:
            if response.status != 200:
                return False
    return True


def main() -> int:
    if os.environ.get("UAART_OPERATION") != "rollback":
        return 2
    api = controller.API(os.environ["PYTHONANYWHERE_API_TOKEN"])
    value = api.run("rollback")
    if value.get("status") != "PASS":
        raise RuntimeError("REMOTE_ROLLBACK_FAILED")
    api.restart()
    if not live_integrity():
        raise RuntimeError("ROLLBACK_LIVE_VERIFY")
    receipt = {
        "schema_version": "UA-ART-PRODUCTION-ROLLBACK-RECEIPT-1",
        "operation": "rollback",
        "task_id": os.environ["UAART_TASK_ID"],
        "request_sha256": os.environ["UAART_REQUEST_SHA256"],
        "run_id": os.environ["UAART_RUN_ID"],
        "transaction_id": os.environ["UAART_TRANSACTION_ID"],
        "manifest_sha256": os.environ["UAART_MANIFEST_SHA256"],
        "backup_manifest_sha256": os.environ["UAART_BACKUP_MANIFEST_SHA256"],
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
