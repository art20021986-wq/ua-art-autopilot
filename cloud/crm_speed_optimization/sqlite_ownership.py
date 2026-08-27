"""
sqlite_ownership.py (TASK 034, preserved unchanged under TASK 038)

Two independent capabilities live in this module:

1. The original structural (AST-based) transformation and verifier
   enforcing short SQLite ownership: SELECT rows are materialized into
   ordinary immutable values and the cursor/connection are closed
   BEFORE any slow-call category (formatting/hash/sleep/network/
   filesystem/Telegram I/O). Preserved unchanged for compatibility and
   reused directly (not duplicated) by candidate_transforms.py under
   TASK 038.

2. A canonical, read-only, fail-closed SQLite evidence API used to
   prove UA-0009 row identity/ownership without ever emitting raw field
   values, names, phones, messages, blobs, or database pages. Only
   structural table/column identifiers, bounded row counts/identity
   hashes, and SHA-256 digests are returned.

No network access. No production paths. No writes. No migrations, WAL
changes, VACUUM, REINDEX, or mutable PRAGMAs are ever issued.
"""
from __future__ import annotations

import ast
import hashlib
import os
import sqlite3
import stat
import sys
import urllib.parse
from dataclasses import dataclass, asdict
from typing import List, Optional, Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --------------------------------------------------------------------
# Section 1: original AST-based short-ownership transform (unchanged
# public interface: AnchorNotFoundError, find_db_handle_names,
# verify_no_live_handle_across_slow_call, transform_short_ownership).
# --------------------------------------------------------------------

SLOW_CALL_NAMES = {
    "sleep", "time.sleep",
    "send_message", "send_photo", "send_video", "send_document",
    "reply_photo", "reply_video", "reply_text", "reply_document",
    "requests.get", "requests.post", "urlopen",
    "open", "write", "system", "run", "Popen", "call",
    "render", "generate", "build",
}


class AnchorNotFoundError(Exception):
    pass


def _iter_functions(tree: ast.AST, names: Set[str]):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            yield node


