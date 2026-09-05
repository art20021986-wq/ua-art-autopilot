#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib

import controller


def main() -> int:
    if os.environ.get("UAART_OPERATION") != "backup":
        return 2
    api = controller.API(os.environ["PYTHONANYWHERE_API_TOKEN"])
    script = pathlib.Path(__file__).with_name("remote_installer.py").read_bytes()
    compile(script.decode("utf-8"), "remote_installer.py", "exec")
    api.upload(controller.REMOTE_SCRIPT, script)
    value = api.run("backup")
    if value.get("status") != "PASS" or value.get("mode") != "BACKUP":
        raise RuntimeError("REMOTE_BACKUP_FAILED")
    receipt = {
        "schema_version": "UA-ART-PRODUCTION-BACKUP-RECEIPT-1",
        "operation": "backup",
        "task_id": os.environ["UAART_TASK_ID"],
        "request_sha256": os.environ["UAART_REQUEST_SHA256"],
        "run_id": os.environ["UAART_RUN_ID"],
        "transaction_id": os.environ["UAART_TRANSACTION_ID"],
        "manifest_sha256": os.environ["UAART_MANIFEST_SHA256"],
        "backup_manifest_sha256": value["backup_manifest_sha256"],
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
