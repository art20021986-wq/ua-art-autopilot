# TASK 029 — CRM-SPEED-001 integrate canonical media transformer with full sources

## Owner authorization and safety

Continue the approved CRM-SPEED-001 repair. This is the unblocked continuation of TASK 028. Work only under cloud/. Do not execute Gate A or modify Production, CRM, database, bot, site, media, cards, generators, WSGI, processes, or UA-0009.

## Required result

Use the exact source snapshots embedded below from commit 1cec53a47cc5282e2b8ff5f0549fcd050ed04804. Make cars_ui_transform.py the only canonical admin-media transform and make crm_speed_gate_a.py / RUN_GATE_A_CRM_SPEED.py / both test suites use that implementation.

Mandatory:
- remove or replace the duplicate legacy transformer/scanner in crm_speed_gate_a.py with thin adapters around cars_ui_transform;
- preserve the established transform_cars_ui(source, entry_points=None) result API: status, candidate, reasons list;
- preserve all 65 discovered test semantics; the prior executed result was 63 PASS, 2 FAIL only because canonical integration was missing;
- ensure end-to-end Gate A and deterministic-repeat paths use the canonical implementation;
- add identity and monkeypatch integration tests;
- run target command for controller discovery: python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py';
- final Claude status READY_FOR_CONTROLLER_REVIEW or BLOCKED only.

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO


## BEGIN EXACT SOURCE: cloud/crm_speed_optimization/cars_ui_transform.py