def _call_qualname(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = ""
        if isinstance(func.value, ast.Name):
            base = func.value.id + "."
        return base + func.attr
    return ""


def find_db_handle_names(func) -> Set[str]:
    names: Set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            qual = _call_qualname(node.value)
            if qual.endswith("connect"):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
    return names


def verify_no_live_handle_across_slow_call(func) -> List[str]:
    """Walk the statements of `func` in execution order (including simple
    nested blocks) and report violations where a DB handle name (or a
    cursor derived from it) is still open -- i.e. not yet closed -- at
    the point a slow call occurs. Conservative: anything that cannot be
    proven safe is reported as a violation.
    """
    handle_names = find_db_handle_names(func)
    if not handle_names:
        return []
    cursor_names: Set[str] = set()
    state = {"closed": False}
    violations: List[str] = []

    def walk_stmts(stmts):
        for stmt in stmts:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                qual = _call_qualname(stmt.value)
                if qual.endswith("cursor") and isinstance(stmt.value.func, ast.Attribute):
                    owner = getattr(stmt.value.func.value, "id", None)
                    if owner in handle_names:
                        for t in stmt.targets:
                            if isinstance(t, ast.Name):
                                cursor_names.add(t.id)
            for node in ast.walk(stmt):
                if isinstance(node, ast.Call):
                    qual = _call_qualname(node)
                    owner = qual.split(".")[0] if "." in qual else None
                    if qual.endswith("close") and (owner in handle_names or owner in cursor_names):
                        state["closed"] = True
                    if any(qual == s or qual.endswith("." + s) or qual == s.split(".")[-1]
                           for s in SLOW_CALL_NAMES):
                        if not state["closed"]:
                            violations.append(
                                f"line {getattr(node, 'lineno', '?')}: slow call "
                                f"'{qual}' before DB handle close"
                            )
            if isinstance(stmt, (ast.If, ast.For, ast.While, ast.With, ast.Try)):
                for field in ("body", "orelse", "finalbody"):
                    block = getattr(stmt, field, None)
                    if isinstance(block, list):
                        walk_stmts(block)
                handlers = getattr(stmt, "handlers", None)
                if handlers:
                    for h in handlers:
                        walk_stmts(h.body)

    walk_stmts(func.body)
    return violations


def _ensure_short_timeout(func, handle_names: Set[str]) -> None:
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            qual = _call_qualname(node.value)
            if qual.endswith("connect"):
                has_timeout = any(kw.arg == "timeout" for kw in node.value.keywords)
                if not has_timeout:
                    node.value.keywords.append(
                        ast.keyword(arg="timeout", value=ast.Constant(value=2))
                    )


def transform_short_ownership(source: str, function_names: Set[str]) -> str:
    """Rewrite the named functions so the sqlite3 connection/cursor is
    guaranteed closed (via try/finally) immediately after the last
    statement referencing the DB handle, before any subsequent
    formatting/slow work. Sets a short (2s) connect timeout if none is
    given. Raises AnchorNotFoundError if a function or its DB handle
    cannot be unambiguously identified.
    """
    tree = ast.parse(source)
    found = list(_iter_functions(tree, function_names))
    found_names = {f.name for f in found}
    missing = function_names - found_names
    if missing:
        raise AnchorNotFoundError(f"functions not found: {sorted(missing)}")

    for func in found:
        handle_names = find_db_handle_names(func)
        if not handle_names:
            raise AnchorNotFoundError(
                f"no sqlite3.connect anchor found in function {func.name}"
            )
        _ensure_short_timeout(func, handle_names)

        handle_stmt_indices = []
        for idx, stmt in enumerate(func.body):
            refs_handle = any(
                isinstance(n, ast.Name) and n.id in handle_names
                for n in ast.walk(stmt)
            )
            if refs_handle:
                handle_stmt_indices.append(idx)
        if not handle_stmt_indices:
            raise AnchorNotFoundError(
                f"DB handle {handle_names} unused after connect in {func.name}"
            )
        last_db_idx = max(handle_stmt_indices)
        db_block = func.body[: last_db_idx + 1]
        rest_block = func.body[last_db_idx + 1:]

        close_stmts = []
        for name in sorted(handle_names):
            close_call = ast.Expr(
                value=ast.Call(
                    func=ast.Attribute(value=ast.Name(id=name, ctx=ast.Load()),
                                        attr="close", ctx=ast.Load()),
                    args=[], keywords=[],
                )
            )
            close_stmts.append(close_call)

        try_node = ast.Try(body=db_block, handlers=[], orelse=[], finalbody=close_stmts)
        func.body = [try_node] + rest_block
        ast.fix_missing_locations(func)

    return ast.unparse(tree)


# --------------------------------------------------------------------
# Section 2: canonical read-only, fail-closed SQLite evidence API
# (TASK 034). Standard library only. Never raises for expected
# operational conditions (missing/locked/malformed/ambiguous/overflow);
# always returns a structured OwnershipEvidence with status OK/BLOCKED.
# --------------------------------------------------------------------

MAX_TABLES = 50
MAX_COLUMNS = 50
MAX_ROWS = 1000
MAX_SERIALIZED_BYTES = 1_000_000


@dataclass
class OwnershipEvidence:
    status: str  # "OK" or "BLOCKED"
    reason: str
    quick_check: Optional[str] = None
    query_only: Optional[int] = None
    table: Optional[str] = None
    row_count: Optional[int] = None
    rows_sha256: Optional[str] = None
    evidence_sha256: Optional[str] = None

    def to_dict(self):
        return asdict(self)


def _sanitize(exc: BaseException) -> str:
    # Only the exception class name is ever surfaced -- never the
    # message, which could embed a path or a fragment of data.
    return type(exc).__name__


def _validate_db_path(path: str):
    """Validate the database path with lstat: must be a regular,
    non-symlink file with a stable identity (nlink == 1). Fails closed
    on any hard-link surprise."""
    try:
        st = os.lstat(path)
    except OSError as exc:
        return False, f"path_stat_failed:{_sanitize(exc)}"
    if stat.S_ISLNK(st.st_mode):
        return False, "path_is_symlink"
    if not stat.S_ISREG(st.st_mode):
        return False, "path_not_regular_file"
    if st.st_nlink != 1:
        return False, "path_hard_linked"
    return True, "ok"


def _quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def collect_ua0009_ownership_evidence(
    db_path: str,
    table: str,
    id_column: str,
    id_value: str = "UA-0009",
    timeout: float = 2.0,
    max_tables: int = MAX_TABLES,
    max_columns: int = MAX_COLUMNS,
    max_rows: int = MAX_ROWS,
    max_serialized_bytes: int = MAX_SERIALIZED_BYTES,
) -> OwnershipEvidence:
    """Read-only, fail-closed evidence collection selecting exactly one
    row identified by the configured exact identifier-column rule
    (table/id_column/id_value). The cursor and connection are always
    closed BEFORE any hashing/serialization occurs. Never raises for
    expected operational conditions."""
    valid, reason = _validate_db_path(db_path)
    if not valid:
        return OwnershipEvidence(status="BLOCKED", reason=reason)

    uri = "file:" + urllib.parse.quote(os.path.abspath(db_path)) + "?mode=ro"
    quick_check_val = None
    query_only_val = None

    try:
        conn = sqlite3.connect(uri, uri=True, timeout=timeout)
    except sqlite3.Error as exc:
        return OwnershipEvidence(status="BLOCKED", reason=f"open_failed:{_sanitize(exc)}")

    rows = None
    try:
        try:
            cur = conn.cursor()
            try:
                cur.execute("PRAGMA query_only=ON")
                row = cur.execute("PRAGMA query_only").fetchone()
                query_only_val = row[0] if row else None

                row = cur.execute("PRAGMA quick_check").fetchone()
                quick_check_val = row[0] if row else None
                if quick_check_val != "ok":
                    return OwnershipEvidence(
                        status="BLOCKED", reason="quick_check_not_ok",
                        quick_check=quick_check_val, query_only=query_only_val,
                    )

                tables = cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' LIMIT ?",
                    (max_tables + 1,),
                ).fetchall()
                if len(tables) > max_tables:
                    return OwnershipEvidence(
                        status="BLOCKED", reason="table_overflow",
                        quick_check=quick_check_val, query_only=query_only_val,
                    )
                table_names = {r[0] for r in tables}
                if table not in table_names:
                    return OwnershipEvidence(
                        status="BLOCKED", reason="missing_table",
                        quick_check=quick_check_val, query_only=query_only_val,
                    )

                columns = cur.execute(f"PRAGMA table_info({_quote_ident(table)})").fetchall()
                if len(columns) > max_columns:
                    return OwnershipEvidence(
                        status="BLOCKED", reason="column_overflow",
                        quick_check=quick_check_val, query_only=query_only_val, table=table,
                    )
                column_names = {c[1] for c in columns}
                if id_column not in column_names:
                    return OwnershipEvidence(
                        status="BLOCKED", reason="missing_column",
                        quick_check=quick_check_val, query_only=query_only_val, table=table,
                    )

                select_sql = (
                    f"SELECT rowid, * FROM {_quote_ident(table)} "
                    f"WHERE {_quote_ident(id_column)} = ? LIMIT ?"
                )
                rows = cur.execute(select_sql, (id_value, max_rows + 1)).fetchall()
            finally:
                cur.close()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return OwnershipEvidence(
            status="BLOCKED", reason=f"sqlite_error:{_sanitize(exc)}",
            quick_check=quick_check_val, query_only=query_only_val,
        )

    # Cursor and connection are now closed. Only materialized, immutable
    # values remain; hashing/serialization happens strictly below.
    if not rows:
        return OwnershipEvidence(
            status="BLOCKED", reason="missing_row",
            quick_check=quick_check_val, query_only=query_only_val, table=table,
        )
    if len(rows) > 1:
        return OwnershipEvidence(
            status="BLOCKED", reason="ambiguous_row",
            quick_check=quick_check_val, query_only=query_only_val, table=table,
        )

    serialized = repr(rows[0]).encode("utf-8")
    if len(serialized) > max_serialized_bytes:
        return OwnershipEvidence(
            status="BLOCKED", reason="serialized_overflow",
            quick_check=quick_check_val, query_only=query_only_val, table=table,
        )
    row_hash = hashlib.sha256(serialized).hexdigest()
    combined = hashlib.sha256(
        f"{quick_check_val}|{query_only_val}|{table}|{id_column}|{row_hash}".encode("utf-8")
    ).hexdigest()

    return OwnershipEvidence(
        status="OK", reason="ok", quick_check=quick_check_val, query_only=query_only_val,
        table=table, row_count=1, rows_sha256=row_hash, evidence_sha256=combined,
    )


def compare_ownership_evidence(before: OwnershipEvidence, after: OwnershipEvidence):
    """Pure comparison helper for before/after UA-0009 evidence. OK only
    when both evidence objects are complete (status OK) and their
    evidence_sha256 hashes match exactly."""
    if before.status != "OK" or after.status != "OK":
        return False, "incomplete_evidence"
    if not before.evidence_sha256 or not after.evidence_sha256:
        return False, "incomplete_evidence"
    if before.evidence_sha256 != after.evidence_sha256:
        return False, "hash_mismatch"
    return True, "ok"
