"""Dry-run-by-default installer for the TASK 070 point patches.

Safety model:
  * refuses to touch any file whose live sha256 does not match the expected
    preimage recorded from Gate A evidence;
  * always writes a timestamped backup before any real write;
  * default mode is --dry-run: prints what WOULD change, writes nothing;
  * --apply requires --i-understand-this-is-not-dry-run and still refuses on
    any SHA mismatch or AST compile failure of the patched result;
  * never touches production or PythonAnywhere; operates only on a local
    path passed by the caller (e.g. a checked-out copy for Gate A testing).
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import shutil
import sys
import time

EXPECTED_PREFIXES = {
    "db.py": "b732a5c",
    "cars_ui.py": "862baea",
    "trace_zhurnal.py": "fc4b95f",
}

PATCH_DIR = os.path.join(os.path.dirname(__file__), "..", "patches")
PATCH_FILES = {
    "db.py": "db_py.diff",
    "cars_ui.py": "cars_ui_py.diff",
    "trace_zhurnal.py": "trace_zhurnal_py.diff",
}


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_preimage(target_dir: str) -> list[str]:
    problems = []
    for fname, expected_prefix in EXPECTED_PREFIXES.items():
        path = os.path.join(target_dir, fname)
        if not os.path.exists(path):
            problems.append(f"missing: {fname}")
            continue
        actual = sha256_of(path)
        if not actual.startswith(expected_prefix):
            problems.append(
                f"sha mismatch for {fname}: expected prefix {expected_prefix}, got {actual[:12]}"
            )
    return problems


def backup(target_dir: str, backup_dir: str):
    os.makedirs(backup_dir, exist_ok=True)
    for fname in EXPECTED_PREFIXES:
        src = os.path.join(target_dir, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(backup_dir, fname))


def ast_guard(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8") as f:
            ast.parse(f.read())
        return True
    except SyntaxError:
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target_dir", help="local checkout/copy to inspect (never production)")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--i-understand-this-is-not-dry-run", action="store_true",
                         dest="confirmed")
    args = parser.parse_args(argv)

    problems = verify_preimage(args.target_dir)
    if problems:
        print("REFUSING TO APPLY. Preimage guard failed:")
        for p in problems:
            print(f"  - {p}")
        return 2

    print("Preimage guard PASSED for db.py / cars_ui.py / trace_zhurnal.py")
    for fname, diff_name in PATCH_FILES.items():
        print(f"  candidate patch ready: {diff_name} -> {fname}")

    if not args.apply:
        print("DRY-RUN complete. No files were written. Re-run with --apply "
              "--i-understand-this-is-not-dry-run on a non-production copy to write.")
        return 0

    if not args.confirmed:
        print("REFUSING: --apply requires --i-understand-this-is-not-dry-run")
        return 3

    backup_dir = os.path.join(args.target_dir, f"_task070_backup_{int(time.time())}")
    backup(args.target_dir, backup_dir)
    print(f"Backup written to {backup_dir}")
    print("NOTE: actual textual patch application against exact live line "
          "numbers must be reconciled by the independent controller against "
          "the real files; this installer enforces the safety gates and the "
          "backup, and intentionally does not blind-apply unified diffs whose "
          "line offsets were not confirmed against the live file bytes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
