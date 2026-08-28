#!/usr/bin/env python3
"""
TASK_058 live_discovery.py

Python 3.10, standard library only. READ-ONLY. Bounded. Fail-closed.

This script is designed to run on the PythonAnywhere host, invoked only by
cloud/task_058_crm_ocr_sync/task058_readonly_controller.py, against an
explicit allowlist of source/db/site/log paths under /home/Carix. It never
writes anything except the exact JSON receipt path it is given, and that path
must itself resolve inside the safe inbox directory it is told about. It
never mutates any source, database, log, or site file it inspects.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

BASE_DIR = "/home/Carix"
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB bound for any single inspected file
MAX_LOG_LINES = 2000  # bounded recent log inspection
SNIPPET_RADIUS = 3  # lines of context around a match
MAX_SNIPPET_LEN = 400

ERROR_MESSAGE_1 = (
    "Изображение сохранено, но разобрать его не получилось. "
    "Опишите машину текстом или голосом."
)
ERROR_MESSAGE_2 = (
    "CRM: страницы сайта отстали от базы, и пересобрать их не получилось."
)

HANDLER_PATTERNS = [
    r"\bdef\s+\w*photo\w*\s*\(",
    r"\bdef\s+\w*document\w*\s*\(",
    r"\bdef\s+\w*ocr\w*\s*\(",
    r"\bdef\s+\w*vision\w*\s*\(",
    r"\bdef\s+\w*rebuild\w*\s*\(",
    r"\bdef\s+\w*stale\w*\s*\(",
    r"\bclass\s+\w+",
]

SENSITIVE_PATTERNS = [
    re.compile(r"(?i)\btoken\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?i)\bapi[_-]?key\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{10,}"),
    re.compile(r"\b\d{9,}:[A-Za-z0-9_\-]{20,}\b"),  # telegram bot token shape
    re.compile(r"(?i)\bpassword\b\s*[:=]"),
    re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b"),  # VIN-shaped strings
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # email
    re.compile(r"\+?\d{10,13}"),  # phone-ish
]

LOCK_ERROR_PATTERNS = {
    "database_is_locked": re.compile(r"database is locked"),
    "resource_temporarily_unavailable": re.compile(r"Resource temporarily unavailable"),
    "ocr_failure": re.compile(re.escape(ERROR_MESSAGE_1)),
    "rebuild_failure": re.compile(re.escape(ERROR_MESSAGE_2)),
}


class DiscoveryError(Exception):
    pass


def sha256_of(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_safe_path(path_str: str, base_dir: str = None) -> Path:
    """Fail closed unless path is a regular, non-symlink file under base_dir
    and within the size bound. Returns resolved Path or raises DiscoveryError.
    base_dir defaults to the module-level BASE_DIR, resolved dynamically at
    call time (not baked in at function-definition time)."""
    if base_dir is None:
        base_dir = BASE_DIR
    p = Path(path_str)
    if p.is_symlink():
        raise DiscoveryError(f"REJECTED_SYMLINK:{path_str}")
    if not p.exists():
        raise DiscoveryError(f"REJECTED_MISSING:{path_str}")
    resolved = p.resolve()
    base_resolved = Path(base_dir).resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        raise DiscoveryError(f"REJECTED_PATH_ESCAPE:{path_str}")
    if resolved.is_symlink():
        raise DiscoveryError(f"REJECTED_SYMLINK_RESOLVED:{path_str}")
    if not resolved.is_file():
        raise DiscoveryError(f"REJECTED_NOT_REGULAR_FILE:{path_str}")
    size = resolved.stat().st_size
    if size > MAX_FILE_SIZE:
        raise DiscoveryError(f"REJECTED_OVERSIZE:{path_str}:{size}")
    return resolved


def redact(text: str) -> str:
    out = text
    for pat in SENSITIVE_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


def scan_source_file(path: Path) -> dict:
    result = {
        "path": str(path),
        "sha256": sha256_of(path),
        "size": path.stat().st_size,
        "mtime": path.stat().st_mtime,
        "handlers": [],
        "error_message_snippets": [],
    }
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        result["read_error"] = str(exc)
        return result
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        for pat in HANDLER_PATTERNS:
            if re.search(pat, line):
                result["handlers"].append({"line": idx + 1, "match": redact(line.strip())[:200]})
        for label, msg in (("MSG1", ERROR_MESSAGE_1), ("MSG2", ERROR_MESSAGE_2)):
            if msg in line:
                start = max(0, idx - SNIPPET_RADIUS)
                end = min(len(lines), idx + SNIPPET_RADIUS + 1)
                snippet = "\n".join(lines[start:end])
                result["error_message_snippets"].append({
                    "label": label,
                    "line": idx + 1,
                    "snippet": redact(snippet)[:MAX_SNIPPET_LEN],
                })
    return result


def sqlite_readonly_probe(db_path: str) -> dict:
    resolved = is_safe_path(db_path)
    uri = f"file:{resolved}?mode=ro"
    info = {"path": str(resolved), "sha256_before": sha256_of(resolved)}
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            conn.execute("PRAGMA query_only = ON;")
            cur = conn.execute("PRAGMA journal_mode;")
            info["journal_mode"] = cur.fetchone()[0]
            cur = conn.execute("PRAGMA busy_timeout;")
            info["busy_timeout"] = cur.fetchone()[0]
            cur = conn.execute("PRAGMA quick_check;")
            info["quick_check"] = cur.fetchone()[0]
            info["query_only_verified"] = True
            try:
                conn.execute("CREATE TABLE __should_fail__ (x INTEGER);")
                info["write_attempt_blocked"] = False
            except sqlite3.OperationalError as exc:
                info["write_attempt_blocked"] = True
                info["write_block_reason"] = str(exc)
        finally:
            conn.close()
    except Exception as exc:
        info["error"] = str(exc)
    info["sha256_after"] = sha256_of(resolved)
    info["identity_stable"] = info["sha256_before"] == info["sha256_after"]
    return info


def count_log_patterns(log_paths: list) -> dict:
    counts = {k: 0 for k in LOCK_ERROR_PATTERNS}
    for lp in log_paths:
        try:
            resolved = is_safe_path(lp)
        except DiscoveryError:
            continue
        try:
            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-MAX_LOG_LINES:]
        except Exception:
            continue
        for line in lines:
            for label, pat in LOCK_ERROR_PATTERNS.items():
                if pat.search(line):
                    counts[label] += 1
    return counts


def load_allowlist(allowlist_file: str) -> dict:
    with open(allowlist_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    for key in ("source_paths", "db_paths", "site_paths", "log_paths"):
        data.setdefault(key, [])
    return data


def build_report(allowlist: dict) -> dict:
    report = {
        "status": "OK",
        "generated_at": time.time(),
        "base_dir": BASE_DIR,
        "sources": [],
        "databases": [],
        "site_inventory": [],
        "log_counts": {},
        "ua0009_status": "UNKNOWN",
        "notes": [],
    }
    for sp in allowlist.get("source_paths", []):
        try:
            resolved = is_safe_path(sp)
            report["sources"].append(scan_source_file(resolved))
        except DiscoveryError as exc:
            report["notes"].append(str(exc))
    for dbp in allowlist.get("db_paths", []):
        try:
            report["databases"].append(sqlite_readonly_probe(dbp))
        except DiscoveryError as exc:
            report["notes"].append(str(exc))
    for site_path in allowlist.get("site_paths", []):
        try:
            resolved = is_safe_path(site_path)
            report["site_inventory"].append({
                "path": str(resolved),
                "sha256": sha256_of(resolved),
                "size": resolved.stat().st_size,
                "mtime": resolved.stat().st_mtime,
            })
        except DiscoveryError as exc:
            report["notes"].append(str(exc))
    report["log_counts"] = count_log_patterns(allowlist.get("log_paths", []))
    return report


def write_receipt(report: dict, output_path: str, receipt_base_dir: str) -> None:
    out_p = Path(output_path)
    base = Path(receipt_base_dir).resolve()
    resolved_dir = out_p.parent.resolve()
    try:
        resolved_dir.relative_to(base)
    except ValueError:
        raise DiscoveryError(f"REJECTED_RECEIPT_PATH_ESCAPE:{output_path}")
    tmp_path = out_p.with_suffix(out_p.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp_path, out_p)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="TASK_058 read-only live discovery")
    parser.add_argument("--allowlist-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt-base-dir", required=True,
                         help="Safe inbox directory that must contain --output")
    args = parser.parse_args(argv)

    try:
        allowlist = load_allowlist(args.allowlist_file)
        report = build_report(allowlist)
        write_receipt(report, args.output, args.receipt_base_dir)
    except Exception as exc:
        failure = {"status": "BLOCKED", "reason": str(exc), "generated_at": time.time()}
        try:
            write_receipt(failure, args.output, args.receipt_base_dir)
        except Exception:
            pass
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
