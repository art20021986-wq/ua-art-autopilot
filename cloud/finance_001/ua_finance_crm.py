"""CRM bot: «Клиенты» → «Кредиты и лизинг» — visits to the finance partners (FINANCE-001).

A visit is the site's own analytics event «finance» (analitika_yadro, /ua/a.js): the partner id, the page
with its model/card parameters, the time. This module only reads analytics.db and shows the counts for
today, 7 and 30 days per partner and the latest visits; partner names come from ua_finance_partners.
Active staff with the owner, administrator or manager role may open it (as ua_site_leads). A failure shows
a short message and never affects the rest of the CRM bot.
"""
from contextlib import closing
import datetime
from html import escape
import logging
import re
import sqlite3
import time
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import ua_finance_partners as finance

CALLBACK = 'finance:visits'
BUTTON = 'Кредиты и лизинг'
BACK = 'cards_clients'
EVENT = 'finance'
LATEST = 15
KYIV = ZoneInfo('Europe/Kyiv')
log = logging.getLogger(__name__)


def _database():
    import analitika_yadro
    return analitika_yadro.BAZA


def _origin(page):
    """Where the visitor pressed the partner button from: a car card, an order-page model or the page itself."""
    query = parse_qs(urlsplit(page).query)
    card = (query.get('card') or [''])[0]
    if re.fullmatch(r'UA-[0-9]{4,}', card):
        return 'карточка ' + card
    model = (query.get('model') or [''])[0]
    if re.fullmatch(r'[a-z0-9-]{1,60}', model):
        return 'подбор: ' + model.replace('-', ' ').title()
    return 'страница кредитов'


def _name(partner_id):
    partner = finance.partner(partner_id)
    return partner['name'] if partner else partner_id


def report(now=None, database=None):
    """HTML text of the screen; database and now are for tests."""
    now = time.time() if now is None else now
    midnight = _kyiv_midnight(now)
    periods = (('Сегодня', midnight), ('7 дней', midnight - 6 * 86400), ('30 дней', midnight - 29 * 86400))
    with closing(sqlite3.connect('file:%s?mode=ro' % (database or _database()), uri=True, timeout=5)) as db:
        rows = db.execute('SELECT ts, znachenie, stranica FROM events WHERE tip=? AND ts>=? ORDER BY ts DESC',
                          (EVENT, periods[-1][1])).fetchall()
    lines = ['<b>Кредиты и лизинг</b> — переходы с сайта к партнёрам', '']
    if not rows:
        lines.append('За 30 дней переходов пока нет. Появятся здесь сами, когда посетитель нажмёт кнопку партнёра.')
        return '\n'.join(lines)
    for partner_id in sorted({r[1] for r in rows}):
        counts = ' · '.join('%s: %d' % (label, sum(1 for r in rows if r[1] == partner_id and r[0] >= start))
                            for label, start in periods)
        lines.append('<b>%s</b> — %s' % (escape(_name(partner_id)), counts))
    lines += ['', 'Последние переходы:']
    for ts, partner_id, page in rows[:LATEST]:
        when = time.strftime('%d.%m %H:%M', _kyiv(ts))
        lines.append('%s — %s, %s' % (when, escape(_name(partner_id)), escape(_origin(page))))
    return '\n'.join(lines)


def _kyiv(ts):
    return datetime.datetime.fromtimestamp(ts, KYIV).timetuple()


def _kyiv_midnight(now):
    local = datetime.datetime.fromtimestamp(now, KYIV)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def allowed(update):
    import ua_site_leads
    return ua_site_leads.allowed(update)


async def screen(update, context):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import ApplicationHandlerStop
    query = update.callback_query
    if not allowed(update):
        await query.answer('Недостаточно прав', show_alert=True)
        raise ApplicationHandlerStop
    await query.answer()
    try:
        text = report()
    except Exception as error:
        log.warning('ua_finance_crm: отчёт недоступен: %s', error)
        text = '<b>Кредиты и лизинг</b>\n\nДанные временно недоступны, попробуйте позже.'
    markup = InlineKeyboardMarkup([[InlineKeyboardButton('Обновить', callback_data=CALLBACK),
                                    InlineKeyboardButton('В меню', callback_data=BACK)]])
    await query.message.reply_text(text, parse_mode='HTML', reply_markup=markup)
    raise ApplicationHandlerStop


def register(app):
    from telegram.ext import CallbackQueryHandler
    # An earlier unused group, after the bot's own registrations (as ua_order.bindings.first_group).
    app.add_handler(CallbackQueryHandler(screen, pattern='^%s$' % re.escape(CALLBACK)),
                    group=min(app.handlers, default=0) - 1)
