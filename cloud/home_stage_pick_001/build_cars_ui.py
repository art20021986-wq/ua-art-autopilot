#!/usr/bin/env python3
"""Append the «Разместить на главную» hook to the exact installed cars_ui.py; nothing else changes.

cars_ui.py already extends itself by re-defining card_kb() and register() at the
end of the file (each block keeps the previous one); the new block does the same.
"""
from __future__ import annotations

import ast
import hashlib
import sys

# Installed source after LEAD-FOLDERS-INSTALL-20261106 (its plan: e4576e5b -> 32eb47b0),
# confirmed by CARD-LANG-PROBE-20261108.
EXPECTED_SHA256 = '32eb47b07378ecd3213f0d85e877a0aa779338764c5738a15ae77bb8771cdd6d'
MARK = '# HOME-STAGE-PICK-001'

BLOCK = '''

# HOME-STAGE-PICK-001: card button «Разместить на главную» (module ua_home_stage_bot).
_ua_home_stage_card_kb = card_kb


def card_kb(card, staff):
    markup = _ua_home_stage_card_kb(card, staff)
    try:
        import ua_home_stage_bot
        return ua_home_stage_bot.with_button(markup, card, staff)
    except Exception as e:
        log.warning('ua_home_stage_bot: кнопка не добавлена: %s', e)
        return markup


_ua_home_stage_register = register


def register(app):
    _ua_home_stage_register(app)
    try:
        import ua_home_stage_bot
        ua_home_stage_bot.register(app)
    except Exception as e:
        log.warning('ua_home_stage_bot не подключён: %s', e)
'''


class BuildError(RuntimeError):
    pass


def build(source: bytes, *, expected=EXPECTED_SHA256) -> bytes:
    if hashlib.sha256(source).hexdigest() != expected:
        raise BuildError('SOURCE_HASH_MISMATCH')
    text = source.decode('utf-8')
    if MARK in text:
        raise BuildError('ALREADY_INSTALLED')
    names = {n.name for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
    if not {'card_kb', 'register'} <= names:
        raise BuildError('HOOKS_MISSING')
    result = text.rstrip('\n') + '\n' + BLOCK
    compile(result, 'cars_ui.py', 'exec')
    return result.encode('utf-8')


if __name__ == '__main__':
    sys.stdout.buffer.write(build(open(sys.argv[1], 'rb').read()))
