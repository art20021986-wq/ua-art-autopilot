"""
TASK 079 - live_patcher.py

This tool is a FAIL-CLOSED, NON-EXECUTING patch preparer. It never writes to
any production path in this delivery. It is designed so that, if ever run by
an authorized operator against a real checkout AFTER separate Gate B owner
approval, it:

  1. Verifies the full-file SHA-256 anchor of each target file against the
     TASK 079 anchors before touching anything.
  2. Locates the named active function definition by AST, computes a hash of
     its exact source block, and compares it against an explicit expected
     hash supplied by the caller. If no expected hash is supplied, or if more
     than one definition of the function exists in the file (duplicate
     definition), it aborts.
  3. Refuses to run at all unless the caller passes the exact owner approval
     token string via the `owner_token` argument AND `allow_write=True`.
     In this repository/delivery, `allow_write` is hardcoded to False at the
     top-level `main()` entrypoint, so no invocation from this codebase can
     ever write to a real file. Direct callers of the internal API must
     explicitly override that, which is out of scope for Gate A.

This file intentionally does NOT embed the actual production source of
db.py / cars_ui.py / konteyner.py / stranica.py / publikaciya.py, since that
would require access this delivery does not have. It only provides the
verification and transplant machinery to be exercised against real files by
an operator with the actual checkout, strictly after Gate B approval.
"""

from __future__ import annotations

import ast
import hashlib
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from eta_release_candidate import LIVE_FULL_FILE_SHA256, AnchorMismatchError, sha256_of_file

OWNER_TOKEN = "CRM-CONTAINER-STAGE-SYNC-004-V1.0-PRODUCTION-APPROVED"

# Hardcoded fail-closed switch. Never flip this in this repository; Gate B
# execution must happen only via the owner-approved manual workflow, not via
# this Cloud/Claude delivery.
ALLOW_WRITE_HARDCODED = False


class PatchAbortedError(RuntimeError):
    pass


@dataclass
class FunctionLocation:
    name: str
    start_line: int
    end_line: int
    source: str
    source_sha256: str


def _find_function_definitions(source_text: str, function_name: str) -> List[FunctionLocation]:
    tree = ast.parse(source_text)
    lines = source_text.splitlines(keepends=True)
    found: List[FunctionLocation] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            start = node.lineno - 1
            end = getattr(node, "end_lineno", node.lineno)
            block = "".join(lines[start:end])
            found.append(
                FunctionLocation(
                    name=function_name,
                    start_line=node.lineno,
                    end_line=end,
                    source=block,
                    source_sha256=hashlib.sha256(block.encode("utf-8")).hexdigest(),
                )
            )
    return found


def verify_target_file_anchor(path: str, anchor_key: str) -> None:
    expected = LIVE_FULL_FILE_SHA256.get(anchor_key)
    if expected is None:
        raise PatchAbortedError(f"No registered anchor for {anchor_key}")
    actual = sha256_of_file(path)
    if actual != expected:
        raise PatchAbortedError(
            f"ABORT: {anchor_key} full-file hash mismatch (expected {expected}, got {actual}). "
            "No write performed."
        )


def verify_function_anchor(
    path: str, function_name: str, expected_function_sha256: Optional[str]
) -> FunctionLocation:
    if not expected_function_sha256:
        raise PatchAbortedError(
            f"ABORT: no expected function-source hash supplied for {function_name}. "
            "Refusing generic search-and-replace."
        )
    with open(path, "r", encoding="utf-8") as f:
        source_text = f.read()
    matches = _find_function_definitions(source_text, function_name)
    if len(matches) == 0:
        raise PatchAbortedError(f"ABORT: function {function_name} not found in {path}")
    if len(matches) > 1:
        raise PatchAbortedError(
            f"ABORT: duplicate definitions of {function_name} found in {path}; refusing."
        )
    match = matches[0]
    if match.source_sha256 != expected_function_sha256:
        raise PatchAbortedError(
            f"ABORT: {function_name} source hash mismatch (expected "
            f"{expected_function_sha256}, got {match.source_sha256}). No write performed."
        )
    return match


def prepare_patch(
    path: str,
    anchor_key: str,
    function_name: str,
    expected_function_sha256: Optional[str],
    replacement_source: str,
) -> str:
    """Returns the fully patched file text WITHOUT writing it anywhere.
    Raises PatchAbortedError on any anchor mismatch.
    """
    verify_target_file_anchor(path, anchor_key)
    match = verify_function_anchor(path, function_name, expected_function_sha256)

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = (
        lines[: match.start_line - 1] + [replacement_source] + lines[match.end_line :]
    )
    return "".join(new_lines)


def main(
    targets: Dict[str, str],
    owner_token: str,
    allow_write: bool = False,
) -> None:
    """Entry point. In this delivery this NEVER writes: allow_write is
    forced False regardless of the argument, and ALLOW_WRITE_HARDCODED
    additionally blocks any accidental future change.
    """
    if owner_token != OWNER_TOKEN:
        raise PatchAbortedError("ABORT: owner token missing or incorrect. No action taken.")

    if not (allow_write and ALLOW_WRITE_HARDCODED):
        raise PatchAbortedError(
            "ABORT: write path is disabled in this delivery (Gate B not executed here). "
            "This call only verifies anchors; it performs no file modification."
        )

    # Unreachable in this delivery by construction.
    for anchor_key, path in targets.items():
        verify_target_file_anchor(path, anchor_key)


if __name__ == "__main__":
    raise SystemExit(
        "live_patcher.py is a library for Gate B tooling only. It performs no "
        "action when run directly, by design, in this delivery."
    )
