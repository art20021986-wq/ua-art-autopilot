# TASK 054 — CRM-SPEED-001 deterministic SQLite compatibility and queue-test cleanup

## Exact scope

Continue from controller snapshot 0b6739e. Independent full discovery is now 308 tests: 301 PASS, 7 FAIL, 0 ERROR, 0 skip, no "Exception in thread".

This task fixes only two bounded non-orchestrator leftovers:
1. The stronger SQLite output correctly materializes tuple-of-tuples but a retained legacy test also requires literal tuple(rows).
2. RebuildQueueTests.test_burst_coalesces_to_one_followup exits TemporaryDirectory without shutting down its daemon worker, producing a nondeterministic cleanup race (Directory not empty) and occasionally perturbing the following lock test. Production RebuildQueue behavior is already correct; fix the test lifecycle, not the primitive.

Exact current files are embedded below.
SHA-256:
0855c2c5459e5abcf5621ac78a9d80d58c2ec309252d53644a485f09ec044946  sqlite_ownership.py
c4d162cdfdce57f1622355bfa146525e643a8261014af9e6e2db32be8284ade9  test_crm_speed_gate_a.py

## Safety

Work only under cloud/crm_speed_optimization/ plus cloud/latest_status.md and cloud/owner_reply.md. Claude authors all changes.

Never execute Gate A, use network/PythonAnywhere, install anything, or modify Production, CRM, database, bot, site, media, cards, generators, WSGI, processes, scheduled tasks, UA-0009, or tasks/.

Markers:
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

Return complete files only. Do not change candidate_transforms.py, canonical_modules.py, crm_speed_gate_a.py, or unrelated tests.

## 1. Preserve tuple-of-tuples and literal compatibility

In sqlite_ownership.transform_short_ownership, keep all TASK 051 ownership/exception guarantees and the complete evidence API unchanged.

For each fetchall/fetchmany result variable, emit deterministic two-step materialization before close:
- rows = tuple(rows)
- rows = tuple(tuple(row) for row in rows)

This preserves the retained legacy literal assertion while still proving every row is an immutable tuple. Do not replace the stronger second step, move it after close, or alter SQL/parameters/timeout/close ordering. Keep deterministic output and all negative BLOCK behavior.

Add/adjust only a compact TASK 054 report; the existing TASK 041 and TASK 051 tests already cover this.

## 2. Deterministic RebuildQueue test cleanup

In test_crm_speed_gate_a.py, modify only RebuildQueueTests.test_burst_coalesces_to_one_followup:
- always call q.shutdown(timeout=5) in a finally block before leaving TemporaryDirectory;
- wait/verify bounded completion as needed without sleep-based flakiness;
- preserve the assertions that enqueue returns accepted and at least one callback occurs;
- do not change canonical_modules.RebuildQueue or weaken concurrency expectations.

No daemon worker may remain alive when the temporary directory is cleaned.

## Acceptance

- compile all package Python files;
- TASK 034/038/041/051 SQLite tests PASS;
- test_crm_speed_gate_a.RebuildQueueTests PASS repeatedly;
- test_task_031_concurrency.TestCrossProcessLockSafety PASS after test_crm_speed_gate_a in the same process;
- full discovery improves to only the known orchestrator failures, with 0 ERROR and no background exception.

## Deliverables — exactly five files

1. cloud/crm_speed_optimization/sqlite_ownership.py
2. cloud/crm_speed_optimization/test_crm_speed_gate_a.py
3. cloud/crm_speed_optimization/TASK_054_REPORT.md
4. cloud/latest_status.md
5. cloud/owner_reply.md

Status: PARTIAL_TASK_054_NON_ORCHESTRATOR_GREEN_READY_FOR_CONTROLLER_AUDIT
Never claim READY_FOR_GATE_A.

## Exact current files

<BEGIN_SQLITE_OWNERSHIP_PY>
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


<END_SQLITE_OWNERSHIP_PY>

