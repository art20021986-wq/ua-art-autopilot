"""Автопоиск в клиентском боте @UA_artcompany_LLC_bot (AUTOSEARCH-001, владелец 17.11).

Одна ответственность — Telegram-часть автопоиска:
- /start as-<код> (ссылка «📲 Підключити Telegram» из «Мій кабінет»): привязать этот чат к клиенту; обработчик стоит
  раньше анкеты (группа -1) и ловит только такую ссылку — обычный /start и метки источников работают как раньше;
- раз в 10 минут: если список лотов korea.html обновился или клиент сохранил новый поиск — прислать клиенту новые
  подходящие лоты (до 10 в сообщении, остальные — «Ще N»), каждый лот одному клиенту один раз.
Записи и сверка — ua_lot_alerts. Сбой пишется в журнал и повторяется в следующий раз; ничего больше бот не меняет.
"""
import html
import logging

import ua_lot_alerts as alerts

log = logging.getLogger(__name__)
JOB = 'ua-lot-alerts-001'
INTERVAL = 10 * 60
SITE = 'https://www.uaart.com.ua/video/korea.html'
SHOWN = 10
START = r'^/start(@\w+)? as-[A-Za-z0-9_-]{8,61}$'
TEXT = {
    'linked': ('✅ Telegram підключено до «Мій кабінет» UA ART.\n'
               'Нові авто з аукціонів Кореї за вашими пошуками будуть приходити сюди.'),
    'bad_code': ('Посилання застаріло або вже використане. Відкрийте «Мій кабінет» на сайті і натисніть '
                 '«📲 Підключити Telegram» ще раз.'),
}


def _date(start):
    """«2026/11/18 12:00» -> «18.11»."""
    return '%s.%s' % (start[8:10], start[5:7]) if len(start) >= 10 else ''


def lot_line(number, lot):
    price = '≈ %s $' % alerts._n(lot['start_usd']) if lot.get('start_usd') else 'ціна уточнюється'
    label = '%s %s · %s км · %s' % (lot['title'], lot['year'], alerts._n(lot.get('mileage_km') or 0), price)
    return '%d. <a href="%s#lot-%s">%s</a> — торги %s' % (number, SITE, html.escape(str(lot['id']), quote=True),
                                                          html.escape(label), _date(lot.get('auction_start', '')))


def message(rule, lots):
    lines = ['🔔 <b>Нові авто за вашим пошуком</b>', html.escape(alerts.describe(rule)), '']
    lines += [lot_line(i, lot) for i, lot in enumerate(lots[:SHOWN], 1)]
    if len(lots) > SHOWN:
        lines += ['', 'Ще %d — на сторінці <a href="%s">аукціонів Кореї</a>.' % (len(lots) - SHOWN, SITE)]
    return '\n'.join(lines)


def _active(phone):
    import ua_auction_clients as clients
    client = clients.get(phone)
    return bool(client) and not client['blocked']


async def start_link(update, context):
    from telegram.ext import ApplicationHandlerStop
    code = (context.args or [''])[0]
    phone = alerts.link(code, update.effective_chat.id)
    await update.effective_message.reply_text(TEXT['linked'] if phone else TEXT['bad_code'])
    log.info('автопоиск: Telegram %s', 'подключён' if phone else 'код не принят')
    raise ApplicationHandlerStop


async def check(context, read=alerts.read_lots, active=_active):
    """Одна проверка: новые подходящие лоты по поискам, которые ещё не сверены с этим списком лотов."""
    from telegram.error import Forbidden
    generated, lots = read()
    if not generated:
        return 0
    sent = 0
    for search in alerts.searches():
        if search['lots_at'] == generated:
            continue
        phone, chat = search['phone'], alerts.chat(search['phone'])
        if chat is None or not active(phone):
            continue  # сверим, когда подключит Telegram (или снова получит доступ)
        found = [lot for lot in lots if alerts.matches(search['criteria'], lot)]
        fresh = set(alerts.unsent(phone, [lot['id'] for lot in found]))
        new = [lot for lot in found if lot['id'] in fresh]
        if new:
            try:
                await context.bot.send_message(chat, message(search['criteria'], new), parse_mode='HTML',
                                               disable_web_page_preview=True)
            except Forbidden:
                alerts.unlink(phone)  # клиент остановил бота: больше не пишем, в кабинете — «не підключено»
                continue
            alerts.record_sent(phone, search['id'], [lot['id'] for lot in new])
            sent += 1
        alerts.mark_checked(search['id'], generated)
    return sent


async def _job(context):
    try:
        sent = await check(context)
        if sent:
            log.info('автопоиск: отправлено сообщений %d', sent)
    except Exception as error:
        log.warning('автопоиск: проверка не прошла: %s', error)


def register(app):
    from telegram.ext import CommandHandler, filters
    app.add_handler(CommandHandler('start', start_link, filters=filters.Regex(START)), group=-1)
    if app.job_queue is None:
        log.warning('автопоиск: нет job_queue — уведомления не отправляются')
        return
    if not app.job_queue.get_jobs_by_name(JOB):
        app.job_queue.run_repeating(_job, interval=INTERVAL, first=60, name=JOB)
