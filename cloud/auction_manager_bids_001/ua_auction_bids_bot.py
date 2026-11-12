"""The CRM bot tells the staff about every bid and takes their answer (JPAUTO-KOREA-001, owner 2026-11-12, variant А).

A repeating job reads the bids ledger (ua_auction_bids) and sends each new entry once to the active staff with the
owner, administrator or manager role:
- a client's request from the site: «🔨 Заявка на ставку» with «🔗 Открыть лот на аукционе» (the person places the bid
  themselves, in their own browser) and «✅ Поставил» / «❌ Не поставил». The first answer is recorded with who gave it
  and every staff copy of the message shows it, without buttons, so nobody places the same bid twice;
- a manager's bid for a client (already placed by that manager): an information message to the others.
Telegram glue only; the ledger and the clients stay in their own modules.
"""
import asyncio
from html import escape
import logging

import ua_auction_bids as bids
import ua_auction_clients as clients

log = logging.getLogger(__name__)
JOB = 'auction-bids-notify'
INTERVAL = 10
ROLES = ('ROLE_OWNER', 'ROLE_ADMIN', 'ROLE_MANAGER')


def _money(value):
    return '{:,}'.format(int(value)).replace(',', ' ')


def _name(staff, manager):
    return staff.get(manager) or 'id %s' % manager


def state(row, staff):
    """The line under the title: who placed it, or that it waits."""
    if row['status'] == 'requested':
        return 'Поставьте сами на аукционе и отметьте.'
    when = (row.get('handled_at') or row['created_at'])[11:16]
    if row['status'] == 'placed':
        return '✅ поставил %s %s' % (_name(staff, row.get('handled_by') or row.get('placed_by')), when)
    return '❌ не поставил %s %s' % (_name(staff, row.get('handled_by')), when)


def text(row, client, staff):
    who = '%s %s' % (client['surname'], client['name']) if client else row['phone']
    title = ('🔨 Ставка менеджера %s за клиента' % _name(staff, row['placed_by']) if row.get('placed_by')
             else '🔨 Заявка на ставку')
    return ('<b>%s</b>\n%s\nКлиент: %s (%s)\nАвто: %s · лот %s\nVIN: %s\nСумма: ₩%s ≈ $%s\nВремя: %s'
            % (escape(title), escape(state(row, staff)), escape(who), escape(row['phone']), escape(row['title']),
               escape(row['lot_id']), escape(row.get('vin') or '—'), _money(row['krw']), _money(row['usd']),
               escape(row['created_at'][:16].replace('T', ' '))))


def buttons(row):
    """The answer buttons of a waiting request, or None."""
    if row['status'] != 'requested':
        return None
    from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M
    return M([[B('🔗 Открыть лот на аукционе', url=bids.LOT_URL % row['lot_id'])],
              [B('✅ Поставил', callback_data='ab:ok:%d' % row['id']),
               B('❌ Не поставил', callback_data='ab:no:%d' % row['id'])]])


def recipients():
    import db
    roles = {getattr(db, name) for name in ROLES}
    return [s['user_id'] for s in db.list_staff(active_only=True) if s['role'] in roles]


def staff_names():
    import ua_auction_clients_bot
    return ua_auction_clients_bot._staff()


async def notify(context):
    try:
        rows = await asyncio.to_thread(bids.unnotified)
        chats = await asyncio.to_thread(recipients) if rows else []
        staff = await asyncio.to_thread(staff_names) if rows else {}
    except Exception as exc:
        log.warning('auction bids: %s', exc)
        return
    for row in rows:
        client = await asyncio.to_thread(clients.get, row['phone'])
        for chat in chats:
            if chat == row['placed_by']:
                continue  # the manager placed it and already saw it in the dialogue
            try:
                sent = await context.bot.send_message(chat, text(row, client, staff), parse_mode='HTML',
                                                      reply_markup=buttons(row))
                if row['status'] == 'requested':
                    await asyncio.to_thread(bids.add_notice, row['id'], chat, sent.message_id)
            except Exception as exc:
                log.warning('auction bid %s to %s: %s', row['id'], chat, exc)
        await asyncio.to_thread(bids.mark_notified, row['id'])


async def answer(update, context):
    """«✅ Поставил» / «❌ Не поставил»: the first answer counts; every staff copy then shows it."""
    from telegram.ext import ApplicationHandlerStop
    query = update.callback_query
    _, verdict, bid_id = query.data.split(':')
    user = update.effective_user.id
    if user not in await asyncio.to_thread(recipients):
        await query.answer('Недостаточно прав', show_alert=True)
        raise ApplicationHandlerStop
    first = await asyncio.to_thread(bids.mark, bid_id, user, verdict == 'ok')
    row = await asyncio.to_thread(bids.get, bid_id)
    if row is None:
        await query.answer('Заявка не найдена', show_alert=True)
        raise ApplicationHandlerStop
    await query.answer('Отмечено' if first else 'Уже отмечено: ' + state(row, await asyncio.to_thread(staff_names)))
    message = text(row, await asyncio.to_thread(clients.get, row['phone']), await asyncio.to_thread(staff_names))
    for chat, message_id in await asyncio.to_thread(bids.notices, bid_id):
        try:
            await context.bot.edit_message_text(message, chat_id=chat, message_id=message_id, parse_mode='HTML')
        except Exception as exc:  # deleted or already the same: the record stays right
            log.info('auction bid %s copy %s: %s', bid_id, chat, exc)
    raise ApplicationHandlerStop


def register(app, group=0):
    from telegram.ext import CallbackQueryHandler
    app.add_handler(CallbackQueryHandler(answer, pattern=r'^ab:(ok|no):[0-9]{1,12}$'), group=group)
    if app.job_queue is not None and not app.job_queue.get_jobs_by_name(JOB):
        app.job_queue.run_repeating(notify, interval=INTERVAL, first=5, name=JOB)
