"""TASK 071 — dry-run/apply installer operating on LOCAL TEMPORARY COPIES only.

Usage:
    python installer.py --source-dir <tmp_source_copy> --dry-run
    python installer.py --source-dir <tmp_source_copy> --apply
    python installer.py --source-dir <tmp_source_copy> --rollback

This installer never touches any live/production path. Callers (the
controller) are responsible for making the temporary copy from a GET-only
download before invoking this installer.
"""
from __future__ import annotations

import argparse
import ast
import shutil
import sys
from pathlib import Path

from cloud.task_071.patch_transformer import ALL_PATCHES, PatchRejected, apply_anchor_patch


def backup_dir(source_dir: Path) -> Path:
    backup = source_dir.parent / (source_dir.name + ".ua071_backup")
    if backup.exists():
        shutil.rmtree(backup)
    shutil.copytree(source_dir, backup)
    return backup


def dry_run(source_dir: Path) -> dict:
    report = {"mode": "dry_run", "results": []}
    for patch in ALL_PATCHES:
        target = source_dir / patch.file_name
        entry = {"file": patch.file_name}
        if not target.exists():
            entry["status"] = "missing"
        else:
            from cloud.task_071.patch_transformer import sha256_of
            actual = sha256_of(target)
            entry["sha_match"] = actual == patch.expected_sha256
            entry["status"] = "ready" if entry["sha_match"] else "sha_mismatch_blocked"
        report["results"].append(entry)
    return report


def apply(source_dir: Path) -> dict:
    backup = backup_dir(source_dir)
    report = {"mode": "apply", "backup": str(backup), "results": []}
    try:
        for patch in ALL_PATCHES:
            target = source_dir / patch.file_name
            entry = {"file": patch.file_name}
            try:
                apply_anchor_patch(target, patch)
                ast.parse(target.read_text(encoding="utf-8"))
                entry["status"] = "applied"
            except PatchRejected as exc:
                entry["status"] = "rejected"
                entry["reason"] = str(exc)
                report["results"].append(entry)
                raise
            report["results"].append(entry)
    except PatchRejected:
        rollback(source_dir, backup)
        report["rolled_back"] = True
    return report


def rollback(source_dir: Path, backup: Path) -> None:
    if not backup.exists():
        return
    for item in backup.iterdir():
        dest = source_dir / item.name
        if dest.exists():
            dest.unlink()
        shutil.copy2(item, dest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    group.add_argument("--rollback", action="store_true")
    args = parser.parse_args()

    source_dir = Path(args.source_dir)
    if args.dry_run:
        print(dry_run(source_dir))
    elif args.apply:
        print(apply(source_dir))
    elif args.rollback:
        backup = source_dir.parent / (source_dir.name + ".ua071_backup")
        rollback(source_dir, backup)
        print({"status": "rolled_back"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
