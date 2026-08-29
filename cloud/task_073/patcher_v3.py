"""
TASK_073 ROUND 4 - patcher_v3.py

Point transforms applied to live CRM source text. Each transform operates on
the exact live function bodies described in cloud/task_073/evidence/live_probe.json
(ROUND 4 correction). No file is rewritten wholesale: every transform is a
narrow, anchored substitution that preserves everything else byte-for-byte.

All transforms are pure string->string functions so they can be exercised in
unit tests against synthetic fixtures that reproduce the exact live anchors,
and later applied to genuine GET-fetched live source inside gate_a_v3.py /
gate_b_installer_v3.py. No network access happens in this module.
"""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass


class Task073TransformError(RuntimeError):
    """Raised when an expected anchor is not found (fail closed)."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class TransformResult:
    name: str
    before_sha256: str
    after_sha256: str
    changed: bool
    source: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Task073TransformError(message)


def transform_gde_mashina_exclude_outer(source: str) -> TransformResult:
    """konteyner.gde_mashina: exclude sea_loaded/sea_transit from the outer
    stage-status keyboard while keeping every other status untouched."""
    before = source
    anchor = "if stage_no == nomer_etapa"
    _require(anchor in source, "gde_mashina anchor not found")
    replacement = 'if stage_no == nomer_etapa and code not in ("sea_loaded", "sea_transit")'
    _require(replacement not in source, "gde_mashina already patched (double-apply guard)")
    new_source = source.replace(anchor, replacement, 1)
    return TransformResult(
        "gde_mashina_exclude_outer",
        sha256_text(before),
        sha256_text(new_source),
        new_source != before,
        new_source,
    )


def transform_stage_menu_exclude_outer(source: str) -> TransformResult:
    """cars_ui.stage_menu: same exclusion, independent anchor/variable name."""
    before = source
    anchor = "if stage_no == number"
    _require(anchor in source, "stage_menu anchor not found")
    replacement = 'if stage_no == number and code not in ("sea_loaded", "sea_transit")'
    _require(replacement not in source, "stage_menu already patched (double-apply guard)")
    new_source = source.replace(anchor, replacement, 1)
    return TransformResult(
        "stage_menu_exclude_outer",
        sha256_text(before),
        sha256_text(new_source),
        new_source != before,
        new_source,
    )


_EKRAN_MARKER = "# TASK073_INNER_CONTAINER_ACTIONS"


def transform_ekran_add_inner_actions(source: str, rows_anchor: str) -> TransformResult:
    """konteyner._ekran: insert exactly one working sea_loaded and one
    sea_transit row into the container section, right after the caller
    supplied anchor line (the last number/date/days control row appended to
    `rows` before navigation/clear controls)."""
    before = source
    _require(rows_anchor in source, "_ekran rows anchor not found")
    _require(_EKRAN_MARKER not in source, "_ekran already patched (double-apply guard)")
    insertion = (
        rows_anchor + "\n"
        "    " + _EKRAN_MARKER + "\n"
        '    rows.append([InlineKeyboardButton("Загружено в контейнер", '
        'callback_data=f"car_setstage:{cid}:sea_loaded")])\n'
        '    rows.append([InlineKeyboardButton("В пути", '
        'callback_data=f"car_setstage:{cid}:sea_transit")])'
    )
    new_source = source.replace(rows_anchor, insertion, 1)
    return TransformResult(
        "ekran_add_inner_actions",
        sha256_text(before),
        sha256_text(new_source),
        new_source != before,
        new_source,
    )


_SEO068_STALE_PRECONDITION = (
    "if not any(_ua_seo068_os.path.isfile(_ua_seo068_os.path.join(root, target)) "
    "for root in ('/home/Carix/video', '/home/Carix/site')):\n"
    "        raise RuntimeError('SEO068_DIAGNOSTIC_TARGET_MISSING:' + identifier)\n"
)


def transform_seo068_drop_stale_precondition(source: str) -> TransformResult:
    """Remove only the stale 'old diagnostic file must already exist'
    precondition shared by stranica.py / master_card.py / yadro.py.
    Canonical/robots/exact-href/CTA/insertion-point guards are untouched."""
    before = source
    _require(_SEO068_STALE_PRECONDITION in source, "seo068 stale precondition anchor not found")
    new_source = source.replace(_SEO068_STALE_PRECONDITION, "", 1)
    return TransformResult(
        "seo068_drop_stale_precondition",
        sha256_text(before),
        sha256_text(new_source),
        new_source != before,
        new_source,
    )


_TOGGLE_PUBLISH_ANCHOR = "_ok_rem2, _txt_rem2 = await _aio_rem2.to_thread(_pub_rem2.opublikovat,"


def transform_toggle_publish_respect_ok(source: str, full_old_block: str, full_new_block: str) -> TransformResult:
    """cars_ui.toggle_publish: honour publisher ok flag, roll DB flag back on
    failure with read-back, and never emit the false success message."""
    before = source
    _require(_TOGGLE_PUBLISH_ANCHOR in source, "toggle_publish anchor not found")
    _require(full_old_block in source, "toggle_publish exact block not found")
    new_source = source.replace(full_old_block, full_new_block, 1)
    return TransformResult(
        "toggle_publish_respect_ok",
        sha256_text(before),
        sha256_text(new_source),
        new_source != before,
        new_source,
    )


def compile_check(source: str, filename: str) -> None:
    try:
        ast.parse(source, filename=filename)
    except SyntaxError as exc:  # pragma: no cover - fail closed path
        raise Task073TransformError("{} failed to compile: {}".format(filename, exc)) from exc
