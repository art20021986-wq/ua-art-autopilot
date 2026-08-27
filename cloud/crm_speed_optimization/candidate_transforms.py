"""
TASK 046 (CRM-SPEED-001 split closure A) - rebuild AST transformer.

Scope: fix candidate_transforms.transform_avtoperedacha_rebuild only.
Root cause fixed vs TASK 041 controller evidence: the previous transformer
rewrote only Expr(Call) trigger sites, so "return generate_x()" fixtures
survived untouched and self-blocked. This version is parent-aware: every
direct generator call and every alias-resolved related subprocess spawn is
classified by its immediate syntactic context BEFORE any mutation, and only
two supported shapes are rewritten: standalone Expr(Call) and exact
Return(Call). Anything else blocks rather than guesses.

IMPORTANT BASELINE-ACCESS DISCLOSURE (read before trusting "preserved"
claims): this bounded continuation task did not provide the literal current
main-branch file content inside the assistant context. This file is a
clean-room reconstruction of the documented public contract
(transform_avtoperedacha_rebuild) written strictly from the TASK 046 (and
inherited TASK 038/041) specification text. No unrelated main-branch
implementation sections could be copied verbatim because they were not
visible to the author. The controller must diff this file against the real
main branch before treating any "preserve all public APIs" claim as
satisfied at the byte level; the *behavioral* contract described in TASK 046
is implemented and covered by cloud/crm_speed_optimization/test_task_046_ast_sqlite.py.

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO
"""

import ast

SPAWN_FUNCS = {"Popen", "run", "call", "check_call", "check_output"}


class TransformBlocked(Exception):
    """Raised internally when a transform must not proceed."""


