"""Автопоиск в CRM-боте: сообщения менеджеру (AUTOSEARCH-002, владелец 17.11).

Одна ответственность — доставить менеджеру (сотруднику CRM, чей запрос) готовые сообщения для группы клиента:
- новый запрос: «📤 Запрос №001 создан» с приветствием (текст владельца);
- новый подходящий лот: «🔔 Новый лот по запросу №001» с текстом лота (до 10 за раз, остальные — одной строкой «ещё N»);
под каждым — «📲 Отправить в группу WhatsApp» (официальная ссылка wa.me) и «👥 Открыть группу».
Проверка раз в минуту: запросы без приветствия и запросы, ещё не сверенные с текущим списком лотов korea.html; файл
лотов читается заново только когда он сменился. Каждый лот по запросу — один раз (ua_lot_alerts.found).
Сбой отправки пишется в журнал и повторяется при следующей проверке. Записи — ua_lot_alerts, тексты — ua_lot_alerts_whatsapp.
"""
import asyncio
import html
import logging
import os

import ua_lot_alerts as alerts
import ua_lot_alerts_whatsapp as whatsapp

log = logging.getLogger(__name__)
JOB = 'ua-lot-alerts-002'
INTERVAL = 60
SHOWN = 10
_lots = {}


def number(request_id):
    return '№%03d' % request_id


def lots(path=None):
    """(generated_at, лоты) опубликованного списка; читается заново только при новом файле."""
    path = str(path or alerts.LOTS)
    try:
        stamp = os.stat(path).st_mtime_ns
    except OSError:
        return None, []
    if _lots.get('stamp') != (path, stamp):
        _lots.update(stamp=(path, stamp), value=alerts.read_lots(path))
    return _lots['value']


def buttons(text, group_link):
    from telegram import InlineKeyboardButton as B, InlineKeyboardMarkup as M
    return M([[B('📲 Отправить в группу WhatsApp', url=whatsapp.share_url(text))],
              [B('👥 Открыть группу', url=group_link)]])


def welcome_message(request, client_name):
    text = whatsapp.welcome(alerts.describe(request['criteria']))
    head = '📤 <b>Запрос %s создан</b> · %s\nТекст для группы клиента готов:\n\n' % (
        number(request['id']), html.escape(client_name))
    return head + '<i>%s</i>' % html.escape(text), text


def lot_message(request, client_name, lot):
    text = whatsapp.lot(lot)
    head = '🔔 <b>Новый лот по запросу %s</b> · %s\n\n' % (number(request['id']), html.escape(client_name))
    return head + html.escape(text), text


def _name(phone):
    import ua_auction_clients as clients
    client = clients.get(phone)
    return '%s %s' % (client['surname'], client['name']) if client else phone


async def _send(bot, request, message, text):
    await bot.send_message(request['staff_id'], message, parse_mode='HTML', disable_web_page_preview=True,
                           reply_markup=buttons(text, request['group_link']))
    await asyncio.sleep(0.05)  # бережно к ограничениям Telegram


async def check(bot, read=lots, name=_name):
    """Одна проверка: приветствия новых запросов и новые подходящие лоты. -> сколько сообщений отправлено."""
    sent, state = 0, {}
    for request in alerts.requests():
        try:
            sent += await _one(bot, request, read, name, state)
        except Exception as error:  # один недоступный менеджер не задерживает остальных
            log.warning('автопоиск: запрос %s не отправлен: %s', number(request['id']), error)
    return sent


async def _one(bot, request, read, name, state):
    """Приветствие (если ещё не было) и новые лоты одного запроса; `state` хранит список лотов на одну проверку."""
    sent = 0
    client_name = await asyncio.to_thread(name, request['client_phone'])
    if not request['welcomed']:
        await _send(bot, request, *welcome_message(request, client_name))
        alerts.mark_welcomed(request['id'])
        sent += 1
    if 'lots' not in state:
        state['lots'] = read()
    generated, items = state['lots']
    if not generated or request['lots_at'] == generated:
        return sent
    found = [lot for lot in items if alerts.matches(request['criteria'], lot)]
    fresh = set(alerts.unfound(request['id'], [lot['id'] for lot in found]))
    new = [lot for lot in found if lot['id'] in fresh]
    for lot in new[:SHOWN]:
        await _send(bot, request, *lot_message(request, client_name, lot))
        alerts.record_found(request['id'], [lot['id']])
        sent += 1
    if len(new) > SHOWN:
        await bot.send_message(request['staff_id'], 'По запросу %s ещё %d подходящих авто — на сайте: %s' % (
            number(request['id']), len(new) - SHOWN, whatsapp.SITE), disable_web_page_preview=True)
        alerts.record_found(request['id'], [lot['id'] for lot in new[SHOWN:]])
        sent += 1
    alerts.mark_checked(request['id'], generated)
    return sent


async def _job(context):
    try:
        sent = await check(context.bot)
        if sent:
            log.info('автопоиск: сообщений менеджерам %d', sent)
    except Exception as error:
        log.warning('автопоиск: проверка не прошла: %s', error)


def register(app):
    if app.job_queue is None:
        log.warning('автопоиск: нет job_queue — сообщения менеджерам не отправляются')
        return
    if not app.job_queue.get_jobs_by_name(JOB):
        app.job_queue.run_repeating(_job, interval=INTERVAL, first=30, name=JOB)
