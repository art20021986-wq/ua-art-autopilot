"""TASK 047 — Bounded, fail-closed, read-only discovery.

No production write. No CRM write. No Gate A/B execution. Reads only,
from a fixed registry, under a single base directory. Missing files are
reported honestly, never fabricated.

BASE_DIR defaults to /home/Carix and can only be overridden via the
FERRY_DISCOVERY_BASE_DIR environment variable, which exists solely to make
this module testable without touching any real filesystem.
"""

import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
from typing import Dict, List, Optional, Tuple

BASE_DIR = os.environ.get("FERRY_DISCOVERY_BASE_DIR", "/home/Carix")

MAX_SIZE = 20 * 1024 * 1024  # 20 MiB bound for a single file read

UA_IDS = tuple("UA-%04d" % i for i in range(1, 10))

REGISTRY: Dict[str, List[str]] = {
    "video_pages": [
        "video/index.html", "video/katalog.html", "video/info.html", "video/podbor.html",
    ] + ["video/UA-%04d.html" % i for i in range(1, 10)],
    "site_pages": [
        "site/index.html", "site/katalog.html", "site/info.html", "site/podbor.html",
    ] + ["site/UA-%04d.html" % i for i in range(1, 10)],
    "diag_track_candidates": (
        ["video/UA-%04d-diag.html" % i for i in range(1, 10)]
        + ["video/UA-%04d-track.html" % i for i in range(1, 10)]
    ),
    "python_modules": [
        "stranica.py", "yadro.py", "master_card.py", "cars_ui.py", "team_bot.py",
        "avtoperedacha.py", "db.py", "run_all.py", "start_safe.py",
    ],
    "database": ["crm.db"],
}

TABLE_ALLOWLIST = {"cars", "cards", "orders", "catalog", "vehicles"}
COLUMN_ALLOWLIST = {
    "id", "catalog_id", "ua_id", "code", "stage", "status",
    "container", "tracking", "diagnostics", "cta",
}

SECRET_RE = re.compile(
    r"(?i)\b(secret|token|password|api[-_]?key|authorization|private[-_]?key|credential)\b\s*[:=]\s*\S+"
)


class _PathIssue(Exception):
    def __init__(self, kind: str, reason: str) -> None:
        self.kind = kind
        self.reason = reason
        super().__init__(reason)


def _resolve_contained_path(base_dir: str, rel_path: str) -> str:
    base_real = os.path.realpath(base_dir)
    rel_norm = os.path.normpath(rel_path)
    parts = rel_norm.split(os.sep)
    if os.path.isabs(rel_norm) or parts[0] == "..":
        raise _PathIssue("BLOCKED", "PATH_ESCAPE_RELATIVE")
    cur_path = base_dir
    for part in parts[:-1]:
        cur_path = os.path.join(cur_path, part)
        if os.path.islink(cur_path):
            raise _PathIssue("BLOCKED", "SYMLINK_PARENT")
        if not os.path.isdir(cur_path):
            raise _PathIssue("MISSING", "MISSING_PARENT_DIR")
    full = os.path.join(cur_path, parts[-1])
    full_real = os.path.realpath(full)
    try:
        common = os.path.commonpath([base_real, full_real])
    except ValueError:
        raise _PathIssue("BLOCKED", "PATH_ESCAPE_DIFFERENT_ROOT")
    if common != base_real:
        raise _PathIssue("BLOCKED", "PATH_ESCAPE")
    return full


def safe_read_file(base_dir: str, rel_path: str) -> dict:
    try:
        full = _resolve_contained_path(base_dir, rel_path)
    except _PathIssue as exc:
        if exc.kind == "MISSING":
            return {"status": "MISSING", "path": rel_path}
        return {"status": "BLOCKED", "reason": exc.reason, "path": rel_path}

    try:
        st_l = os.lstat(full)
    except FileNotFoundError:
        return {"status": "MISSING", "path": rel_path}
    except OSError as exc:
        return {"status": "BLOCKED", "reason": "LSTAT_FAILED:%s" % exc, "path": rel_path}

    if stat.S_ISLNK(st_l.st_mode):
        return {"status": "BLOCKED", "reason": "SYMLINK_FINAL", "path": rel_path}
    if not stat.S_ISREG(st_l.st_mode):
        return {"status": "BLOCKED", "reason": "NOT_REGULAR_FILE", "path": rel_path}
    if st_l.st_nlink != 1:
        return {"status": "BLOCKED", "reason": "HARDLINK_DETECTED", "path": rel_path}

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        fd = os.open(full, flags)
    except OSError as exc:
        return {"status": "BLOCKED", "reason": "OPEN_FAILED:%s" % exc, "path": rel_path}

    try:
        st_before = os.fstat(fd)
        identity_before = (st_before.st_dev, st_before.st_ino, st_before.st_size, st_before.st_mtime_ns)
        identity_lstat = (st_l.st_dev, st_l.st_ino, st_l.st_size, st_l.st_mtime_ns)
        if identity_before != identity_lstat:
            return {"status": "BLOCKED", "reason": "TOCTOU_MISMATCH", "path": rel_path}
        if st_before.st_size > MAX_SIZE:
            return {"status": "BLOCKED", "reason": "OVERSIZE", "path": rel_path}

        data = b""
        remaining = st_before.st_size
        while remaining > 0:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                return {"status": "BLOCKED", "reason": "TRUNCATED_READ", "path": rel_path}
            data += chunk
            remaining -= len(chunk)

        extra = os.read(fd, 1)
        if extra:
            return {"status": "BLOCKED", "reason": "SIZE_CHANGED_DURING_READ", "path": rel_path}

        st_after = os.fstat(fd)
        identity_after = (st_after.st_dev, st_after.st_ino, st_after.st_size, st_after.st_mtime_ns)
        if identity_after != identity_before:
            return {"status": "BLOCKED", "reason": "TOCTOU_AFTER_READ", "path": rel_path}
    finally:
        os.close(fd)

    try:
        data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return {"status": "BLOCKED", "reason": "NON_UTF8", "path": rel_path}

    sha = hashlib.sha256(data).hexdigest()
    return {
        "status": "OK",
        "path": rel_path,
        "sha256": sha,
        "size": len(data),
        "mtime_ns": st_after.st_mtime_ns,
        "dev": st_after.st_dev,
        "ino": st_after.st_ino,
    }