<BEGIN_TEST_CRM_SPEED_GATE_A_PY>
"""Offline test suite for CRM-SPEED-001 Gate A package (round 3 corrections).

Run with: python -m unittest test_crm_speed_gate_a -v
from inside cloud/crm_speed_optimization/. This suite never touches
production, /home/Carix, or PythonAnywhere.
"""
import os
import sys
import time
import uuid
import random
import sqlite3
import tempfile
import unittest
import multiprocessing
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import canonical_modules
import cross_process_lock
import rebuild_queue as rebuild_queue_module
import safe_writer as safe_writer_module
import crm_speed_gate_a as gate_a

from canonical_modules import CrossProcessLock, SingletonGuard, RebuildQueue, SafeWriter
from crm_speed_gate_a import (
    scan_reachable_call_graph, transform_cars_ui, measure_deterministic_repeat,
    scan_bounded_inventory, check_ua0009_not_public, evaluate_gate_a, run_gate_a,
    DEFAULT_MAX_FILES_PER_ROOT, ADMIN_ROUTE_NAMES,
)


# ---------------------------------------------------------------------------
# Identity assertions (correction D)
# ---------------------------------------------------------------------------

class IdentityTests(unittest.TestCase):
    def test_cross_process_lock_identity(self):
        self.assertIs(cross_process_lock.CrossProcessLock, canonical_modules.CrossProcessLock)
        self.assertIs(gate_a.CrossProcessLock, canonical_modules.CrossProcessLock)

    def test_rebuild_queue_identity(self):
        self.assertIs(rebuild_queue_module.RebuildQueue, canonical_modules.RebuildQueue)
        self.assertIs(gate_a.RebuildQueue, canonical_modules.RebuildQueue)

    def test_safe_writer_identity(self):
        self.assertIs(safe_writer_module.SafeWriter, canonical_modules.SafeWriter)
        self.assertIs(gate_a.SafeWriter, canonical_modules.SafeWriter)

    def test_singleton_guard_identity(self):
        self.assertIs(cross_process_lock.SingletonGuard, canonical_modules.SingletonGuard)
        self.assertIs(gate_a.SingletonGuard, canonical_modules.SingletonGuard)


# ---------------------------------------------------------------------------
# Correction A: dynamic dispatch call-graph scanner + cars_ui transform
# ---------------------------------------------------------------------------

