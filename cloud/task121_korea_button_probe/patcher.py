#!/usr/bin/env python3
"""Pure, fail-closed transform for restoring only the CRM button «В Корее»."""
from __future__ import annotations

import ast
import re
from typing import Any


KOREA_CODE = "kr_bought"
KOREA_LABEL = "В Корее"
HIDDEN_CODES = ("sea_loaded", "sea_transit", "ua_handed")
OLD_HIDDEN_LITERAL = "{'kr_bought', 'sea_loaded', 'sea_transit', 'ua_handed'}"
NEW_HIDDEN_LITERAL = "{'sea_loaded', 'sea_transit', 'ua_handed'}"
OLD_CALLBACK_PATTERN = (
    r'^car_setstage:\d+:(?:kr_bought|sea_loaded|sea_transit|ua_handed)$'
)
NEW_CALLBACK_PATTERN = (
    r'^car_setstage:\d+:(?:sea_loaded|sea_transit|ua_handed)$'
)


class PatchError(RuntimeError):
    pass


def _compile(source: str, filename: str) -> None:
    compile(source, filename, "exec")


def _status_map(source: str) -> dict[str, tuple[int, str]]:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "STATUSES"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if not isinstance(value, dict):
                break
            return value
    raise PatchError("STATUSES_NOT_FOUND")


def _replace_hidden(source: str, filename: str) -> str:
    old = "_UA117_HIDDEN_STATUS_CODES = frozenset(%s)" % OLD_HIDDEN_LITERAL
    new = "_UA117_HIDDEN_STATUS_CODES = frozenset(%s)" % NEW_HIDDEN_LITERAL
    if source.count(new) == 1 and source.count(old) == 0:
        return source
    if source.count(old) != 1 or source.count(new) != 0:
        raise PatchError("%s_HIDDEN_SET_SHAPE" % filename.upper())
    return source.replace(old, new, 1)


def patch_cars_ui(source: str) -> str:
    _compile(source, "cars_ui.py")
    source = _replace_hidden(source, "cars_ui")
    old = 'pattern=r"%s"' % OLD_CALLBACK_PATTERN.replace("\\", "\\")
    new = 'pattern=r"%s"' % NEW_CALLBACK_PATTERN.replace("\\", "\\")
    if source.count(new) == 1 and source.count(old) == 0:
        result = source
    elif source.count(old) == 1 and source.count(new) == 0:
        result = source.replace(old, new, 1)
    else:
        raise PatchError("CARS_UI_CALLBACK_PATTERN_SHAPE")
    _compile(result, "cars_ui.py")
    return result


def patch_konteyner(source: str) -> str:
    _compile(source, "konteyner.py")
    result = _replace_hidden(source, "konteyner")
    _compile(result, "konteyner.py")
    return result


def patch_schema(source: str) -> str:
    _compile(source, "cars_schema.py")
    statuses = _status_map(source)
    current = statuses.get(KOREA_CODE)
    if current == (1, KOREA_LABEL):
        return source
    if current != (1, "Выкуплено, на нашей парковке"):
        raise PatchError("SCHEMA_KOREA_PREIMAGE")
    pattern = re.compile(
        r'("kr_bought"\s*:\s*\(\s*1\s*,\s*)'
        r'"Выкуплено, на нашей парковке"(\s*\),)'
    )
    result, count = pattern.subn(r'\1"В Корее"\2', source, count=1)
    if count != 1:
        raise PatchError("SCHEMA_KOREA_SHAPE")
    _compile(result, "cars_schema.py")
    return result


def verify(cars_ui: str, konteyner: str, schema: str) -> dict[str, Any]:
    _compile(cars_ui, "cars_ui.py")
    _compile(konteyner, "konteyner.py")
    _compile(schema, "cars_schema.py")
    statuses = _status_map(schema)
    if statuses.get(KOREA_CODE) != (1, KOREA_LABEL):
        raise PatchError("KOREA_LABEL_NOT_EXACT")
    hidden_line = "_UA117_HIDDEN_STATUS_CODES = frozenset(%s)" % NEW_HIDDEN_LITERAL
    if cars_ui.count(hidden_line) != 1 or konteyner.count(hidden_line) != 1:
        raise PatchError("HIDDEN_SET_NOT_EXACT")
    if "code not in _UA117_HIDDEN_STATUS_CODES" not in cars_ui:
        raise PatchError("PRIMARY_MENU_FILTER_MISSING")
    if "if code in _UA117_HIDDEN_STATUS_CODES:" not in cars_ui:
        raise PatchError("PRIMARY_SETTER_GUARD_MISSING")
    if "code not in _UA117_HIDDEN_STATUS_CODES" not in konteyner:
        raise PatchError("FALLBACK_MENU_FILTER_MISSING")
    if ('pattern=r"%s"' % NEW_CALLBACK_PATTERN) not in cars_ui:
        raise PatchError("STALE_CALLBACK_GUARD_MISSING")
    if OLD_CALLBACK_PATTERN in cars_ui or OLD_HIDDEN_LITERAL in cars_ui or OLD_HIDDEN_LITERAL in konteyner:
        raise PatchError("KOREA_STILL_BLOCKED")
    visible = [code for code in statuses if code not in HIDDEN_CODES]
    if KOREA_CODE not in visible:
        raise PatchError("KOREA_NOT_VISIBLE")
    if any(code in visible for code in HIDDEN_CODES):
        raise PatchError("REMOVED_BUTTON_RESTORED")
    return {
        "button_code": KOREA_CODE,
        "button_label": KOREA_LABEL,
        "button_count_added": 1,
        "hidden_codes": list(HIDDEN_CODES),
        "primary_menu": "PASS",
        "fallback_menu": "PASS",
        "callback": "ENABLED",
        "other_removed_buttons": "STILL_HIDDEN",
        "schema_status_count": len(statuses),
    }
