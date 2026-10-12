#!/usr/bin/env python3
"""A new CRM field prompt cancels every older pending input in the exact installed cars_ui.py.

Cause (CRM-DIAG-LINK-PROBE-20261012): after «Добавить видео/фото» the media wait
(car_media_wait) stays set. edit_ask/client_ask then set car_wait, but
catch_message checks the media wait first and returns for plain text, so the
text falls through to team_bot.intake → «Поля CRM не распознаны».
"""
from __future__ import annotations

import ast
import hashlib
import sys

# Installed source observed by CRM-DIAG-LINK-PROBE-20261012 (after CRM-CARD-DELETE-INSTALL).
EXPECTED_SHA256 = '5da4d9e828d8f68913eea283d0ed736ea7be3458e75c3a04f64e128a41932ee2'

HELPER = '''
def _ua_wait_text(context, wait):
    """Ждать текстовое значение поля: прежние ожидания ввода (файлы, контейнер, характеристика) отменяются."""
    drop_wait(context)
    context.user_data.pop('cont_wait', None)
    context.user_data.pop('ua099_spec_edit', None)
    context.user_data['car_wait'] = wait
'''
PROMPTS = ('edit_ask', 'client_ask')


class BuildError(RuntimeError):
    pass


def _unique(tree, name, kind):
    nodes = [n for n in tree.body if isinstance(n, kind) and n.name == name]
    if len(nodes) != 1 or nodes[0].decorator_list:
        raise BuildError(name.upper() + '_NOT_UNIQUE')
    return nodes[0]


def _wait_assignment(function, lines):
    """The single statement `context.user_data['car_wait'] = {...}` that owns its whole lines."""
    found = [n for n in function.body if isinstance(n, ast.Assign) and len(n.targets) == 1
             and ast.unparse(n.targets[0]) == "context.user_data['car_wait']"]
    if len(found) != 1:
        raise BuildError('CAR_WAIT_NOT_UNIQUE:' + function.name)
    node = found[0]
    first, last = lines[node.lineno - 1], lines[node.end_lineno - 1]
    if first[:node.col_offset].strip() or last[node.end_col_offset:].strip():
        raise BuildError('CAR_WAIT_SHARES_LINE:' + function.name)
    return node


def build(source: bytes, *, expected=EXPECTED_SHA256) -> bytes:
    if hashlib.sha256(source).hexdigest() != expected:
        raise BuildError('SOURCE_HASH_MISMATCH')
    text = source.decode('utf-8')
    tree = ast.parse(text)
    if any(getattr(n, 'name', None) == '_ua_wait_text' for n in tree.body):
        raise BuildError('ALREADY_BUILT')
    anchor = _unique(tree, 'drop_wait', ast.FunctionDef)
    lines = text.splitlines(keepends=True)
    # Replace bottom-up so earlier line numbers stay valid; a multi-line value keeps its own layout.
    edits = [_wait_assignment(_unique(tree, name, ast.AsyncFunctionDef), lines) for name in PROMPTS]
    for node in sorted(edits, key=lambda n: n.lineno, reverse=True):
        indent = lines[node.lineno - 1][:node.col_offset]
        lines[node.lineno - 1:node.end_lineno] = [
            '%s_ua_wait_text(context, %s)\n' % (indent, ast.get_source_segment(text, node.value))]
    if anchor.end_lineno >= min(n.lineno for n in edits):
        raise BuildError('DROP_WAIT_AFTER_PROMPTS')
    lines.insert(anchor.end_lineno, HELPER)
    result = ''.join(lines)
    compile(result, 'cars_ui.py', 'exec')
    return result.encode('utf-8')


if __name__ == '__main__':
    sys.stdout.buffer.write(build(open(sys.argv[1], 'rb').read()))
