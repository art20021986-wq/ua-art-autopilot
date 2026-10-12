#!/usr/bin/env python3
"""Owner menu without «Отчёт по клиентам», «Запуск оптимизации» and «Ещё» in the exact installed cars_ui.py.

Owner request 2026-10-12: remove these sections from the CRM bot. All three
buttons (and the «Ещё» submenu entry) are added by one function,
with_stats_button. The replacement keeps its existing job — drop HIDE buttons —
and now also drops the buttons that used to move into «Ещё». Nothing else in
the file changes; the old handlers stay registered, so buttons in older chat
messages keep answering instead of failing.
"""
from __future__ import annotations

import ast
import hashlib
import sys

# Installed source after CRM-FIELD-INPUT-INSTALL-20261012-R4 (receipt code_sha256).
EXPECTED_SHA256 = 'ce0d132710bfc1e2371758bda0d5159a6756bd82305843c109edb91e522e939b'
TARGET = 'with_stats_button'
REMOVED = ('crm_stats', 'crm_optimize', 'crm_more')

REPLACEMENT = '''def with_stats_button(markup):
    """Главное меню владельца: только рабочие кнопки, без «Ещё» и его разделов."""
    try:
        rows = list(markup.inline_keyboard)
    except Exception:
        return markup
    clean = []
    for row in rows:
        keep = [b for b in row
                if getattr(b, "callback_data", None) not in HIDE
                and getattr(b, "callback_data", None) not in MORE]
        if keep:
            clean.append(keep)
    return InlineKeyboardMarkup(clean)
'''


class BuildError(RuntimeError):
    pass


def _target(tree):
    nodes = [n for n in tree.body if getattr(n, 'name', None) == TARGET]
    if len(nodes) != 1 or not isinstance(nodes[0], ast.FunctionDef) or nodes[0].decorator_list:
        raise BuildError('TARGET_NOT_UNIQUE')
    node = nodes[0]
    found = {c.value for c in ast.walk(node) if isinstance(c, ast.Constant)}
    if not set(REMOVED) <= found:
        raise BuildError('TARGET_UNEXPECTED_BODY')
    return node


def build(source: bytes, *, expected=EXPECTED_SHA256) -> bytes:
    if hashlib.sha256(source).hexdigest() != expected:
        raise BuildError('SOURCE_HASH_MISMATCH')
    text = source.decode('utf-8')
    tree = ast.parse(text)
    node = _target(tree)
    lines = text.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [REPLACEMENT]
    result = ''.join(lines)
    compile(result, 'cars_ui.py', 'exec')
    return result.encode('utf-8')


if __name__ == '__main__':
    sys.stdout.buffer.write(build(open(sys.argv[1], 'rb').read()))
