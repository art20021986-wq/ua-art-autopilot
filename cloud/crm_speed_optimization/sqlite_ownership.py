"""
TASK 046 (CRM-SPEED-001 split closure A) - SQLite exact-ownership transform.

Scope: Section 1 only (exact-ownership close/exception-safety rewrite).
Root cause fixed vs TASK 041 controller evidence: cursor discovery previously
recognized only "cur = conn.cursor()"; "cur = conn.execute(<literal SQL>)"
escaped detection so its close was never generated and its escape (e.g.
"return cur") was never rejected. This version recognizes both forms as the
same owned-cursor pattern and rejects escape identically for both.

IMPORTANT BASELINE-ACCESS DISCLOSURE: the literal current main-branch content
of this file (including the separate canonical read-only UA-0009 evidence
API) was not present in the assistant context for this bounded continuation.
Only Section 1 (exact-ownership transform) is implemented here as a
clean-room reconstruction from the TASK 046 specification. The controller
must merge this Section 1 implementation into the real main-branch file,
verifying byte-for-byte that Section 2 (the UA-0009 evidence API) and any
other unrelated implementation sections are carried over unmodified. This
file intentionally does not fabricate placeholder Section 2 content because
doing so could mislead an auditor into believing real UA-0009 evidence code
was preserved when it was not visible to the author.

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO
"""

import ast

WRITE_KEYWORDS = ("insert", "update", "delete", "create", "drop", "alter", "replace")
COMMIT_ATTRS = ("commit", "rollback")


class OwnershipBlocked(Exception):
    """Raised internally when the ownership segment cannot be safely rewritten."""


def _sql_literal(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_write_sql(sql):
    s = sql.strip().lower()
    if any(s.startswith(k) for k in WRITE_KEYWORDS):
        return True
    if s.startswith("pragma") and "=" in s:
        return True
    return False


def _find_ownership_segment(func_node):
    for stmt in func_node.body:
        if isinstance(stmt, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.AsyncFor, ast.AsyncWith)):
            raise OwnershipBlocked("branch_loop_try_with_in_segment")

    conn_name = None
    connect_idx = None
    connect_count = 0

    for idx, stmt in enumerate(func_node.body):
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            value = stmt.value
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr == "connect":
                connect_count += 1
                conn_name = stmt.targets[0].id
                connect_idx = idx

    if connect_count == 0:
        raise OwnershipBlocked("no_local_connection")
    if connect_count > 1:
        raise OwnershipBlocked("multiple_connections")

    cur_name = None
    cursor_count = 0
    for stmt in func_node.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            value = stmt.value
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) \
                    and isinstance(value.func.value, ast.Name) and value.func.value.id == conn_name:
                if value.func.attr == "cursor":
                    cursor_count += 1
                    cur_name = stmt.targets[0].id
                elif value.func.attr == "execute":
                    sql = _sql_literal(value.args[0]) if value.args else None
                    if sql is None:
                        raise OwnershipBlocked("nonliteral_or_uncertain_sql")
                    if _is_write_sql(sql):
                        raise OwnershipBlocked("write_detected_in_ownership_segment")
                    cursor_count += 1
                    cur_name = stmt.targets[0].id

    if cursor_count > 1:
        raise OwnershipBlocked("multiple_cursors")

    tracked = {conn_name}
    if cur_name:
        tracked.add(cur_name)

    for stmt in func_node.body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "execute" \
                    and isinstance(node.func.value, ast.Name) and node.func.value.id in tracked:
                sql = _sql_literal(node.args[0]) if node.args else None
                if sql is None:
                    raise OwnershipBlocked("nonliteral_or_uncertain_sql")
                if _is_write_sql(sql):
                    raise OwnershipBlocked("write_detected_in_ownership_segment")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in COMMIT_ATTRS \
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == conn_name:
                raise OwnershipBlocked("commit_or_rollback_present")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "sleep":
                raise OwnershipBlocked("slow_work_while_handle_open")

    for stmt in func_node.body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Name) and node.value.id in tracked:
                raise OwnershipBlocked("escape_via_return")
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name) and node.value.id in tracked:
                ok_targets = {conn_name, cur_name} if cur_name else {conn_name}
                if not (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                        and node.targets[0].id in ok_targets):
                    raise OwnershipBlocked("escape_via_alias")
            if isinstance(node, ast.FunctionDef):
                for inner in ast.walk(node):
                    if isinstance(inner, ast.Name) and inner.id in tracked:
                        raise OwnershipBlocked("escape_via_closure")

    for stmt in func_node.body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call):
                for arg in list(node.args) + [kw.value for kw in node.keywords]:
                    if isinstance(arg, ast.Name) and arg.id in tracked:
                        is_self_method = isinstance(node.func, ast.Attribute) \
                            and isinstance(node.func.value, ast.Name) and node.func.value.id in tracked
                        if not is_self_method:
                            raise OwnershipBlocked("escape_via_argument_pass")

    return {"conn_name": conn_name, "cur_name": cur_name, "connect_idx": connect_idx}


def _is_close_call(stmt, conn_name, cur_name):
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        call = stmt.value
        if isinstance(call.func, ast.Attribute) and call.func.attr == "close":
            if isinstance(call.func.value, ast.Name) and call.func.value.id in (conn_name, cur_name):
                return True
    return False