class CarsUiTransformTests(unittest.TestCase):
    def test_dynamic_dispatch_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    fn = getattr(update.message, 'reply_photo')\n"
            "    fn(open('x.jpg', 'rb'))\n"
            "def video_gallery(update, context):\n"
            "    pass\n"
            "def diag_photo_show(update, context):\n"
            "    pass\n"
            "def diag_video_show(update, context):\n"
            "    pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any(r.startswith("dynamic_dispatch_forbidden") for r in result["reasons"]))

    def test_getattr_computed_name_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    name = pick_name()\n"
            "    fn = getattr(update.message, name)\n"
            "    fn()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_bound_method_alias_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    sender = update.message.reply_photo\n"
            "    sender(open('x.jpg','rb'))\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_callback_dict_media_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    handlers = {'photo': update.message.reply_photo}\n"
            "    handlers['photo']()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_callback_list_media_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    handlers = [update.message.reply_photo]\n"
            "    handlers[0]()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_lambda_media_call_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    f = lambda: update.message.reply_photo(open('x.jpg','rb'))\n"
            "    f()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_return_alias_blocks(self):
        source = (
            "def _pick(update):\n"
            "    return update.message.reply_photo\n"
            "def gallery(update, context):\n"
            "    fn = _pick(update)\n"
            "    fn()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_await_alias_blocks(self):
        source = (
            "async def gallery(update, context):\n"
            "    sender = update.message.reply_photo\n"
            "    await sender()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_nested_helper_media_call_blocks(self):
        source = (
            "def _send(update):\n"
            "    update.message.reply_photo(open('x.jpg','rb'))\n"
            "def gallery(update, context):\n"
            "    _send(update)\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertEqual(result["status"], "OK")
        self.assertIsNotNone(result["candidate"])
        clean, violations = scan_reachable_call_graph(result["candidate"], ADMIN_ROUTE_NAMES)
        self.assertTrue(clean, violations)
        self.assertNotIn("reply_photo", result["candidate"])

    def test_ambiguous_unresolved_callable_blocks(self):
        source = (
            "def gallery(update, context):\n"
            "    dispatch_table[update.kind](update)\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
        )
        result = transform_cars_ui(source)
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_direct_simple_media_call_transforms_cleanly(self):
        source = (
            "def gallery(update, context):\n"
            "    update.message.reply_photo(open('x.jpg','rb'))\n"
            "def video_gallery(update, context):\n"
            "    update.message.reply_video(open('x.mp4','rb'))\n"
            "def diag_photo_show(update, context):\n"
            "    pass\n"
            "def diag_video_show(update, context):\n"
            "    pass\n"
        )
        result = transform_cars_ui(source)
        self.assertEqual(result["status"], "OK")
        clean, violations = scan_reachable_call_graph(result["candidate"], ADMIN_ROUTE_NAMES)
        self.assertTrue(clean, violations)
        self.assertNotIn("reply_photo(", result["candidate"])
        self.assertIn("reply_text", result["candidate"])


# ---------------------------------------------------------------------------
# Correction B: deterministic repeat with agreed API
# ---------------------------------------------------------------------------

class DeterministicRepeatTests(unittest.TestCase):
    def test_deterministic_transform_passes(self):
        source = "def gallery(update, context):\n    update.message.reply_photo(1)\n" \
                 "def video_gallery(update, context): pass\n" \
                 "def diag_photo_show(update, context): pass\n" \
                 "def diag_video_show(update, context): pass\n"
        measurement = measure_deterministic_repeat(transform_cars_ui, source, args=(), repeats=10)
        self.assertTrue(measurement["deterministic"])
        self.assertEqual(measurement["repeats"], 10)

    def test_deterministic_transform_passes_with_source_kwarg(self):
        source = "def gallery(update, context): pass\n" \
                 "def video_gallery(update, context): pass\n" \
                 "def diag_photo_show(update, context): pass\n" \
                 "def diag_video_show(update, context): pass\n"
        measurement = measure_deterministic_repeat(transform_cars_ui, source=source, repeats=10)
        self.assertTrue(measurement["deterministic"])

    def _nondeterministic_random_content(self, source):
        return {"candidate": source + f"# {random.random()}", "status": "OK", "reasons": []}

    def _nondeterministic_time(self, source):
        return {"candidate": source + f"# {time.time()}", "status": "OK", "reasons": []}

    def _nondeterministic_uuid(self, source):
        return {"candidate": source + f"# {uuid.uuid4().hex}", "status": "OK", "reasons": []}

    def _nondeterministic_unordered_set(self, source):
        s = {random.randint(0, 10**9) for _ in range(5)}
        return {"candidate": source + f"# {sorted(s) if random.random() > 2 else list(s)}", "status": "OK", "reasons": []}

    def _nondeterministic_metadata(self, source):
        return {"candidate": source, "status": "OK", "reasons": [f"seen_at:{time.time()}"]}

    def test_nondeterministic_transform_blocks(self):
        source = "x = 1\n"
        variants = [
            self._nondeterministic_random_content,
            self._nondeterministic_time,
            self._nondeterministic_uuid,
            self._nondeterministic_unordered_set,
            self._nondeterministic_metadata,
        ]
        for variant in variants:
            measurement = measure_deterministic_repeat(variant, source, args=(), repeats=10)
            self.assertFalse(measurement["deterministic"], variant.__name__)
            forced_status, unmet = evaluate_gate_a({
                **{k: {"status": "OK"} for k in gate_a.REQUIRED_PREDICATES},
                "deterministic_repeat_all_transforms": {"status": "BLOCKED", "failures": [variant.__name__]},
            })
            self.assertEqual(forced_status, "BLOCKED")
            self.assertIn("deterministic_repeat_all_transforms", unmet)


# ---------------------------------------------------------------------------
# Correction C: real, honest overflow test with production default preserved
# ---------------------------------------------------------------------------

class SiteInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name in ["index.html", "katalog.html", "UA-0001.html"]:
            with open(os.path.join(self.tmp.name, name), "w") as fh:
                fh.write("<html></html>")

    def test_production_default_max_is_32(self):
        self.assertEqual(DEFAULT_MAX_FILES_PER_ROOT, 32)

    def test_overflow_blocks(self):
        allowed = ["index.html", "katalog.html", "UA-0001.html"]
        result = scan_bounded_inventory(self.tmp.name, allowed, max_files_per_root=2)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "overflow")
        self.assertEqual(result["matched_count"], 3)

    def test_exact_boundary_n_passes(self):
        allowed = ["index.html", "katalog.html", "UA-0001.html"]
        result = scan_bounded_inventory(self.tmp.name, allowed, max_files_per_root=3)
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["matched_count"], 3)

    def test_boundary_n_plus_one_blocks(self):
        allowed = ["index.html", "katalog.html", "UA-0001.html"]
        result = scan_bounded_inventory(self.tmp.name, allowed, max_files_per_root=2)
        self.assertEqual(result["status"], "BLOCKED")

    def test_default_production_cap_accepts_up_to_32(self):
        for i in range(2, 10):
            with open(os.path.join(self.tmp.name, f"UA-000{i}.html"), "w") as fh:
                fh.write("<html></html>")
        allowed = list(gate_a.ALLOWED_SITE_NAMES)
        result = scan_bounded_inventory(self.tmp.name, allowed)
        self.assertEqual(result["status"], "OK")
        self.assertLessEqual(result["matched_count"], 32)

    def test_missing_root_blocks(self):
        result = scan_bounded_inventory(os.path.join(self.tmp.name, "nope"), ["index.html"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_symlink_rejected(self):
        target = os.path.join(self.tmp.name, "index.html")
        link = os.path.join(self.tmp.name, "katalog.html")
        os.remove(link)
        os.symlink(target, link)
        result = scan_bounded_inventory(self.tmp.name, ["index.html", "katalog.html"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reason"], "symlink_rejected")


# ---------------------------------------------------------------------------
# Publication probe fail-closed behavior
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, code):
        self._code = code

    def getcode(self):
        return self._code


class _FakeOpener:
    def __init__(self, raise_exc=None, response_code=None):
        self.raise_exc = raise_exc
        self.response_code = response_code

    def open(self, req, timeout=5):
        if self.raise_exc is not None:
            raise self.raise_exc
        return _FakeResponse(self.response_code)


class PublicationProbeTests(unittest.TestCase):
    def test_404_passes(self):
        opener = _FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "OK")

    def test_410_passes(self):
        opener = _FakeOpener(raise_exc=urllib.error.HTTPError("u", 410, "gone", {}, None))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "OK")

    def test_200_blocks(self):
        opener = _FakeOpener(response_code=200)
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "BLOCKED")

    def test_redirect_blocks(self):
        opener = _FakeOpener(raise_exc=urllib.error.HTTPError("u", 302, "redir", {}, None))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "BLOCKED")

    def test_network_error_blocks(self):
        opener = _FakeOpener(raise_exc=urllib.error.URLError("connection refused"))
        result = check_ua0009_not_public("https://example.com/UA-0009.html", opener)
        self.assertEqual(result["status"], "BLOCKED")

    def test_non_https_blocks(self):
        result = check_ua0009_not_public("http://example.com/UA-0009.html")
        self.assertEqual(result["status"], "BLOCKED")

    def test_missing_url_blocks(self):
        result = check_ua0009_not_public("")
        self.assertEqual(result["status"], "BLOCKED")


