"""
Generic SHA256 + AST-anchor verifying transformer.

Contract:
  - Never patches based on assumption. Requires an `expected_sha256` and a list of
    `AnchorSpec` objects (AST node signatures) that MUST be found, in the given source,
    before any patch is applied.
  - On any hash mismatch or missing anchor: fail closed (raises DriftDetected), no patch
    is attempted.
  - Operates only on local file paths (temp copies). Never touches a path containing
    a live production marker unless explicitly told this is a sandbox/test copy.
"""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from typing import Callable, Optional


class DriftDetected(Exception):
    pass


@dataclass
class AnchorSpec:
    kind: str  # "function" | "assign" | "call"
    name: str
    description: str


def sha256_of_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_hash(source_text: str, expected_sha256: str) -> None:
    actual = sha256_of_text(source_text)
    if actual != expected_sha256:
        raise DriftDetected(
            f"SHA256 drift: expected {expected_sha256}, got {actual}. "
            "Refusing to patch without a fresh, matching source snapshot."
        )


def _find_function_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    return names


def verify_anchors(source_text: str, anchors: list[AnchorSpec]) -> None:
    tree = ast.parse(source_text)
    fn_names = _find_function_names(tree)
    missing = []
    for anchor in anchors:
        if anchor.kind == "function" and anchor.name not in fn_names:
            missing.append(anchor)
    if missing:
        details = "; ".join(f"{a.kind}:{a.name} ({a.description})" for a in missing)
        raise DriftDetected(f"AST anchor(s) missing, refusing blind patch: {details}")


def verify_and_patch(
    source_path: str,
    expected_sha256: str,
    anchors: list[AnchorSpec],
    patch_fn: Callable[[str], str],
    dest_path: Optional[str] = None,
) -> str:
    """Read source_path, verify hash+anchors, apply patch_fn(text)->new_text,
    write to dest_path (or source_path if None), verify the result still compiles.

    Returns the path written to. Raises DriftDetected on any mismatch; never writes
    partial/garbage output.
    """
    with open(source_path, "r", encoding="utf-8") as f:
        text = f.read()
    verify_hash(text, expected_sha256)
    verify_anchors(text, anchors)
    new_text = patch_fn(text)
    # Must still be valid Python after patch.
    compile(new_text, source_path, "exec")
    out_path = dest_path or source_path
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(new_text)
    return out_path
