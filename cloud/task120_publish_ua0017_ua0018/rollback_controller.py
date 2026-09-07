#!/usr/bin/env python3
"""Restore backup A for the TASK120 CRITICAL transaction."""
from __future__ import annotations

import json
import os

import controller


def main() -> int:
    values, _request = controller.required(os.environ, "rollback")
    target = controller.receipt_target(values)
    if target.exists():
        raise controller.ControllerError("ROLLBACK_RECEIPT_PREEXISTING")
    script = controller.REMOTE_SCRIPT_LOCAL.read_bytes()
    compile(script.decode("utf-8"), "remote_installer.py", "exec")
    digest = controller._sha(script)
    api = controller.API(values["PYTHONANYWHERE_API_TOKEN"])
    backup_sha = values["UAART_BACKUP_MANIFEST_SHA256"]
    api.claim_transport(script)
    try:
        value = api.run(
            "rollback", digest,
            workflow_run_id=values["UAART_RUN_ID"],
            transaction_id=values["UAART_TRANSACTION_ID"],
            backup_sha=backup_sha,
        )
        controller.validate_receipt(value, "rollback", digest)
    finally:
        api.release_transport(script)
    if value.get("backup_manifest_sha256") != backup_sha:
        raise controller.ControllerError("REMOTE_BACKUP_IDENTITY")
    proof = value.get("rollback") or {}
    if (
        proof.get("status") != "PASS"
        or (proof.get("web") or {}).get("status") != "PASS"
        or (proof.get("media") or {}).get("status") != "PASS"
        or (proof.get("flags") or {}).get("status") != "PASS"
        or (proof.get("crm") or {}).get("status") != "UNCHANGED"
        or (proof.get("spec") or {}).get("status") != "UNCHANGED"
        or (proof.get("protected_media") or {}).get("status") != "UNCHANGED"
        or (proof.get("prevalidation") or {}).get("status") != "PASS"
    ):
        raise controller.ControllerError("REMOTE_ROLLBACK_PROOF")
    public = controller.public_preimage_verify(proof.get("public_preimage") or {})
    if public.get("status") != "PASS":
        raise controller.ControllerError("PUBLIC_ROLLBACK_VERIFY")
    receipt = {
        "schema_version": "UA-ART-PRODUCTION-ROLLBACK-RECEIPT-1",
        "operation": "rollback",
        "task_id": controller.TASK_ID,
        "request_sha256": values["UAART_REQUEST_SHA256"],
        "run_id": values["UAART_RUN_ID"],
        "transaction_id": values["UAART_TRANSACTION_ID"],
        "manifest_sha256": values["UAART_MANIFEST_SHA256"],
        "backup_manifest_sha256": backup_sha,
        "status": "ROLLED_BACK",
        "rollback": "PASS",
        "restored": True,
        "unexpected_changes": 0,
        "protected_files_unchanged": True,
        "crm_unchanged": True,
        "live_verify": "PASS",
    }
    controller._atomic_json(target, receipt)
    print(json.dumps({
        **receipt,
        "resolved_backup_manifest": value.get("backup_manifest"),
        "existing_media_unchanged": True,
        "target_media_evidence": proof.get("media"),
        "public_verification": public,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
