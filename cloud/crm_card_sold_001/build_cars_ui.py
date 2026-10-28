#!/usr/bin/env python3
"""Replace only the top-level mark_sold_ok handler in the exact installed cars_ui.py."""
from __future__ import annotations

import ast
import hashlib
import sys

# Installed source observed by CRM-SOLD-PROBE-20261028.
EXPECTED_SHA256 = '19adbff34be18402897ca4b54889c9361bcdd261f329218e147b72f8031f9ad6'

HANDLER = '''async def mark_sold_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q)
    cid = int(q.data.split(':')[-1])
    import asyncio as _ua_sold_asyncio
    import publikaciya as _ua_sold_publisher
    import ua_card_sold as _ua_card_sold
    try:
        result = await _ua_sold_asyncio.to_thread(
            _ua_card_sold.mark_sold, cid, q.from_user.id, db=db, publisher=_ua_sold_publisher)
        text = result.text
    except Exception as e:
        log.exception('Не отметил продажу %s', cid)
        text = 'Не получилось отметить продажу: %s' % e
    await q.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('← Вернуться к карточке', callback_data='car_open:%d' % cid)]]))
    raise ApplicationHandlerStop
'''


class BuildError(RuntimeError):
    pass


def build(source: bytes, *, expected=EXPECTED_SHA256) -> bytes:
    if hashlib.sha256(source).hexdigest() != expected:
        raise BuildError('SOURCE_HASH_MISMATCH')
    text = source.decode('utf-8')
    nodes = [n for n in ast.parse(text).body
             if isinstance(n, ast.AsyncFunctionDef) and n.name == 'mark_sold_ok']
    if len(nodes) != 1 or nodes[0].decorator_list:
        raise BuildError('MARK_SOLD_OK_NOT_UNIQUE')
    lines = text.splitlines(keepends=True)
    node = nodes[0]
    result = ''.join(lines[:node.lineno - 1]) + HANDLER + ''.join(lines[node.end_lineno:])
    compile(result, 'cars_ui.py', 'exec')
    return result.encode('utf-8')


if __name__ == '__main__':
    sys.stdout.buffer.write(build(open(sys.argv[1], 'rb').read()))
