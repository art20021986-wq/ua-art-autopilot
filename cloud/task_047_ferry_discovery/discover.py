"""
discover.py -- TASK 052 baseline-restored ferry discovery.

Restores the TASK 047 safe-read contract (lstat regular/nlink==1, O_NOFOLLOW,
fstat before/after identity, bounded read with oversize/TOCTOU BLOCK, full
SHA256) and the fixed /home/Carix registry, and adds the TASK 049 verified
CRM schema (table cars, identity auto_number, container sea_container).

No PythonAnywhere execution occurs from this module. The CLI never accepts an
arbitrary path argument; only test code may inject a temp root explicitly.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sqlite3
import stat
from pathlib import Path
from typing import Optional

import transform

DEFAULT_ROOT = Path("/home/Carix")

HTML_CORE_PAGES = [
    "video/index.html",
    "video/katalog.html",
    "video/info.html",
    "video/podbor.html",
]

UA_CARD_PAGES = [f"video/UA-{i:04d}.html" for i in range(1, 10)]

PY_MODULES = [
    "stranica.py", "yadro.py", "master_card.py", "cars_ui.py",
    "team_bot.py", "avtoperedacha.py", "db.py", "run_all.py", "start_safe.py",
]

DB_FILE_NAME = "crm.db"

REQUIRED_UA_IDS = [f"UA-{i:04d}" for i in range(1, 10)]

SECRET_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'password\s*[:=]\s*\S+',
        r'api[_-]?key\s*[:=]\s*\S+',
        r'secret\s*[:=]\s*\S+',
        r'token\s*[:=]\s*\S+',
        r'AKIA[0-9A-Z]{16}',
        r'-----BEGIN [A-Z ]*PRIVATE KEY-----',
    ]
]


def redact_text(s: str) -> str:
    for pat in SECRET_PATTERNS:
        s = pat.sub("[REDACTED]", s)
    return s


def redact_obj(obj):
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(v) for v in obj]
    return obj


def _path_has_symlink_ancestor(path: Path, root: Path) -> bool:
    p = path
    while True:
        if p.is_symlink() and p != path:
            return True
        if p == root or p == p.parent:
            break
        p = p.parent
    return False


def safe_read_file(path: Path, root: Path, max_bytes: int = 5_000_000):
    """Verified, non-following, bounded read. Returns (meta, data_or_None).

    meta["status"] is OK or BLOCKED; meta["reason"] explains BLOCKED.
    """
    result = {"path": str(path), "status": "BLOCKED", "reason": None}
    try:
        resolved = path.resolve(strict=False)
        root_resolved = root.resolve(strict=False)
        resolved.relative_to(root_resolved)
    except Exception:
        result["reason"] = "OUTSIDE_ROOT_OR_RESOLVE_FAILED"
        return result, None

    if _path_has_symlink_ancestor(path, root):
        result["reason"] = "SYMLINK_IN_PATH"
        return result, None

    try:
        st_before = os.lstat(path)
    except FileNotFoundError:
        result["reason"] = "MISSING"
        return result, None
    except OSError:
        result["reason"] = "LSTAT_FAILED"
        return result, None

    if not stat.S_ISREG(st_before.st_mode):
        result["reason"] = "NOT_REGULAR"
        return result, None
    if st_before.st_nlink != 1:
        result["reason"] = "NLINK_NOT_ONE"
        return result, None

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError:
        result["reason"] = "OPEN_FAILED"
        return result, None

    try:
        fst1 = os.fstat(fd)
        if (fst1.st_dev, fst1.st_ino) != (st_before.st_dev, st_before.st_ino):
            result["reason"] = "IDENTITY_MISMATCH"
            return result, None

        data = bytearray()
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > max_bytes:
                result["reason"] = "OVERSIZE"
                return result, None

        fst2 = os.fstat(fd)
        if (fst2.st_dev, fst2.st_ino, fst2.st_size, fst2.st_mtime_ns) != (
            fst1.st_dev, fst1.st_ino, fst1.st_size, fst1.st_mtime_ns
        ):
            result["reason"] = "CHANGED_DURING_READ"
            return result, None
        if len(data) != fst2.st_size:
            result["reason"] = "SIZE_MISMATCH"
            return result, None
    finally:
        os.close(fd)

    sha = hashlib.sha256(bytes(data)).hexdigest()
    result.update({
        "status": "OK",
        "reason": None,
        "sha256": sha,
        "size": fst2.st_size,
        "dev": fst2.st_dev,
        "inode": fst2.st_ino,
        "mtime_ns": fst2.st_mtime_ns,
    })
    return result, bytes(data)


def check_crm(db_path: Path):
    receipt = {"status": "BLOCKED", "reason": None}
    if not db_path.exists():
        receipt["reason"] = "DB_MISSING"
        return receipt
    try:
        st1 = os.lstat(db_path)
    except OSError:
        receipt["reason"] = "LSTAT_FAILED"
        return receipt

    uri = f"file:{db_path.as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("PRAGMA query_only=ON")
        qc = conn.execute("PRAGMA quick_check").fetchone()
        if not qc or qc[0] != "ok":
            conn.close()
            receipt["reason"] = "QUICK_CHECK_FAILED"
            return receipt

        cols = [r[1] for r in conn.execute("PRAGMA table_info(cars)").fetchall()]
        if "auto_number" not in cols or "sea_container" not in cols:
            conn.close()
            receipt["reason"] = "SCHEMA_MISMATCH"
            return receipt

        placeholders = ",".join("?" * len(REQUIRED_UA_IDS))
        rows = conn.execute(
            f"SELECT auto_number, sea_container FROM cars WHERE auto_number IN ({placeholders})",
            REQUIRED_UA_IDS,
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        receipt["reason"] = "SQLITE_ERROR"
        return receipt

    st2 = os.lstat(db_path)
    if (st1.st_dev, st1.st_ino, st1.st_size, st1.st_mtime_ns) != (
        st2.st_dev, st2.st_ino, st2.st_size, st2.st_mtime_ns
    ):
        receipt["reason"] = "DB_CHANGED"
        return receipt

    found_ids = [r[0] for r in rows]
    found_set = set(found_ids)
    missing = [i for i in REQUIRED_UA_IDS if i not in found_set]
    duplicates = len(found_ids) != len(found_set)

    if missing:
        receipt["reason"] = "MISSING_IDS"
        receipt["missing"] = missing
        return receipt
    if duplicates:
        receipt["reason"] = "DUPLICATE_IDS"
        return receipt

    receipt["status"] = "PASS"
    receipt["ids_found"] = sorted(found_set)
    return receipt


def run_discovery(root: Path, db_path: Optional[Path] = None) -> dict:
    root = Path(root)
    if db_path is None:
        db_path = root / DB_FILE_NAME

    if not str(root) or not root.exists():
        return {
            "status": "BLOCKED", "reason": "ROOT_MISSING", "root": str(root),
            "markers": _markers(),
        }

    required_core = list(HTML_CORE_PAGES) + list(UA_CARD_PAGES)
    html_results = {}
    missing_core = []
    total_source_occurrences = 0
    ambiguous_targets = []

    for rel in required_core:
        p = root / rel
        meta, data = safe_read_file(p, root, max_bytes=5_000_000)
        if meta["status"] != "OK":
            missing_core.append(rel)
            html_results[rel] = meta
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            meta["status"] = "BLOCKED"
            meta["reason"] = "DECODE_ERROR"
            missing_core.append(rel)
            html_results[rel] = meta
            continue
        _new_text, report = transform.transform_html(text)
        occ = len(report["changes"])
        amb = report["ambiguous"]
        total_source_occurrences += occ
        if rel in UA_CARD_PAGES and amb:
            ambiguous_targets.append(rel)
        html_results[rel] = {
            "status": "OK", "sha256": meta["sha256"], "size": meta["size"],
            "changes": occ, "ambiguous": len(amb),
        }

    py_results = {}
    for rel in PY_MODULES:
        p = root / rel
        meta, data = safe_read_file(p, root, max_bytes=5_000_000)
        if meta["status"] != "OK":
            py_results[rel] = meta
            continue
        try:
            src = data.decode("utf-8")
            ast.parse(src)
            parse_ok = True
        except (UnicodeDecodeError, SyntaxError):
            parse_ok = False
        py_results[rel] = {
            "status": "OK" if parse_ok else "BLOCKED",
            "sha256": meta["sha256"], "size": meta["size"], "parse_ok": parse_ok,
        }

    crm = check_crm(db_path)

    overall_status = "OK"
    reasons = []
    if missing_core:
        overall_status = "BLOCKED"
        reasons.append("MISSING_CORE_PAGES")
    if crm["status"] != "PASS":
        overall_status = "BLOCKED"
        reasons.append("CRM_NOT_PASS")
    if ambiguous_targets:
        overall_status = "BLOCKED"
        reasons.append("AMBIGUOUS_TARGET")
    if total_source_occurrences == 0:
        overall_status = "BLOCKED"
        reasons.append("ZERO_OCCURRENCES")

    receipt = {
        "status": overall_status,
        "reasons": reasons,
        "root": str(root),
        "html": html_results,
        "python": py_results,
        "crm": crm,
        "total_source_occurrences": total_source_occurrences,
        "ambiguous_targets": ambiguous_targets,
        "markers": _markers(),
    }
    return receipt


def _markers():
    return {
        "PRODUCTION_TOUCHED": "NO",
        "CRM_TOUCHED": "NO",
        "CRM_DB_WRITTEN": "NO",
        "GATE_B_EXECUTED": "NO",
        "UA_0009_PUBLISHED": "NO",
    }


def serialize_receipt(receipt: dict) -> str:
    redacted = redact_obj(receipt)
    s = json.dumps(redacted, ensure_ascii=False, sort_keys=True)
    for pat in SECRET_PATTERNS:
        if pat.search(s):
            minimal = {"status": "BLOCKED", "reason": "SECRET_LEAK_DETECTED"}
            return json.dumps(minimal, ensure_ascii=False, sort_keys=True)
    return s


def main():
    receipt = run_discovery(DEFAULT_ROOT)
    print(serialize_receipt(receipt))


if __name__ == "__main__":
    main()
