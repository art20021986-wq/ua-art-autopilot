"""
cloud/task_073/tools/patcher_v2.py

Point, SHA+AST anchored transforms for CRM-UNIFIED-CATALOG-001 v1.0.

These transforms operate on real live Python source text (fetched GET-only
by gate_a_v2.py, executed by a Codex-run workflow with real credentials).
They never invent source; every transform fails closed by raising
PatchAnchorError if the expected anchor is not found, so live source drift
can never silently produce a wrong patch. This module never talks to
PythonAnywhere itself; it is pure text/AST transformation so it can be unit
tested offline with synthetic fixtures that mirror the anchors documented in
cloud/task_073/evidence/live_probe.json.
"""
from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass


class PatchAnchorError(RuntimeError):
    """Raised when an expected anchor is missing or drifted. Fail closed."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class PatchResult:
    source: str
    changed: bool
    sha_before: str
    sha_after: str


def _require_function(source: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise PatchAnchorError(f"function {name!r} not found in source")


def _function_span(source: str, node: ast.FunctionDef):
    lines = source.splitlines(keepends=True)
    start = sum(len(l) for l in lines[: node.lineno - 1])
    end = sum(len(l) for l in lines[: node.end_lineno])
    return start, end


CONTAINER_BUTTON_TEMPLATE = (
    '        [InlineKeyboardButton("\U0001F4E6 Загружено в контейнер", '
    'callback_data=f"car_setstage:{cid}:sea_loaded")],\n'
    '        [InlineKeyboardButton("\U0001F6A2 В пути", '
    'callback_data=f"car_setstage:{cid}:sea_transit")],\n'
)


def transform_ekran_add_inner_actions(source: str) -> PatchResult:
    """Insert the two container status actions inside konteyner._ekran, once.

    Anchor: the _ekran function must contain a row rendering 'Назад'
    (back-to-card); we insert immediately before that row so the actions
    stay inside the container section.
    """
    sha_before = sha256_text(source)
    node = _require_function(source, "_ekran")
    start, end = _function_span(source, node)
    body = source[start:end]

    if "sea_loaded" in body and "sea_transit" in body:
        return PatchResult(source, False, sha_before, sha_before)

    back_row_pattern = re.compile(
        r'(\n[ \t]*\[InlineKeyboardButton\("[^"]*Назад[^"]*"[^\n]*\],?\n)'
    )
    match = back_row_pattern.search(body)
    if not match:
        raise PatchAnchorError(
            "konteyner._ekran: 'Назад' row anchor not found; refusing to guess insertion point"
        )
    insert_at = match.start(1)
    new_body = body[:insert_at] + "\n" + CONTAINER_BUTTON_TEMPLATE + body[insert_at:]
    new_source = source[:start] + new_body + source[end:]

    if new_source.count('sea_loaded"') != 1 or new_source.count('sea_transit"') != 1:
        raise PatchAnchorError("post-transform inner-action count mismatch; aborting")

    ast.parse(new_source)
    return PatchResult(new_source, True, sha_before, sha256_text(new_source))


def _strip_outer_status_entries(source: str, func_name: str) -> PatchResult:
    """Remove the sea_loaded / sea_transit rows from an outer stage-menu
    builder function, without touching any status entry elsewhere.
    """
    sha_before = sha256_text(source)
    node = _require_function(source, func_name)
    start, end = _function_span(source, node)
    body = source[start:end]

    if "sea_loaded" not in body and "sea_transit" not in body:
        return PatchResult(source, False, sha_before, sha_before)

    row_pattern = re.compile(
        r'[ \t]*\[?InlineKeyboardButton\([^\n]*sea_(?:loaded|transit)[^\n]*\][^\n]*,?\n'
    )
    new_body, count = row_pattern.subn("", body)
    if count != 2:
        raise PatchAnchorError(
            f"{func_name}: expected exactly 2 outer status rows to remove, found {count}"
        )
    new_source = source[:start] + new_body + source[end:]
    if "sea_loaded" in new_source or "sea_transit" in new_source:
        raise PatchAnchorError(f"{func_name}: residual outer status reference after strip")
    ast.parse(new_source)
    return PatchResult(new_source, True, sha_before, sha256_text(new_source))


def transform_gde_mashina_remove_outer(source: str) -> PatchResult:
    return _strip_outer_status_entries(source, "gde_mashina")


def transform_stage_menu_remove_outer(source: str) -> PatchResult:
    return _strip_outer_status_entries(source, "stage_menu")


def transform_toggle_publish_respect_ok(source: str) -> PatchResult:
    """Make cars_ui.toggle_publish honor publikaciya.opublikovat's ok flag,
    roll back the published flag with a read-back compare-and-swap on
    failure, and never send the success message unless ok is True.
    """
    sha_before = sha256_text(source)
    node = _require_function(source, "toggle_publish")
    start, end = _function_span(source, node)
    body = source[start:end]

    if "ROLLBACK_ON_PUBLISH_FAIL_073" in body:
        return PatchResult(source, False, sha_before, sha_before)

    call_pattern = re.compile(
        r'([ \t]*)ok,\s*text\s*=\s*publikaciya\.opublikovat\(([^\n]*)\)\n'
    )
    match = call_pattern.search(body)
    if not match:
        raise PatchAnchorError(
            "cars_ui.toggle_publish: 'ok, text = publikaciya.opublikovat(...)' anchor not found"
        )
    indent, args = match.group(1), match.group(2)
    guard = (
        f"{indent}ok, text = publikaciya.opublikovat({args})\n"
        f"{indent}# ROLLBACK_ON_PUBLISH_FAIL_073\n"
        f"{indent}if not ok:\n"
        f"{indent}    _rb = repo.get_car(cid)\n"
        f"{indent}    if _rb and _rb.get('published') != preimage_published:\n"
        f"{indent}        repo.set_field(cid, 'published', preimage_published)\n"
        f"{indent}        _readback = repo.get_car(cid)\n"
        f"{indent}        if _readback.get('published') != preimage_published:\n"
        f"{indent}            raise RuntimeError('rollback read-back mismatch')\n"
        f"{indent}    await update.effective_message.reply_text('Публикация не выполнена. Данные не изменены.')\n"
        f"{indent}    return\n"
    )
    new_body = body[: match.start()] + guard + body[match.end():]

    if not re.search(r'Машина видна клиентам в каталоге\.', new_body):
        raise PatchAnchorError("success message anchor not found for guard placement")

    new_source = source[:start] + new_body + source[end:]
    ast.parse(new_source)
    return PatchResult(new_source, True, sha_before, sha256_text(new_source))


def transform_seo068_drop_stale_precondition(source: str, func_name: str = "_ua_seo068_normalize") -> PatchResult:
    """Remove only the precondition that requires an already-existing live
    <UA>-diag.html before the new bundle is built. All other fail-closed
    checks (canonical, robots, exact href, CTA, insertion point) stay
    untouched.
    """
    sha_before = sha256_text(source)
    node = _require_function(source, func_name)
    start, end = _function_span(source, node)
    body = source[start:end]

    if "SEO068_DIAGNOSTIC_TARGET_MISSING" not in body:
        raise PatchAnchorError(f"{func_name}: SEO068_DIAGNOSTIC_TARGET_MISSING anchor missing")

    stale_block_pattern = re.compile(
        r'[ \t]*if not os\.path\.exists\([^\n]*diag[^\n]*\):\n'
        r'([ \t]+raise[^\n]*SEO068_DIAGNOSTIC_TARGET_MISSING[^\n]*\n)+',
        re.IGNORECASE,
    )
    new_body, count = stale_block_pattern.subn("", body)
    if count != 1:
        raise PatchAnchorError(
            f"{func_name}: expected exactly one stale-precondition block, found {count}"
        )
    if "SEO068_DIAGNOSTIC_TARGET_MISSING" in new_body:
        raise PatchAnchorError(f"{func_name}: guard string still present after removal -- unexpected shape")

    new_source = source[:start] + new_body + source[end:]
    ast.parse(new_source)
    return PatchResult(new_source, True, sha_before, sha256_text(new_source))
