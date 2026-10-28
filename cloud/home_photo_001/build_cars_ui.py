#!/usr/bin/env python3
"""Append the «Фото главной страницы» hook to the exact installed cars_ui.py; nothing else changes.

cars_ui.py already extends itself by re-defining register() at the end of the file
(each block keeps the previous one); the new block does the same for register()
and with_stats_button(), the owner main-menu filter that team_bot calls.
"""
from __future__ import annotations

import ast
import hashlib
import sys

# Installed source after CRM-CARD-SOLD-INSTALL-20261028 (its plan: 19adbff3 -> 0e529a92).
EXPECTED_SHA256 = '0e529a9292203737f22d0137dface8f9cd3c2ba94e466847967f8aba21e7719a'
MARK = '# HOME-PHOTO-001'

BLOCK = '''

# HOME-PHOTO-001: CRM button «Фото главной страницы» (module ua_home_photo_bot).
_ua_home_photo_menu = with_stats_button


def with_stats_button(markup):
    menu = _ua_home_photo_menu(markup)
    try:
        import ua_home_photo_bot
        return ua_home_photo_bot.with_button(markup, menu)
    except Exception as e:
        log.warning('ua_home_photo_bot: кнопка не добавлена: %s', e)
        return menu


_ua_home_photo_register = register


def register(app):
    _ua_home_photo_register(app)
    try:
        import ua_home_photo_bot
        ua_home_photo_bot.register(app)
    except Exception as e:
        log.warning('ua_home_photo_bot не подключён: %s', e)
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
    if not {'with_stats_button', 'register'} <= names:
        raise BuildError('HOOKS_MISSING')
    result = text.rstrip('\n') + '\n' + BLOCK
    compile(result, 'cars_ui.py', 'exec')
    return result.encode('utf-8')


if __name__ == '__main__':
    sys.stdout.buffer.write(build(open(sys.argv[1], 'rb').read()))
