#!/usr/bin/env python3
"""Bounded AST-aware integration patch for TASK 091."""
from __future__ import annotations

import ast


CONTRACT_ID = "CRM-NUMERIC-SINGLE-CLAIM-091-V1.0"
MARKER = "# " + CONTRACT_ID + ": one numeric occurrence may populate one CRM field."


class PatchError(RuntimeError):
    pass


def _function_bounds(source: str, name: str) -> tuple[int, int, str]:
    tree = ast.parse(source)
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(matches) != 1:
        raise PatchError("FUNCTION_COUNT:%s:%d" % (name, len(matches)))
    node = matches[0]
    lines = source.splitlines(keepends=True)
    start = sum(len(line) for line in lines[:node.lineno - 1])
    end = sum(len(line) for line in lines[:node.end_lineno])
    return start, end, source[start:end]


def _replace_function(source: str, name: str, transform) -> str:
    start, end, block = _function_bounds(source, name)
    replacement = transform(block)
    if replacement == block:
        raise PatchError("FUNCTION_UNCHANGED:" + name)
    return source[:start] + replacement + source[end:]


def patch_ai_filter(source: str) -> str:
    if MARKER in source:
        return source

    def transform(block: str) -> str:
        anchor = "    _log_parsed(parsed, out)\n    return out"
        if block.count(anchor) != 1:
            raise PatchError("AI_FILTER_RETURN_ANCHOR:%d" % block.count(anchor))
        replacement = (
            "    from field_claim_guard import enforce as _v191_enforce_numeric_claims\n"
            "    out = _v191_enforce_numeric_claims(out, extra_text)\n"
            "    _log_parsed(parsed, out)\n"
            "    return out"
        )
        return block.replace(anchor, replacement, 1)

    candidate = _replace_function(source, "clean", transform)
    candidate = MARKER + "\n" + candidate
    compile(candidate, "ai_filter.py.candidate", "exec")
    return candidate


def patch_local_ocr(source: str) -> str:
    if MARKER in source:
        return source

    def transform(block: str) -> str:
        anchor = "    return data"
        if block.count(anchor) != 1:
            raise PatchError("LOCAL_OCR_RETURN_ANCHOR:%d" % block.count(anchor))
        replacement = (
            "    from field_claim_guard import enforce as _v191_enforce_numeric_claims\n"
            "    return _v191_enforce_numeric_claims(data, raw)"
        )
        return block.replace(anchor, replacement, 1)

    candidate = _replace_function(source, "fields_from_text", transform)
    candidate = MARKER + "\n" + candidate
    compile(candidate, "local_ocr.py.candidate", "exec")
    return candidate


def validate_candidates(ai_filter: str, local_ocr: str) -> dict[str, bool]:
    compile(ai_filter, "ai_filter.py.candidate", "exec")
    compile(local_ocr, "local_ocr.py.candidate", "exec")
    checks = {
        "ai_filter_marker": ai_filter.count(MARKER) == 1,
        "local_ocr_marker": local_ocr.count(MARKER) == 1,
        "ai_filter_guard_call": ai_filter.count("_v191_enforce_numeric_claims(out, extra_text)") == 1,
        "local_ocr_guard_call": local_ocr.count("_v191_enforce_numeric_claims(data, raw)") == 1,
        "ai_filter_clean_unique": len([
            node for node in ast.parse(ai_filter).body
            if isinstance(node, ast.FunctionDef) and node.name == "clean"
        ]) == 1,
        "local_ocr_fields_unique": len([
            node for node in ast.parse(local_ocr).body
            if isinstance(node, ast.FunctionDef) and node.name == "fields_from_text"
        ]) == 1,
    }
    if not all(checks.values()):
        raise PatchError("CANDIDATE_VALIDATION:" + repr(checks))
    return checks


__all__ = [
    "CONTRACT_ID", "MARKER", "PatchError", "patch_ai_filter",
    "patch_local_ocr", "validate_candidates",
]
