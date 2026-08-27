"""TASK 043 — Hardened, fail-closed, read-only PythonAnywhere discovery tool.

This tool NEVER writes anything. It reads a bounded, hardcoded candidate
file registry rooted at the real account root, verifies file identity
(no symlinks, no multi-hardlink ambiguity, no TOCTOU swap), redacts secret
lines, classifies every ferry-wording occurrence, and emits exactly one
strict JSON object to stdout when run as a script.

Standard library only.
"""

import hashlib
import json
import os
import re
import sqlite3
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from transform import classify_text  # noqa: E402

ALLOWED_ROOT_DEFAULT = "/home/Carix"

# Bounded, hardcoded candidate registry. Nothing outside this list is ever
# scanned. No recursive directory walk of the account is performed.
CANDIDATE_REGISTRY = [
    "stranica.py", "yadro.py", "master_card.py", "cars_ui.py",
    "team_bot.py", "avtoperedacha.py", "db.py", "run_all.py", "start_safe.py",
    "video/public/index.html", "video/public/catalog.html",
] + ["video/public/UA-000%d.html" % i for i in range(1, 10)] + ["crm.db"]

MAX_FILES = 64
MAX_BYTES_PER_FILE = 262144
MAX_MATCHES_PER_FILE = 50

SECRET_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    r"secret", r"token", r"password", r"api[-_]?key", r"authorization",
    r"private[-_]?key", r"credential", r"[A-Za-z0-9]{32,}",
]]

ANCHOR_PHRASES = ["В море", "У морі", "На пароме", "На поромі"]


class DiscoveryBlocked(Exception):
    pass


def redact_line(line):
    for pat in SECRET_PATTERNS:
        if pat.search(line):
            return "[REDACTED LINE]"
    return line


def lstat_check(full_path):
    st = os.lstat(full_path)
    if stat.S_ISLNK(st.st_mode):
        raise DiscoveryBlocked("symlink rejected: %s" % full_path)
    if not stat.S_ISREG(st.st_mode):
        raise DiscoveryBlocked("not a regular file: %s" % full_path)
    if getattr(st, "st_nlink", 1) != 1:
        raise DiscoveryBlocked("hardlink identity unproven: %s" % full_path)
    return st


def safe_read(full_path, max_bytes):
    before = lstat_check(full_path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(full_path, flags)
    try:
        after = os.fstat(fd)
        if (after.st_ino, after.st_dev) != (before.st_ino, before.st_dev):
            raise DiscoveryBlocked("TOCTOU identity mismatch: %s" % full_path)
        data = os.read(fd, max_bytes + 1)
    finally:
        os.close(fd)
    truncated = len(data) > max_bytes
    return data[:max_bytes], truncated, after


def scan_text_file(root, rel_path):
    full_path = os.path.join(root, rel_path)
    if not os.path.exists(full_path):
        return None
    data, truncated, _st = safe_read(full_path, MAX_BYTES_PER_FILE)
    sha = hashlib.sha256(data).hexdigest()
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    occurrences = []
    seen = set()
    for idx, line in enumerate(lines):
        if len(occurrences) >= MAX_MATCHES_PER_FILE:
            break
        if not any(p in line for p in ANCHOR_PHRASES):
            continue
        key = (idx, line)
        if key in seen:
            continue
        seen.add(key)
        classification = classify_text(line)
        context = redact_line(line)[:200]
        occurrences.append({
            "line": idx + 1,
            "classification": classification,
            "context": context,
        })
    return {
        "path": rel_path,
        "sha256": sha,
        "bytes_read": len(data),
        "truncated": truncated,
        "occurrences": occurrences,
    }


def query_crm_db_readonly(full_path, ua_ids):
    if not os.path.exists(full_path):
        return {"available": False, "reason": "crm.db not present in registry root"}
    try:
        lstat_check(full_path)
    except DiscoveryBlocked as exc:
        return {"available": False, "reason": str(exc)}
    uri = "file:%s?mode=ro" % full_path
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("PRAGMA query_only=ON")
        quick = conn.execute("PRAGMA quick_check").fetchone()
        cur = conn.cursor()
        placeholders = ",".join("?" for _ in ua_ids)
        schema_error = None
        rows = []
        try:
            cur.execute(
                "SELECT id, stage FROM cars WHERE id IN (%s)" % placeholders,
                list(ua_ids),
            )
            rows = cur.fetchall()
        except sqlite3.OperationalError as exc:
            schema_error = str(exc)
        conn.close()
        return {
            "available": True,
            "quick_check": quick[0] if quick else None,
            "rows": rows,
            "schema_error": schema_error,
        }
    except sqlite3.Error as exc:
        return {"available": False, "reason": "sqlite error: %s" % exc}


def run_discovery(root=ALLOWED_ROOT_DEFAULT, allowed_root=ALLOWED_ROOT_DEFAULT,
                   registry=None, max_files=MAX_FILES, ua_ids=None):
    if root != allowed_root:
        raise DiscoveryBlocked(
            "root %r does not match allowed account root %r" % (root, allowed_root)
        )
    if registry is None:
        registry = CANDIDATE_REGISTRY
    if ua_ids is None:
        ua_ids = ["UA-000%d" % i for i in range(1, 10)]
    files = []
    blocked = []
    count = 0
    for rel_path in registry:
        if count >= max_files:
            blocked.append({"path": rel_path, "reason": "max_files cap reached"})
            continue
        if rel_path == "crm.db":
            continue
        try:
            result = scan_text_file(root, rel_path)
        except DiscoveryBlocked as exc:
            blocked.append({"path": rel_path, "reason": str(exc)})
            continue
        if result is not None:
            files.append(result)
            count += 1
    crm_result = query_crm_db_readonly(os.path.join(root, "crm.db"), ua_ids)
    receipt = {
        "task": "task_043_ferry_wording",
        "root": root,
        "files_scanned": len(files),
        "files": files,
        "blocked": blocked,
        "crm_db": crm_result,
        "production_touched": "NO",
        "crm_touched": "NO",
        "crm_db_written": "NO",
        "gate_b_executed": "NO",
    }
    return receipt


if __name__ == "__main__":
    receipt = run_discovery()
    sys.stdout.write(json.dumps(receipt, sort_keys=True))
    sys.stdout.write("\n")
