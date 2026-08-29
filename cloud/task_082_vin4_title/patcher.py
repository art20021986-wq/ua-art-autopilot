"""AST + SHA anchored patcher for the active render functions in cars_ui.py.

Fail-closed design: this module will NOT modify anything unless it can
uniquely and confidently identify the render function(s) that build the car
title/button text, and unless the caller supplies an operator-reviewed
allowlist (`anchor_config.json`) that matches the discovered candidates
exactly. If evidence is ambiguous, `patch_source` raises `AnchorMismatch` and
no file is ever written.

No network, no DB access. Pure text/AST transformation with SHA anchoring.
"""
from __future__ import annotations

import ast
import hashlib
import json
import textwrap
from dataclasses import dataclass, field


class AnchorMismatch(Exception):
    pass


HELPER_IMPORT_LINE = "from vin4_helper import render_title_html, render_button_label\n"

# Heuristic tokens that suggest a function builds a car title/button label.
_TITLE_TOKENS = ("ua_id", "ua-", "brand", "model", "vin")
_HTML_TOKENS = ("<b>", "parse_mode", "html")


@dataclass
class CandidateFunc:
    name: str
    lineno: int
    end_lineno: int
    kind: str  # "title_html" or "button_label" or "unknown"
    source_sha256: str
    source_text: str


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def locate_render_functions(source_text: str) -> list[CandidateFunc]:
    """Return a list of function definitions that look like car title/button
    renderers, based on conservative AST heuristics. Never guesses wildly:
    a function is only a candidate if its source text contains at least two
    of the title tokens (case-insensitive).
    """
    tree = ast.parse(source_text)
    lines = source_text.splitlines(keepends=True)
    candidates: list[CandidateFunc] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = node.lineno - 1
        end = getattr(node, "end_lineno", node.lineno)
        segment = "".join(lines[start:end])
        seg_lower = segment.lower()
        hits = sum(1 for t in _TITLE_TOKENS if t in seg_lower)
        if hits < 2:
            continue
        kind = "unknown"
        if any(t in seg_lower for t in _HTML_TOKENS):
            kind = "title_html"
        elif "inlinekeyboardbutton" in seg_lower or "button" in seg_lower:
            kind = "button_label"
        candidates.append(
            CandidateFunc(
                name=node.name,
                lineno=node.lineno,
                end_lineno=end,
                kind=kind,
                source_sha256=_sha256(segment),
                source_text=segment,
            )
        )
    return candidates


def load_anchor_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def verify_anchor_match(candidates: list[CandidateFunc], anchor_config: dict) -> list[CandidateFunc]:
    """Cross-check discovered candidates against the operator-reviewed
    allowlist. Returns the subset that is approved for patching. Raises
    AnchorMismatch if the allowlist references a function name that was not
    discovered, or if a discovered high-confidence candidate is missing from
    the allowlist (fail closed instead of silently skipping).
    """
    approved_names = {a["name"]: a for a in anchor_config.get("functions", [])}
    by_name = {c.name: c for c in candidates}

    for name, entry in approved_names.items():
        if name not in by_name:
            raise AnchorMismatch(
                f"Allowlisted function '{name}' not found in current live source; "
                "live file may have drifted since the allowlist was reviewed."
            )
        cand = by_name[name]
        expected_sha = entry.get("expected_source_sha256")
        if expected_sha and expected_sha != cand.source_sha256:
            raise AnchorMismatch(
                f"Function '{name}' source SHA changed since allowlist review "
                f"(expected {expected_sha}, got {cand.source_sha256}). Aborting; "
                "re-review required before patching."
            )

    high_conf = [c for c in candidates if c.kind in ("title_html", "button_label")]
    unapproved_high_conf = [c for c in high_conf if c.name not in approved_names]
    if unapproved_high_conf:
        names = ", ".join(c.name for c in unapproved_high_conf)
        raise AnchorMismatch(
            f"High-confidence render function(s) [{names}] found but not present "
            "in the reviewed allowlist. Refusing to patch until reviewed and added."
        )

    return [by_name[n] for n in approved_names if n in by_name]


def _wrap_return_expr(func_source: str, kind: str) -> str:
    """Insert a call to the centralized helper around every `return <expr>`
    inside the function body, using the already-computed local variables
    (ua_id, brand, model, year, vin) that must exist in the function's local
    scope for this wrap to be semantically safe. This is intentionally a
    narrow textual transform (not a blind AST return-wrapper) so behavior
    stays auditable; it is only ever applied to functions that passed
    verify_anchor_match.
    """
    if kind == "title_html":
        call = "render_title_html(ua_id, brand, model, year, vin, existing_title=__vin4_base)"
    elif kind == "button_label":
        call = "render_button_label(ua_id, brand, model, year, vin, existing_label=__vin4_base)"
    else:
        return func_source

    lines = func_source.splitlines(keepends=True)
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("return "):
            indent = line[: len(line) - len(line.lstrip())]
            expr = stripped[len("return "):]
            out.append(f"{indent}__vin4_base = {expr}\n")
            out.append(f"{indent}return {call}\n")
        else:
            out.append(line)
    return "".join(out)


def patch_source(source_text: str, anchor_config: dict) -> tuple[str, list[str]]:
    """Return (patched_source, changed_function_names). Raises AnchorMismatch
    if anything is ambiguous. Only the identified function bodies are
    modified (return-statement wrapping); everything else is byte-identical.
    """
    candidates = locate_render_functions(source_text)
    approved = verify_anchor_match(candidates, anchor_config)
    if not approved:
        raise AnchorMismatch("No approved render functions to patch; refusing no-op silent success.")

    lines = source_text.splitlines(keepends=True)
    changed_names = []
    # Patch from bottom to top so earlier line numbers stay valid.
    for cand in sorted(approved, key=lambda c: c.lineno, reverse=True):
        start = cand.lineno - 1
        end = cand.end_lineno
        original_segment = "".join(lines[start:end])
        patched_segment = _wrap_return_expr(original_segment, cand.kind)
        if patched_segment == original_segment:
            continue
        lines[start:end] = [patched_segment]
        changed_names.append(cand.name)

    patched_source = "".join(lines)
    if HELPER_IMPORT_LINE.strip() not in patched_source:
        # Insert import right after the last top-level import block, or at top.
        insert_at = 0
        tree = ast.parse(patched_source)
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                insert_at = node.end_lineno
            else:
                break
        out_lines = patched_source.splitlines(keepends=True)
        out_lines.insert(insert_at, HELPER_IMPORT_LINE)
        patched_source = "".join(out_lines)

    # Sanity: patched source must still be valid Python.
    ast.parse(patched_source)
    return patched_source, changed_names
