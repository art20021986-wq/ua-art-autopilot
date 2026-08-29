#!/usr/bin/env python3
"""Exact, self-contained cars_ui.py patch for CRM-VIN4-TITLE-001 v1.0."""
from __future__ import annotations

import ast
import hashlib
import re

CONTRACT = "CRM-VIN4-TITLE-001-V1.0"
START = "# CRM-VIN4-TITLE-001-V1.0:START"
END = "# CRM-VIN4-TITLE-001-V1.0:END"

# Fresh GET-only production evidence, 2026-08-29.  Full-file drift is allowed;
# these exact function bodies are not.  A remote installer also rechecks the
# full source SHA between shadow and atomic replacement.
EXPECTED_FUNCTION_SHA = {
    "render": "09fbb1baabdf297a24a2f4fb757464836a718edc086680f699218cacf77c97a8",
    "cars_list": "058a155a5910fa7819f3a4d9b701b1cd98e8639493c0d8af8ad5f0eeb79395c0",
}

OLD_RENDER_TITLE = '''    L.append("<b>%s</b>" % (card.get("auto_number") or "#%s" % card.get("id")))'''
NEW_RENDER_TITLE = '''    L.append(_ua082_vin4_title_html(card))'''

OLD_LIST_TITLE = '''        lines.append("<b>%s</b> · %s" % (nomer, name))'''
NEW_LIST_TITLE = '''        lines.append(_ua082_vin4_title_html(card))'''

OLD_LIST_BUTTON = '''        rows.append([InlineKeyboardButton("%s · %s" % (nomer, name[:28]),
                                          callback_data="car_open:%d" % card["id"])])'''
NEW_LIST_BUTTON = '''        rows.append([InlineKeyboardButton(_ua082_vin4_button_label(card),
                                          callback_data="car_open:%d" % card["id"])])'''

HELPER = r'''# CRM-VIN4-TITLE-001-V1.0:START
import html as _ua082_html
import re as _ua082_re

_UA082_VIN_RE = _ua082_re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
_UA082_BUTTON_LIMIT = 64


def _ua082_normalize_vin(value):
    return _ua082_re.sub(r"[\s-]+", "", str(value or "")).upper()


def _ua082_vin4(card):
    vin = _ua082_normalize_vin((card or {}).get("vin"))
    return vin[-4:] if _UA082_VIN_RE.fullmatch(vin) else None


def _ua082_title_parts(card):
    card = card or {}
    identifier = str(card.get("auto_number") or "#%s" % card.get("id") or "—").strip()
    name = " ".join(str(value).strip() for value in (
        card.get("brand"), card.get("model"), card.get("year")
    ) if value not in (None, "") and str(value).strip()) or "без названия"
    return identifier, name


def _ua082_vin4_title_html(card):
    identifier, name = _ua082_title_parts(card)
    vin4 = _ua082_vin4(card)
    identifier = _ua082_html.escape(identifier, quote=True)
    name = _ua082_html.escape(name, quote=True)
    suffix = "VIN <b>%s</b>" % vin4 if vin4 else "<b>VIN НЕТ</b>"
    return "<b>%s</b> · %s · %s" % (identifier, name, suffix)


def _ua082_vin4_button_label(card):
    identifier, name = _ua082_title_parts(card)
    vin4 = _ua082_vin4(card)
    suffix = " · VIN %s" % vin4 if vin4 else " · VIN НЕТ"
    base = "%s · %s" % (identifier, name)
    available = _UA082_BUTTON_LIMIT - len(suffix)
    if len(base) > available:
        if available > 1:
            base = base[:available - 1].rstrip() + "…"
        else:
            base = base[:max(0, available)]
    return base + suffix
# CRM-VIN4-TITLE-001-V1.0:END'''


class PatchBlocked(RuntimeError):
    pass


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _functions(source: str):
    tree = ast.parse(source, filename="cars_ui.py")
    lines = source.splitlines(keepends=True)
    result = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        segment = "".join(lines[node.lineno - 1:node.end_lineno])
        result.setdefault(node.name, []).append((node, segment))
    return result


def _one_function(source: str, name: str):
    matches = _functions(source).get(name, [])
    if len(matches) != 1:
        raise PatchBlocked("FUNCTION_COUNT:%s:%d" % (name, len(matches)))
    return matches[0]


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise PatchBlocked("ANCHOR_COUNT:%s:%d" % (label, text.count(old)))
    return text.replace(old, new, 1)


def _helper_namespace():
    namespace = {}
    exec(compile(HELPER, "<task082-helper>", "exec"), namespace)
    return namespace


def validate_helper() -> dict:
    ns = _helper_namespace()
    fixtures = [
        ({"id": 1, "auto_number": "UA-0001", "brand": "Mercedes-Benz", "model": "E 220", "year": 2017, "vin": "WDD2120011A543001"}, "3001"),
        ({"id": 13, "auto_number": "UA-0013", "brand": "Mercedes-Benz", "model": "Б-КЛАССА", "year": 2015, "vin": "WDD2462121J00253X"}, "253X"),
        ({"id": 9999, "auto_number": "UA-9999", "brand": "<Kia>", "model": "K5", "year": 2026, "vin": None}, None),
    ]
    for card, expected in fixtures:
        title = ns["_ua082_vin4_title_html"](card)
        button = ns["_ua082_vin4_button_label"](card)
        if expected:
            assert title.endswith("VIN <b>%s</b>" % expected), title
            assert button.endswith("VIN %s" % expected), button
        else:
            assert title.endswith("<b>VIN НЕТ</b>"), title
            assert button.endswith("VIN НЕТ"), button
        assert len(button) <= 64
        assert button.count("VIN") == 1
        assert title.count("VIN") == 1 and title.count("<b>") == 2
        assert "WDD" not in title and "WDD" not in button
    assert "&lt;Kia&gt;" in ns["_ua082_vin4_title_html"](fixtures[-1][0])
    return {"fixtures": len(fixtures), "future_card": True, "html_escape": True}


