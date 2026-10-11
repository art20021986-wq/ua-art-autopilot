#!/usr/bin/env python3
"""Replace only the top-level delete_ok handler in the exact installed cars_ui.py."""
from __future__ import annotations

import ast
import hashlib
import sys

# Installed source observed by CRM-DELETE-PROBE-20261011 / R2.
EXPECTED_SHA256 = 'fed3ccd110e750947288bbe5892f1c62262b23d6818653f43c7d57b584bf92dd'

HANDLER = '''async def delete_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q)
    cid = int(q.data.split(':')[-1])
    import asyncio as _ua_delete_asyncio
    import publikaciya as _ua_delete_publisher
    import ua_card_delete as _ua_card_delete
    try:
        result = await _ua_delete_asyncio.to_thread(
            _ua_card_delete.delete_card, cid, q.from_user.id, db=db, publisher=_ua_delete_publisher)
        text = result.text
        if result.deleted:
            context.user_data.pop('car_last', None)
    except Exception as e:
        log.exception('Не удалил карточку %s', cid)
        text = 'Не получилось удалить: %s' % e
    await q.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('← Все автомобили', callback_data='cards_cars')]]))
    raise ApplicationHandlerStop
'''


class BuildError(RuntimeError):
    pass


def build(source: bytes, *, expected=EXPECTED_SHA256) -> bytes:
    if hashlib.sha256(source).hexdigest() != expected:
        raise BuildError('SOURCE_HASH_MISMATCH')
    text = source.decode('utf-8')
    nodes = [n for n in ast.parse(text).body
             if isinstance(n, ast.AsyncFunctionDef) and n.name == 'delete_ok']
    if len(nodes) != 1 or nodes[0].decorator_list:
        raise BuildError('DELETE_OK_NOT_UNIQUE')
    lines = text.splitlines(keepends=True)
    node = nodes[0]
    result = ''.join(lines[:node.lineno - 1]) + HANDLER + ''.join(lines[node.end_lineno:])
    compile(result, 'cars_ui.py', 'exec')
    return result.encode('utf-8')


if __name__ == '__main__':
    sys.stdout.buffer.write(build(open(sys.argv[1], 'rb').read()))