```python
'''
CRM-SPEED-001 admin-media transform utilities.

Rewrites direct Telegram media-send calls (reply_photo, reply_video,
send_photo, send_video, reply_document, send_document,
reply_media_group, send_media_group) that are structurally direct and
reachable only from the fixed admin "cars UI" entry routes into
lightweight text-only replies.

Correction applied under TASK 027 (root cause from controller run on
commit 6e0ddb846f88eb4d36d0df36b69ed7f8b4fc437e):

The previous pre-scan descended into the argument subtree of an
already-recognized direct media-send call and separately reported the
media arguments (for example open('x.jpg','rb')) as an
unresolved_callable, which made transform_cars_ui BLOCK before the
whole media-send expression could be atomically replaced. This module
now treats a structurally direct media-send call as a single atomic
unit: its target/callee shape is inspected and blocked if dynamic, but
calls strictly inside its own argument subtree are not treated as
independently reachable runtime once the whole expression is replaced,
unless they are not on the small safe-to-drop allowlist
(open/download/thumbnail), in which case the whole call is left
unrewritten and blocked to avoid silently discarding side effects.

Any open()/download() call located outside such a removed expression is
still treated as a normal unresolved call and still blocks, exactly as
before this correction.
'''

import ast
import copy
import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

MEDIA_METHODS = {
    'reply_photo',
    'reply_video',
    'send_photo',
    'send_video',
    'reply_document',
    'send_document',
    'reply_media_group',
    'send_media_group',
}

_TEXT_METHOD_MAP = {
    'reply_photo': 'reply_text',
    'reply_video': 'reply_text',
    'reply_document': 'reply_text',
    'reply_media_group': 'reply_text',
    'send_photo': 'send_message',
    'send_video': 'send_message',
    'send_document': 'send_message',
    'send_media_group': 'send_message',
}

_MEDIA_KIND = {
    'reply_photo': 'photo',
    'send_photo': 'photo',
    'reply_video': 'video',
    'send_video': 'video',
    'reply_document': 'document',
    'send_document': 'document',
    'reply_media_group': 'media group',
    'send_media_group': 'media group',
}

_SAFE_ARG_CALL_PATTERNS = ('open', 'download', 'thumbnail')

DEFAULT_ADMIN_ENTRY_ROUTES = (
    'admin_car_view',
    'admin_car_list',
    'admin_car_edit',
    'admin_car_delete',
)


@dataclass
class MediaCallInfo:
    func_name: str
    node: ast.Call
    stmt: ast.stmt
    method: str
    is_await: bool
    lineno: int


@dataclass
class ScanResult:
    call_graph: Dict[str, Set[str]]
    reverse_callers: Dict[str, Set[str]]
    reachable: Set[str]
    direct_media_calls: Dict[str, List[MediaCallInfo]]
    unresolved_dynamic: Dict[str, List[str]]
    functions: Dict[str, ast.AST]


def _is_static_receiver(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return True
    if isinstance(node, ast.Attribute):
        return _is_static_receiver(node.value)
    return False


def _is_direct_attribute_call(node: ast.Call) -> Optional[str]:
    func = node.func
    if isinstance(func, ast.Attribute) and _is_static_receiver(func.value):
        return func.attr
    return None


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return '<unknown>'


def _is_safe_media_arg_call(node: ast.Call) -> bool:
    name = _call_name(node).lower()
    return any(pattern in name for pattern in _SAFE_ARG_CALL_PATTERNS)


def _find_unsafe_arg_calls(call_node: ast.Call) -> List[str]:
    unsafe = []
    exprs = list(call_node.args) + [kw.value for kw in call_node.keywords]
    for expr in exprs:
        for sub in ast.walk(expr):
            if isinstance(sub, ast.Call) and not _is_safe_media_arg_call(sub):
                unsafe.append(_call_name(sub))
    return unsafe


class _FunctionAnalyzer(ast.NodeVisitor):
    def __init__(self, func_name: str, module_func_names: Set[str]):
        self.func_name = func_name
        self.module_func_names = module_func_names
        self.callees: Set[str] = set()
        self.direct_media_calls: List[MediaCallInfo] = []
        self.dynamic_flags: List[str] = []
        self._consumed_attrs: Set[int] = set()

    def visit_Expr(self, node: ast.Expr):
        value = node.value
        is_await = False
        call_node = value
        if isinstance(value, ast.Await):
            is_await = True
            call_node = value.value
        if isinstance(call_node, ast.Call):
            method = _is_direct_attribute_call(call_node)
            if method in MEDIA_METHODS:
                unsafe = _find_unsafe_arg_calls(call_node)
                if unsafe:
                    self.dynamic_flags.append(
                        'unsafe_media_argument_side_effect:%s:line%s'
                        % (','.join(unsafe), node.lineno)
                    )
                    self.generic_visit(node)
                    return
                self.direct_media_calls.append(
                    MediaCallInfo(
                        func_name=self.func_name,
                        node=call_node,
                        stmt=node,
                        method=method,
                        is_await=is_await,
                        lineno=node.lineno,
                    )
                )
                return
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            if func.id == 'getattr':
                self.dynamic_flags.append('getattr_dispatch:line%s' % node.lineno)
            elif func.id in self.module_func_names:
                self.callees.add(func.id)
            else:
                self.dynamic_flags.append(
                    'unresolved_callable:%s:line%s' % (func.id, node.lineno)
                )
        elif isinstance(func, ast.Attribute):
            self._consumed_attrs.add(id(func))
            if _is_static_receiver(func.value):
                if func.attr in MEDIA_METHODS:
                    self.dynamic_flags.append(
                        'non_atomic_media_use:%s:line%s' % (func.attr, node.lineno)
                    )
            else:
                self.dynamic_flags.append(
                    'dynamic_attribute_receiver:line%s' % node.lineno
                )
        elif isinstance(func, ast.Subscript):
            self.dynamic_flags.append('subscript_dispatch:line%s' % node.lineno)
        elif isinstance(func, ast.Call):
            self.dynamic_flags.append('computed_call_target:line%s' % node.lineno)
        elif isinstance(func, ast.Lambda):
            self.dynamic_flags.append('lambda_dispatch:line%s' % node.lineno)

        self.visit(func)
        for arg in node.args:
            self.visit(arg)
        for kw in node.keywords:
            self.visit(kw.value)

    def visit_Attribute(self, node: ast.Attribute):
        if id(node) not in self._consumed_attrs and node.attr in MEDIA_METHODS:
            self.dynamic_flags.append(
                'attribute_alias_reference:%s:line%s' % (node.attr, node.lineno)
            )
        self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda):
        self.dynamic_flags.append('lambda_present:line%s' % node.lineno)
        self.generic_visit(node)


def scan_reachable_call_graph(tree: ast.AST, entry_points) -> ScanResult:
    module_funcs: Dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module_funcs[node.name] = node
    module_func_names = set(module_funcs.keys())

    call_graph: Dict[str, Set[str]] = {}
    direct_media_calls: Dict[str, List[MediaCallInfo]] = {}
    dynamic_flags: Dict[str, List[str]] = {}

    for name, fn in module_funcs.items():
        analyzer = _FunctionAnalyzer(name, module_func_names)
        for stmt in fn.body:
            analyzer.visit(stmt)
        call_graph[name] = analyzer.callees
        direct_media_calls[name] = analyzer.direct_media_calls
        dynamic_flags[name] = analyzer.dynamic_flags

    reverse_callers: Dict[str, Set[str]] = {name: set() for name in module_func_names}
    for caller, callees in call_graph.items():
        for callee in callees:
            if callee in reverse_callers:
                reverse_callers[callee].add(caller)

    reachable: Set[str] = set()
    frontier = [e for e in entry_points if e in module_func_names]
    reachable.update(frontier)
    while frontier:
        nxt = []
        for f in frontier:
            for callee in call_graph.get(f, ()):
                if callee not in reachable:
                    reachable.add(callee)
                    nxt.append(callee)
        frontier = nxt

    return ScanResult(
        call_graph=call_graph,
        reverse_callers=reverse_callers,
        reachable=reachable,
        direct_media_calls=direct_media_calls,
        unresolved_dynamic=dynamic_flags,
        functions=module_funcs,
    )


def _build_text_replacement(node: ast.Expr, call_node: ast.Call, method: str, is_await: bool) -> ast.Expr:
    kind = _MEDIA_KIND[method]
    text_method = _TEXT_METHOD_MAP[method]

    if method.endswith('media_group'):
        count = None
        for arg in call_node.args:
            if isinstance(arg, (ast.List, ast.Tuple)):
                count = len(arg.elts)
                break
        count_text = str(count) if count is not None else 'multiple'
        message_text = '[%s: %s item(s) - media send disabled in admin fast mode]' % (kind, count_text)
    else:
        message_text = '[%s - media send disabled in admin fast mode]' % kind

    new_args = []
    new_keywords = []
    if text_method == 'send_message':
        if call_node.args:
            new_args.append(call_node.args[0])
        for kw in call_node.keywords:
            if kw.arg == 'chat_id':
                new_keywords.append(kw)

    new_args.append(ast.Constant(value=message_text))

    new_call = ast.Call(
        func=ast.Attribute(
            value=copy.deepcopy(call_node.func.value),
            attr=text_method,
            ctx=ast.Load(),
        ),
        args=new_args,
        keywords=new_keywords,
    )
    value = new_call
    if is_await:
        value = ast.Await(value=new_call)
    new_expr = ast.Expr(value=value)
    ast.copy_location(new_expr, node)
    ast.fix_missing_locations(new_expr)
    return new_expr


class _MediaCallTextTransformer(ast.NodeTransformer):
    '''Replaces exactly one atomic direct media-send expression per Expr
    statement with a text-only equivalent, without evaluating original
    media arguments (open/download/thumbnail/binary operations).'''

    def visit_Expr(self, node: ast.Expr):
        value = node.value
        is_await = False
        call_node = value
        if isinstance(value, ast.Await):
            is_await = True
            call_node = value.value
        if isinstance(call_node, ast.Call):
            method = _is_direct_attribute_call(call_node)
            if method in MEDIA_METHODS and not _find_unsafe_arg_calls(call_node):
                return _build_text_replacement(node, call_node, method, is_await)
        return self.generic_visit(node)


def _apply_rewrites(tree: ast.Module, rewrite_targets: Set[str]) -> None:
    transformer = _MediaCallTextTransformer()
    new_body = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in rewrite_targets:
            node = transformer.visit(node)
        new_body.append(node)
    tree.body = new_body
    ast.fix_missing_locations(tree)


def _semantic_hash(node: ast.AST) -> str:
    dumped = ast.dump(node, annotate_fields=True, include_attributes=False)
    return hashlib.sha256(dumped.encode('utf-8')).hexdigest()


def _protected_function_hashes(tree: ast.Module, exclude_names: Set[str]) -> Dict[str, str]:
    hashes = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name not in exclude_names:
            hashes[node.name] = _semantic_hash(node)
    return hashes


def transform_cars_ui(source: str, entry_points) -> Dict[str, object]:
    entry_points = list(entry_points)
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {'status': 'BLOCKED', 'reason': 'syntax_error:%s' % exc, 'candidate': None}

    scan = scan_reachable_call_graph(tree, entry_points)

    missing = [e for e in entry_points if e not in scan.functions]
    if missing:
        return {
            'status': 'BLOCKED',
            'reason': 'missing_entry_points:%s' % sorted(missing),
            'candidate': None,
        }

    rewrite_targets: Set[str] = set()
    block_reasons: List[str] = []

    for func_name in sorted(scan.reachable):
        flags = scan.unresolved_dynamic.get(func_name, [])
        if flags:
            block_reasons.append('%s: %s' % (func_name, flags))
            continue
        media_calls = scan.direct_media_calls.get(func_name, [])
        if not media_calls:
            continue
        if func_name in entry_points:
            rewrite_targets.add(func_name)
            continue
        callers = scan.reverse_callers.get(func_name, set())
        outside_callers = callers - scan.reachable
        if outside_callers:
            block_reasons.append(
                '%s: shared_helper_called_by:%s' % (func_name, sorted(outside_callers))
            )
            continue
        rewrite_targets.add(func_name)

    if block_reasons:
        return {'status': 'BLOCKED', 'reason': '; '.join(block_reasons), 'candidate': None}

    if not rewrite_targets:
        return {
            'status': 'BLOCKED',
            'reason': 'no_direct_media_calls_found_to_rewrite',
            'candidate': None,
        }

    pre_hashes = _protected_function_hashes(tree, rewrite_targets)

    candidate_tree = copy.deepcopy(tree)
    _apply_rewrites(candidate_tree, rewrite_targets)

    post_hashes = _protected_function_hashes(candidate_tree, rewrite_targets)
    if pre_hashes != post_hashes:
        return {
            'status': 'BLOCKED',
            'reason': 'protected_function_hash_mismatch',
            'candidate': None,
        }

    try:
        candidate_src = ast.unparse(candidate_tree)
    except Exception as exc:
        return {'status': 'BLOCKED', 'reason': 'unparse_failed:%s' % exc, 'candidate': None}

    try:
        compile(candidate_src, '<candidate>', 'exec')
    except SyntaxError as exc:
        return {
            'status': 'BLOCKED',
            'reason': 'candidate_compile_failed:%s' % exc,
            'candidate': None,
        }

    post_tree = ast.parse(candidate_src)
    post_scan = scan_reachable_call_graph(post_tree, entry_points)
    for func_name in post_scan.reachable:
        if post_scan.direct_media_calls.get(func_name):
            return {
                'status': 'BLOCKED',
                'reason': 'post_transform_media_still_reachable:%s' % func_name,
                'candidate': None,
            }
        flags = post_scan.unresolved_dynamic.get(func_name)
        if flags:
            return {
                'status': 'BLOCKED',
                'reason': 'post_transform_dynamic_still_reachable:%s:%s' % (func_name, flags),
                'candidate': None,
            }

    return {
        'status': 'OK',
        'reason': 'rewritten',
        'candidate': candidate_src,
        'rewritten_functions': sorted(rewrite_targets),
    }

```

