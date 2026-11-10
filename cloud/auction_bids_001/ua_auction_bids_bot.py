"""The CRM bot tells the staff about every client bid (JPAUTO-KOREA-001 step В).

A repeating job reads the bids ledger (ua_auction_bids) and sends each new entry once to the active staff with the
owner, administrator or manager role. Telegram glue only; the ledger and the clients stay in their own modules.
"""
import asyncio
from html import escape
import logging

import ua_auction_bids as bids
import ua_auction_clients as clients

log = logging.getLogger(__name__)
JOB = 'auction-bids-notify'
INTERVAL = 10
REASONS = {'not_confirmed': 'аукцион не подтвердил ставку', 'form': 'на странице лота нет формы ставки',
           'too_low': 'ниже минимальной', 'limit': 'выше лимита клиента', 'day_limit': 'исчерпан лимит 30 ставок в день'}


def _money(value):
    return '{:,}'.format(int(value)).replace(',', ' ')


def text(row, client):
    who = '%s %s' % (client['surname'], client['name']) if client else row['phone']
    state = ('✅ Ставка поставлена на аукционе' if row['status'] == 'placed'
             else '❌ Ставка НЕ поставлена: ' + REASONS.get(row['message'], row['message'] or 'ошибка'))
    return ('<b>🔨 Ставка клиента</b>\n%s\nКлиент: %s (%s)\nАвто: %s · лот %s\nСумма: ₩%s ≈ $%s\nВремя: %s'
            % (state, escape(who), escape(row['phone']), escape(row['title']), escape(row['lot_id']),
               _money(row['krw']), _money(row['usd']), escape(row['created_at'][:16].replace('T', ' '))))


def recipients():
    import db
    return [s['user_id'] for s in db.list_staff(active_only=True)
            if s['role'] in (db.ROLE_OWNER, db.ROLE_ADMIN, db.ROLE_MANAGER)]


async def notify(context):
    try:
        rows = await asyncio.to_thread(bids.unnotified)
        chats = await asyncio.to_thread(recipients) if rows else []
    except Exception as exc:
        log.warning('auction bids: %s', exc)
        return
    for row in rows:
        message = text(row, await asyncio.to_thread(clients.get, row['phone']))
        for chat in chats:
            try:
                await context.bot.send_message(chat, message, parse_mode='HTML')
            except Exception as exc:
                log.warning('auction bid %s to %s: %s', row['id'], chat, exc)
        await asyncio.to_thread(bids.mark_notified, row['id'])


def register(app):
    if app.job_queue is not None and not app.job_queue.get_jobs_by_name(JOB):
        app.job_queue.run_repeating(notify, interval=INTERVAL, first=5, name=JOB)
