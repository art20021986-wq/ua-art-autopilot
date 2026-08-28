"""TASK 071 — rollback helper.

Restores the pre-patch backup created by installer.backup_dir() into the
temporary source-copy directory, and clears any test-only queue database
created during a Gate A run. Operates ONLY inside the runner's temp
directories; never touches any live/production path.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def rollback_source(source_dir: Path) -> dict:
    backup = source_dir.parent / (source_dir.name + ".ua071_backup")
    if not backup.exists():
        return {"status": "no_backup_found", "source_dir": str(source_dir)}
    for item in backup.iterdir():
        dest = source_dir / item.name
        if dest.exists():
            dest.unlink()
        shutil.copy2(item, dest)
    return {"status": "rolled_back", "source_dir": str(source_dir)}


def clear_test_queue(queue_db_path: Path) -> dict:
    if queue_db_path.exists():
        queue_db_path.unlink()
        return {"status": "queue_cleared", "path": str(queue_db_path)}
    return {"status": "no_queue_found", "path": str(queue_db_path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    parser.add_argument("--queue-db", required=False)
    args = parser.parse_args()

    print(rollback_source(Path(args.source_dir)))
    if args.queue_db:
        print(clear_test_queue(Path(args.queue_db)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