def patch_source(source: str) -> tuple[str, dict]:
    if source.count(START) or source.count(END):
        if source.count(START) != 1 or source.count(END) != 1:
            raise PatchBlocked("MARKER_COUNT")
        validate_patched(source)
        return source, {"already_installed": True, "changed_functions": []}

    before_functions = _functions(source)
    anchors = {}
    for name, expected in EXPECTED_FUNCTION_SHA.items():
        _node, segment = _one_function(source, name)
        actual = _sha(segment)
        anchors[name] = actual
        if actual != expected:
            raise PatchBlocked("FUNCTION_SHA_DRIFT:%s:%s" % (name, actual))

    render_node, render_segment = _one_function(source, "render")
    list_node, list_segment = _one_function(source, "cars_list")
    render_new = _replace_once(render_segment, OLD_RENDER_TITLE, NEW_RENDER_TITLE, "render_title")
    list_new = _replace_once(list_segment, OLD_LIST_TITLE, NEW_LIST_TITLE, "list_title")
    list_new = _replace_once(list_new, OLD_LIST_BUTTON, NEW_LIST_BUTTON, "list_button")

    lines = source.splitlines(keepends=True)
    replacements = [
        (render_node.lineno - 1, render_node.end_lineno, render_new),
        (list_node.lineno - 1, list_node.end_lineno, list_new),
    ]
    for start, end, value in sorted(replacements, reverse=True):
        lines[start:end] = [value if value.endswith("\n") else value + "\n"]
    candidate = "".join(lines)

    needle = "def render(card, staff):"
    if candidate.count(needle) != 1:
        raise PatchBlocked("HELPER_INSERTION_ANCHOR")
    candidate = candidate.replace(needle, HELPER + "\n\n\n" + needle, 1)
    compile(candidate, "cars_ui.py", "exec")

    after_functions = _functions(candidate)
    for name, items in before_functions.items():
        if name in {"render", "cars_list"}:
            continue
        before_segments = [segment for _node, segment in items]
        after_segments = [segment for _node, segment in after_functions.get(name, [])]
        if before_segments != after_segments:
            raise PatchBlocked("UNRELATED_FUNCTION_CHANGED:%s" % name)

    validate_patched(candidate)
    return candidate, {
        "already_installed": False,
        "changed_functions": ["render", "cars_list"],
        "function_sha_before": anchors,
        "source_sha_before": _sha(source),
        "source_sha_after": _sha(candidate),
    }


def validate_patched(source: str) -> None:
    compile(source, "cars_ui.py", "exec")
    if source.count(START) != 1 or source.count(END) != 1:
        raise PatchBlocked("MARKER_INVALID")
    _node, render_segment = _one_function(source, "render")
    _node, list_segment = _one_function(source, "cars_list")
    if render_segment.count("_ua082_vin4_title_html(card)") != 1:
        raise PatchBlocked("RENDER_CONTRACT")
    if list_segment.count("_ua082_vin4_title_html(card)") != 1:
        raise PatchBlocked("LIST_TITLE_CONTRACT")
    if list_segment.count("_ua082_vin4_button_label(card)") != 1:
        raise PatchBlocked("LIST_BUTTON_CONTRACT")
    if list_segment.count('callback_data="car_open:%d" % card["id"]') != 1:
        raise PatchBlocked("CALLBACK_CHANGED")
    validate_helper()


def self_test() -> None:
    validate_helper()
    fixture = '''from object import InlineKeyboardButton, InlineKeyboardMarkup\n\n''' + '''def render(card, staff):\n    L = []\n    L.append("<b>%s</b>" % (card.get("auto_number") or "#%s" % card.get("id")))\n    return "\\n".join(L)\n\n''' + '''async def cars_list(update, context):\n    cards = []\n    lines = []\n    rows = []\n    for card in cards:\n        card = card\n        nomer = card.get("auto_number") or "#%d" % card["id"]\n        name = " ".join(str(x) for x in (card.get("brand"), card.get("model"), card.get("year")) if x) or "без названия"\n        lines.append("<b>%s</b> · %s" % (nomer, name))\n        rows.append([InlineKeyboardButton("%s · %s" % (nomer, name[:28]),\n                                          callback_data="car_open:%d" % card["id"])])\n'''
    # Fixture hashes intentionally differ from production, so exercise the
    # exact transforms directly and keep the production anchor test separate.
    render = _replace_once(_one_function(fixture, "render")[1], OLD_RENDER_TITLE, NEW_RENDER_TITLE, "fixture_render")
    listing = _replace_once(_one_function(fixture, "cars_list")[1], OLD_LIST_TITLE, NEW_LIST_TITLE, "fixture_list")
    listing = _replace_once(listing, OLD_LIST_BUTTON, NEW_LIST_BUTTON, "fixture_button")
    assert "_ua082_vin4_title_html(card)" in render
    assert "_ua082_vin4_button_label(card)" in listing


if __name__ == "__main__":
    self_test()
    print("TASK082_EXACT_PATCH_SELF_TEST_PASS")
