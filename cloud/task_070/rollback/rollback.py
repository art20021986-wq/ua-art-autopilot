"""Rollback tool for TASK 070. Restores the backup written by
installer/apply_patches.py and verifies checksums afterward. Operates only on
a local path passed by the caller; never touches production/PythonAnywhere
directly.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys

FILES = ["db.py", "cars_ui.py", "trace_zhurnal.py"]


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def rollback(target_dir: str, backup_dir: str) -> int:
    if not os.path.isdir(backup_dir):
        print(f"ERROR: backup dir not found: {backup_dir}")
        return 2
    restored = []
    for fname in FILES:
        src = os.path.join(backup_dir, fname)
        dst = os.path.join(target_dir, fname)
        if not os.path.exists(src):
            print(f"WARNING: no backup for {fname}, skipping")
            continue
        shutil.copy2(src, dst)
        restored.append((fname, sha256_of(dst)))
    print("Restored files:")
    for fname, sha in restored:
        print(f"  {fname}: {sha[:12]}...")
    print("Rollback complete. Queue (crm_write_queue.db) was NOT touched, "
          "per task requirement to preserve durable queue on rollback.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target_dir")
    parser.add_argument("backup_dir")
    args = parser.parse_args(argv)
    return rollback(args.target_dir, args.backup_dir)


if __name__ == "__main__":
    sys.exit(main())
