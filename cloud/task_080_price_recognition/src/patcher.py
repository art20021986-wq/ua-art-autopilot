"""
TASK 080 — narrow, fail-closed integration patcher (design/candidate only).

This module NEVER touches production, crm.db, or the public site. It is a
local, offline tool that:

  1. Accepts a manifest of {file_path: expected_sha256, function_name:
     expected_function_sha256} pairs that MUST have been produced by a
     genuine live Gate A GET (see ../audit/GATE_A_STATUS.md).
  2. Reads the local copy of each target file that the controller has
     placed for inspection.
  3. Recomputes whole-file SHA-256 and the SHA-256 of the named active
     function's source block.
  4. Refuses (fails closed) unless every hash matches exactly and there is
     no duplicate active definition of the target function in the file.
  5. Only if all checks pass does it apply the narrow, reviewed patch that
     wires the shared `price_parser.parse_sale_price_message` into the
     caller instead of the old narrow regex / colon-label logic.

In this delivery round no live hashes exist, so `expected_hashes` is empty
and `run()` always returns a FAIL_CLOSED result. This is intentional.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class PatchTarget:
    file_path: str
    expected_whole_file_sha256: str
    function_name: str
    expected_function_sha256: str


@dataclass
class PatchResult:
    ok: bool
    reason: str
    file_path: Optional[str] = None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _extract_function_source(file_text: str, function_name: str):
    """Return (count_of_definitions, source_of_first_definition_or_None).
    Uses a simple indentation-aware scan; good enough to detect duplicate
    top-level/class-level active defs for the fail-closed duplicate check.
    """
    pattern = re.compile(
        rf"^([ \t]*)def\s+{re.escape(function_name)}\s*\(", re.MULTILINE
    )
    matches = list(pattern.finditer(file_text))
    if not matches:
        return 0, None
    m = matches[0]
    indent = m.group(1)
    start = m.start()
    lines = file_text[start:].splitlines(keepends=True)
    out_lines = [lines[0]]
    for line in lines[1:]:
        if line.strip() == "":
            out_lines.append(line)
            continue
        cur_indent = re.match(r"^([ \t]*)", line).group(1)
        if len(cur_indent) <= len(indent) and line.strip() != "":
            break
        out_lines.append(line)
    return len(matches), "".join(out_lines)


def verify_target(local_file_text: str, target: PatchTarget) -> PatchResult:
    whole_hash = _sha256(local_file_text.encode("utf-8"))
    if whole_hash != target.expected_whole_file_sha256:
        return PatchResult(False, "WHOLE_FILE_HASH_MISMATCH", target.file_path)

    count, func_src = _extract_function_source(local_file_text, target.function_name)
    if count == 0:
        return PatchResult(False, "FUNCTION_NOT_FOUND", target.file_path)
    if count > 1:
        return PatchResult(False, "DUPLICATE_ACTIVE_DEFINITION", target.file_path)

    func_hash = _sha256(func_src.encode("utf-8"))
    if func_hash != target.expected_function_sha256:
        return PatchResult(False, "FUNCTION_HASH_MISMATCH", target.file_path)

    return PatchResult(True, "VERIFIED", target.file_path)


def run(local_files: Dict[str, str], expected_hashes: Dict[str, PatchTarget]) -> PatchResult:
    """Top-level entry point. Fails closed unless every configured target
    verifies. `local_files` maps file_path -> file text (already read by
    the controller from a real Gate A GET). `expected_hashes` maps
    file_path -> PatchTarget as produced by that same Gate A round.
    """
    if not expected_hashes:
        return PatchResult(False, "NO_LIVE_GATE_A_HASHES_SUPPLIED")

    for file_path, target in expected_hashes.items():
        text = local_files.get(file_path)
        if text is None:
            return PatchResult(False, "TARGET_FILE_NOT_PROVIDED", file_path)
        result = verify_target(text, target)
        if not result.ok:
            return result

    # All targets verified. In this round, no live hashes exist, so this
    # line is unreachable and the function always returns FAIL_CLOSED above.
    return PatchResult(True, "ALL_TARGETS_VERIFIED_PATCH_ELIGIBLE")
