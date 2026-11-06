"""Texts and buttons of the enquiry desk in the CRM bot (ORDER-PROCESS-001). Pure functions, no I/O.

A row is the order package's enquiry view (id, number, created_at, data); state comes from ua_lead_desk_store.
Buttons are (label, callback_data) or (label, None, url) tuples.
"""
import datetime
from html import escape

import ua_lead_calendar as cal
from ua_lead_desk_store import CLIENT, IN_WORK, NEW, STOPPED

NEW_LEAD_URL = 'https://www.uaart.com.ua/video/podbor.html'
WEEKDAYS = ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')
DONE = {IN_WORK: '🔵 В работе', STOPPED: '⚪ Остановлена', CLIENT: '✅ В клиентах'}
ACTIONS = ((IN_WORK, '🔵 В работе'), (STOPPED, '⚪ Остановить'))


def _day(moment):
    return '%s %s' % (WEEKDAYS[moment.weekday()], moment.strftime('%d.%m'))


def stage(row, state, now, track_from):
    """'done' | 'untracked' | 'ok' | 'last_day' | 'overdue'."""
    if state['status'] != NEW:
        return 'done'
    if row['created_at'] < track_from:
        return 'untracked'
    left = cal.working_days_left(row['created_at'], now)
    return 'overdue' if left == 0 else 'last_day' if left == 1 else 'ok'


def badge(row, state, now, track_from):
    kind = stage(row, state, now, track_from)
    if kind == 'done':
        return DONE[state['status']]
    if kind == 'untracked':
        return '🟢 Новая'
    if kind == 'overdue':
        return '🔴 Просрочена'
    if kind == 'last_day':
        return '🟡 Последний день'
    return '🟢 Осталось %d раб. дн.' % cal.working_days_left(row['created_at'], now)


def name(row):
    return ' '.join(str(row['data'].get('customer_name') or 'без имени').split())


def list_label(row, state, now, track_from):
    received = datetime.datetime.fromtimestamp(row['created_at'], cal.KYIV)
    return '%s · %s · %s' % (badge(row, state, now, track_from), name(row)[:30], received.strftime('%d.%m %H:%M'))


def list_view(rows, states, now, track_from, cursor, menu_callback):
    buttons = [[(list_label(r, states[r['id']], now, track_from), 'leads:open:%d' % r['id'])] for r in rows]
    if cursor:
        buttons.append([('Далее →', 'leads:list:%d' % cursor)])
    buttons.append([('➕ Новая заявка', None, NEW_LEAD_URL)])
    buttons.append([('Обновить', 'leads:list'), ('В меню', menu_callback)])
    text = ('<b>Заявки с сайта</b>\nСтрого по очереди поступления. Ответ — предварительный расчёт, '
            'срок 3 рабочих дня (кроме воскресенья и праздников).' if rows else 'Пока нет заявок')
    return {'text': text, 'buttons': buttons}


def desk_block(row, state, now, track_from):
    received = datetime.datetime.fromtimestamp(row['created_at'], cal.KYIV)
    lines = ['', '<b>Статус:</b> ' + escape(badge(row, state, now, track_from)),
             '<b>Поступила:</b> %s %s' % (_day(received), received.strftime('%H:%M'))]
    if row['created_at'] >= track_from:
        last = cal.deadline(row['created_at']) - datetime.timedelta(seconds=1)
        lines.append('<b>Ответить до:</b> конца дня %s' % _day(last))
    lines.append('<b>Заметка:</b> ' + (escape(state['note']) if state['note'] else '—'))
    return '\n'.join(lines)


def detail_view(body, row, state, now, track_from):
    order_id = row['id']
    actions = [(label, 'leads:st:%d:%s' % (order_id, status)) for status, label in ACTIONS if status != state['status']]
    client = (('👤 Открыть клиента', 'card_open:clients:%d' % state['client_id']) if state['client_id']
              else ('👤 Перенести в Клиенты', 'leads:client:%d' % order_id))
    buttons = [actions, [('✏️ Заметка', 'leads:note:%d' % order_id), client], [('К заявкам', 'leads:list')]]
    return {'text': body + '\n' + desk_block(row, state, now, track_from), 'buttons': buttons}


def reminder(row, kind):
    head = ('⏰ Сегодня последний день ответа' if kind == 'last_day' else '🔴 Срок ответа прошёл')
    last = cal.deadline(row['created_at']) - datetime.timedelta(seconds=1)
    text = '%s\nЗаявка %s · %s\nСрок: до конца дня %s. Дайте клиенту предварительный расчёт.' % (
        head, row['number'], escape(name(row)), _day(last))
    return {'text': text, 'buttons': [[('Открыть заявку', 'leads:open:%d' % row['id'])]]}


def client_card(row, note, model_label):
    data = row['data']
    contact = data.get('contact') or {}
    card = {'name': name(row), 'phone': contact.get('phone', ''), 'telegram': contact.get('telegram', ''),
            'whatsapp': contact.get('whatsapp', ''), 'car_interest': model_label, 'wishes': note,
            'source': 'Заявка с сайта %s' % row['number']}
    return {key: value for key, value in card.items() if value}