def discover_registry(base_dir: str = BASE_DIR) -> Dict[str, dict]:
    results: Dict[str, dict] = {}
    for _cat, files in REGISTRY.items():
        for f in files:
            results[f] = safe_read_file(base_dir, f)
    return results


def _lstat_identity(path: str) -> Tuple[int, int, int, int]:
    st_l = os.lstat(path)
    return (st_l.st_dev, st_l.st_ino, st_l.st_size, st_l.st_mtime_ns)


def crm_readonly_summary(path: str) -> dict:
    if not os.path.exists(path):
        return {"status": "MISSING", "path": path}
    try:
        identity_before = _lstat_identity(path)
    except OSError as exc:
        return {"status": "BLOCKED", "reason": "LSTAT_FAILED:%s" % exc}

    uri = "file:%s?mode=ro" % path
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        return {"status": "BLOCKED", "reason": "CONNECT_FAILED:%s" % exc}

    try:
        cur = conn.cursor()
        cur.execute("PRAGMA query_only=ON")
        cur.execute("PRAGMA quick_check")
        qc_row = cur.fetchone()
        quick_check_ok = bool(qc_row) and qc_row[0] == "ok"

        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        matched_tables = [t for t in tables if t.lower() in TABLE_ALLOWLIST]
        if not matched_tables:
            return {"status": "BLOCKED", "reason": "AMBIGUOUS_SCHEMA_NO_TABLE", "quick_check": quick_check_ok}

        table = matched_tables[0]
        cur.execute("PRAGMA table_info(%s)" % table)
        cols = [r[1] for r in cur.fetchall()]
        matched_cols = [c for c in cols if c.lower() in COLUMN_ALLOWLIST]
        id_col = next((c for c in matched_cols if "id" in c.lower() or c.lower() == "code"), None)
        if not id_col or not matched_cols:
            return {"status": "BLOCKED", "reason": "AMBIGUOUS_SCHEMA_NO_ID_COLUMN", "quick_check": quick_check_ok}

        col_list = ", ".join(matched_cols)
        results: Dict[str, Optional[dict]] = {}
        for ua in UA_IDS:
            query = "SELECT %s FROM %s WHERE %s = ?" % (col_list, table, id_col)
            cur.execute(query, (ua,))
            row = cur.fetchone()
            results[ua] = dict(zip(matched_cols, row)) if row else None
    except sqlite3.Error as exc:
        return {"status": "BLOCKED", "reason": "SQLITE_ERROR:%s" % exc}
    finally:
        conn.close()

    try:
        identity_after = _lstat_identity(path)
    except OSError as exc:
        return {"status": "BLOCKED", "reason": "LSTAT_FAILED_AFTER:%s" % exc}
    if identity_after != identity_before:
        return {"status": "BLOCKED", "reason": "IDENTITY_CHANGED_AFTER_READ"}

    return {
        "status": "OK",
        "quick_check": quick_check_ok,
        "table": table,
        "id_column": id_col,
        "results": results,
    }


def discover_all(base_dir: str = BASE_DIR) -> dict:
    registry_result = discover_registry(base_dir)
    crm_result = crm_readonly_summary(os.path.join(base_dir, "crm.db"))
    return {"base_dir": base_dir, "registry": registry_result, "crm": crm_result}


def scan_for_secrets(serialized: str) -> bool:
    return bool(SECRET_RE.search(serialized))


def redact_secrets(serialized: str) -> str:
    return SECRET_RE.sub(lambda m: m.group(1) + "=[REDACTED]", serialized)


def main() -> int:
    try:
        report = discover_all(BASE_DIR)
        receipt = {"status": "OK", "report": report}
    except Exception as exc:  # noqa: BLE001 - fail closed, single JSON, no traceback
        receipt = {"status": "BLOCKED", "reason": "EXCEPTION:%s:%s" % (type(exc).__name__, exc)}

    serialized = json.dumps(receipt, ensure_ascii=False, sort_keys=True)
    if scan_for_secrets(serialized):
        serialized = redact_secrets(serialized)
    sys.stdout.write(serialized + "\n")
    return 0 if receipt.get("status") == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