def _iter_child_parent(tree):
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _resolve_literal(node, aliases):
    """Resolve an AST node to a literal python value, or None if uncertain."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in aliases:
        return aliases[node.id]
    if isinstance(node, (ast.List, ast.Tuple)):
        parts = []
        for elt in node.elts:
            value = _resolve_literal(elt, aliases)
            if value is None:
                return None
            parts.append(value)
        return parts
    return None


def _collect_alias_literals(tree):
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                aliases[node.targets[0].id] = node.value.value
    return aliases


def _is_subprocess_call(call):
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in SPAWN_FUNCS:
        return True
    if isinstance(func, ast.Name) and func.id in SPAWN_FUNCS:
        return True
    return False


def _classify_context(call_node, parents):
    parent = parents.get(call_node)
    if isinstance(parent, ast.Expr):
        return ("expr", parent)
    if isinstance(parent, ast.Return):
        return ("return", parent)
    return ("unsupported", parent)


def _body_contains(container_node, target_node):
    for node in ast.walk(container_node):
        if node is target_node:
            return True
    return False


def transform_avtoperedacha_rebuild(source, lock_path="/tmp/rebuild.lock"):
    """
    Parent-aware AST transform that rewrites supported in-process rebuild
    generator calls and related subprocess spawns into RebuildQueue.enqueue()
    calls, inserting exactly one RebuildQueue instantiation after the
    generator definition.

    Returns:
      {"status": "OK", "code": <str>} on success
      {"status": "BLOCKED", "reason": <str>} on any ambiguity or unsupported shape
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {"status": "BLOCKED", "reason": "syntax_error: %s" % exc}

    parents = _iter_child_parent(tree)
    aliases = _collect_alias_literals(tree)

    generator_defs = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            a = node.args
            if not a.args and not a.vararg and not a.kwonlyargs and not a.kwarg and not a.posonlyargs:
                generator_defs.append(node)

    if not generator_defs:
        return {"status": "BLOCKED", "reason": "no_zero_arg_generator_candidate"}

    real_candidates = []
    for gdef in generator_defs:
        name = gdef.name
        direct_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name:
                if _body_contains(gdef, node):
                    continue
                direct_calls.append(node)
        if direct_calls:
            real_candidates.append((gdef, direct_calls))

    if len(real_candidates) == 0:
        return {"status": "BLOCKED", "reason": "no_direct_call_to_any_generator"}
    if len(real_candidates) > 1:
        return {"status": "BLOCKED", "reason": "ambiguous_multiple_generator_candidates"}

    gdef, direct_calls = real_candidates[0]
    gname = gdef.name

    for node in ast.walk(gdef):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == gname:
            return {"status": "BLOCKED", "reason": "recursive_or_dynamic_dispatch_generator"}

    related_spawns = []
    unrelated_spawns = []
    dynamic_spawns = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_subprocess_call(node):
            if not node.args:
                dynamic_spawns.append(node)
                continue
            resolved = _resolve_literal(node.args[0], aliases)
            if resolved is None:
                dynamic_spawns.append(node)
                continue
            flat = resolved if isinstance(resolved, list) else [resolved]
            if any(isinstance(p, str) and "stranica.py" in p for p in flat):
                related_spawns.append(node)
            else:
                unrelated_spawns.append(node)

    if dynamic_spawns and not related_spawns:
        return {"status": "BLOCKED", "reason": "dynamic_or_ambiguous_command_construction"}

    if len(related_spawns) == 0:
        return {"status": "BLOCKED", "reason": "no_related_spawn_found"}

    all_call_sites = list(direct_calls) + list(related_spawns)
    classified = []
    for call in all_call_sites:
        kind, parent = _classify_context(call, parents)
        if kind == "unsupported":
            return {"status": "BLOCKED", "reason": "unsupported_call_context"}
        classified.append((call, kind, parent))

    expr_calls = [c for c, k, p in classified if k == "expr"]
    return_calls = [c for c, k, p in classified if k == "return"]

    queue_name = "_queue"

    class Rewriter(ast.NodeTransformer):
        def visit_FunctionDef(self, node):
            if node is gdef:
                return node
            self.generic_visit(node)
            return node

        def visit_Expr(self, node):
            if isinstance(node.value, ast.Call) and node.value in expr_calls:
                new_call = ast.Call(
                    func=ast.Attribute(value=ast.Name(id=queue_name, ctx=ast.Load()), attr="enqueue", ctx=ast.Load()),
                    args=[],
                    keywords=[],
                )
                ast.copy_location(new_call, node.value)
                node.value = new_call
                return node
            self.generic_visit(node)
            return node

        def visit_Return(self, node):
            if isinstance(node.value, ast.Call) and node.value in return_calls:
                new_call = ast.Call(
                    func=ast.Attribute(value=ast.Name(id=queue_name, ctx=ast.Load()), attr="enqueue", ctx=ast.Load()),
                    args=[],
                    keywords=[],
                )
                ast.copy_location(new_call, node.value)
                node.value = new_call
                return node
            return node

    new_tree = Rewriter().visit(tree)
    ast.fix_missing_locations(new_tree)

    queue_assign = ast.Assign(
        targets=[ast.Name(id=queue_name, ctx=ast.Store())],
        value=ast.Call(
            func=ast.Name(id="RebuildQueue", ctx=ast.Load()),
            args=[ast.Name(id=gname, ctx=ast.Load()), ast.Constant(value=lock_path)],
            keywords=[],
        ),
    )
    ast.fix_missing_locations(queue_assign)

    new_body = []
    inserted = False
    for node in new_tree.body:
        new_body.append(node)
        if node is gdef and not inserted:
            new_body.append(queue_assign)
            inserted = True
    new_tree.body = new_body

    still_used_as_attr = any(
        isinstance(n, ast.Attribute) and n.attr in SPAWN_FUNCS for n in ast.walk(new_tree)
    )
    still_used_as_name = any(
        isinstance(n, ast.Name) and n.id in SPAWN_FUNCS for n in ast.walk(new_tree)
    )
    if not still_used_as_attr and not still_used_as_name:
        filtered = []
        for node in new_tree.body:
            if isinstance(node, ast.Import) and all(a.name == "subprocess" for a in node.names):
                continue
            filtered.append(node)
        new_tree.body = filtered

    remaining_direct = [
        n for n in ast.walk(new_tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == gname
        and not _body_contains(gdef, n)
    ]
    if remaining_direct:
        return {"status": "BLOCKED", "reason": "post_transform_direct_call_remains"}

    remaining_related = []
    for n in ast.walk(new_tree):
        if isinstance(n, ast.Call) and _is_subprocess_call(n):
            if not n.args:
                continue
            resolved = _resolve_literal(n.args[0], aliases)
            if resolved is None:
                continue
            flat = resolved if isinstance(resolved, list) else [resolved]
            if any(isinstance(p, str) and "stranica.py" in p for p in flat):
                remaining_related.append(n)
    if remaining_related:
        return {"status": "BLOCKED", "reason": "post_transform_spawn_call_remains"}

    queue_assigns = [
        n for n in ast.walk(new_tree)
        if isinstance(n, ast.Assign) and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Name) and n.targets[0].id == queue_name
    ]
    if len(queue_assigns) != 1:
        return {"status": "BLOCKED", "reason": "post_transform_queue_assign_count_invalid"}

    qa = queue_assigns[0]
    if not (isinstance(qa.value, ast.Call) and isinstance(qa.value.func, ast.Name) and qa.value.func.id == "RebuildQueue"):
        return {"status": "BLOCKED", "reason": "post_transform_queue_shape_invalid"}
    first_arg = qa.value.args[0]
    if not (isinstance(first_arg, ast.Name) and first_arg.id == gname):
        return {"status": "BLOCKED", "reason": "post_transform_callback_not_function_object"}

    for node in new_tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Attribute) and call.func.attr == "enqueue":
                return {"status": "BLOCKED", "reason": "module_level_enqueue_execution"}
            if isinstance(call.func, ast.Name) and call.func.id == gname:
                return {"status": "BLOCKED", "reason": "module_level_callback_execution"}

    try:
        code = ast.unparse(new_tree)
    except AttributeError:
        return {"status": "BLOCKED", "reason": "ast_unparse_unavailable"}

    try:
        compile(code, "<rebuild_transform>", "exec")
    except SyntaxError as exc:
        return {"status": "BLOCKED", "reason": "post_transform_compile_error: %s" % exc}

    return {"status": "OK", "code": code}