# ---------------------------------------------------------------------------
# CrossProcessLock stress test (aggregate >=100 contention attempts)
# ---------------------------------------------------------------------------

def _contender_worker(lock_path, start_barrier, result_queue, hold_event):
    guard = CrossProcessLock(lock_path)
    start_barrier.wait()
    acquired = guard.acquire()
    result_queue.put((os.getpid(), acquired))
    if acquired:
        hold_event.wait(timeout=5)
        guard.release()


class CrossProcessLockStressTests(unittest.TestCase):
    def test_simultaneous_stale_takeover_only_one_wins(self):
        ctx = multiprocessing.get_context("fork") if hasattr(multiprocessing, "get_context") else multiprocessing
        rounds = 25
        contenders_per_round = 4
        for round_idx in range(rounds):
            with tempfile.TemporaryDirectory() as tmp:
                lock_path = os.path.join(tmp, "test.lock")
                with open(lock_path, "w") as fh:
                    fh.write(f"999999|stale|deadtoken|{time.time() - 100000}\n")
                start_barrier = ctx.Barrier(contenders_per_round)
                result_queue = ctx.Queue()
                hold_event = ctx.Event()
                procs = [
                    ctx.Process(target=_contender_worker, args=(lock_path, start_barrier, result_queue, hold_event))
                    for _ in range(contenders_per_round)
                ]
                for p in procs:
                    p.start()
                results = [result_queue.get(timeout=10) for _ in procs]
                hold_event.set()
                for p in procs:
                    p.join(timeout=10)
                winners = [r for r in results if r[1]]
                self.assertEqual(len(winners), 1, f"round {round_idx}: {results}")

    def test_release_then_fresh_contender_can_acquire(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = os.path.join(tmp, "test.lock")
            first = CrossProcessLock(lock_path)
            self.assertTrue(first.acquire())
            first.release()
            second = CrossProcessLock(lock_path)
            self.assertTrue(second.acquire())
            second.release()

    def test_idempotent_release_no_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = os.path.join(tmp, "test.lock")
            lock = CrossProcessLock(lock_path)
            self.assertTrue(lock.acquire())
            lock.release()
            lock.release()

    def test_release_after_directory_removed_does_not_raise(self):
        tmp = tempfile.mkdtemp()
        lock_path = os.path.join(tmp, "test.lock")
        lock = CrossProcessLock(lock_path)
        self.assertTrue(lock.acquire())
        import shutil
        shutil.rmtree(tmp)
        lock.release()


# ---------------------------------------------------------------------------
# RebuildQueue and SafeWriter basic behavior
# ---------------------------------------------------------------------------

class RebuildQueueTests(unittest.TestCase):
    def test_burst_coalesces_to_one_followup(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            q = RebuildQueue(lambda: calls.append(1), os.path.join(tmp, "rebuild.lock"))
            statuses = [q.enqueue() for _ in range(5)]
            self.assertIn("accepted", statuses)
            self.assertGreaterEqual(len(calls), 1)

    def test_requires_bound_callback(self):
        with self.assertRaises(ValueError):
            RebuildQueue(None, "/tmp/whatever.lock")


class SafeWriterTests(unittest.TestCase):
    def test_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = SafeWriter(tmp)
            with self.assertRaises(ValueError):
                writer.write_text("../escape.txt", "x")

    def test_writes_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = SafeWriter(tmp)
            target = writer.write_text("out.txt", "hello")
            with open(target) as fh:
                self.assertEqual(fh.read(), "hello")


# ---------------------------------------------------------------------------
# Correction E: real synthetic end-to-end Gate A
# ---------------------------------------------------------------------------

CLEAN_CARS_UI = (
    "def gallery(update, context):\n"
    "    count = count_media(update)\n"
    "    update.message.reply_text(f'photos: {count}')\n"
    "def video_gallery(update, context):\n"
    "    count = count_media(update)\n"
    "    update.message.reply_text(f'videos: {count}')\n"
    "def diag_photo_show(update, context):\n"
    "    update.message.reply_text('diag photo text')\n"
    "def diag_video_show(update, context):\n"
    "    update.message.reply_text('diag video text')\n"
    "def count_media(update):\n"
    "    return len(update.media)\n"
    "def upload_media(path, data):\n"
    "    with open(path, 'wb') as fh:\n"
    "        fh.write(data)\n"
    "    return True\n"
    "def delete_media(path):\n"
    "    import os as _os\n"
    "    _os.remove(path)\n"
    "    return True\n"
)

CLEAN_USERCUSTOMIZE = "import sys\n\n\ndef _noop():\n    return None\n"

CLEAN_AVTOPEREDACHA = (
    "import sqlite3\n"
    "import time\n"
    "def kolonki_cars(conn):\n"
    "    cur = conn.execute('SELECT 1')\n"
    "    rows = cur.fetchall()\n"
    "    cur.close()\n"
    "    conn.close()\n"
    "    time.sleep(0)\n"
    "    return rows\n"
)

DB_FUNCTION_SOURCE = (
    "def kolonki_cars(conn):\n"
    "    cur = conn.execute('SELECT 1')\n"
    "    rows = cur.fetchall()\n"
    "    cur.close()\n"
    "    conn.close()\n"
    "    time.sleep(0)\n"
    "    return rows\n"
)


class EndToEndGateATests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.required_input_paths = []
        for name in ["usercustomize.py", "start_safe.py", "run_all.py", "cars_ui.py",
                     "avtoperedacha.py", "samokontrol.py", "db.py", "team_bot.py", "stranica.py"]:
            p = os.path.join(self.tmp.name, name)
            with open(p, "w") as fh:
                fh.write("# fixture\n")
            self.required_input_paths.append(p)

        self.db_path = os.path.join(self.tmp.name, "crm.db")
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.commit()
        conn.close()
        self.required_input_paths.append(self.db_path)

        self.backup_archive = os.path.join(self.tmp.name, "backup.tar.gz")
        with open(self.backup_archive, "wb") as fh:
            fh.write(b"fixture-backup-bytes")
        self.backup_sha256 = gate_a._sha256_file(self.backup_archive)

        self.site_root = os.path.join(self.tmp.name, "site")
        os.makedirs(self.site_root)
        with open(os.path.join(self.site_root, "index.html"), "w") as fh:
            fh.write("<html></html>")
        with open(os.path.join(self.site_root, "katalog.html"), "w") as fh:
            fh.write("<html></html>")

        self.run_dir = os.path.join(self.tmp.name, "run")

        fp = {"a": 1}
        self.fixture = {
            "required_inputs": self.required_input_paths,
            "backup_archive": self.backup_archive,
            "backup_archive_sha256": self.backup_sha256,
            "cars_ui_source": CLEAN_CARS_UI,
            "usercustomize_source": CLEAN_USERCUSTOMIZE,
            "avtoperedacha_source": CLEAN_AVTOPEREDACHA,
            "protected_fingerprints_before": fp,
            "protected_fingerprints_after": dict(fp),
            "db_path": self.db_path,
            "ua0009_fingerprint_before": {"h": "same"},
            "ua0009_fingerprint_after": {"h": "same"},
            "ua0009_url": "https://example.com/UA-0009.html",
            "ua0009_opener": _FakeOpener(raise_exc=urllib.error.HTTPError("u", 404, "nf", {}, None)),
            "site_root": self.site_root,
            "allowed_site_names": ["index.html", "katalog.html"],
            "protected_function_names": ["upload_media", "delete_media"],
            "tmp_dir": self.tmp.name,
            "db_function_source": DB_FUNCTION_SOURCE,
            "site_before": {"x": 1},
            "site_after": {"x": 1},
            "run_dir": self.run_dir,
        }

    def test_clean_fixture_reaches_pass_awaiting_approval(self):
        receipt = run_gate_a(self.fixture)
        self.assertEqual(receipt["status"], "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", receipt["unmet_predicates"])
        self.assertEqual(receipt["unmet_predicates"], [])
        self.assertEqual(receipt["production_write"], "NO")
        self.assertTrue(os.path.exists(os.path.join(self.run_dir, "receipt.json")))

    def test_backup_hash_mismatch_blocks(self):
        bad = dict(self.fixture)
        bad["backup_archive_sha256"] = "0" * 64
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("backup_verified", receipt["unmet_predicates"])

    def test_protected_fingerprint_change_blocks(self):
        bad = dict(self.fixture)
        bad["protected_fingerprints_after"] = {"a": 2}
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("protected_fingerprints_unchanged", receipt["unmet_predicates"])
        self.assertIn("no_production_write", receipt["unmet_predicates"])

    def test_publication_probe_200_blocks(self):
        bad = dict(self.fixture)
        bad["ua0009_opener"] = _FakeOpener(response_code=200)
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("ua0009_not_public", receipt["unmet_predicates"])

    def test_dynamic_dispatch_in_cars_ui_blocks(self):
        bad = dict(self.fixture)
        bad["cars_ui_source"] = (
            "def gallery(update, context):\n"
            "    fn = getattr(update.message, 'reply_photo')\n"
            "    fn()\n"
            "def video_gallery(update, context): pass\n"
            "def diag_photo_show(update, context): pass\n"
            "def diag_video_show(update, context): pass\n"
            "def upload_media(path, data): return True\n"
            "def delete_media(path): return True\n"
        )
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("admin_routes_text_only", receipt["unmet_predicates"])

    def test_usercustomize_forbidden_import_blocks(self):
        bad = dict(self.fixture)
        bad["usercustomize_source"] = "import team_bot\n"
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("usercustomize_inert", receipt["unmet_predicates"])

    def test_rebuild_subprocess_blocks(self):
        bad = dict(self.fixture)
        bad["avtoperedacha_source"] = "import subprocess\ndef run():\n    subprocess.Popen(['x'])\n"
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("rebuild_queue_bound_no_process_spawn", receipt["unmet_predicates"])

    def test_slow_work_before_close_blocks(self):
        bad = dict(self.fixture)
        bad["db_function_source"] = (
            "def kolonki_cars(conn):\n"
            "    cur = conn.execute('SELECT 1')\n"
            "    time.sleep(0)\n"
            "    rows = cur.fetchall()\n"
            "    cur.close()\n"
            "    conn.close()\n"
            "    return rows\n"
        )
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("db_closed_before_slow_work", receipt["unmet_predicates"])

    def test_site_inventory_overflow_blocks(self):
        bad = dict(self.fixture)
        bad["allowed_site_names"] = ["index.html", "katalog.html"]
        bad["max_files_per_root"] = 1
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("site_inventory_unchanged", receipt["unmet_predicates"])

    def test_media_persistence_function_removed_blocks(self):
        bad = dict(self.fixture)
        bad["cars_ui_source"] = CLEAN_CARS_UI.replace(
            "def delete_media(path):\n    import os as _os\n    _os.remove(path)\n    return True\n", "")
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("media_persistence_unchanged", receipt["unmet_predicates"])

    def test_missing_input_blocks(self):
        bad = dict(self.fixture)
        bad["required_inputs"] = self.required_input_paths + [os.path.join(self.tmp.name, "missing.py")]
        receipt = run_gate_a(bad)
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("inputs_present_and_regular", receipt["unmet_predicates"])


if __name__ == "__main__":
    unittest.main()


<END_TEST_CRM_SPEED_GATE_A_PY>