## END EXACT SOURCE: cloud/crm_speed_optimization/cars_ui_transform.py

## BEGIN EXACT SOURCE: cloud/crm_speed_optimization/crm_speed_gate_a.py

```python
"""CRM-SPEED-001 Gate A orchestration logic (round 3 corrected).

This module imports canonical mechanisms from canonical_modules.py rather
than redefining them (correction D). It implements:

- a bounded reachable call-graph scanner that fails closed on dynamic
  dispatch, aliasing, callback containers, lambdas, return-aliases, and
  unresolved callables (correction A);
- a deterministic-repeat measurement function with one explicit signature
  used identically by tests and the orchestrator (correction B);
- a bounded, non-recursive site/public inventory scanner with a
  test-only max_files_per_root parameter while production default stays 32
  (correction C);
- an evidence-driven Gate A predicate aggregator with no fabricated True
  values (round 2 correction retained) and an executable end-to-end
  orchestration function (correction E).

Gate A is never executed against production by this repository. Every
function here operates only on strings/bytes/paths explicitly supplied by
the caller (production launcher or test fixture).
"""
import os
import ast
import stat
import json
import time
import hashlib
import difflib
import sqlite3
import urllib.request
import urllib.error

from canonical_modules import CrossProcessLock, SingletonGuard, RebuildQueue, SafeWriter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_FILES_PER_ROOT = 32

ADMIN_ROUTE_NAMES = ["gallery", "video_gallery", "diag_photo_show", "diag_video_show"]

MEDIA_METHOD_NAMES = {
    "reply_photo", "reply_video", "reply_media_group", "reply_document",
    "reply_audio", "reply_voice", "reply_animation",
    "send_photo", "send_video", "send_media_group", "send_document",
    "send_audio", "send_voice", "send_animation",
    "download", "download_to_drive", "get_file",
}

DYNAMIC_DISPATCH_FORBIDDEN = {"getattr", "setattr", "eval", "exec", "globals", "locals"}

SAFE_BUILTIN_NAMES = {
    "str", "int", "float", "bool", "len", "print", "list", "dict", "set",
    "tuple", "sorted", "enumerate", "range", "isinstance", "format", "repr",
    "min", "max", "sum", "any", "all", "zip", "map", "filter",
}

ALLOWED_SITE_NAMES = (
    ["index.html", "katalog.html"]
    + [f"UA-000{n}.html" for n in range(1, 10)]
    + [f"UA-000{n}-diag.html" for n in range(1, 10)]
    + [f"UA-000{n}-track.html" for n in range(1, 10)]
)

DEFAULT_CONFIG = {
    "required_inputs": [
        "/home/Carix/.local/lib/python3.10/site-packages/usercustomize.py",
        "/home/Carix/.local/lib/python3.13/site-packages/usercustomize.py",
        "/home/Carix/start_safe.py",
        "/home/Carix/run_all.py",
        "/home/Carix/cars_ui.py",
        "/home/Carix/avtoperedacha.py",
        "/home/Carix/samokontrol.py",
        "/home/Carix/db.py",
        "/home/Carix/team_bot.py",
        "/home/Carix/stranica.py",
        "/home/Carix/crm.db",
    ],
    "site_roots": {
        "/home/Carix/site": ALLOWED_SITE_NAMES,
        "/home/Carix/video": ALLOWED_SITE_NAMES,
        "/home/Carix/public_html": ALLOWED_SITE_NAMES,
    },
    "ua0009_url": "https://ua-art-detailing.ru/UA-0009.html",
    "run_root": "/home/Carix/qa/crm_speed_task020",
    "backup_archive": "/home/Carix/backups/crm_speed_20260827_1038_before.tar.gz",
    "backup_archive_sha256": "b6e68a8382e5a6bbf0e7ffc957ac33d14c53db28b89a08cfd6e456e15a5a8913",
}

REQUIRED_PREDICATES = [
    "inputs_present_and_regular",
    "backup_verified",
    "candidates_compile",
    "protected_fingerprints_unchanged",
    "sqlite_readonly_quickcheck_ok",
    "ua0009_fingerprint_unchanged",
    "ua0009_not_public",
    "site_inventory_unchanged",
    "admin_routes_text_only",
    "media_persistence_unchanged",
    "usercustomize_inert",
    "singleton_guard_present",
    "rebuild_queue_bound_no_process_spawn",
    "db_closed_before_slow_work",
    "deterministic_repeat_all_transforms",
    "no_production_write",
]


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint_file(path):
    if not os.path.exists(path):
        return None
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode):
        return {"symlink": True}
    return {
        "mode": st.st_mode,
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "sha256": _sha256_file(path),
    }


# ---------------------------------------------------------------------------
# Correction A: bounded reachable call-graph scanner, fail closed
# ---------------------------------------------------------------------------

class _FunctionVisitor(ast.NodeVisitor):
    def __init__(self, module_functions, violations, visited_stack, max_depth, depth=0):
        self.module_functions = module_functions
        self.violations = violations
        self.visited_stack = visited_stack
        self.max_depth = max_depth
        self.depth = depth
        self.alias_media = set()

    def visit_Assign(self, node):
        if isinstance(node.value, ast.Attribute) and node.value.attr in MEDIA_METHOD_NAMES:
            for t in node.targets:
                if isinstance(t, ast.Name):
                    self.alias_media.add(t.id)
                    self.violations.append(f"bound_method_alias:{t.id}={node.value.attr}")
        if isinstance(node.value, ast.Dict):
            for v in node.value.values:
                if isinstance(v, ast.Attribute) and v.attr in MEDIA_METHOD_NAMES:
                    self.violations.append(f"callback_dict_media:{v.attr}")
        if isinstance(node.value, (ast.List, ast.Tuple)):
            for v in node.value.elts:
                if isinstance(v, ast.Attribute) and v.attr in MEDIA_METHOD_NAMES:
                    self.violations.append(f"callback_list_media:{v.attr}")
        self.generic_visit(node)

    def visit_Return(self, node):
        if isinstance(node.value, ast.Attribute) and node.value.attr in MEDIA_METHOD_NAMES:
            self.violations.append(f"return_alias_media:{node.value.attr}")
        self.generic_visit(node)

    def visit_Call(self, node):
        func = node.func
        if isinstance(func, ast.Attribute):
            if func.attr in MEDIA_METHOD_NAMES:
                self.violations.append(f"direct_media_call:{func.attr}")
        elif isinstance(func, ast.Name):
            name = func.id
            if name in DYNAMIC_DISPATCH_FORBIDDEN:
                self.violations.append(f"dynamic_dispatch_forbidden:{name}")
            elif name in self.alias_media:
                self.violations.append(f"aliased_media_call:{name}")
            elif name in self.module_functions:
                if self.depth >= self.max_depth:
                    self.violations.append(f"max_depth_exceeded:{name}")
                elif name not in self.visited_stack:
                    self.visited_stack.add(name)
                    fv = _FunctionVisitor(self.module_functions, self.violations, self.visited_stack, self.max_depth, self.depth + 1)
                    fv.visit(self.module_functions[name])
            elif name in SAFE_BUILTIN_NAMES:
                pass
            else:
                self.violations.append(f"unresolved_callable:{name}")
        elif isinstance(func, ast.Call):
            self.violations.append("chained_call_ambiguous")
        elif isinstance(func, ast.Subscript):
            self.violations.append("subscript_dispatch_ambiguous")
        self.generic_visit(node)


def scan_reachable_call_graph(source, entry_points, max_depth=25):
    """Bounded reachable call-graph scan. Returns (clean, violations).
    Ambiguous or dynamic constructs are always recorded as violations
    (fail closed); callers decide which violations are fatal."""
    tree = ast.parse(source)
    module_functions = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module_functions[node.name] = node
    violations = []
    visited_stack = set(entry_points)
    for ep in entry_points:
        fn = module_functions.get(ep)
        if fn is None:
            violations.append(f"missing_entry_point:{ep}")
            continue
        fv = _FunctionVisitor(module_functions, violations, visited_stack, max_depth, depth=0)
        fv.visit(fn)
    return (len(violations) == 0), violations


class _MediaCallTextTransformer(ast.NodeTransformer):
    def _replace(self, call_node):
        caller = call_node.func.value
        return ast.Call(
            func=ast.Attribute(value=caller, attr="reply_text", ctx=ast.Load()),
            args=[ast.Constant(value=f"[media] type={call_node.func.attr} count=1")],
            keywords=[],
        )

    def visit_Expr(self, node):
        self.generic_visit(node)
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
            if node.value.func.attr in MEDIA_METHOD_NAMES:
                return ast.Expr(value=self._replace(node.value))
        return node

    def visit_Await(self, node):
        self.generic_visit(node)
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
            if node.value.func.attr in MEDIA_METHOD_NAMES:
                return ast.Await(value=self._replace(node.value))
        return node


def generate_unified_diff(original, candidate):
    original = original or ""
    candidate = candidate or ""
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        candidate.splitlines(keepends=True),
        fromfile="original", tofile="candidate",
    )
    return "".join(diff)


def transform_cars_ui(source, entry_points=None):
    """Transform cars_ui.py admin routes to text-only. Fails closed:
    - if the ORIGINAL reachable call graph contains any dynamic/ambiguous
      construct (getattr/setattr/eval/exec/globals/locals, aliasing,
      callback containers, unresolved callables, chained/subscript
      dispatch), the candidate is None and status is BLOCKED;
    - otherwise direct media call sites are rewritten to text-only replies
      and the transformed graph is re-scanned; any remaining violation
      also yields candidate None / BLOCKED.
    """
    entry_points = entry_points or ADMIN_ROUTE_NAMES
    try:
        clean_before, violations_before = scan_reachable_call_graph(source, entry_points)
    except SyntaxError as exc:
        return {"candidate": None, "status": "BLOCKED", "reasons": [f"syntax_error:{exc}"]}

    dynamic_flags = [v for v in violations_before if not v.startswith("direct_media_call")]
    if dynamic_flags:
        return {"candidate": None, "status": "BLOCKED", "reasons": violations_before}

    if not violations_before:
        return {"candidate": source, "status": "OK", "reasons": []}

    tree = ast.parse(source)
    new_tree = _MediaCallTextTransformer().visit(tree)
    ast.fix_missing_locations(new_tree)
    try:
        candidate = ast.unparse(new_tree)
    except Exception as exc:
        return {"candidate": None, "status": "BLOCKED", "reasons": [f"unparse_error:{exc}"]}

    clean_after, violations_after = scan_reachable_call_graph(candidate, entry_points)
    if not clean_after:
        return {"candidate": None, "status": "BLOCKED", "reasons": violations_before + violations_after}
    return {"candidate": candidate, "status": "OK", "reasons": violations_before}


# ---------------------------------------------------------------------------
# Correction B: deterministic repeat, one explicit signature
# ---------------------------------------------------------------------------

def _stable_bytes(value):
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8")


def measure_deterministic_repeat(transform_fn, source, args=(), repeats=10):
    """Run transform_fn(source, *args) `repeats` times from the exact same
    original source and compare candidate bytes, unified-diff bytes,
    status, reason list, and a metadata digest across all repetitions.
    transform_fn must return a dict with keys 'candidate', 'status',
    'reasons'. Returns a dict with 'deterministic' (bool), 'repeats', and
    the full list of per-repetition records."""
    records = []
    for _ in range(repeats):
        result = transform_fn(source, *args)
        candidate = result.get("candidate")
        status = result.get("status")
        reasons = result.get("reasons", [])
        candidate_bytes = _stable_bytes(candidate)
        diff_text = generate_unified_diff(source, candidate)
        diff_bytes = diff_text.encode("utf-8")
        metadata_digest = hashlib.sha256(
            json.dumps({"status": status, "reasons": reasons}, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        records.append({
            "candidate_sha256": _sha256_bytes(candidate_bytes),
            "diff_sha256": _sha256_bytes(diff_bytes),
            "status": status,
            "reasons": reasons,
            "metadata_digest": metadata_digest,
        })
    first = records[0]
    deterministic = all(r == first for r in records)
    return {"deterministic": deterministic, "repeats": repeats, "records": records}


# ---------------------------------------------------------------------------
# Correction C: bounded site/public inventory with test-only max override
# ---------------------------------------------------------------------------

def scan_bounded_inventory(root, allowed_names, max_files_per_root=DEFAULT_MAX_FILES_PER_ROOT):
    """Non-recursive bounded scan of `root` for entries in `allowed_names`.
    Production callers must use the default max_files_per_root=32. Tests
    may pass a smaller value explicitly to construct real overflow cases
    without lowering the production default."""
    if not os.path.isdir(root):
        return {"status": "BLOCKED", "reason": "missing_root", "root": root}
    matched = []
    for name in allowed_names:
        candidate_path = os.path.join(root, name)
        if os.path.lexists(candidate_path):
            matched.append(candidate_path)
    if len(matched) > max_files_per_root:
        return {
            "status": "BLOCKED", "reason": "overflow",
            "matched_count": len(matched), "max_files_per_root": max_files_per_root,
        }
    entries = []
    for path in matched:
        st = os.lstat(path)
        if stat.S_ISLNK(st.st_mode):
            return {"status": "BLOCKED", "reason": "symlink_rejected", "path": path}
        if not stat.S_ISREG(st.st_mode):
            return {"status": "BLOCKED", "reason": "not_regular_file", "path": path}
        if st.st_nlink != 1:
            return {"status": "BLOCKED", "reason": "hard_link_rejected", "path": path}
        entries.append({
            "path": os.path.realpath(path),
            "mode": st.st_mode,
            "size": st.st_size,
            "mtime_ns": st.st_mtime_ns,
            "sha256": _sha256_file(path),
        })
    entries.sort(key=lambda e: e["path"])
    return {"status": "OK", "entries": entries, "matched_count": len(matched), "max_files_per_root": max_files_per_root}


# ---------------------------------------------------------------------------
# Publication probe -- fails closed on every network ambiguity
# ---------------------------------------------------------------------------

class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check_ua0009_not_public(url, opener=None):
    if not url or not url.startswith("https://"):
        return {"status": "BLOCKED", "reason": "missing_or_non_https_url"}
    if opener is None:
        opener = urllib.request.build_opener(_NoRedirectHandler)
    try:
        req = urllib.request.Request(url, method="GET")
        resp = opener.open(req, timeout=5)
        code = getattr(resp, "getcode", lambda: getattr(resp, "code", None))()
        return {"status": "BLOCKED", "reason": f"unexpected_status_{code}"}
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            return {"status": "OK", "reason": f"not_served_{exc.code}", "http_status": exc.code}
        return {"status": "BLOCKED", "reason": f"http_error_{exc.code}"}
    except urllib.error.URLError as exc:
        return {"status": "BLOCKED", "reason": f"network_error:{exc.reason}"}
    except Exception as exc:
        return {"status": "BLOCKED", "reason": f"probe_exception:{type(exc).__name__}"}


# ---------------------------------------------------------------------------
# Remaining Gate A predicate checks (evidence-derived, no fabricated True)
# ---------------------------------------------------------------------------

def check_inputs_present_and_regular(paths):
    missing = []
    for p in paths:
        if not os.path.exists(p):
            missing.append(p)
            continue
        st = os.lstat(p)
        if stat.S_ISLNK(st.st_mode):
            missing.append(p)
    if missing:
        return {"status": "BLOCKED", "missing_or_symlink": missing}
    return {"status": "OK", "checked": paths}


def check_backup_verified(archive_path, expected_sha256):
    if not os.path.exists(archive_path):
        return {"status": "BLOCKED", "reason": "backup_missing"}
    actual = _sha256_file(archive_path)
    if actual != expected_sha256:
        return {"status": "BLOCKED", "reason": "backup_hash_mismatch"}
    return {"status": "OK", "sha256": actual}


def check_candidates_compile(candidate_sources):
    errors = {}
    for name, src in candidate_sources.items():
        try:
            compile(src, name, "exec")
        except SyntaxError as exc:
            errors[name] = str(exc)
    if errors:
        return {"status": "BLOCKED", "errors": errors}
    return {"status": "OK", "compiled": list(candidate_sources.keys())}


def check_protected_fingerprints_unchanged(before, after):
    if not before or not after:
        return {"status": "BLOCKED", "reason": "missing_fingerprints"}
    if before != after:
        diff_keys = [k for k in before if before.get(k) != after.get(k)]
        return {"status": "BLOCKED", "reason": "changed", "diff_keys": diff_keys}
    return {"status": "OK"}


def check_sqlite_readonly_quickcheck_ok(db_path):
    if not os.path.exists(db_path):
        return {"status": "BLOCKED", "reason": "db_missing"}
    try:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=2)
        try:
            conn.execute("PRAGMA query_only=ON;")
            cur = conn.execute("PRAGMA quick_check;")
            result = cur.fetchone()
        finally:
            conn.close()
        if result and result[0] == "ok":
            return {"status": "OK", "quick_check": result[0]}
        return {"status": "BLOCKED", "reason": "quick_check_failed", "value": result}
    except sqlite3.OperationalError as exc:
        return {"status": "BLOCKED", "reason": f"sqlite_locked_or_error:{exc}"}


def check_admin_routes_text_only(cars_ui_source):
    result = transform_cars_ui(cars_ui_source)
    if result["status"] != "OK" or result["candidate"] is None:
        return {"status": "BLOCKED", "reasons": result["reasons"]}
    clean, violations = scan_reachable_call_graph(result["candidate"], ADMIN_ROUTE_NAMES)
    if not clean:
        return {"status": "BLOCKED", "reasons": violations}
    return {"status": "OK", "candidate_sha256": _sha256_bytes(result["candidate"].encode("utf-8"))}


def _extract_function_ast_dumps(source, names):
    tree = ast.parse(source)
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            found[node.name] = ast.dump(node)
    return found


def check_media_persistence_unchanged(original_source, candidate_source, protected_function_names):
    before = _extract_function_ast_dumps(original_source, protected_function_names)
    after = _extract_function_ast_dumps(candidate_source or "", protected_function_names)
    missing = [n for n in protected_function_names if n not in after]
    if missing:
        return {"status": "BLOCKED", "reason": "missing_protected_functions", "missing": missing}
    changed = [n for n in protected_function_names if before.get(n) != after.get(n)]
    if changed:
        return {"status": "BLOCKED", "reason": "protected_functions_changed", "changed": changed}
    return {"status": "OK"}


FORBIDDEN_USERCUSTOMIZE_MODULES = {
    "team_bot", "run_all", "start_safe", "avtoperedacha", "stranica",
    "threading", "multiprocessing", "subprocess",
}


def check_usercustomize_inert(source):
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {"status": "BLOCKED", "reason": f"syntax_error:{exc}"}
    violations = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_USERCUSTOMIZE_MODULES:
                    violations.append(f"forbidden_import:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in FORBIDDEN_USERCUSTOMIZE_MODULES:
                violations.append(f"forbidden_import_from:{node.module}")
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            violations.append("top_level_call_statement")
    if violations:
        return {"status": "BLOCKED", "violations": violations}
    return {"status": "OK"}


def check_singleton_guard_present(tmp_dir):
    lock_path = os.path.join(tmp_dir, "singleton.lock")
    guard1 = SingletonGuard(lock_path)
    ok1 = guard1.acquire()
    guard2 = SingletonGuard(lock_path)
    ok2 = guard2.acquire()
    guard1.release()
    guard3 = SingletonGuard(lock_path)
    ok3 = guard3.acquire()
    guard3.release()
    if ok1 and not ok2 and ok3:
        return {"status": "OK"}
    return {"status": "BLOCKED", "reason": "singleton_semantics_violated", "ok1": ok1, "ok2": ok2, "ok3": ok3}


def check_rebuild_queue_bound_no_process_spawn(avtoperedacha_source):
    try:
        tree = ast.parse(avtoperedacha_source)
    except SyntaxError as exc:
        return {"status": "BLOCKED", "reason": f"syntax_error:{exc}"}
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in ("subprocess", "multiprocessing"):
                    violations.append(f"forbidden_import:{alias.name}")
        if isinstance(node, ast.Attribute) and node.attr in ("system", "Popen", "call", "run", "check_call", "check_output"):
            violations.append(f"forbidden_call_site:{node.attr}")
    if violations:
        return {"status": "BLOCKED", "violations": violations}
    return {"status": "OK"}


SLOW_CALL_NAMES = {"sleep", "send_message", "send_photo", "render", "generate", "post", "request"}


def check_db_closed_before_slow_work(function_source):
    try:
        tree = ast.parse(function_source)
    except SyntaxError as exc:
        return {"status": "BLOCKED", "reason": f"syntax_error:{exc}"}
    func = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = node
            break
    if func is None:
        return {"status": "BLOCKED", "reason": "no_function_found"}
    close_index = None
    slow_index = None
    for i, stmt in enumerate(func.body):
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "close" and close_index is None:
                    close_index = i
                if node.func.attr in SLOW_CALL_NAMES and slow_index is None:
                    slow_index = i
    if close_index is None:
        return {"status": "BLOCKED", "reason": "no_close_found"}
    if slow_index is not None and slow_index < close_index:
        return {"status": "BLOCKED", "reason": "slow_work_before_close"}
    return {"status": "OK", "close_index": close_index, "slow_index": slow_index}


def check_deterministic_repeat_all_transforms(transform_map):
    failures = []
    for name, (fn, source, args) in transform_map.items():
        measurement = measure_deterministic_repeat(fn, source, args=args, repeats=10)
        if not measurement["deterministic"]:
            failures.append(name)
    if failures:
        return {"status": "BLOCKED", "failures": failures}
    return {"status": "OK", "checked": list(transform_map.keys())}


def check_site_inventory_unchanged(root, allowed_names, max_files_per_root=DEFAULT_MAX_FILES_PER_ROOT):
    before = scan_bounded_inventory(root, allowed_names, max_files_per_root)
    after = scan_bounded_inventory(root, allowed_names, max_files_per_root)
    if before.get("status") != "OK" or after.get("status") != "OK":
        return {"status": "BLOCKED", "before": before, "after": after}
    if before["entries"] != after["entries"]:
        return {"status": "BLOCKED", "reason": "inventory_changed"}
    return {"status": "OK", "matched_count": before["matched_count"]}


def check_no_production_write(protected_before, protected_after, site_before, site_after):
    if protected_before != protected_after:
        return {"status": "BLOCKED", "reason": "protected_changed"}
    if site_before != site_after:
        return {"status": "BLOCKED", "reason": "site_inventory_changed"}
    return {"status": "OK"}


def evaluate_gate_a(evidence):
    """Derive final status only from measured evidence. No predicate may
    default to True. Missing/failed evidence -> BLOCKED."""
    unmet = []
    for key in REQUIRED_PREDICATES:
        item = evidence.get(key)
        if not isinstance(item, dict) or item.get("status") != "OK":
            unmet.append(key)
    if unmet:
        return "BLOCKED", unmet
    return "GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL", []


def run_gate_a(fixture):
    """Single, real, executable orchestration entry point. `fixture` supplies
    every bounded input needed for one full Gate A evaluation (production
    launcher builds it from DEFAULT_CONFIG bound to real /home/Carix paths;
    tests pass a synthetic fixture). This repository never invokes this
    function against production; GATE_A_EXECUTED remains NO for every task
    delivered under cloud/."""
    evidence = {}
    evidence["inputs_present_and_regular"] = check_inputs_present_and_regular(fixture["required_inputs"])
    evidence["backup_verified"] = check_backup_verified(fixture["backup_archive"], fixture["backup_archive_sha256"])

    cars_ui_candidate = transform_cars_ui(fixture["cars_ui_source"])
    usercustomize_source = fixture["usercustomize_source"]
    avtoperedacha_source = fixture["avtoperedacha_source"]

    candidate_sources = {
        "cars_ui.py": cars_ui_candidate.get("candidate") or fixture["cars_ui_source"],
        "usercustomize.py": usercustomize_source,
        "avtoperedacha.py": avtoperedacha_source,
    }
    evidence["candidates_compile"] = check_candidates_compile(candidate_sources)

    evidence["protected_fingerprints_unchanged"] = check_protected_fingerprints_unchanged(
        fixture["protected_fingerprints_before"], fixture["protected_fingerprints_after"])
    evidence["sqlite_readonly_quickcheck_ok"] = check_sqlite_readonly_quickcheck_ok(fixture["db_path"])
    evidence["ua0009_fingerprint_unchanged"] = check_protected_fingerprints_unchanged(
        fixture["ua0009_fingerprint_before"], fixture["ua0009_fingerprint_after"])
    evidence["ua0009_not_public"] = check_ua0009_not_public(fixture["ua0009_url"], fixture.get("ua0009_opener"))
    evidence["site_inventory_unchanged"] = check_site_inventory_unchanged(
        fixture["site_root"], fixture["allowed_site_names"], fixture.get("max_files_per_root", DEFAULT_MAX_FILES_PER_ROOT))
    evidence["admin_routes_text_only"] = check_admin_routes_text_only(fixture["cars_ui_source"])
    evidence["media_persistence_unchanged"] = check_media_persistence_unchanged(
        fixture["cars_ui_source"], cars_ui_candidate.get("candidate"), fixture["protected_function_names"])
    evidence["usercustomize_inert"] = check_usercustomize_inert(usercustomize_source)
    evidence["singleton_guard_present"] = check_singleton_guard_present(fixture["tmp_dir"])
    evidence["rebuild_queue_bound_no_process_spawn"] = check_rebuild_queue_bound_no_process_spawn(avtoperedacha_source)
    evidence["db_closed_before_slow_work"] = check_db_closed_before_slow_work(fixture["db_function_source"])
    evidence["deterministic_repeat_all_transforms"] = check_deterministic_repeat_all_transforms({
        "cars_ui": (transform_cars_ui, fixture["cars_ui_source"], ()),
    })
    evidence["no_production_write"] = check_no_production_write(
        fixture["protected_fingerprints_before"], fixture["protected_fingerprints_after"],
        fixture.get("site_before"), fixture.get("site_after"))

    status, unmet = evaluate_gate_a(evidence)
    receipt = {
        "status": status,
        "unmet_predicates": unmet,
        "evidence": evidence,
        "production_write": "NO",
        "generated_at": time.time(),
    }
    if fixture.get("run_dir"):
        writer = SafeWriter(fixture["run_dir"])
        writer.write_text("receipt.json", json.dumps(receipt, indent=2, default=str))
    return receipt

```

