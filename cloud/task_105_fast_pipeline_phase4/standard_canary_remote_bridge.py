#!/usr/bin/env python3
"""Compatibility-safe remote bridge for TASK105 STANDARD canary.

It wraps the original canary executor, repairs the immutable backup-manifest
contract, supports recovery cleanup from attempt 1, and keeps the same TASK105
identity. No existing site, CRM, Cloudflare or DNS target is added.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
BASE_PATH = HERE / "task105_standard_canary_base.py"


def load_base():
    spec = importlib.util.spec_from_file_location(
        "task105_standard_canary_base", BASE_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("BASE_SPEC")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


base = load_base()
CONTRACT_ID = base.CONTRACT_ID
CLEANUP_RECEIPT = base.REMOTE / "task105_standard_canary_cleanup_receipt.json"
ENRICHMENT_KEYS = {
    "backup_root",
    "protected_before",
    "final_expected",
    "cases",
    "installed_at_utc",
}


def validate_backup_compatible(
    manifest: dict[str, Any], backup_root: pathlib.Path
) -> None:
    """Validate both the attempt-1 core manifest and the corrected full manifest."""
    if manifest.get("contract_id") != CONTRACT_ID:
        raise base.CanaryError("BACKUP_CONTRACT")
    if manifest.get("targets") != {
        name: str(path) for name, path in base.TARGETS.items()
    }:
        raise base.CanaryError("BACKUP_TARGETS")
    root = backup_root.resolve(strict=True)
    allowed = base.BACKUPS.resolve(strict=True)
    if root == allowed or not root.is_relative_to(allowed):
        raise base.CanaryError("BACKUP_PATH_ESCAPE")
    disk = json.loads(
        (backup_root / "manifest.json").read_text(encoding="utf-8")
    )
    core_keys = {"contract_id", "targets", "before", "created_at_utc"}
    for key in core_keys:
        if disk.get(key) != manifest.get(key):
            raise base.CanaryError("BACKUP_MANIFEST_CORE_MISMATCH:" + key)
    for key, value in disk.items():
        if key not in core_keys and value != manifest.get(key):
            raise base.CanaryError("BACKUP_MANIFEST_ENRICHMENT_MISMATCH:" + key)
    unexpected = set(manifest) - core_keys - ENRICHMENT_KEYS
    if unexpected:
        raise base.CanaryError(
            "BACKUP_MANIFEST_UNEXPECTED_KEYS:" + ",".join(sorted(unexpected))
        )
    for name, metadata in manifest["before"].items():
        if metadata["existed"]:
            backup_file = pathlib.Path(metadata["backup_file"])
            if not backup_file.resolve(strict=True).is_relative_to(root):
                raise base.CanaryError("BACKUP_FILE_ESCAPE:" + name)
            if base.sha_bytes(base.read_small(backup_file)) != metadata["sha256"]:
                raise base.CanaryError("BACKUP_FILE_SHA:" + name)


# All inherited restore/postcheck functions now use the compatible validator.
base.validate_backup = validate_backup_compatible


def rewrite_full_manifest() -> dict[str, Any] | None:
    if not base.LAST_SUCCESS.is_file():
        return None
    manifest = json.loads(base.LAST_SUCCESS.read_text(encoding="utf-8"))
    backup_root = pathlib.Path(manifest["backup_root"])
    validate_backup_compatible(manifest, backup_root)
    base.atomic_json(backup_root / "manifest.json", manifest)
    validate_backup_compatible(manifest, backup_root)
    return manifest


def run_cleanup() -> dict[str, Any]:
    started = base.utc_now()
    base.assert_scope()
    with base.production_lock():
        if not base.LAST_SUCCESS.is_file():
            return {
                "contract_id": CONTRACT_ID,
                "status": "PASS",
                "mode": "CLEANUP",
                "production_write": False,
                "crm_write": False,
                "cleanup_needed": False,
                "protected_unchanged": True,
                "runtime_llm_tokens": 0,
                "started_at_utc": started,
                "finished_at_utc": base.utc_now(),
                "errors": [],
            }
        manifest = rewrite_full_manifest()
        if manifest is None:
            raise base.CanaryError("CLEANUP_MANIFEST_MISSING")
        backup_root = pathlib.Path(manifest["backup_root"])
        protected_before = base.protected_snapshot()
        restored = base.restore_initial(manifest, backup_root)
        protected_after = base.protected_snapshot()
        if protected_before != protected_after:
            raise base.CanaryError("CLEANUP_PROTECTED_DRIFT")
        base.LAST_SUCCESS.unlink()
        base.fsync_dir(base.LAST_SUCCESS.parent)
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "mode": "CLEANUP",
        "production_write": True,
        "crm_write": False,
        "cleanup_needed": True,
        "restored": restored,
        "rollback_source": str(backup_root),
        "protected_before": protected_before,
        "protected_after": protected_after,
        "protected_unchanged": True,
        "runtime_llm_tokens": 0,
        "started_at_utc": started,
        "finished_at_utc": base.utc_now(),
        "errors": [],
    }


def run_install() -> dict[str, Any]:
    result = base.run_install()
    if result.get("status") == "PASS":
        rewrite_full_manifest()
    return result


def run_postcheck() -> dict[str, Any]:
    rewrite_full_manifest()
    return base.run_postcheck()


def run_rollback() -> dict[str, Any]:
    rewrite_full_manifest()
    result = base.run_rollback()
    if result.get("status") == "PASS" and base.LAST_SUCCESS.exists():
        base.LAST_SUCCESS.unlink()
        base.fsync_dir(base.LAST_SUCCESS.parent)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=("cleanup", "install", "postcheck", "rollback")
    )
    args = parser.parse_args()
    receipt = {
        "cleanup": CLEANUP_RECEIPT,
        "install": base.RECEIPTS["install"],
        "postcheck": base.RECEIPTS["postcheck"],
        "rollback": base.RECEIPTS["rollback"],
    }[args.mode]
    try:
        result = {
            "cleanup": run_cleanup,
            "install": run_install,
            "postcheck": run_postcheck,
            "rollback": run_rollback,
        }[args.mode]()
    except Exception as exc:
        result = {
            "contract_id": CONTRACT_ID,
            "status": "FAIL",
            "mode": args.mode.upper(),
            "production_write": False,
            "crm_write": False,
            "errors": [type(exc).__name__ + ":" + str(exc)],
            "finished_at_utc": base.utc_now(),
        }
    base.atomic_json(receipt, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
