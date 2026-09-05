#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import re
import time
import urllib.request

import controller


ROLLBACK_TARGET_PATHS = frozenset(
    "/home/Carix/" + name for name in (
        "ua_additional_spec.py", "vin_spec_service.py", "master_card.py",
        "stranica.py", "yadro.py", "cars_ui.py", "client_ui.py",
        "publikaciya.py",
    )
) | frozenset(
    "/home/Carix/" + surface + "/" + uid + ".html"
    for surface in ("video", "site") for uid in controller.IDS
)


def validate_rollback_backup(value: dict, expected_sha256: str) -> dict[str, str]:
    if (value.get("task_id") != controller.TASK_ID
            or value.get("contract_id") != controller.CONTRACT
            or value.get("mode") != "ROLLBACK"
            or value.get("crm_write") is not False
            or value.get("media_write") is not False):
        raise RuntimeError("REMOTE_ROLLBACK_IDENTITY")
    actual = value.get("backup_manifest_sha256")
    if actual != expected_sha256:
        raise RuntimeError("REMOTE_ROLLBACK_BACKUP_MISMATCH")
    if (value.get("status") != "PASS" or value.get("restored_exact") is not True
            or value.get("protected_files_unchanged") is not True
            or value.get("crm_unchanged") is not True
            or type(value.get("unexpected_changes")) is not int
            or value.get("unexpected_changes") != 0):
        raise RuntimeError("REMOTE_ROLLBACK_PROOF_MISSING")
    restored_sha256 = value.get("restored_sha256")
    if (not isinstance(restored_sha256, dict)
            or set(restored_sha256) != ROLLBACK_TARGET_PATHS
            or any(not isinstance(path, str) or not isinstance(digest, str)
                   or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                   for path, digest in restored_sha256.items())):
        raise RuntimeError("REMOTE_ROLLBACK_HASHES_INVALID")
    restored_mode = value.get("restored_mode")
    if (not isinstance(restored_mode, dict)
            or set(restored_mode) != ROLLBACK_TARGET_PATHS
            or any(type(mode) is not int or mode < 0 or mode > 0o7777
                   for mode in restored_mode.values())):
        raise RuntimeError("REMOTE_ROLLBACK_MODES_INVALID")
    return restored_sha256


def live_integrity(restored_sha256: dict[str, str]) -> bool:
    for uid in controller.IDS:
        request = urllib.request.Request(
            controller.PUBLIC + uid + ".html?rollback=" + str(time.time_ns()),
            headers={"Cache-Control": "no-cache", "User-Agent": "ua-art-task115-rollback/1"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(controller.MAX_BYTES + 1)
            expected = restored_sha256["/home/Carix/video/" + uid + ".html"]
            if (response.status != 200 or len(body) > controller.MAX_BYTES
                    or controller.sha(body) != expected):
                return False
    return True


def main() -> int:
    if os.environ.get("UAART_OPERATION") != "rollback":
        return 2
    api = controller.API(os.environ["PYTHONANYWHERE_API_TOKEN"])
    expected_backup_sha256 = os.environ["UAART_BACKUP_MANIFEST_SHA256"]
    value = api.run("rollback", backup_manifest_sha256=expected_backup_sha256)
    restored_sha256 = validate_rollback_backup(value, expected_backup_sha256)
    api.remove_legacy_vin_ad_triggers({})
    api.remove_legacy_vin_ad_remote_files({})
    api.restart()
    if not live_integrity(restored_sha256):
        raise RuntimeError("ROLLBACK_LIVE_VERIFY")
    receipt = {
        "schema_version": "UA-ART-PRODUCTION-ROLLBACK-RECEIPT-1",
        "operation": "rollback",
        "task_id": os.environ["UAART_TASK_ID"],
        "request_sha256": os.environ["UAART_REQUEST_SHA256"],
        "run_id": os.environ["UAART_RUN_ID"],
        "transaction_id": os.environ["UAART_TRANSACTION_ID"],
        "manifest_sha256": os.environ["UAART_MANIFEST_SHA256"],
        "backup_manifest_sha256": expected_backup_sha256,
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