## END EXACT SOURCE: cloud/crm_speed_optimization/crm_speed_gate_a.py

## BEGIN EXACT SOURCE: cloud/crm_speed_optimization/test_cars_ui_transform.py

```python
import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cars_ui_transform import transform_cars_ui, scan_reachable_call_graph  # noqa: E402


class CarsUiTransformTests(unittest.TestCase):
    def test_direct_simple_media_call_transforms_cleanly(self):
        src = (
            "async def admin_car_view(message, bot):\n"
            "    await message.reply_photo(open('car.jpg', 'rb'), caption='Car')\n"
            "    await message.reply_video(open('car.mp4', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_view'])
        self.assertEqual(result['status'], 'OK')
        candidate = result['candidate']
        self.assertNotIn('open(', candidate)
        self.assertIn('reply_text', candidate)
        compile(candidate, '<test>', 'exec')

    def test_reachable_private_helper_exclusive_to_admin_transforms_cleanly(self):
        # Historical fixture name was 'nested helper media call blocks'.
        # The correct required behavior is that a helper reachable only
        # from an admin route, containing an exact direct media
        # expression, is rewritten cleanly (status OK), not blocked.
        src = (
            "def _send_car_photo(message):\n"
            "    message.reply_photo(open('car.jpg', 'rb'))\n"
            "\n"
            "def admin_car_edit(message):\n"
            "    _send_car_photo(message)\n"
        )
        result = transform_cars_ui(src, ['admin_car_edit'])
        self.assertEqual(result['status'], 'OK')
        candidate = result['candidate']
        self.assertNotIn('open(', candidate)
        self.assertNotIn('reply_photo', candidate)
        self.assertIn('reply_text', candidate)
        compile(candidate, '<test>', 'exec')

    def test_shared_helper_with_external_caller_blocks(self):
        src = (
            "def _send_car_photo(message):\n"
            "    message.reply_photo(open('car.jpg', 'rb'))\n"
            "\n"
            "def admin_car_edit(message):\n"
            "    _send_car_photo(message)\n"
            "\n"
            "def customer_car_view(message):\n"
            "    _send_car_photo(message)\n"
        )
        result = transform_cars_ui(src, ['admin_car_edit'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('shared_helper_called_by', result['reason'])

    def test_media_group_count_and_async_await_ok(self):
        src = (
            "async def admin_car_edit(message):\n"
            "    await message.reply_media_group([open('a.jpg', 'rb'), open('b.jpg', 'rb')])\n"
        )
        result = transform_cars_ui(src, ['admin_car_edit'])
        self.assertEqual(result['status'], 'OK')
        self.assertIn('2 item', result['candidate'])
        self.assertIn('await', result['candidate'])

    def test_open_call_outside_media_expression_blocks(self):
        src = (
            "def admin_car_delete(message):\n"
            "    f = open('car.jpg', 'rb')\n"
            "    message.reply_text('deleted')\n"
        )
        result = transform_cars_ui(src, ['admin_car_delete'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('unresolved_callable:open', result['reason'])

    def test_getattr_dynamic_dispatch_blocks(self):
        src = (
            "def admin_car_list(message):\n"
            "    getattr(message, 'reply_photo')(open('car.jpg', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_list'])
        self.assertEqual(result['status'], 'BLOCKED')

    def test_attribute_alias_assignment_blocks(self):
        src = (
            "def admin_car_list(message):\n"
            "    fn = message.reply_photo\n"
            "    fn(open('car.jpg', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_list'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('attribute_alias_reference', result['reason'])

    def test_lambda_wrapped_media_call_blocks(self):
        src = (
            "def admin_car_list(message):\n"
            "    handlers = [lambda: message.reply_photo(open('car.jpg', 'rb'))]\n"
            "    handlers[0]()\n"
        )
        result = transform_cars_ui(src, ['admin_car_list'])
        self.assertEqual(result['status'], 'BLOCKED')

    def test_callback_container_media_reference_blocks(self):
        src = (
            "def admin_car_list(message):\n"
            "    callbacks = {'photo': message.reply_photo}\n"
            "    callbacks['photo'](open('car.jpg', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_list'])
        self.assertEqual(result['status'], 'BLOCKED')

    def test_return_alias_of_media_method_blocks(self):
        src = (
            "def admin_car_list(message):\n"
            "    return message.reply_photo\n"
        )
        result = transform_cars_ui(src, ['admin_car_list'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('attribute_alias_reference', result['reason'])

    def test_side_effectful_media_argument_helper_blocks(self):
        src = (
            "def _prepare_photo():\n"
            "    log_side_effect()\n"
            "    return b'data'\n"
            "\n"
            "def admin_car_view(message):\n"
            "    message.reply_photo(_prepare_photo())\n"
        )
        result = transform_cars_ui(src, ['admin_car_view'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('unsafe_media_argument_side_effect', result['reason'])

    def test_protected_customer_function_untouched_when_not_reachable(self):
        src = (
            "def customer_car_view(message):\n"
            "    message.reply_photo(open('x.jpg', 'rb'))\n"
            "\n"
            "def admin_car_view(message):\n"
            "    message.reply_photo(open('y.jpg', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_view'])
        self.assertEqual(result['status'], 'OK')
        candidate_tree = ast.parse(result['candidate'])
        funcs = {n.name: n for n in candidate_tree.body if isinstance(n, ast.FunctionDef)}
        customer_src = ast.dump(funcs['customer_car_view'])
        admin_src = ast.dump(funcs['admin_car_view'])
        self.assertIn('reply_photo', customer_src)
        self.assertNotIn('reply_photo', admin_src)

    def test_missing_entry_point_blocks(self):
        src = (
            "def admin_car_view(message):\n"
            "    message.reply_photo(open('x.jpg', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_missing'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('missing_entry_points', result['reason'])

    def test_candidate_compiles_for_all_ok_cases(self):
        src = (
            "async def admin_car_view(message, bot):\n"
            "    await message.reply_photo(open('car.jpg', 'rb'))\n"
            "\n"
            "def admin_car_list(message):\n"
            "    message.reply_document(open('doc.pdf', 'rb'))\n"
        )
        result = transform_cars_ui(src, ['admin_car_view', 'admin_car_list'])
        self.assertEqual(result['status'], 'OK')
        compile(result['candidate'], '<test>', 'exec')


if __name__ == '__main__':
    unittest.main()

```

