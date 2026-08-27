#!/usr/bin/env python3
"""
uaart_backup_gate.py — TASK 012 Phase D

Intended for later Gate-A-approved execution only. Creates ONE timestamped,
non-public security backup of an explicit allowlist of critical files.
Stdlib-only (Python 3.10+). Never mutates production; only reads production
files and writes new backup copies under a dedicated, non-web-root backup
directory.

Restore is explicitly NOT performed by this script — restore is a separate,
future Gate B action requiring its own explicit owner approval.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path("/home/Carix").resolve()

# Dedicated, non-public backup root. Must never be under any web/static/
# media/public directory.
BACKUP_ROOT = (ROOT / "security_backups").resolve()

PUBLIC_ROOT_CANDIDATES = [
    (ROOT / "video").resolve(),
    (ROOT / "static").resolve(),
    (ROOT / "media").resolve(),
    (ROOT / "public").resolve(),
]

# Explicit allowlist of files eligible for backup. Nothing outside this list
# is ever copied. Non-existent candidates are simply skipped and reported.
BACKUP_FILE_ALLOWLIST = [
    ROOT / "crm.db",
    ROOT / "mysite" / "wsgi.py",
    ROOT / "mysite" / "settings.py",
    ROOT / "app.py",
    ROOT / "generator.py",
    ROOT / "main.py",
]

RETENTION_PROPOSAL_DAYS = 30  # proposal only; this script never deletes
                              # old backups automatically.


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def assert_backup_root_is_private():
    for pub in PUBLIC_ROOT_CANDIDATES:
        if pub.exists() and is_within(BACKUP_ROOT, pub):
            raise RuntimeError("refusing: backup root would be inside a public web root")


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def backup_sqlite_consistent(src: Path, dest: Path):
    """Use SQLite's backup API against a read-only connection so the copy is
    transactionally consistent, instead of a blind byte-level file copy."""
    uri = f"file:{src.as_posix()}?mode=ro"
    src_conn = sqlite3.connect(uri, uri=True)
    try:
        src_conn.execute("PRAGMA query_only=ON;")
        dest_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()


def atomic_copy(src: Path, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_backup_", dir=str(dest.parent))
    os.close(fd)
    try:
        shutil.copy2(src, tmp_path)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, dest)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def main():
    assert_backup_root_is_private()
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(BACKUP_ROOT, 0o700)
    except Exception:
        pass

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    session_dir = BACKUP_ROOT / f"backup_{stamp}"
    session_dir.mkdir(parents=True, exist_ok=False, mode=0o700)

    manifest = {
        "created_at_utc": stamp,
        "backup_root": str(BACKUP_ROOT),
        "session_dir": str(session_dir),
        "files": [],
        "skipped": [],
        "retention_proposal_days": RETENTION_PROPOSAL_DAYS,
        "note": "Backup only. No production mutation. Restore requires a separate Gate B action.",
    }

    for src in BACKUP_FILE_ALLOWLIST:
        if not src.exists():
            manifest["skipped"].append({"path": str(src), "reason": "not found"})
            continue
        rel_name = src.name
        dest = session_dir / rel_name
        try:
            if src.name == "crm.db":
                backup_sqlite_consistent(src, dest)
            else:
                atomic_copy(src, dest)
            digest = sha256_of_file(dest)
            manifest["files"].append({
                "source": str(src),
                "backup_path": str(dest),
                "sha256": digest,
            })
        except Exception as exc:
            manifest["skipped"].append({"path": str(src), "reason": f"{type(exc).__name__}: {exc}"})

    manifest_path = session_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    try:
        os.chmod(manifest_path, 0o600)
    except Exception:
        pass

    receipt = {
        "status": "BACKUP_CREATED",
        "session_dir": str(session_dir),
        "manifest": str(manifest_path),
        "files_backed_up": len(manifest["files"]),
        "files_skipped": len(manifest["skipped"]),
        "restore_instructions": (
            "Restore is NOT performed automatically. To restore crm.db, an owner-"
            "approved Gate B action must: (1) stop write access to the live DB, "
            "(2) copy the desired backup file over the production path, (3) verify "
            "SHA-256 matches manifest, (4) resume service. For other files, replace "
            "the production file with the backup copy only after Gate B approval "
            "and SHA-256 verification against this manifest."
        ),
    }
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
