"""
BOT-LOGISTICS-001 Phase A — prepared, fail-closed, NOT EXECUTED Gate B
installer.

This module defines the installer logic that a future, explicitly
approved Phase B run would use. Calling `run_gate_b()` from this Phase A
deliverable will always fail closed unless every precondition holds,
and even then it stops before doing anything (see NOTE below) because
Phase A forbids execution entirely.

NOTE: `run_gate_b()` is provided for structural completeness and offline
testing of its *refusal* logic only. It must never be invoked against
real paths from this repository/environment. There is no code path in
this file that can reach `/home/Carix/*` because no caller in this
repository supplies those paths, and the safety checks below refuse
anyway if they ever were supplied without a matching, verified
discovery manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from . import bot_logistics_transform as transform


class GateBRefused(Exception):
    pass


@dataclass
class FileManifestEntry:
    path: str
    sha256: str
    mode: int
    size: int
    mtime_ns: int


def manifest_entry_for(path: str) -> FileManifestEntry:
    st = os.stat(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return FileManifestEntry(
        path=path,
        sha256=h.hexdigest(),
        mode=st.st_mode,
        size=st.st_size,
        mtime_ns=st.st_mtime_ns,
    )


def build_manifest(paths: List[str]) -> Dict[str, dict]:
    manifest = {}
    for p in paths:
        e = manifest_entry_for(p)
        manifest[p] = {
            "sha256": e.sha256,
            "mode": e.mode,
            "size": e.size,
            "mtime_ns": e.mtime_ns,
        }
    return manifest


def assert_manifest_matches_live(manifest: Dict[str, dict], paths: List[str]) -> None:
    live = build_manifest(paths)
    for p in paths:
        if manifest.get(p, {}).get("sha256") != live.get(p, {}).get("sha256"):
            raise GateBRefused(
                f"REFUSED: live SHA-256 for {p} differs from Gate A discovery manifest"
            )


def backup_source_files(paths: List[str], backup_dir: str) -> List[str]:
    os.makedirs(backup_dir, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    backed_up = []
    for p in paths:
        dest = os.path.join(backup_dir, f"{os.path.basename(p)}.{ts}.bak")
        shutil.copy2(p, dest)
        backed_up.append(dest)
    return backed_up


def backup_sqlite_consistent(db_path: str, backup_path: str) -> None:
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(backup_path)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def atomic_replace(candidate_path: str, target_path: str) -> None:
    tmp_path = target_path + ".tmp_atomic"
    shutil.copy2(candidate_path, tmp_path)
    os.replace(tmp_path, target_path)


def update_single_container_row(db_path: str, ua_id: str, new_container: str,
                                 table: str, id_col: str, container_col: str) -> bool:
    """Returns True if a change was applied, False if the value was
    already correct (idempotent no-op, not an error).
    Raises GateBRefused on any ambiguity or failure; caller must roll back.
    """
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE;")
        cur = conn.execute(
            f"SELECT \"{container_col}\" FROM '{table}' WHERE \"{id_col}\" = ?",
            (ua_id,),
        )
        rows = cur.fetchall()
        if len(rows) != 1:
            conn.execute("ROLLBACK;")
            raise GateBRefused(f"REFUSED: expected exactly 1 row for {ua_id}, found {len(rows)}")
        current_value = rows[0][0]
        normalized_new = transform.normalize_container(new_container)
        if (current_value or "").strip().upper() == normalized_new:
            conn.execute("ROLLBACK;")
            return False
        cur2 = conn.execute(
            f"UPDATE '{table}' SET \"{container_col}\" = ? WHERE \"{id_col}\" = ?",
            (normalized_new, ua_id),
        )
        if cur2.rowcount != 1:
            conn.execute("ROLLBACK;")
            raise GateBRefused(f"REFUSED: rowcount != 1 ({cur2.rowcount})")
        conn.execute("COMMIT;")
        return True
    except Exception:
        try:
            conn.execute("ROLLBACK;")
        except sqlite3.Error:
            pass
        raise
    finally:
        conn.close()


def verify_readback(db_path: str, ua_id: str, expected_container: str,
                     table: str, id_col: str, container_col: str) -> bool:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.execute("PRAGMA query_only=ON;")
        qc = conn.execute("PRAGMA quick_check;").fetchone()
        if not qc or qc[0] != "ok":
            return False
        rows = conn.execute(
            f"SELECT \"{container_col}\" FROM '{table}' WHERE \"{id_col}\" = ?",
            (ua_id,),
        ).fetchall()
        if len(rows) != 1:
            return False
        return (rows[0][0] or "").strip().upper() == expected_container.strip().upper()
    finally:
        conn.close()


def run_gate_b(*_args, **_kwargs):
    """Always refuses in Phase A. Phase B requires:
      - a verified discovery manifest committed to the repo,
      - separate explicit owner approval (APPROVE),
      - execution happening outside this Phase A deliverable.
    """
    raise GateBRefused(
        "Gate B execution is disabled in Phase A. This deliverable only "
        "provides the prepared, testable installer primitives. It ends "
        "WAITING_OWNER_APPROVAL by design and must not be invoked here."
    )
