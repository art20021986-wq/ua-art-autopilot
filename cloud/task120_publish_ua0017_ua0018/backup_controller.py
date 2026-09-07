#!/usr/bin/env python3
"""Create immutable backup A for the TASK120 CRITICAL transaction."""
from __future__ import annotations

import json
import os

import controller


def main() -> int:
    values, _request = controller.required(os.environ, "backup")
    target = controller.receipt_target(values)
    if target.exists():
        raise controller.ControllerError("BACKUP_RECEIPT_PREEXISTING")
    script = controller.REMOTE_SCRIPT_LOCAL.read_bytes()
    compile(script.decode("utf-8"), "remote_installer.py", "exec")
    digest = controller._sha(script)
    api = controller.API(values["PYTHONANYWHERE_API_TOKEN"])
    api.claim_transport(script)
    try:
        probe = api.run(
            "probe", digest,
            workflow_run_id=values["UAART_RUN_ID"],
            transaction_id=values["UAART_TRANSACTION_ID"],
        )
        controller.validate_receipt(probe, "probe", digest)
        controller.validate_probe(probe)
        backup = api.run(
            "backup", digest,
            workflow_run_id=values["UAART_RUN_ID"],
            transaction_id=values["UAART_TRANSACTION_ID"],
            preflight=probe["observation"]["preflight_digest"],
        )
        controller.validate_receipt(backup, "backup", digest)
    finally:
        api.release_transport(script)
    backup_sha = str(backup.get("backup_manifest_sha256") or "")
    if not controller.SHA_RE.fullmatch(backup_sha):
        raise controller.ControllerError("REMOTE_BACKUP_IDENTITY")
    receipt = {
        "schema_version": "UA-ART-PRODUCTION-BACKUP-RECEIPT-1",
        "operation": "backup",
        "task_id": controller.TASK_ID,
        "request_sha256": values["UAART_REQUEST_SHA256"],
        "run_id": values["UAART_RUN_ID"],
        "transaction_id": values["UAART_TRANSACTION_ID"],
        "manifest_sha256": values["UAART_MANIFEST_SHA256"],
        "backup_manifest_sha256": backup_sha,
        "status": "PASS",
        "backup": "PASS",
        "unexpected_changes": 0,
    }
    controller._atomic_json(target, receipt)
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
