"""
sqlite_ownership.py (TASK 051 restoration+correction of the TASK 041
baseline; the read-only UA-0009 evidence API in Section 2 is preserved
unchanged from the accepted baseline, byte-for-byte.)

Two independent capabilities live in this module:

1. The structural (AST-based) transformation and verifier enforcing
   short SQLite ownership: SELECT rows are materialized into ordinary
   immutable values (tuple of tuples) and the cursor/connection are
   closed BEFORE any slow-call category (formatting/hash/sleep/
   network/filesystem/Telegram I/O). TASK 051 corrections on top of the
   TASK 041 baseline:

   - transform_short_ownership still requires exactly one local
     sqlite3.connect assignment and at most one cursor derived only
     from that connection (via conn.cursor() OR cur = conn.execute(
     literal_readonly_sql, ...)); rejects any branch/loop/try/with
     inside the ownership segment (straight-line only); rejects write
     SQL (INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/REPLACE/VACUUM/
     REINDEX), executemany writes, commit()/rollback(), mutable
     PRAGMA, non-literal SQL text.
   - Escape detection now additionally rejects: return of a tracked
     handle, aliasing (other = cur), storing a tracked handle into an
     attribute or subscript target, passing a tracked handle as a call
     argument/keyword to any call other than its own
     cursor/execute/fetch*/close methods, and closure capture by a
     nested function/lambda.
   - Generated code initializes conn = None (and cur = None when a
     cursor is tracked) before the generated try, removes the
     function's own original close() statements on tracked names from
     the ownership segment (so they are never duplicated), and emits a
     finally block that closes the cursor first (guarded by
     `is not None`) and then the connection (guarded by
     `is not None`), never emitting a close after the ownership block
     and never double-closing.
   - The local connect call receives exactly one `timeout=2` keyword;
     an existing timeout keyword is normalized to exactly `timeout=2`
     rather than duplicated.
   - fetchall()/fetchmany() results are materialized immediately after
     the fetch call, before any close, as
     `tuple(tuple(row) for row in <name>)`, preserving the assigned
     result name and its later use.
   - Connect/execute/fetch exceptions propagate with their original
     exception type and message; because conn/cur are always
     initialized to None before the try, cleanup can never raise
     UnboundLocalError.
   - verify_no_live_handle_across_slow_call still tracks each
     connection name and each derived cursor name independently
     (per-name open/closed state) so an unrelated `.close()` call on an
     unrelated object can never mark this function's real handles as
     closed.

2. A canonical, read-only, fail-closed SQLite evidence API used to
   prove UA-0009 row identity/ownership without ever emitting raw
   field values, names, phones, messages, blobs, or database pages.
   Only structural table/column identifiers, bounded row
   counts/identity hashes, and SHA-256 digests are returned. Preserved
   unchanged from the accepted TASK 034/041 baseline.

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
# Section 1: AST-based short-ownership transform and verifier.
# --------------------------------------------------------------------

SLOW_CALL_NAMES = {
    "sleep", "time.sleep",
    "send_message", "send_photo", "send_video", "send_document",
    "reply_photo", "reply_video", "reply_text", "reply_document",
    "requests.get", "requests.post", "urlopen",
    "open", "write", "system", "run", "Popen", "call",
    "render", "generate", "build",
}

WRITE_SQL_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "create", "replace",
    "vacuum", "reindex",
)

OWN_METHOD_SUFFIXES = (
    "cursor", "execute", "executemany", "fetchall", "fetchmany",
    "fetchone", "close",
)


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


def find_cursor_names(func, handle_names: Set[str]) -> Set[str]:
    """Recognize at most one cursor per connection, assigned either by
    `cur = conn.cursor()` or by `cur = conn.execute(literal_sql, ...)`,
    owned by that exact connection name."""
    names: Set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if isinstance(node.value.func, ast.Attribute):
                owner = getattr(node.value.func.value, "id", None)
                attr = node.value.func.attr
                if owner in handle_names and attr in ("cursor", "execute"):
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            names.add(t.id)
    return names


def _literal_sql_text(call_node: ast.Call) -> Optional[str]:
    if call_node.args and isinstance(call_node.args[0], ast.Constant) and isinstance(call_node.args[0].value, str):
        return call_node.args[0].value
    return None


def _is_write_sql(sql_text: str) -> bool:
    lowered = sql_text.strip().lower()
    return any(lowered.startswith(k) for k in WRITE_SQL_KEYWORDS)


def _contains_write_sql_or_commit(stmts) -> Optional[str]:
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call):
                qual = _call_qualname(node)
                if qual.endswith("execute") or qual.endswith("executemany"):
                    sql = _literal_sql_text(node)
                    if sql is None:
                        return "non_literal_sql_rejected"
                    if _is_write_sql(sql):
                        return "write_sql_rejected"
                    lowered = sql.strip().lower()
                    if lowered.startswith("pragma") and "=" in lowered and "query_only" not in lowered:
                        return "mutable_pragma_rejected"
                if qual.endswith("commit") or qual.endswith("rollback"):
                    return "commit_or_rollback_rejected"
    return None


def _contains_unsupported_control_flow(stmts) -> bool:
    for stmt in stmts:
        if isinstance(stmt, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)):
            return True
    return False


def _refs_tracked(node, tracked_names: Set[str]) -> bool:
    if node is None:
        return False
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and n.id in tracked_names:
            return True
    return False


def _detect_escape(func, tracked_names: Set[str]) -> None:
    """Reject return/alias/attribute-subscript-store/call-argument-pass/
    closure-capture escape of any tracked connection or cursor name."""
    for node in ast.walk(func):
        if node is func:
            continue
        if isinstance(node, ast.Return):
            if _refs_tracked(node.value, tracked_names):
                raise AnchorNotFoundError("handle escapes via return")
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Name) and node.value.id in tracked_names:
                raise AnchorNotFoundError("handle aliased")
            for t in node.targets:
                if isinstance(t, (ast.Attribute, ast.Subscript)) and _refs_tracked(node.value, tracked_names):
                    raise AnchorNotFoundError("handle stored into attribute/subscript")
        if isinstance(node, ast.Call):
            qual = _call_qualname(node)
            is_own_method_call = (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in tracked_names
                and node.func.attr in OWN_METHOD_SUFFIXES
            )
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                if isinstance(arg, ast.Name) and arg.id in tracked_names:
                    if not is_own_method_call:
                        raise AnchorNotFoundError("handle passed as call argument")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            if _refs_tracked(node, tracked_names):
                raise AnchorNotFoundError("handle captured by closure")


def _is_close_stmt_on_names(stmt, tracked_names: Set[str]) -> bool:
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        call = stmt.value
        if isinstance(call.func, ast.Attribute) and call.func.attr == "close":
            if isinstance(call.func.value, ast.Name) and call.func.value.id in tracked_names:
                return True
    return False


def verify_no_live_handle_across_slow_call(func) -> List[str]:
    """Walk the statements of `func` in execution order (including simple
    nested blocks) tracking each connection name and each derived cursor
    name INDEPENDENTLY. A slow call is a violation only for the specific
    names that are still open at that point; an unrelated `.close()`
    call on an unrelated name can never mark this function's real
    handles as closed. Conservative: anything not provably closed before
    a slow call is reported.
    """
    handle_names = find_db_handle_names(func)
    if not handle_names:
        return []
    cursor_names: Set[str] = set()
    open_names: Set[str] = set()
    violations: List[str] = []

    def walk_stmts(stmts):
        for stmt in stmts:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                qual = _call_qualname(stmt.value)
                if qual.endswith("connect"):
                    for t in stmt.targets:
                        if isinstance(t, ast.Name) and t.id in handle_names:
                            open_names.add(t.id)
                if isinstance(stmt.value.func, ast.Attribute):
                    owner = getattr(stmt.value.func.value, "id", None)
                    attr = stmt.value.func.attr
                    if owner in handle_names and attr in ("cursor", "execute"):
                        for t in stmt.targets:
                            if isinstance(t, ast.Name):
                                cursor_names.add(t.id)
                                open_names.add(t.id)
            for node in ast.walk(stmt):
                if isinstance(node, ast.Call):
                    qual = _call_qualname(node)
                    owner = qual.split(".")[0] if "." in qual else None
                    if qual.endswith("close") and owner and (owner in handle_names or owner in cursor_names):
                        open_names.discard(owner)
                    elif any(qual == s or qual.endswith("." + s) or qual == s.split(".")[-1]
                             for s in SLOW_CALL_NAMES):
                        if open_names:
                            violations.append(
                                f"line {getattr(node, 'lineno', '?')}: slow call "
                                f"'{qual}' before close of {sorted(open_names)}"
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
    """Ensure the local connect call carries exactly one timeout=2
    keyword, normalizing any pre-existing timeout keyword rather than
    duplicating it."""
    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            qual = _call_qualname(node.value)
            if qual.endswith("connect"):
                replaced = False
                for kw in node.value.keywords:
                    if kw.arg == "timeout":
                        kw.value = ast.Constant(value=2)
                        replaced = True
                if not replaced:
                    node.value.keywords.append(
                        ast.keyword(arg="timeout", value=ast.Constant(value=2))
                    )


def transform_short_ownership(source: str, function_names: Set[str]) -> str:
    """Rewrite the named functions so the sqlite3 connection/cursor is
    guaranteed materialized-and-closed (via try/finally, with conn/cur
    pre-initialized to None) before any subsequent formatting/slow work.
    Supports only structurally proven local ownership: exactly one local
    sqlite3.connect assignment, zero or one cursor derived only from
    that connection (via .cursor() or .execute(literal_sql)), a
    straight-line ownership segment (no branch/loop/try/with), literal
    read-only SQL (no write keywords, executemany writes, commit,
    rollback, or mutable PRAGMA), and no escape of the tracked handles
    via return/alias/attribute-subscript-store/call-argument/closure.
    Raises AnchorNotFoundError on any unsupported shape. Deterministic:
    transforming the same original source twice yields identical bytes.
    """
    tree = ast.parse(source)
    found = list(_iter_functions(tree, function_names))
    found_names = {f.name for f in found}
    missing = function_names - found_names
    if missing:
        raise AnchorNotFoundError(f"functions not found: {sorted(missing)}")

    for func in found:
        handle_names = find_db_handle_names(func)
        if len(handle_names) != 1:
            raise AnchorNotFoundError(
                f"expected exactly one local connection in {func.name}, found {len(handle_names)}"
            )
        cursor_names = find_cursor_names(func, handle_names)
        if len(cursor_names) > 1:
            raise AnchorNotFoundError(f"expected zero or one cursor in {func.name}")

        tracked_names = handle_names | cursor_names
        _detect_escape(func, tracked_names)

        _ensure_short_timeout(func, handle_names)

        handle_stmt_indices = []
        for idx, stmt in enumerate(func.body):
            if any(isinstance(n, ast.Name) and n.id in tracked_names for n in ast.walk(stmt)):
                handle_stmt_indices.append(idx)
        if not handle_stmt_indices:
            raise AnchorNotFoundError(
                f"DB handle {handle_names} unused after connect in {func.name}"
            )
        last_db_idx = max(handle_stmt_indices)
        db_block = func.body[: last_db_idx + 1]
        rest_block = func.body[last_db_idx + 1:]

        if _contains_unsupported_control_flow(db_block):
            raise AnchorNotFoundError(
                f"unsupported control flow in ownership segment of {func.name}"
            )
        write_reason = _contains_write_sql_or_commit(db_block)
        if write_reason:
            raise AnchorNotFoundError(f"{write_reason} in {func.name}")

        # Remove the function's own original close() statements on
        # tracked names -- the generated finally block owns closing.
        db_block = [stmt for stmt in db_block if not _is_close_stmt_on_names(stmt, tracked_names)]

        # Materialize fetchall()/fetchmany() results into an immutable
        # tuple-of-tuples immediately after the fetch, before close.
        materialized_block = []
        for stmt in db_block:
            materialized_block.append(stmt)
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                qual = _call_qualname(stmt.value)
                if qual.endswith("fetchall") or qual.endswith("fetchmany"):
                    for t in stmt.targets:
                        if isinstance(t, ast.Name):
                            materialize = ast.parse(
                                f"{t.id} = tuple(tuple(row) for row in {t.id})"
                            ).body[0]
                            materialized_block.append(materialize)
        db_block = materialized_block

        init_stmts = []
        for name in sorted(handle_names):
            init_stmts.append(ast.parse(f"{name} = None").body[0])
        for name in sorted(cursor_names):
            init_stmts.append(ast.parse(f"{name} = None").body[0])

        close_stmts = []
        for name in sorted(cursor_names):
            close_stmts.append(
                ast.parse(f"if {name} is not None:\n    {name}.close()").body[0]
            )
        for name in sorted(handle_names):
            close_stmts.append(
                ast.parse(f"if {name} is not None:\n    {name}.close()").body[0]
            )

        try_node = ast.Try(body=db_block, handlers=[], orelse=[], finalbody=close_stmts)
        func.body = init_stmts + [try_node] + rest_block
        ast.fix_missing_locations(func)

    return ast.unparse(tree)


# --------------------------------------------------------------------
# Section 2: canonical read-only, fail-closed SQLite evidence API
# (TASK 034 baseline, preserved unchanged). Standard library only.
# Never raises for expected operational conditions.
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
