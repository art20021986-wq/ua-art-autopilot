#!/usr/bin/env python3
"""
Gate A — GET-only audit tool for TASK 077 (CRM-CONTAINER-STAGE-SYNC-004).

HARD SAFETY RULES (enforced in code, not just comments):
- Only HTTP GET is ever issued. Any other verb raises SystemExit.
- Only sqlite3 read-only URI mode ("file:...?mode=ro") is ever opened.
- No file under audit is ever modified.

This script is production-ready but has NOT been executed against the live
PythonAnywhere host from within this authoring environment (no live network
access / credentials available here). A controller with proper read
credentials must run it for real and commit the output into
evidence/gate_a_findings.md.
"""
import argparse
import hashlib
import re
import sqlite3
import sys
import urllib.request

ALLOWED_METHOD = "GET"


def safe_get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, method=ALLOWED_METHOD)
    if req.get_method() != "GET":
        raise SystemExit("REFUSED: non-GET method attempted")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def count_callback_tokens(text: str, tokens):
    counts = {}
    for t in tokens:
        # match callback strings like car_setstage:<cid>:sea_loaded and button labels
        pattern = re.compile(re.escape(t))
        counts[t] = len(pattern.findall(text))
    return counts


def open_readonly_sqlite(path: str) -> sqlite3.Connection:
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only = ON;")
    return conn


def main():
    ap = argparse.ArgumentParser(description="Gate A GET-only audit (TASK 077)")
    ap.add_argument("--target", help="local file path or URL to hash")
    ap.add_argument("--sha", action="store_true")
    ap.add_argument("--count-callbacks", help="comma separated tokens")
    ap.add_argument("--files", help="comma separated local file paths to scan")
    ap.add_argument("--db", help="read-only sqlite path for read-back checks")
    args = ap.parse_args()

    if args.target and args.sha:
        if args.target.startswith("http"):
            data = safe_get(args.target)
        else:
            with open(args.target, "rb") as f:
                data = f.read()
        print(f"TARGET={args.target} SHA256={sha256_of(data)} BYTES={len(data)}")

    if args.count_callbacks and args.files:
        tokens = args.count_callbacks.split(",")
        for fp in args.files.split(","):
            try:
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except FileNotFoundError:
                print(f"FILE={fp} STATUS=NOT_FOUND")
                continue
            counts = count_callback_tokens(text, tokens)
            print(f"FILE={fp} COUNTS={counts}")

    if args.db:
        conn = open_readonly_sqlite(args.db)
        try:
            cur = conn.execute(
                "SELECT status, COUNT(*) FROM cars GROUP BY status"
            )
            for row in cur.fetchall():
                print(f"DB_STATUS_COUNT status={row[0]} count={row[1]}")
        except sqlite3.OperationalError as e:
            print(f"DB_READ_ERROR={e}")
        finally:
            conn.close()

    if not any([args.target, args.count_callbacks, args.db]):
        print("NOTHING_TO_DO: supply --target/--sha, --count-callbacks+--files, or --db")
        sys.exit(1)


if __name__ == "__main__":
    main()
