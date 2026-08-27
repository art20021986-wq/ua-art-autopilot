#!/usr/bin/env python3
"""
uaart_security_audit.py — TASK 012 Phase B

STRICTLY READ-ONLY audit tool intended for later Gate-A-approved execution
on PythonAnywhere. Stdlib-only (Python 3.10+). Never mutates production,
CRM, or any file outside the two explicitly allowed report paths.

Allowed writes (atomic, non-symlink, path-contained):
  /home/Carix/video/security/uaart_security_audit.txt
  /home/Carix/video/security/uaart_security_audit.json

This script performs NO subprocess/shell/eval/exec/dynamic-import/network/
chmod/delete/rename/reload of any production resource. It only reads.

Every finding is PASS, FAIL, or NOT_PROVEN. Nothing is ever upgraded to
PASS by assumption. Secret VALUES are never printed; only a truncated
SHA-256 fingerprint of matched secret-like content is stored, together with
file path, line number (if safely obtainable), and category.

This script does nothing when merely imported; it only acts when executed
directly, and even then only after Gate A owner approval in the operational
process (this file itself contains no gate-check bypass — the gate is a
process control, not a code control, per TASK 010/012 architecture).
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
import tempfile
import time
from pathlib import Path

# --------------------------------------------------------------------------
# Hardcoded, non-overridable roots. No CLI argument can change these.
# --------------------------------------------------------------------------
ROOT = Path("/home/Carix").resolve()
REPORT_DIR = (ROOT / "video" / "security").resolve()
REPORT_TXT = REPORT_DIR / "uaart_security_audit.txt"
REPORT_JSON = REPORT_DIR / "uaart_security_audit.json"

# Roots considered "public web / static / media" for cross-checking secrets
# accidentally placed where the public web server could serve them.
PUBLIC_ROOT_CANDIDATES = [
    ROOT / "video",
    ROOT / "static",
    ROOT / "media",
    ROOT / "public",
]

# Candidate critical production files. Paths are best-effort guesses based
# on prior task context (UA-0001..UA-0009). If a candidate does not exist,
# it is reported as NOT_PROVEN, never assumed absent-and-fine or present.
CRITICAL_FILE_CANDIDATES = [
    ROOT / "crm.db",
    ROOT / "mysite" / "wsgi.py",
    ROOT / "mysite" / "settings.py",
    ROOT / "app.py",
    ROOT / "generator.py",
    ROOT / "main.py",
]

BACKUP_DIR_CANDIDATES = [
    ROOT / "security_backups",
    ROOT / "backups",
]

MAX_FILE_SCAN_BYTES = 2_000_000  # do not slurp huge files fully
MAX_FILES_PER_WALK = 20000       # sane cap so audit cannot run unbounded

SECRET_PATTERNS = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("generic_api_key", re.compile(r"(?i)api[_-]?key['\"]?\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]")),
    ("private_key_header", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----")),
    ("password_assignment", re.compile(r"(?i)password['\"]?\s*[:=]\s*['\"][^'\"]{4,}['\"]")),
    ("secret_assignment", re.compile(r"(?i)secret[_-]?key['\"]?\s*[:=]\s*['\"][^'\"]{8,}['\"]")),
    ("token_assignment", re.compile(r"(?i)token['\"]?\s*[:=]\s*['\"][A-Za-z0-9_\-\.]{16,}['\"]")),
    ("django_debug_true", re.compile(r"(?i)\bDEBUG\s*=\s*True\b")),
]

SENSITIVE_FILENAME_PATTERNS = re.compile(
    r"(?i)(\.env(\..*)?$|id_rsa|id_ed25519|\.pem$|\.key$|\.pfx$|\.p12$|credentials\.json$|service-account.*\.json$|customers_export|clients_export)"
)

findings = []
not_proven = []


def record(category, target, status, detail):
    entry = {"category": category, "target": str(target), "status": status, "detail": detail}
    if status == "NOT_PROVEN":
        not_proven.append(entry)
    findings.append(entry)


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]


def sha256_of_file(path: Path, max_bytes: int = None):
    try:
        h = hashlib.sha256()
        read = 0
        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
                read += len(chunk)
                if max_bytes and read >= max_bytes:
                    break
        return h.hexdigest()
    except Exception as exc:
        return None


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def safe_lstat(path: Path):
    try:
        return os.lstat(path)
    except Exception:
        return None


def check_permissions():
    if not ROOT.exists():
        record("filesystem_root", ROOT, "NOT_PROVEN", "ROOT path not accessible from this environment")
        return
    count = 0
    for dirpath, dirnames, filenames in os.walk(ROOT, followlinks=False):
        for name in list(dirnames) + list(filenames):
            count += 1
            if count > MAX_FILES_PER_WALK:
                record("walk_limit", ROOT, "NOT_PROVEN", "file count exceeded scan cap; partial scan only")
                return
            full = Path(dirpath) / name
            st = safe_lstat(full)
            if st is None:
                continue
            if stat.S_ISLNK(st.st_mode):
                target_resolved = None
                try:
                    target_resolved = full.resolve()
                except Exception:
                    pass
                if target_resolved is None or not is_within(target_resolved, ROOT):
                    record("symlink_escape", full, "FAIL", "symlink resolves outside ROOT or is unreadable")
                else:
                    record("symlink", full, "PASS", "symlink resolves within ROOT")
                continue
            mode = st.st_mode
            world_writable = bool(mode & stat.S_IWOTH)
            group_writable = bool(mode & stat.S_IWGRP)
            is_sensitive_name = bool(SENSITIVE_FILENAME_PATTERNS.search(name))
            if world_writable:
                record("world_writable", full, "FAIL", f"mode={oct(mode)}")
            if group_writable and is_sensitive_name:
                record("group_writable_sensitive", full, "FAIL", f"mode={oct(mode)}")
            if is_sensitive_name:
                for pub in PUBLIC_ROOT_CANDIDATES:
                    if pub.exists() and is_within(full, pub):
                        record("sensitive_in_public_root", full, "FAIL", f"sensitive filename under {pub}")
            if stat.S_ISREG(st.st_mode) and (mode & stat.S_IXUSR) and any(
                pub.exists() and is_within(full, pub) for pub in PUBLIC_ROOT_CANDIDATES
            ):
                record("unexpected_executable_in_public_root", full, "FAIL", f"mode={oct(mode)}")


def scan_secrets_in_file(path: Path):
    try:
        if not path.is_file():
            return
        size = path.stat().st_size
        if size > MAX_FILE_SCAN_BYTES:
            record("secret_scan_skip_large", path, "NOT_PROVEN", f"file size {size} exceeds scan cap")
            return
        with open(path, "r", errors="ignore") as f:
            for lineno, line in enumerate(f, start=1):
                for category, pattern in SECRET_PATTERNS:
                    m = pattern.search(line)
                    if m:
                        fp = fingerprint(m.group(0))
                        record("secret_like_pattern", path, "FAIL", f"category={category} line={lineno} fingerprint={fp}")
    except Exception as exc:
        record("secret_scan_error", path, "NOT_PROVEN", f"unreadable: {type(exc).__name__}")


def scan_secret_candidates():
    text_exts = {".py", ".txt", ".cfg", ".ini", ".env", ".json", ".yml", ".yaml", ".conf"}
    count = 0
    for dirpath, dirnames, filenames in os.walk(ROOT, followlinks=False):
        for name in filenames:
            count += 1
            if count > MAX_FILES_PER_WALK:
                return
            p = Path(dirpath) / name
            if p.suffix.lower() in text_exts or SENSITIVE_FILENAME_PATTERNS.search(name):
                scan_secrets_in_file(p)


def check_sqlite_db(db_path: Path):
    if not db_path.exists():
        record("crm_db_presence", db_path, "NOT_PROVEN", "file not found at candidate path")
        return
    st = safe_lstat(db_path)
    if st:
        mode = st.st_mode
        if mode & stat.S_IWOTH:
            record("crm_db_permissions", db_path, "FAIL", f"world-writable mode={oct(mode)}")
        else:
            record("crm_db_permissions", db_path, "PASS", f"mode={oct(mode)}")
    uri = f"file:{db_path.as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            conn.execute("PRAGMA query_only=ON;")
            cur = conn.execute("PRAGMA quick_check;")
            result = cur.fetchone()
            if result and result[0] == "ok":
                record("crm_db_integrity", db_path, "PASS", "quick_check=ok")
            else:
                record("crm_db_integrity", db_path, "FAIL", f"quick_check={result}")
        finally:
            conn.close()
    except Exception as exc:
        record("crm_db_integrity", db_path, "NOT_PROVEN", f"could not open read-only: {type(exc).__name__}")


def check_critical_files_baseline():
    for path in CRITICAL_FILE_CANDIDATES:
        if not path.exists():
            record("critical_file_baseline", path, "NOT_PROVEN", "candidate path not found in this environment")
            continue
        digest = sha256_of_file(path)
        if digest:
            record("critical_file_baseline", path, "PASS", f"sha256={digest}")
        else:
            record("critical_file_baseline", path, "NOT_PROVEN", "could not compute sha256")


def check_python_syntax():
    for path in CRITICAL_FILE_CANDIDATES:
        if path.suffix != ".py" or not path.exists():
            continue
        try:
            with open(path, "r", errors="strict") as f:
                source = f.read()
            ast.parse(source, filename=str(path))
            record("python_syntax", path, "PASS", "ast.parse succeeded (no import/exec performed)")
        except SyntaxError as exc:
            record("python_syntax", path, "FAIL", f"SyntaxError: {exc.msg} at line {exc.lineno}")
        except Exception as exc:
            record("python_syntax", path, "NOT_PROVEN", f"could not parse: {type(exc).__name__}")


def check_wsgi_config_text():
    for name in ["wsgi.py", "settings.py"]:
        for candidate in CRITICAL_FILE_CANDIDATES:
            if candidate.name == name and candidate.exists():
                try:
                    with open(candidate, "r", errors="ignore") as f:
                        text = f.read()
                    if re.search(r"(?i)\bDEBUG\s*=\s*True\b", text):
                        record("debug_flag", candidate, "FAIL", "DEBUG=True found in text (not executed)")
                    else:
                        record("debug_flag", candidate, "PASS", "no DEBUG=True literal found")
                except Exception as exc:
                    record("debug_flag", candidate, "NOT_PROVEN", f"unreadable: {type(exc).__name__}")


def check_backup_presence():
    found_any = False
    for bdir in BACKUP_DIR_CANDIDATES:
        if bdir.exists() and bdir.is_dir():
            found_any = True
            entries = sorted(bdir.glob("*"))
            if not entries:
                record("backup_presence", bdir, "NOT_PROVEN", "backup dir exists but is empty")
                continue
            newest = max(entries, key=lambda p: p.stat().st_mtime if p.exists() else 0)
            age_days = (time.time() - newest.stat().st_mtime) / 86400.0
            record("backup_presence", bdir, "PASS", f"newest={newest.name} age_days={age_days:.1f}")
    if not found_any:
        record("backup_presence", BACKUP_DIR_CANDIDATES, "NOT_PROVEN", "no known backup directory found")


def atomic_write(dest: Path, content: str):
    dest_resolved = dest.resolve() if dest.exists() else dest
    if not is_within(dest.parent, REPORT_DIR) and dest.parent != REPORT_DIR:
        raise RuntimeError("refusing to write outside REPORT_DIR")
    if dest.exists():
        st = safe_lstat(dest)
        if st and stat.S_ISLNK(st.st_mode):
            raise RuntimeError("refusing to write over a symlink")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_audit_", dir=str(REPORT_DIR))
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, dest)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def main():
    if str(REPORT_DIR).startswith(str(Path("/home/Carix/video").resolve())) is False:
        print("report dir misconfigured", file=sys.stderr)
        return 2
    check_permissions()
    scan_secret_candidates()
    for candidate in CRITICAL_FILE_CANDIDATES:
        if candidate.name == "crm.db":
            check_sqlite_db(candidate)
    check_critical_files_baseline()
    check_python_syntax()
    check_wsgi_config_text()
    check_backup_presence()

    summary = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "root": str(ROOT),
        "total_findings": len(findings),
        "not_proven_count": len(not_proven),
        "findings": findings,
        "note": "READ-ONLY audit. No production/CRM mutation performed. "
                "Unknown facts are NOT_PROVEN, never assumed PASS.",
    }
    atomic_write(REPORT_JSON, json.dumps(summary, indent=2))

    lines = [
        "UA ART SECURITY AUDIT REPORT (read-only)",
        f"Generated: {summary['generated_at_utc']}",
        f"Root scanned: {ROOT}",
        f"Total findings: {len(findings)}  NOT_PROVEN: {len(not_proven)}",
        "-" * 60,
    ]
    for entry in findings:
        lines.append(f"[{entry['status']}] {entry['category']}: {entry['target']} — {entry['detail']}")
    atomic_write(REPORT_TXT, "\n".join(lines) + "\n")
    print(f"Audit complete. {len(findings)} findings written to {REPORT_TXT} and {REPORT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
