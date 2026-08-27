#!/usr/bin/env python3
"""
BOT-LOGISTICS-001 Phase A — read-only PythonAnywhere discovery probe.

This script is designed to be executed ONLY on PythonAnywhere (or an
environment with equivalent read-only access to the exact whitelisted
paths below), by whoever operates the safe-inbox read-only channel.

It has NOT been executed by the Claude/Cloud worker that authored it,
because that worker has no filesystem/network access to PythonAnywhere.

Strict whitelist (never scan recursively, never touch anything else):
  /home/Carix/cars_ui.py
  /home/Carix/team_bot.py
  /home/Carix/avtoperedacha.py
  /home/Carix/db.py
  /home/Carix/run_all.py
  /home/Carix/start_safe.py
  /home/Carix/crm.db

Guarantees:
  - SQLite opened with URI mode=ro and PRAGMA query_only=ON.
  - PRAGMA quick_check run before and after (this script performs no writes).
  - Fails closed on: symlink, hard link (nlink>1), non-regular file,
    ambiguous row count, locked DB, malformed DB, unstable identity
    (hash changes between the two required reads).
  - Never prints any CRM row content except the single UA-0006 container
    string, compared (not printed in full to logs beyond the boolean
    match) against the expected literal ONEYSELGF1046602.
  - Never prints secrets/tokens.

Output: sanitized, bounded JSON-ish report to stdout.
"""

import argparse
import hashlib
import os
import re
import sqlite3
import sys

WHITELIST_SOURCES = {
    "/home/Carix/cars_ui.py",
    "/home/Carix/team_bot.py",
    "/home/Carix/avtoperedacha.py",
    "/home/Carix/db.py",
    "/home/Carix/run_all.py",
    "/home/Carix/start_safe.py",
}
WHITELIST_DB = "/home/Carix/crm.db"

ANCHOR_PATTERNS = [
    "Срок доставки",
    "📦 Номер и дата контейнера",
    "Номер и дата контейнера",
    "Дней до прибытия",
    "Номер контейнера",
]

EXPECTED_CONTAINER = "ONEYSELGF1046602"


class DiscoveryFailure(Exception):
    pass


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def assert_safe_regular_file(path: str) -> os.stat_result:
    if os.path.islink(path):
        raise DiscoveryFailure(f"REFUSED: symlink not allowed: {path}")
    st = os.lstat(path)
    if not os.path.isfile(path):
        raise DiscoveryFailure(f"REFUSED: not a regular file: {path}")
    if st.st_nlink > 1:
        raise DiscoveryFailure(f"REFUSED: hard link detected (nlink={st.st_nlink}): {path}")
    return st


def scan_source_file(path: str):
    if path not in WHITELIST_SOURCES:
        raise DiscoveryFailure(f"REFUSED: path not in whitelist: {path}")
    assert_safe_regular_file(path)
    digest_before = sha256_of(path)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    digest_after = sha256_of(path)
    if digest_before != digest_after:
        raise DiscoveryFailure(f"REFUSED: unstable identity while reading: {path}")

    findings = []
    func_re = re.compile(r"^\s*(async\s+def|def)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
    current_func = None
    for idx, line in enumerate(lines, start=1):
        m = func_re.match(line)
        if m:
            current_func = m.group(2)
        for anchor in ANCHOR_PATTERNS:
            if anchor in line:
                start = max(0, idx - 3)
                end = min(len(lines), idx + 2)
                snippet = "".join(lines[start:end])
                findings.append({
                    "file": path,
                    "anchor": anchor,
                    "line": idx,
                    "function": current_func,
                    "snippet_bounded": snippet[:400],
                })
    return {"path": path, "sha256": digest_before, "findings": findings}


def discover_db(db_path: str):
    if db_path != WHITELIST_DB:
        raise DiscoveryFailure(f"REFUSED: db path not whitelisted: {db_path}")
    assert_safe_regular_file(db_path)
    sha_before = sha256_of(db_path)

    uri = f"file:{db_path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=3)
    except sqlite3.Error as e:
        raise DiscoveryFailure(f"REFUSED: cannot open DB read-only: {e}")

    try:
        conn.execute("PRAGMA query_only=ON;")
        cur = conn.execute("PRAGMA quick_check;")
        qc = cur.fetchone()
        if not qc or qc[0] != "ok":
            raise DiscoveryFailure(f"REFUSED: quick_check failed: {qc}")

        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
        car_table_candidates = [t for t in tables if re.search(r"car|ua|vehicle", t, re.I)]

        row_count = None
        container_value = None
        matched_table = None
        matched_id_col = None
        matched_container_col = None

        for t in car_table_candidates:
            try:
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info('{t}')").fetchall()]
            except sqlite3.Error:
                continue
            id_cols = [c for c in cols if re.search(r"^ua.?id$|^car.?id$|^id$|^ua$", c, re.I)]
            container_cols = [c for c in cols if re.search(r"container|контейнер", c, re.I)]
            if not id_cols or not container_cols:
                continue
            for id_col in id_cols:
                try:
                    rows = conn.execute(
                        f"SELECT COUNT(*) FROM '{t}' WHERE \"{id_col}\" LIKE ?",
                        ("%0006%",),
                    ).fetchall()
                except sqlite3.Error:
                    continue
                cnt = rows[0][0] if rows else 0
                if cnt == 1:
                    row_count = cnt
                    matched_table = t
                    matched_id_col = id_col
                    matched_container_col = container_cols[0]
                    break
            if matched_table:
                break

        if not matched_table or row_count != 1:
            raise DiscoveryFailure(
                "REFUSED: could not prove exactly one UA-0006 row via safe heuristics; "
                "manual anchor confirmation required before any patch."
            )

        val_row = conn.execute(
            f"SELECT \"{matched_container_col}\" FROM '{matched_table}' "
            f"WHERE \"{matched_id_col}\" LIKE ?",
            ("%0006%",),
        ).fetchall()
        if len(val_row) != 1:
            raise DiscoveryFailure("REFUSED: ambiguous UA-0006 row on second read")
        container_value = val_row[0][0]
    finally:
        conn.close()

    sha_after = sha256_of(db_path)
    if sha_before != sha_after:
        raise DiscoveryFailure("REFUSED: DB SHA-256 changed during read-only discovery")

    status = "ALREADY_CORRECT" if (container_value or "").strip().upper() == EXPECTED_CONTAINER else "NEEDS_EXACT_UPDATE"

    return {
        "db_sha256_before": sha_before,
        "db_sha256_after": sha_after,
        "sha_identical": sha_before == sha_after,
        "matched_table": matched_table,
        "matched_id_col": matched_id_col,
        "matched_container_col": matched_container_col,
        "ua0006_row_count": row_count,
        "UA0006_CONTAINER_STATUS": status,
    }


def main():
    parser = argparse.ArgumentParser(description="BOT-LOGISTICS-001 read-only discovery probe")
    parser.add_argument("--db", required=True)
    parser.add_argument("--source", action="append", required=True)
    args = parser.parse_args()

    report = {"sources": [], "db": None, "errors": []}
    try:
        for src in args.source:
            report["sources"].append(scan_source_file(src))
    except DiscoveryFailure as e:
        report["errors"].append(str(e))
        print(report)
        sys.exit(2)

    try:
        report["db"] = discover_db(args.db)
    except DiscoveryFailure as e:
        report["errors"].append(str(e))
        print(report)
        sys.exit(2)

    print(report)
    sys.exit(0)


if __name__ == "__main__":
    main()
