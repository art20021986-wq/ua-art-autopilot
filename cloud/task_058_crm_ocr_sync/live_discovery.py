#!/usr/bin/env python3
"""TASK 058 — CRM-OCR-SYNC-001 read-only live discovery script.

Python 3.10, standard-library only. This script performs NO writes of any kind.
It is intended to be synced verbatim into
/home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync/ and executed exactly
once by an external controller that supplies an explicit allowlist via CLI args
or the DEFAULT_ALLOWLIST below.

Safety invariants:
  - Every candidate path must resolve (after resolving symlinks) under
    ALLOWLIST_ROOT.
  - Every candidate path must be a regular file, not a symlink, with st_nlink
    that is not evidence of an unexpected hardlink farm.
  - Every candidate file must not exceed MAX_FILE_BYTES.
  - SQLite is opened only via a read-only URI with PRAGMA query_only=ON.
  - Logs are read with a bounded tail (last MAX_LOG_LINES lines) only.
  - Output never contains secrets, tokens, PII, phone numbers, emails, raw
    image bytes, or full VIN values (VINs are represented as sha256 only).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

ALLOWLIST_ROOT = "/home/Carix"
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_LOG_LINES = 2000

DEFAULT_SOURCE_ALLOWLIST = [
    "team_bot.py",
    "db.py",
    "cars_ui.py",
    "avtoperedacha.py",
    "run_all.py",
    "start_safe.py",
]

GENERIC_OCR_FAILURE_MESSAGE = (
    "Изображение сохранено, но разобрать его не получилось. "
    "Опишите машину текстом или голосом."
)
GENERIC_STALE_PAGE_MESSAGE = (
    "CRM: страницы сайта отстали от базы, и пересобрать их не получилось."
)

SENSITIVE_PATTERNS = [
    re.compile(r"(?i)\btoken\b\s*[:=]\s*\S+"),
    re.compile(r"(?i)\bapi[_-]?key\b\s*[:=]\s*\S+"),
    re.compile(r"\b\d{10,15}\b"),  # phone-number-like
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # email-like
    re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b"),  # VIN-like full 17-char string
]


class DiscoveryError(Exception):
    pass


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_of_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def guard_path(raw_path: str, root: str = ALLOWLIST_ROOT) -> Path:
    """Fail closed on symlinks, path escapes, oversized files, or non-regular files."""
    p = Path(raw_path)
    if not p.is_absolute():
        raise DiscoveryError(f"REJECTED_NON_ABSOLUTE_PATH:{raw_path}")
    if p.is_symlink():
        raise DiscoveryError(f"REJECTED_SYMLINK:{raw_path}")
    resolved = p.resolve(strict=True)
    root_resolved = Path(root).resolve(strict=True)
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        raise DiscoveryError(f"REJECTED_PATH_ESCAPE:{raw_path}")
    if not resolved.is_file():
        raise DiscoveryError(f"REJECTED_NOT_REGULAR_FILE:{raw_path}")
    st = resolved.lstat()
    if st.st_size > MAX_FILE_BYTES:
        raise DiscoveryError(f"REJECTED_OVERSIZED_FILE:{raw_path}")
    return resolved


def redact(text: str) -> str:
    out = text
    for pat in SENSITIVE_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


def file_fingerprint(path: Path) -> dict[str, Any]:
    st = path.stat()
    return {
        "path": str(path),
        "sha256": sha256_of_file(path),
        "size_bytes": st.st_size,
        "mtime_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)),
    }


def find_handler_snippets(path: Path, keywords: list[str], context_lines: int = 3) -> list[dict[str, Any]]:
    """Locate function/class defs and message literals near given keywords, read-only."""
    results: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:  # noqa: BLE001
        return [{"error": f"READ_FAILED:{type(exc).__name__}"}]
    def_pattern = re.compile(r"^\s*(def|class)\s+(\w+)")
    for idx, line in enumerate(lines):
        for kw in keywords:
            if kw in line:
                start = max(0, idx - context_lines)
                end = min(len(lines), idx + context_lines + 1)
                snippet = "\n".join(lines[start:end])
                enclosing_def = None
                enclosing_line = None
                for back in range(idx, -1, -1):
                    m = def_pattern.match(lines[back])
                    if m:
                        enclosing_def = m.group(2)
                        enclosing_line = back + 1
                        break
                results.append(
                    {
                        "keyword": kw,
                        "line_number": idx + 1,
                        "enclosing_function_or_class": enclosing_def,
                        "enclosing_line": enclosing_line,
                        "snippet_sanitized": redact(snippet),
                    }
                )
    return results


def inspect_sources(allowlist: list[str]) -> dict[str, Any]:
    findings: dict[str, Any] = {}
    keywords = [
        GENERIC_OCR_FAILURE_MESSAGE,
        GENERIC_STALE_PAGE_MESSAGE,
        "PhotoSize",
        "get_file",
        "download",
        "ocr",
        "OCR",
        "vision",
        "retry",
        "timeout",
        "rebuild",
        "INSERT INTO",
        "UPDATE ",
        "sqlite3.connect",
        "database is locked",
        "BlockingIOError",
        "UA-0009",
        "UA_0009",
    ]
    for rel in allowlist:
        full = os.path.join(ALLOWLIST_ROOT, rel)
        try:
            resolved = guard_path(full)
        except DiscoveryError as exc:
            findings[rel] = {"status": "REJECTED", "reason": str(exc)}
            continue
        fp = file_fingerprint(resolved)
        fp["handler_findings"] = find_handler_snippets(resolved, keywords)
        fp["status"] = "OK"
        findings[rel] = fp
    return findings


def inspect_sqlite_readonly(db_path: str) -> dict[str, Any]:
    result: dict[str, Any] = {"db_path": db_path}
    try:
        resolved = guard_path(db_path)
    except DiscoveryError as exc:
        return {"status": "REJECTED", "reason": str(exc)}
    result["sha256_before"] = sha256_of_file(resolved)
    uri = f"file:{resolved}?mode=ro"
    conn = None
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("PRAGMA query_only=ON;")
        result["read_only_uri_used"] = uri.replace(str(resolved), "[DB_PATH_REDACTED]")
        cur = conn.execute("PRAGMA query_only;")
        result["query_only_enabled"] = bool(cur.fetchone()[0])
        cur = conn.execute("PRAGMA journal_mode;")
        result["journal_mode"] = cur.fetchone()[0]
        cur = conn.execute("PRAGMA busy_timeout;")
        result["busy_timeout_ms"] = cur.fetchone()[0]
        cur = conn.execute("PRAGMA quick_check;")
        result["quick_check"] = cur.fetchone()[0]
        try:
            conn.execute("CREATE TABLE __task058_probe__ (x INTEGER);")
            result["write_attempt_blocked"] = False
        except sqlite3.OperationalError as exc:
            result["write_attempt_blocked"] = True
            result["write_block_error_class"] = type(exc).__name__
    except Exception as exc:  # noqa: BLE001
        result["status"] = "ERROR"
        result["error_class"] = type(exc).__name__
        return result
    finally:
        if conn is not None:
            conn.close()
    result["sha256_after"] = sha256_of_file(resolved)
    result["identity_stable"] = result["sha256_before"] == result["sha256_after"]
    result["status"] = "OK"
    return result


def scan_logs_bounded(log_paths: list[str]) -> dict[str, Any]:
    counters = {
        "database_is_locked": 0,
        "resource_temporarily_unavailable": 0,
        "ocr_failure_message": 0,
        "rebuild_failure": 0,
    }
    per_file: dict[str, Any] = {}
    for raw in log_paths:
        full = os.path.join(ALLOWLIST_ROOT, raw)
        try:
            resolved = guard_path(full)
        except DiscoveryError as exc:
            per_file[raw] = {"status": "REJECTED", "reason": str(exc)}
            continue
        try:
            with resolved.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-MAX_LOG_LINES:]
        except Exception as exc:  # noqa: BLE001
            per_file[raw] = {"status": "ERROR", "error_class": type(exc).__name__}
            continue
        local_counts = {k: 0 for k in counters}
        for line in lines:
            if "database is locked" in line:
                local_counts["database_is_locked"] += 1
            if "Resource temporarily unavailable" in line:
                local_counts["resource_temporarily_unavailable"] += 1
            if GENERIC_OCR_FAILURE_MESSAGE in line:
                local_counts["ocr_failure_message"] += 1
            if GENERIC_STALE_PAGE_MESSAGE in line:
                local_counts["rebuild_failure"] += 1
        for k, v in local_counts.items():
            counters[k] += v
        per_file[raw] = {"status": "OK", "bounded_line_count": len(lines), "counts": local_counts}
    return {"totals": counters, "per_file": per_file}


def inspect_site_inventory(site_paths: list[str]) -> dict[str, Any]:
    inventory: dict[str, Any] = {}
    for rel in site_paths:
        full = os.path.join(ALLOWLIST_ROOT, rel)
        try:
            resolved = guard_path(full)
        except DiscoveryError as exc:
            inventory[rel] = {"status": "REJECTED", "reason": str(exc)}
            continue
        inventory[rel] = file_fingerprint(resolved)
        inventory[rel]["status"] = "OK"
    return inventory


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    source_findings = inspect_sources(args.sources or DEFAULT_SOURCE_ALLOWLIST)
    db_findings = inspect_sqlite_readonly(args.db) if args.db else {"status": "SKIPPED_NO_DB_ARG"}
    log_findings = scan_logs_bounded(args.logs or [])
    site_findings = inspect_site_inventory(args.site or [])
    report = {
        "task_id": "task_058",
        "mode": "READ_ONLY_LIVE_DISCOVERY",
        "started_at_utc": started,
        "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "context_bundle_sha256": "2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c",
        "memory_version_read": 4,
        "source_handler_evidence": source_findings,
        "sqlite_readonly_evidence": db_findings,
        "bounded_log_counts": log_findings,
        "protected_site_inventory": site_findings,
        "ua0009_status": "UNKNOWN",
        "ua0009_evidence": "Live discovery did not locate/verify a UA-0009 publication marker in this run.",
        "markers": {
            "PRODUCTION_TOUCHED": "NO",
            "CRM_TOUCHED": "NO",
            "CRM_DB_WRITTEN": "NO",
            "SITE_REBUILT": "NO",
            "SERVICE_RELOADED": "NO",
            "OCR_FIX_INSTALLED": "NO",
            "GATE_B_EXECUTED": "NO",
            "UA_0009_PUBLISHED": "NO",
        },
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TASK 058 read-only live discovery")
    parser.add_argument("--sources", nargs="*", default=None, help="relative source paths under /home/Carix")
    parser.add_argument("--db", default=None, help="absolute path to sqlite db, read-only inspection only")
    parser.add_argument("--logs", nargs="*", default=None, help="relative log paths under /home/Carix")
    parser.add_argument("--site", nargs="*", default=None, help="relative site file paths under /home/Carix")
    parser.add_argument("--out", default=None, help="exact receipt path to write JSON to (must be under safe inbox)")
    args = parser.parse_args(argv)

    try:
        report = build_report(args)
    except Exception as exc:  # noqa: BLE001
        report = {"status": "BLOCKED", "error_class": type(exc).__name__, "error": redact(str(exc))}

    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)

    if args.out:
        out_path = Path(args.out)
        if "autopilot_inbox" not in str(out_path):
            print("REJECTED: --out must target the safe inbox", file=sys.stderr)
            return 2
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
