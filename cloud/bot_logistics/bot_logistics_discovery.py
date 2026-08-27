#!/usr/bin/env python3
"""Bounded, read-only discovery for BOT-LOGISTICS-001.

The script reads exactly six approved source files and /home/Carix/crm.db,
finds the real menu/handler anchors and the unique UA-0006 container field,
and emits one sanitized JSON object. It has no write path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
import urllib.parse

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

CORRECT_CONTAINER = "ONEYSELGF1046602"
IDENTITY_VALUES = ("UA-0006", "UA0006", "0006", 6)

MAX_SOURCE_SIZE = 2_000_000
MAX_SOURCE_LINES = 40_000
MAX_ANCHORS_PER_SOURCE = 80
MAX_SNIPPET_CHARS = 1_200
MAX_DB_SIZE = 512 * 1024 * 1024
MAX_TABLES = 100
MAX_COLUMNS = 160
MAX_SCHEMA_HINTS = 60

ID_COLUMN_CANDIDATES = (
    "ua_id",
    "id",
    "uaid",
    "ua_number",
    "ua",
    "ua_code",
    "number",
    "car_id",
    "auto_number",
)
CONTAINER_COLUMN_HINTS = ("container", "контейнер")
ANCHOR_PATTERNS = (
    "срок доставки",
    "номер и дата контейнера",
    "дней до прибытия",
    "номер контейнера",
    "этапы и доставка",
    "container_number",
    "container_date",
    "container_handler",
    "ua0006_container",
    "days_to_arrival",
    "delivery_days",
    "departure_date",
    "logistics_hub",
    "edit_container",
    "set_container",
    "change_stage",
    "set_stage",
    "def card_kb",
    "def edit_menu",
    "def edit_ask",
    "def stage_menu",
    "def stage_set",
    "car_setf:",
    "car_stage:",
    "car_setstage:",
    "car_wait",
    "eta_days",
    "sea_container",
    "sea_date_out",
    "days_to_kyiv",
    "ge_to_kyiv_at",
)

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
FUNCTION_RE = re.compile(
    r"^\s*(?:async\s+def|def)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("
)
SENSITIVE_WORD_RE = re.compile(
    r"(?i)(?:secret|token|password|api[-_ ]?key|authorization|"
    r"private[-_ ]?key|credential)"
)
TOKEN_SHAPE_RE = re.compile(
    r"(?<![A-Za-z0-9_-])(?:sk-[A-Za-z0-9_-]{16,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|"
    r"eyJ[A-Za-z0-9_-]{20,}(?:\.[A-Za-z0-9_-]+){1,2}|"
    r"[A-Za-z0-9_-]{40,})(?![A-Za-z0-9_-])"
)
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d ()-]{7,}\d(?!\w)")
VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.IGNORECASE)


class DiscoveryError(RuntimeError):
    """A fail-closed discovery refusal."""


def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _identity(st: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        st.st_dev,
        st.st_ino,
        stat.S_IFMT(st.st_mode),
        st.st_nlink,
        st.st_size,
        st.st_mtime_ns,
        st.st_ctime_ns,
    )


def _validate_regular(st: os.stat_result, *, path: str, size_cap: int) -> None:
    if not stat.S_ISREG(st.st_mode):
        raise DiscoveryError("not_regular_file:" + path)
    if st.st_nlink != 1:
        raise DiscoveryError("unexpected_link_count:" + path)
    if st.st_size < 0 or st.st_size > size_cap:
        raise DiscoveryError("file_size_out_of_bounds:" + path)


def _open_no_follow(path: str, size_cap: int) -> tuple[int, os.stat_result]:
    try:
        before = os.lstat(path)
    except OSError as exc:
        raise DiscoveryError("lstat_failed:" + path) from exc
    _validate_regular(before, path=path, size_cap=size_cap)

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise DiscoveryError("open_failed:" + path) from exc
    try:
        opened = os.fstat(fd)
        _validate_regular(opened, path=path, size_cap=size_cap)
        if _identity(opened) != _identity(before):
            raise DiscoveryError("identity_changed_during_open:" + path)
        return fd, before
    except Exception:
        os.close(fd)
        raise


def _finish_no_follow(path: str, fd: int, before: os.stat_result, size_cap: int) -> None:
    opened_after = os.fstat(fd)
    _validate_regular(opened_after, path=path, size_cap=size_cap)
    try:
        path_after = os.lstat(path)
    except OSError as exc:
        raise DiscoveryError("lstat_after_failed:" + path) from exc
    _validate_regular(path_after, path=path, size_cap=size_cap)
    expected = _identity(before)
    if _identity(opened_after) != expected or _identity(path_after) != expected:
        raise DiscoveryError("concurrent_change_detected:" + path)


def secure_read_bytes(path: str, size_cap: int) -> tuple[bytes, str]:
    fd, before = _open_no_follow(path, size_cap)
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = os.read(fd, min(65_536, size_cap + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > size_cap:
                raise DiscoveryError("file_size_out_of_bounds:" + path)
        _finish_no_follow(path, fd, before, size_cap)
    finally:
        os.close(fd)
    data = b"".join(chunks)
    return data, sha256_bytes(data)


def secure_digest(path: str, size_cap: int) -> tuple[str, tuple[int, ...]]:
    fd, before = _open_no_follow(path, size_cap)
    digest = hashlib.sha256()
    total = 0
    try:
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > size_cap:
                raise DiscoveryError("file_size_out_of_bounds:" + path)
            digest.update(chunk)
        _finish_no_follow(path, fd, before, size_cap)
    finally:
        os.close(fd)
    return digest.hexdigest(), _identity(before)


def contains_sensitive_text(text: str, *, allow_sha256: bool = False) -> bool:
    if allow_sha256 and HEX64_RE.fullmatch(text):
        return False
    if CORRECT_CONTAINER in text.upper():
        return True
    return bool(
        SENSITIVE_WORD_RE.search(text)
        or TOKEN_SHAPE_RE.search(text)
        or EMAIL_RE.search(text)
        or PHONE_RE.search(text)
        or VIN_RE.search(text)
    )


def redact_line(line: str) -> str:
    return "[REDACTED]" if contains_sensitive_text(line) else line


def _safe_identifier(value: object) -> str:
    text = str(value)
    if len(text) > 120 or contains_sensitive_text(text):
        return "[REDACTED]"
    return text


def _nearest_function(lines: list[str], index: int) -> str | None:
    for offset in range(index, max(-1, index - 80), -1):
        match = FUNCTION_RE.match(lines[offset])
        if match:
            name = match.group(1)
            return "[REDACTED]" if contains_sensitive_text(name) else name
    return None


def scan_source(path: str) -> dict:
    data, digest = secure_read_bytes(path, MAX_SOURCE_SIZE)
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > MAX_SOURCE_LINES:
        raise DiscoveryError("source_line_count_out_of_bounds:" + path)

    anchors: list[dict] = []
    folded_patterns = tuple(item.casefold() for item in ANCHOR_PATTERNS)
    for index, line in enumerate(lines):
        folded = line.casefold()
        matched = [item for item in folded_patterns if item in folded]
        if not matched:
            continue
        if len(anchors) >= MAX_ANCHORS_PER_SOURCE:
            raise DiscoveryError("too_many_source_anchors:" + path)
        start = max(0, index - 6)
        end = min(len(lines), index + 7)
        context = "\n".join(
            f"{line_no + 1}: {redact_line(lines[line_no])[:240]}"
            for line_no in range(start, end)
        )
        anchors.append(
            {
                "line": index + 1,
                "matches": matched[:8],
                "function": _nearest_function(lines, index),
                "snippet": context[:MAX_SNIPPET_CHARS],
            }
        )

    return {
        "path": path,
        "sha256": digest,
        "size": len(data),
        "line_count": len(lines),
        "anchors": anchors,
    }


def validate_sources_arg(sources, required=None) -> tuple[str, ...]:
    required_sources = tuple(REQUIRED_SOURCES if required is None else required)
    supplied = tuple(sources)
    if len(supplied) != len(required_sources):
        raise DiscoveryError(
            "source_count_mismatch:expected=%d:got=%d"
            % (len(required_sources), len(supplied))
        )
    if len(set(supplied)) != len(supplied):
        raise DiscoveryError("duplicate_source_supplied")
    if set(supplied) != set(required_sources):
        raise DiscoveryError("source_set_mismatch")
    return required_sources


def open_readonly_db(db_path: str, required_db: str | None = None):
    expected = REQUIRED_DB if required_db is None else required_db
    if db_path != expected:
        raise DiscoveryError("db_path_mismatch")
    before = os.lstat(db_path)
    _validate_regular(before, path=db_path, size_cap=MAX_DB_SIZE)
    encoded = urllib.parse.quote(db_path, safe="/")
    connection = sqlite3.connect(f"file:{encoded}?mode=ro", uri=True, timeout=3)
    try:
        after = os.lstat(db_path)
        _validate_regular(after, path=db_path, size_cap=MAX_DB_SIZE)
        if _identity(before) != _identity(after):
            raise DiscoveryError("db_identity_changed_during_open")
        connection.execute("PRAGMA query_only=ON")
        return connection, _identity(before)
    except Exception:
        connection.close()
        raise


def list_tables(connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = ? AND name NOT GLOB 'sqlite_*' "
        "ORDER BY name LIMIT ?",
        ("table", MAX_TABLES + 1),
    ).fetchall()
    names = [row[0] for row in rows if isinstance(row[0], str)]
    if len(names) > MAX_TABLES:
        raise DiscoveryError("too_many_sqlite_tables")
    return names


def list_columns(connection, table: str) -> list[str]:
    rows = connection.execute(
        "PRAGMA table_info(%s)" % quote_ident(table)
    ).fetchall()
    if len(rows) > MAX_COLUMNS:
        raise DiscoveryError("too_many_sqlite_columns")
    return [row[1] for row in rows if isinstance(row[1], str)]


def find_ua0006(connection) -> tuple[list[dict], list[dict]]:
    candidates: list[dict] = []
    schema: list[dict] = []
    placeholders = ",".join("?" for _ in IDENTITY_VALUES)

    for table in list_tables(connection):
        columns = list_columns(connection, table)
        schema.append(
            {
                "table": _safe_identifier(table),
                "columns": [_safe_identifier(column) for column in columns],
            }
        )
        by_lower = {column.casefold(): column for column in columns}
        id_columns = [
            by_lower[name]
            for name in ID_COLUMN_CANDIDATES
            if name in by_lower
        ]
        container_columns = [
            column
            for column in columns
            if any(hint in column.casefold() for hint in CONTAINER_COLUMN_HINTS)
        ]
        for id_column in id_columns:
            for container_column in container_columns:
                statement = (
                    "SELECT %s FROM %s WHERE %s IN (%s) LIMIT 3"
                    % (
                        quote_ident(container_column),
                        quote_ident(table),
                        quote_ident(id_column),
                        placeholders,
                    )
                )
                rows = connection.execute(statement, IDENTITY_VALUES).fetchall()
                if not rows:
                    continue
                current = rows[0][0] if len(rows) == 1 else None
                candidates.append(
                    {
                        "table": table,
                        "id_column": id_column,
                        "container_column": container_column,
                        "row_count": len(rows),
                        "already_correct": (
                            len(rows) == 1
                            and str(current or "").strip().upper() == CORRECT_CONTAINER
                        ),
                    }
                )
    return candidates, schema[:MAX_SCHEMA_HINTS]


def _base_result() -> dict:
    return {
        "task_id": TASK_ID,
        "mode": MODE,
        "status": "BLOCKED",
        "production_write": False,
        "crm_write": False,
        "db_write": False,
        "ua0009_published": False,
        "sources": [],
        "db": {},
        "errors": [],
    }


def run_discovery(
    db_path: str,
    sources,
    required_sources=None,
    required_db: str | None = None,
) -> dict:
    result = _base_result()
    errors = result["errors"]

    try:
        exact_sources = validate_sources_arg(sources, required_sources)
        for path in exact_sources:
            result["sources"].append(scan_source(path))
    except (DiscoveryError, OSError) as exc:
        errors.append(
            str(exc) if isinstance(exc, DiscoveryError) else "source_os_error"
        )
        return result

    expected_db = REQUIRED_DB if required_db is None else required_db
    if db_path != expected_db:
        errors.append("db_path_mismatch")
        return result

    connection = None
    try:
        db_sha_before, db_identity_before = secure_digest(db_path, MAX_DB_SIZE)
        connection, db_open_identity = open_readonly_db(db_path, required_db)
        if db_open_identity != db_identity_before:
            raise DiscoveryError("db_identity_changed_before_query")
        data_version_before = connection.execute("PRAGMA data_version").fetchone()[0]
        quick_before = connection.execute("PRAGMA quick_check").fetchall()
        candidates, schema = find_ua0006(connection)
        quick_after = connection.execute("PRAGMA quick_check").fetchall()
        data_version_after = connection.execute("PRAGMA data_version").fetchone()[0]
        if connection.total_changes != 0:
            raise DiscoveryError("unexpected_sqlite_change_count")
        connection.close()
        connection = None

        db_sha_after, db_identity_after = secure_digest(db_path, MAX_DB_SIZE)
        quick_ok = quick_before == [("ok",)] and quick_after == [("ok",)]
        identity_stable = (
            db_identity_before == db_identity_after
            and db_sha_before == db_sha_after
            and data_version_before == data_version_after
        )
        result["db"] = {
            "path": db_path,
            "sha256_before": db_sha_before,
            "sha256_after": db_sha_after,
            "quick_check_ok": quick_ok,
            "identity_stable": identity_stable,
            "candidate_count": len(candidates),
        }
        if not quick_ok:
            errors.append("db_quick_check_failed")
            return result
        if not identity_stable:
            errors.append("db_concurrent_change_detected")
            return result
        if not candidates:
            errors.append("ua0006_no_match_found")
            result["db"]["schema_hint"] = schema
            return result
        if len(candidates) != 1 or candidates[0]["row_count"] != 1:
            errors.append("ua0006_ambiguous_match")
            result["db"]["ambiguous_candidates"] = [
                {
                    "table": _safe_identifier(item["table"]),
                    "id_column": _safe_identifier(item["id_column"]),
                    "container_column": _safe_identifier(item["container_column"]),
                    "row_count": item["row_count"],
                }
                for item in candidates[:20]
            ]
            return result

        match = candidates[0]
        result["db"].update(
            {
                "matched_table": _safe_identifier(match["table"]),
                "matched_id_column": _safe_identifier(match["id_column"]),
                "matched_container_column": _safe_identifier(
                    match["container_column"]
                ),
                "ua0006_row_count": 1,
            }
        )
        result["UA0006_CONTAINER_STATUS"] = (
            "ALREADY_CORRECT"
            if match["already_correct"]
            else "NEEDS_EXACT_UPDATE"
        )
        result["status"] = "PASS"
        return result
    except DiscoveryError as exc:
        errors.append(str(exc))
        return result
    except (OSError, sqlite3.Error, ValueError, TypeError):
        errors.append("read_only_db_discovery_failed")
        return result
    finally:
        if connection is not None:
            connection.close()


def output_contains_sensitive_data(value: object, key: str | None = None) -> bool:
    if isinstance(value, dict):
        return any(
            output_contains_sensitive_data(item, str(item_key))
            for item_key, item in value.items()
        )
    if isinstance(value, list):
        return any(output_contains_sensitive_data(item, key) for item in value)
    if isinstance(value, str):
        allow_hash = key in {"sha256", "sha256_before", "sha256_after"}
        return contains_sensitive_text(value, allow_sha256=allow_hash)
    return False


def _emit(result: dict) -> int:
    if output_contains_sensitive_data(result):
        result = _base_result()
        result["errors"] = ["unsafe_output_redacted"]
    sys.stdout.write(
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )
    return 0 if result["status"] == "PASS" else 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument("--db", required=True)
    parser.add_argument("--source", action="append", default=[])
    try:
        args = parser.parse_args(argv)
    except (argparse.ArgumentError, SystemExit):
        result = _base_result()
        result["errors"] = ["invalid_arguments"]
        return _emit(result)
    return _emit(run_discovery(args.db, args.source))


if __name__ == "__main__":
    raise SystemExit(main())