## END EXACT SOURCE: cloud/crm_speed_optimization/test_cars_ui_transform.py

## BEGIN EXACT SOURCE: cloud/crm_speed_optimization/test_crm_speed_gate_a.py

```python
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

```

## END EXACT SOURCE: cloud/crm_speed_optimization/test_crm_speed_gate_a.py

## BEGIN EXACT SOURCE: cloud/crm_speed_optimization/RUN_GATE_A_CRM_SPEED.py

```python
#!/usr/bin/env python3
"""No-argument Gate A launcher artifact.

IMPORTANT: This script is delivered for independent controller/owner
execution on PythonAnywhere ONLY, after review and explicit approval. It is
NEVER executed automatically by Claude/Cloud or by this repository's own
automation. Running this file is a separate, owner-approved action outside
the scope of any cloud/ task.
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crm_speed_gate_a import DEFAULT_CONFIG  # noqa: E402


def main():
    run_id = time.strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(DEFAULT_CONFIG["run_root"], run_id)
    print("This launcher is a delivered artifact for controller/owner-run execution only.")
    print("Claude/Cloud automation does not execute Gate A against production.")
    print(json.dumps({"planned_run_dir": run_dir, "config": DEFAULT_CONFIG}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

```

## END EXACT SOURCE: cloud/crm_speed_optimization/RUN_GATE_A_CRM_SPEED.py

## Completion
Return complete replacement contents for every changed implementation/test file, update status/report truthfully, and commit via AUTOPILOT. Do not omit unchanged required behavior.
