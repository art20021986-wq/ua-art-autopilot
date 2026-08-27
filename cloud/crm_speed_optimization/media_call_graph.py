"""
media_call_graph.py

Bounded, same-module reachable-call analysis proving (or disproving) that
the four administrator display routes (gallery, video_gallery,
diag_photo_show, diag_video_show) can never reach an automatic Telegram
media-send call, including through statically resolvable helpers and
simple aliases. Ambiguous dynamic dispatch that could reach a media send
is treated as BLOCKED, never as a pass.
"""
from __future__ import annotations

import ast
import hashlib
from typing import Dict, List, Set, Tuple

MEDIA_SEND_ATTRS = {
    "reply_photo", "reply_video", "reply_document", "reply_media_group",
    "reply_animation", "reply_audio", "reply_voice",
    "send_photo", "send_video", "send_document", "send_media_group",
    "send_animation", "send_audio", "send_voice",
}

DYNAMIC_DISPATCH_MARKERS = {"getattr", "eval", "exec"}

ENTRY_POINTS = ("gallery", "video_gallery", "diag_photo_show", "diag_video_show")


class MediaScanResult:
    def __init__(self):
        self.violations: Dict[str, List[str]] = {}
        self.blocked: Dict[str, str] = {}

    def is_clean(self) -> bool:
        return not self.violations and not self.blocked


def _func_defs(tree) -> Dict[str, ast.AST]:
    defs: Dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs[node.name] = node
    return defs


def _called_names(node) -> Set[Tuple[str, int, str]]:
    found: Set[Tuple[str, int, str]] = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Call):
            func = inner.func
            lineno = getattr(inner, "lineno", 0)
            if isinstance(func, ast.Attribute) and func.attr in MEDIA_SEND_ATTRS:
                found.add(("media", lineno, func.attr))
            elif isinstance(func, ast.Name):
                if func.id in DYNAMIC_DISPATCH_MARKERS:
                    found.add(("dynamic", lineno, func.id))
                else:
                    found.add(("local", lineno, func.id))
            elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                found.add(("local", lineno, func.attr))
        if isinstance(inner, ast.Assign) and isinstance(inner.value, ast.Attribute):
            if inner.value.attr in MEDIA_SEND_ATTRS:
                for t in inner.targets:
                    if isinstance(t, ast.Name):
                        found.add(("media_alias", getattr(inner, "lineno", 0), t.id))
    return found


def build_call_graph(tree) -> Dict[str, Set[Tuple[str, int, str]]]:
    defs = _func_defs(tree)
    graph: Dict[str, Set[Tuple[str, int, str]]] = {}
    for name, node in defs.items():
        graph[name] = _called_names(node)
    return graph


def find_reachable_media_calls(source: str, entry_points=ENTRY_POINTS) -> MediaScanResult:
    tree = ast.parse(source)
    defs = _func_defs(tree)
    graph = build_call_graph(tree)
    result = MediaScanResult()
    alias_media_names: Set[str] = set()
    for edges in graph.values():
        for kind, _lineno, name in edges:
            if kind == "media_alias":
                alias_media_names.add(name)

    for entry in entry_points:
        if entry not in defs:
            result.blocked[entry] = "entry point not found in source"
            continue
        seen: Set[str] = set()
        stack = [entry]
        violations: List[str] = []
        blocked_reason = None
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for kind, lineno, name in graph.get(cur, set()):
                if kind in ("media", "media_alias") or name in alias_media_names:
                    violations.append(f"{cur} -> line {lineno}: media send '{name}'")
                elif kind == "dynamic":
                    blocked_reason = (
                        f"ambiguous dynamic dispatch '{name}' reachable from {cur} "
                        f"at line {lineno}; cannot prove absence of media send"
                    )
                elif kind == "local" and name in defs and name not in seen:
                    stack.append(name)
        if blocked_reason:
            result.blocked[entry] = blocked_reason
        if violations:
            result.violations[entry] = violations
    return result


def normalized_ast_dump(node) -> str:
    clone = ast.parse(ast.unparse(node)) if not isinstance(node, ast.Module) else node
    return ast.dump(clone, annotate_fields=True, include_attributes=False)


def semantic_hash(source: str, function_names) -> Dict[str, str]:
    tree = ast.parse(source)
    defs = _func_defs(tree)
    out: Dict[str, str] = {}
    for name in function_names:
        node = defs.get(name)
        if node is None:
            out[name] = "MISSING"
            continue
        dump = normalized_ast_dump(node)
        out[name] = hashlib.sha256(dump.encode("utf-8")).hexdigest()
    return out
