#!/usr/bin/env python3
"""
Production-ready-but-NOT-EXECUTED patch descriptor for TASK 077.

This file describes the exact surgical edits required in the real, currently
active renderer files, to be applied ONLY during a separately approved Gate B
run, after Gate A confirms exact file identity via SHA256.

Because the live file contents were not fetched in this environment (Gate A
not executed here), this module expresses the edits as named, testable
transformations against an in-memory text model rather than as a blind
line-numbered diff against unseen live files. The Gate B controller must
re-anchor these transformations against the real file text confirmed by
Gate A before writing anything.

"""
from __future__ import annotations

import re

CANONICAL_LABEL = "На пароме"
ACTION_BUTTON_LABEL = "Загружено в контейнер"
STANDALONE_TRANSIT_BUTTON_PATTERNS = [
    re.compile(r"['\"]В пути['\"]\s*,\s*['\"]sea_transit['\"]"),
    re.compile(r"car_setstage:\{[a-zA-Z_]+\}:sea_transit"),
    re.compile(r"car_setstage:<cid>:sea_transit"),
]


def find_standalone_transit_buttons(source_text: str):
    """Return list of (pattern, matches) for standalone 'В пути' buttons that
    must be removed from active renderers. sold_transit is never matched."""
    findings = []
    for pat in STANDALONE_TRANSIT_BUTTON_PATTERNS:
        matches = pat.findall(source_text)
        if matches:
            findings.append((pat.pattern, matches))
    return findings


def count_active_sea_loaded_buttons(source_text: str) -> int:
    return len(re.findall(r"car_setstage:[^:]*:sea_loaded", source_text))


def assert_single_sea_loaded_button(source_text: str) -> None:
    n = count_active_sea_loaded_buttons(source_text)
    if n != 1:
        raise AssertionError(f"expected exactly 1 active sea_loaded button, found {n}")


def relabel_status_display(status: str) -> str:
    """CRM display label mapping for the menu/status text."""
    if status in ("sea_loaded", "sea_transit"):
        return CANONICAL_LABEL
    raise ValueError(f"relabel_status_display called for unmanaged status: {status}")


def site_badge_and_category(status: str):
    """Public site badge + category mapping. No standalone 'В пути' category exists."""
    if status in ("sea_loaded", "sea_transit"):
        return {"badge": "На пароме", "category": "more"}
    raise ValueError(f"site_badge_and_category called for unmanaged status: {status}")


def remove_standalone_transit_button(keyboard_rows):
    """Given a list of button rows (each row a list of (label, callback) tuples),
    return a new list with any standalone 'В пути' / sea_transit-only button
    removed, and confirm the sea_loaded action button (labelled
    'Загружено в контейнер') is present exactly once. sold_transit rows are
    left untouched."""
    out_rows = []
    sea_loaded_count = 0
    for row in keyboard_rows:
        new_row = []
        for label, callback in row:
            if callback.endswith(":sea_transit") and "sold_transit" not in callback:
                # drop standalone transit button entirely
                continue
            if callback.endswith(":sea_loaded"):
                sea_loaded_count += 1
                new_row.append((ACTION_BUTTON_LABEL, callback))
                continue
            new_row.append((label, callback))
        if new_row:
            out_rows.append(new_row)
    if sea_loaded_count != 1:
        raise AssertionError(
            f"post-patch invariant violated: sea_loaded button count={sea_loaded_count}, expected 1"
        )
    return out_rows