def _materialize_fetch_calls(body, cur_name):
    for stmt in body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) \
                    and isinstance(node.value.func, ast.Attribute) \
                    and node.value.func.attr in ("fetchall", "fetchmany") \
                    and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == cur_name:
                original_call = node.value
                node.value = ast.Call(
                    func=ast.Name(id="tuple", ctx=ast.Load()),
                    args=[ast.GeneratorExp(
                        elt=ast.Call(
                            func=ast.Name(id="tuple", ctx=ast.Load()),
                            args=[ast.Name(id="__row", ctx=ast.Load())],
                            keywords=[],
                        ),
                        generators=[ast.comprehension(
                            target=ast.Name(id="__row", ctx=ast.Store()),
                            iter=original_call,
                            ifs=[],
                            is_async=0,
                        )],
                    )],
                    keywords=[],
                )


def _rewrite_function(func_node, segment):
    conn_name = segment["conn_name"]
    cur_name = segment["cur_name"]
    connect_idx = segment["connect_idx"]

    body = func_node.body
    connect_stmt = body[connect_idx]
    call = connect_stmt.value
    if not any(kw.arg == "timeout" for kw in call.keywords):
        call.keywords.append(ast.keyword(arg="timeout", value=ast.Constant(value=2)))

    _materialize_fetch_calls(body, cur_name)

    wrapped = [stmt for stmt in body if not _is_close_call(stmt, conn_name, cur_name)]

    init_stmts = [ast.Assign(targets=[ast.Name(id=conn_name, ctx=ast.Store())], value=ast.Constant(value=None))]
    if cur_name:
        init_stmts.append(ast.Assign(targets=[ast.Name(id=cur_name, ctx=ast.Store())], value=ast.Constant(value=None)))

    finally_stmts = []
    if cur_name:
        finally_stmts.append(ast.If(
            test=ast.Compare(left=ast.Name(id=cur_name, ctx=ast.Load()), ops=[ast.IsNot()],
                              comparators=[ast.Constant(value=None)]),
            body=[ast.Expr(value=ast.Call(
                func=ast.Attribute(value=ast.Name(id=cur_name, ctx=ast.Load()), attr="close", ctx=ast.Load()),
                args=[], keywords=[]))],
            orelse=[],
        ))
    finally_stmts.append(ast.If(
        test=ast.Compare(left=ast.Name(id=conn_name, ctx=ast.Load()), ops=[ast.IsNot()],
                          comparators=[ast.Constant(value=None)]),
        body=[ast.Expr(value=ast.Call(
            func=ast.Attribute(value=ast.Name(id=conn_name, ctx=ast.Load()), attr="close", ctx=ast.Load()),
            args=[], keywords=[]))],
        orelse=[],
    ))

    try_node = ast.Try(body=wrapped, handlers=[], orelse=[], finalbody=finally_stmts)
    func_node.body = init_stmts + [try_node]
    ast.fix_missing_locations(func_node)


def _verify_transformed_function(func_node, segment):
    conn_name = segment["conn_name"]
    cur_name = segment["cur_name"]

    tries = [n for n in func_node.body if isinstance(n, ast.Try)]
    if len(tries) != 1:
        raise OwnershipBlocked("verifier_try_count_invalid")
    try_node = tries[0]
    finally_body = try_node.finalbody

    expected_len = 2 if cur_name else 1
    if len(finally_body) != expected_len:
        raise OwnershipBlocked("verifier_finally_shape_invalid")

    close_order = []
    for stmt in finally_body:
        if isinstance(stmt, ast.If) and isinstance(stmt.test, ast.Compare) and isinstance(stmt.test.left, ast.Name):
            close_order.append(stmt.test.left.id)

    expected_order = [cur_name, conn_name] if cur_name else [conn_name]
    if close_order != expected_order:
        raise OwnershipBlocked("verifier_close_order_invalid")

    connect_calls = [
        n for n in ast.walk(func_node)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "connect"
    ]
    for c in connect_calls:
        timeout_kwargs = [kw for kw in c.keywords if kw.arg == "timeout"]
        if len(timeout_kwargs) != 1:
            raise OwnershipBlocked("verifier_timeout_invalid")

    return True


def transform_sqlite_ownership(source):
    """
    Rewrite exactly-owned local sqlite3 connection/cursor segments so that
    both handles are guaranteed closed (cursor first, then connection) on
    every success and exception path, with timeout=2 applied exactly once
    and fetched rows materialized as immutable tuples-of-tuples before close.

    Returns:
      {"status": "OK", "code": <str>} on success
      {"status": "BLOCKED", "reason": <str>} on any unsafe or ambiguous shape
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {"status": "BLOCKED", "reason": "syntax_error: %s" % exc}

    changed_any = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            has_connect = any(
                isinstance(s, ast.Assign) and isinstance(s.value, ast.Call)
                and isinstance(s.value.func, ast.Attribute) and s.value.func.attr == "connect"
                for s in node.body
            )
            if not has_connect:
                continue
            try:
                segment = _find_ownership_segment(node)
                _rewrite_function(node, segment)
                _verify_transformed_function(node, segment)
            except OwnershipBlocked as exc:
                return {"status": "BLOCKED", "reason": str(exc)}
            changed_any = True

    if not changed_any:
        return {"status": "BLOCKED", "reason": "no_ownership_pattern_found"}

    ast.fix_missing_locations(tree)
    try:
        code = ast.unparse(tree)
    except AttributeError:
        return {"status": "BLOCKED", "reason": "ast_unparse_unavailable"}

    try:
        compile(code, "<sqlite_ownership_transform>", "exec")
    except SyntaxError as exc:
        return {"status": "BLOCKED", "reason": "post_transform_compile_error: %s" % exc}

    return {"status": "OK", "code": code}
