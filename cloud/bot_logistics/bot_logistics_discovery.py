#!/usr/bin/env python3
"""bot_logistics_discovery.py -- TASK 037/039 READ-ONLY discovery tool.

STRICT CONTRACT (see TASK_039_REPORT.md for full rationale):
  * Reads exactly six named PythonAnywhere source files and one named
    read-only SQLite database. Never writes to any of them.
  * Never prints secrets. Every output line is scanned for secret-shaped
    content before being emitted; on any match the process fails closed.
  * Emits exactly one UTF-8 JSON object on stdout via
    json.dumps(..., ensure_ascii=False, sort_keys=True). No other stdout.
  * Exit code 0 only for status == PASS; non-zero otherwise.
  * Never performs a SQL write, ATTACH, VACUUM, or migration. The database
    connection is opened URI-style with mode=ro and PRAGMA query_only=ON.
  * Uses only bounded/parameterized identity lookups for UA-0006 -- never
    LIKE '%0006%'.
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys

TASK_ID = "task_037"
MODE = "READ_ONLY_DISCOVERY"

REQUIRED_SOURCES = (
    "/home/Carix/cars_ui.py",
    "/home/Carix/team_bot.py",
    "/home/Carix/avtoperedacha.py",
    "/home/Carix/db.py",
    "/home/Carix/run_all.py",
    "/home/Carix/start_safe.py",
)
REQUIRED_DB = "/home/Carix/crm.db"

MAX_SOURCE_SIZE = 2_000_000
MAX_LINES_READ = 20000
MAX_ANCHORS = 40
MAX_SNIPPET_CHARS = 200
MAX_TABLES = 50
MAX_COLUMNS = 100

# Exact validated correct container identity established under TASK 037.
CORRECT_CONTAINER = "ONEYSELGF1046602"

# Exact identity representations proven usable for UA-0006. No LIKE.
IDENTITY_VALUES = ("UA-0006", "UA0006", "0006", 6)

ID_COLUMN_CANDIDATES = ("ua_id", "id", "uaid", "ua_number", "ua", "ua_code")
CONTAINER_COLUMN_HINT = "container"

ANCHOR_KEYWORDS = (
    "ua-0006", "ua0006", "container", "def ", "callback",
    "update_single_container_row", "hub", "menu", "gate_b",
)

SECRET_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in (
        r"secret", r"token", r"password", r"api[-_]?key",
        r"authorization", r"private[-_]?key", r"credential",
    )
] + [re.compile(r"[A-Za-z0-9_\-]{32,}")]


def quote_ident(name):
    """Canonical double-quote SQL identifier helper (safe for our own
    schema-derived identifiers only -- never used with user input)."""
    return '"' + str(name).replace('"', '""') + '"'


def redact_line(line):
    for pat in SECRET_PATTERNS:
        if pat.search(line):
            return "[REDACTED-SECRET-LINE]"
    return line


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


class DiscoveryError(Exception):
    pass


def secure_read_source(path):
    """Read one source file defensively. Returns bounded, redacted evidence."""
    try:
        st_before = os.lstat(path)
    except OSError as exc:
        raise DiscoveryError("lstat_failed:%s:%s" % (path, exc))

    if not stat.S_ISREG(st_before.st_mode):
        raise DiscoveryError("not_regular_file:%s" % path)
    if st_before.st_nlink != 1:
        raise DiscoveryError("unexpected_nlink:%s" % path)
    if st_before.st_size > MAX_SOURCE_SIZE:
        raise DiscoveryError("oversize:%s" % path)

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise DiscoveryError("open_failed:%s:%s" % (path, exc))

    try:
        st_fd = os.fstat(fd)
        if st_fd.st_ino != st_before.st_ino or st_fd.st_dev != st_before.st_dev:
            raise DiscoveryError("identity_mismatch_open:%s" % path)
        if st_fd.st_size > MAX_SOURCE_SIZE:
            raise DiscoveryError("oversize_fd:%s" % path)
        data = os.read(fd, MAX_SOURCE_SIZE + 1)
        if len(data) > MAX_SOURCE_SIZE:
            raise DiscoveryError("oversize_read:%s" % path)
    finally:
        os.close(fd)

    try:
        st_after = os.lstat(path)
    except OSError as exc:
        raise DiscoveryError("lstat_after_failed:%s:%s" % (path, exc))

    identity_before = (st_before.st_ino, st_before.st_dev, st_before.st_size, st_before.st_mtime)
    identity_after = (st_after.st_ino, st_after.st_dev, st_after.st_size, st_after.st_mtime)
    if identity_before != identity_after:
        raise DiscoveryError("concurrent_change_detected:%s" % path)

    digest = sha256_bytes(data)
    try:
        text = data.decode("utf-8", errors="replace")
    except Exception as exc:  # pragma: no cover - decode() with replace should not raise
        raise DiscoveryError("decode_failed:%s:%s" % (path, exc))

    lines = text.splitlines()[:MAX_LINES_READ]
    redacted_lines = [redact_line(l) for l in lines]

    anchors = []
    for idx, line in enumerate(redacted_lines):
        low = line.lower()
        if any(k in low for k in ANCHOR_KEYWORDS):
            snippet = line.strip()[:MAX_SNIPPET_CHARS]
            anchors.append({"line": idx + 1, "snippet": snippet})
            if len(anchors) >= MAX_ANCHORS:
                break

    return {
        "path": path,
        "sha256": digest,
        "size": len(data),
        "lines_read": len(lines),
        "anchors": anchors,
    }


def validate_sources_arg(sources, required=None):
    required = required if required is not None else REQUIRED_SOURCES
    if len(sources) != len(required):
        raise DiscoveryError(
            "source_count_mismatch:expected=%d:got=%d" % (len(required), len(sources))
        )
    if len(set(sources)) != len(sources):
        raise DiscoveryError("duplicate_source_supplied")
    if set(sources) != set(required):
        raise DiscoveryError("source_set_mismatch")


def open_readonly_db(db_path, required_db=None):
    required_db = required_db if required_db is not None else REQUIRED_DB
    if db_path != required_db:
        raise DiscoveryError("db_path_mismatch")
    try:
        st = os.lstat(db_path)
    except OSError as exc:
        raise DiscoveryError("db_lstat_failed:%s" % exc)
    if not stat.S_ISREG(st.st_mode):
        raise DiscoveryError("db_not_regular_file")
    uri = "file:%s?mode=ro" % db_path
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("PRAGMA query_only=ON;")
    return conn, st


def list_tables(conn):
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name LIMIT ?",
        (MAX_TABLES,),
    )
    return [r[0] for r in cur.fetchall()]


def list_columns(conn, table):
    cur = conn.execute("PRAGMA table_info(%s)" % quote_ident(table))
    cols = [r[1] for r in cur.fetchall()]
    return cols[:MAX_COLUMNS]


def find_ua0006(conn, tables_examined_out):
    matches = []
    for table in list_tables(conn):
        try:
            cols = list_columns(conn, table)
        except sqlite3.Error:
            continue
        tables_examined_out.append({"table": table, "columns": cols})
        low_cols = {c.lower(): c for c in cols}
        id_cols = [low_cols[c] for c in ID_COLUMN_CANDIDATES if c in low_cols]
        container_cols = [c for c in cols if CONTAINER_COLUMN_HINT in c.lower()]
        if not id_cols or not container_cols:
            continue
        for id_col in id_cols:
            for container_col in container_cols:
                sql = "SELECT rowid, %s FROM %s WHERE %s = ? LIMIT 3" % (
                    quote_ident(container_col), quote_ident(table), quote_ident(id_col)
                )
                for value in IDENTITY_VALUES:
                    try:
                        rows = conn.execute(sql, (value,)).fetchall()
                    except sqlite3.Error:
                        continue
                    for rowid, container_val in rows:
                        matches.append({
                            "table": table,
                            "id_column": id_col,
                            "container_column": container_col,
                            "rowid": rowid,
                            "container_value": container_val,
                        })
    dedup = {}
    for m in matches:
        key = (m["table"], m["id_column"], m["container_column"], m["rowid"])
        dedup[key] = m
    return list(dedup.values())


def run_discovery(db_path, sources, required_sources=None, required_db=None):
    errors = []
    result = {
        "task_id": TASK_ID,
        "mode": MODE,
        "status": "BLOCKED",
        "production_write": False,
        "crm_write": False,
        "db_write": False,
        "ua0009_published": False,
        "sources": [],
        "db": {},
        "errors": errors,
    }

    req_sources = required_sources if required_sources is not None else REQUIRED_SOURCES

    try:
        validate_sources_arg(sources, required=req_sources)
    except DiscoveryError as exc:
        errors.append(str(exc))
        return result

    source_evidence = []
    try:
        for path in req_sources:
            source_evidence.append(secure_read_source(path))
    except DiscoveryError as exc:
        errors.append(str(exc))
        result["sources"] = source_evidence
        return result

    result["sources"] = source_evidence

    conn = None
    try:
        conn, db_stat_before = open_readonly_db(db_path, required_db=required_db)
        quick = conn.execute("PRAGMA quick_check;").fetchall()
        quick_ok = len(quick) == 1 and quick[0][0] == "ok"
        tables_examined = []
        matches = find_ua0006(conn, tables_examined)

        db_stat_after = os.lstat(db_path)
        identity_stable = (
            db_stat_after.st_ino == db_stat_before.st_ino
            and db_stat_after.st_dev == db_stat_before.st_dev
            and db_stat_after.st_size == db_stat_before.st_size
            and db_stat_after.st_mtime == db_stat_before.st_mtime
        )

        result["db"] = {
            "path": db_path,
            "quick_check_ok": quick_ok,
            "tables_examined": len(tables_examined),
            "identity_stable": identity_stable,
        }

        if not quick_ok:
            errors.append("db_quick_check_failed")
            return result
        if not identity_stable:
            errors.append("db_concurrent_change_detected")
            return result

        if len(matches) == 0:
            errors.append("ua0006_no_match_found")
            result["db"]["schema_hint"] = [
                {"table": t["table"], "columns": t["columns"]} for t in tables_examined
            ]
            return result
        if len(matches) > 1:
            errors.append("ua0006_ambiguous_match")
            result["db"]["ambiguous_candidates"] = [
                {
                    "table": m["table"],
                    "id_column": m["id_column"],
                    "container_column": m["container_column"],
                }
                for m in matches
            ]
            return result

        match = matches[0]
        current = match["container_value"]
        status_value = (
            "ALREADY_CORRECT" if current == CORRECT_CONTAINER else "NEEDS_EXACT_UPDATE"
        )
        result["UA0006_CONTAINER_STATUS"] = status_value
        result["status"] = "PASS"
        return result
    except DiscoveryError as exc:
        errors.append(str(exc))
        return result
    except sqlite3.Error as exc:
        errors.append("sqlite_error:%s" % exc)
        return result
    finally:
        if conn is not None:
            conn.close()


def scan_for_secrets(text):
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            return True
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--source", action="append", default=[])
    args = parser.parse_args(argv)

    result = run_discovery(args.db, args.source)
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True)

    if scan_for_secrets(payload):
        fail = {
            "task_id": TASK_ID,
            "mode": MODE,
            "status": "BLOCKED",
            "production_write": False,
            "crm_write": False,
            "db_write": False,
            "ua0009_published": False,
            "sources": [],
            "db": {},
            "errors": ["secret_pattern_detected_in_output_refused"],
        }
        print(json.dumps(fail, ensure_ascii=False, sort_keys=True))
        return 1

    print(payload)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
