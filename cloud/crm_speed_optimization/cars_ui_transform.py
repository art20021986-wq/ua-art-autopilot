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
