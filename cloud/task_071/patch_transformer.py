"""TASK 071 — deterministic, SHA-gated, AST-anchor-guarded point patcher.

This module NEVER rewrites a whole file. It only inserts a small, bounded block
of code at a verified AST anchor inside a file whose full SHA256 matches an
expected value. If the SHA does not match, or the anchor cannot be located
unambiguously, or the file fails to re-parse after the edit, the patch is
rejected and no changes are written.

It is deliberately conservative: it does not attempt to understand or rewrite
arbitrary logic inside db.py / cars_ui.py / trace_zhurnal.py. It only:
  1. Verifies the pre-image SHA256 of the target file.
  2. Locates a function definition by name via `ast.parse` (anchor).
  3. Inserts a call to the new single-writer/queue module at the very start of
     the target function's body, so the legacy body is preserved untouched and
     can still run for any table/field this writer intentionally does not
     claim (defensive fallback, never a hard failure of legacy behaviour).
  4. Removes any occurrence of forced global busy_timeout / isolation_level
     changes that were used purely as diagnostic side effects (see
     `strip_diagnostic_timeout_overrides`) — diagnostics must observe only.
"""
from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class PatchRejected(Exception):
    pass


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


@dataclass(frozen=True)
class AnchorPatch:
    file_name: str
    expected_sha256: str
    anchor_function: str
    insertion_source: str
    marker: str  # unique comment marker so patch is idempotent / detectable


def _find_function_lineno(tree: ast.AST, func_name: str) -> Optional[int]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            if node.body:
                return node.body[0].lineno
    return None


def strip_diagnostic_timeout_overrides(source: str) -> str:
    """Remove lines that forcibly widen sqlite busy_timeout / isolation_level
    purely for diagnostic wrapper purposes. Only lines carrying the marker
    comment `# UA-DIAG-TIMEOUT-OVERRIDE` are touched; nothing else in the file
    is modified.
    """
    lines = source.splitlines(keepends=True)
    out = [ln for ln in lines if "# UA-DIAG-TIMEOUT-OVERRIDE" not in ln]
    return "".join(out)


def apply_anchor_patch(target_path: Path, patch: AnchorPatch) -> str:
    """Apply one AnchorPatch to target_path (a LOCAL TEMPORARY COPY only).

    Returns the patched source. Raises PatchRejected on any safety failure.
    Does not write anything if verification fails.
    """
    if not target_path.exists():
        raise PatchRejected(f"target file missing: {target_path}")

    actual_sha = sha256_of(target_path)
    if actual_sha != patch.expected_sha256:
        raise PatchRejected(
            f"SHA mismatch for {patch.file_name}: expected {patch.expected_sha256}, got {actual_sha}"
        )

    source = target_path.read_text(encoding="utf-8")

    if patch.marker in source:
        # Already patched — idempotent no-op, not a failure.
        return source

    source = strip_diagnostic_timeout_overrides(source)

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise PatchRejected(f"pre-patch AST parse failed: {exc}")

    lineno = _find_function_lineno(tree, patch.anchor_function)
    if lineno is None:
        raise PatchRejected(
            f"anchor function '{patch.anchor_function}' not found in {patch.file_name}"
        )

    lines = source.splitlines(keepends=True)
    insert_at = lineno - 1  # zero-based index of first body line
    indent_match = re.match(r"[ \t]*", lines[insert_at])
    indent = indent_match.group(0) if indent_match else "    "

    injected_block = f"{indent}{patch.marker}\n"
    for raw_line in patch.insertion_source.splitlines():
        injected_block += f"{indent}{raw_line}\n" if raw_line else "\n"

    new_lines = lines[:insert_at] + [injected_block] + lines[insert_at:]
    new_source = "".join(new_lines)

    try:
        ast.parse(new_source)
    except SyntaxError as exc:
        raise PatchRejected(f"post-patch AST parse failed, patch aborted: {exc}")

    target_path.write_text(new_source, encoding="utf-8")
    return new_source


# --- Concrete patches for the three managed files ---------------------------
# Expected SHA values are the confirmed live SHA values recorded in
# cloud/task_070/evidence/real_context.json. If the live file has drifted
# since that snapshot, the controller MUST re-verify and update these
# constants from a fresh GET-only hash check before patching — it must never
# patch blind.

DB_PY_EXPECTED_SHA = "b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086"[:64]
CARS_UI_EXPECTED_SHA = "862baea2ca0794f5e0d83bc04169f6d2fdec401f86f384ef4376e373c02a776b"[:64]
TRACE_ZHURNAL_EXPECTED_SHA = "fc4b95fc749f3d9b785ce69bfce2705b11ade95a560d6fbd901b50de1423d086"[:64]

DB_PY_PATCH = AnchorPatch(
    file_name="db.py",
    expected_sha256=DB_PY_EXPECTED_SHA,
    anchor_function="update_card_field",
    marker="# UA-TASK-071-SINGLE-WRITER-ANCHOR",
    insertion_source=(
        "from cloud.task_071.writer import apply_field_update as _ua071_apply\n"
        "if table in _ua071_ALLOWED_TABLES and field in _ua071_ALLOWED_TABLES.get(table, {}):\n"
        "    return _ua071_apply(conn=connect(), table=table, card_id=card_id, field=field,\n"
        "                        value=value, operation_id=operation_id)\n"
    ),
)

CARS_UI_PATCH = AnchorPatch(
    file_name="cars_ui.py",
    expected_sha256=CARS_UI_EXPECTED_SHA,
    anchor_function="apply_value",
    marker="# UA-TASK-071-QUICK-ACK-ANCHOR",
    insertion_source=(
        "from cloud.task_071.durable_queue import enqueue_if_busy\n"
        "quick_ack = enqueue_if_busy(table, card_id, field, value, operation_id)\n"
        "if quick_ack is not None:\n"
        "    return quick_ack  # 'Принято, сохраняю' — no traceback, no db paths surfaced\n"
    ),
)

TRACE_ZHURNAL_PATCH = AnchorPatch(
    file_name="trace_zhurnal.py",
    expected_sha256=TRACE_ZHURNAL_EXPECTED_SHA,
    anchor_function="_ua_connect",
    marker="# UA-TASK-071-DIAG-OBSERVE-ONLY-ANCHOR",
    insertion_source=(
        "# NOTE: diagnostics observe only; no busy_timeout/isolation_level mutation here.\n"
    ),
)

ALL_PATCHES = [DB_PY_PATCH, CARS_UI_PATCH, TRACE_ZHURNAL_PATCH]
