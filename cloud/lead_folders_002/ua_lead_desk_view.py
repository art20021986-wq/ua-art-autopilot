"""Texts and buttons of the lead desk in the client bot (LEAD-FOLDERS-001). Pure functions, no I/O.

A lead is ua_lead_sources.Lead; its state comes from ua_lead_desk_store. Buttons are (label, callback_data) tuples.
Callback data: 'ld:home', 'ld:f:<folder>', 'ld:o:<lead key>', 'ld:st:<status>:<lead key>', 'ld:note:<key>',
'ld:contract:<key>', 'ld:ok:<key>', 'ld:cancel:<key>'.
"""
import datetime
from html import escape

import ua_lead_calendar as cal
import ua_lead_folders as folders
from ua_lead_desk_store import CONTRACT, IN_WORK, NEW, STOPPED

WEEKDAYS = ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')
DONE = {IN_WORK: '🔵 В работе', STOPPED: '⚪ Остановлен', CONTRACT: '✅ Договор'}
ACTIONS = ((IN_WORK, '🔵 В работе'), (STOPPED, '⚪ Остановить'))


def _day(moment):
    return '%s %s' % (WEEKDAYS[moment.weekday()], moment.strftime('%d.%m'))


def stage(lead, state, now, track_from):
    """'done' | 'untracked' | 'ok' | 'last_day' | 'overdue'."""
    if state['status'] != NEW:
        return 'done'
    if lead.created_at < track_from:
        return 'untracked'
    left = cal.working_days_left(lead.created_at, now)
    return 'overdue' if left == 0 else 'last_day' if left == 1 else 'ok'


def badge(lead, state, now, track_from):
    kind = stage(lead, state, now, track_from)
    if kind == 'done':
        return DONE[state['status']]
    if kind == 'untracked':
        return '🟢 Новый'
    if kind == 'overdue':
        return '🔴 Просрочен'
    if kind == 'last_day':
        return '🟡 Последний день'
    return '🟢 Осталось %d раб. дн.' % cal.working_days_left(lead.created_at, now)


def active(leads, states):
    """Leads still in work: a lead with a signed contract has become an order in the CRM bot."""
    return [lead for lead in leads if states.get(lead.key, {}).get('status') != CONTRACT]


def stats(leads, states, now, track_from, contracts_this_month):
    open_leads = active(leads, states)
    kinds = [stage(lead, states.get(lead.key) or {'status': NEW}, now, track_from) for lead in open_leads]
    new = sum(kind != 'done' for kind in kinds)
    in_work = sum(states.get(lead.key, {}).get('status') == IN_WORK for lead in open_leads)
    overdue = kinds.count('overdue')
    return ('<b>Лиды</b>: новых %d · в работе %d · просрочено %d\n<b>Договоров за месяц:</b> %d'
            % (new, in_work, overdue, contracts_this_month))


def folders_view(header, leads, states):
    counts = {folder: 0 for folder in folders.FOLDERS}
    for lead in active(leads, states):
        counts[lead.folder] += 1
    buttons = [[('%s · %d' % (folders.label(folder), counts[folder]), 'ld:f:' + folder)] for folder in folders.FOLDERS]
    buttons.append([('Обновить', 'ld:home')])
    return {'text': header + '\n\nВыберите папку. Лиды — строго по очереди поступления.', 'buttons': buttons}


def received(lead):
    return datetime.datetime.fromtimestamp(lead.created_at, cal.KYIV)


def list_view(folder, leads, states, now, track_from):
    rows = [lead for lead in active(leads, states) if lead.folder == folder]
    buttons = []
    for lead in rows[:40]:
        state = states.get(lead.key) or {'status': NEW}
        about = (' · ' + lead.subject) if lead.subject and folder == folders.STOCK else ''
        label = '%s · %s%s · %s' % (badge(lead, state, now, track_from), lead.name[:24], about[:14],
                                    received(lead).strftime('%d.%m %H:%M'))
        buttons.append([(label, 'ld:o:' + lead.key)])
    buttons.append([('К папкам', 'ld:home')])
    text = '<b>%s</b>\n%s' % (escape(folders.label(folder)), 'Лидов: %d' % len(rows) if rows else 'Пока нет лидов')
    return {'text': text, 'buttons': buttons}


def detail_view(lead, state, now, track_from):
    lines = [lead.detail, '', '<b>Папка:</b> ' + escape(folders.label(lead.folder)),
             '<b>Источник:</b> ' + escape(lead.source),
             '<b>Статус:</b> ' + escape(badge(lead, state, now, track_from)),
             '<b>Поступил:</b> %s %s' % (_day(received(lead)), received(lead).strftime('%H:%M'))]
    if lead.created_at >= track_from and state['status'] == NEW:
        last = cal.deadline(lead.created_at) - datetime.timedelta(seconds=1)
        lines.append('<b>Ответить до:</b> конца дня %s' % _day(last))
    lines.append('<b>Заметка:</b> ' + (escape(state['note']) if state['note'] else '—'))
    if state['status'] == CONTRACT:
        return {'text': '\n'.join(lines + ['', 'Договор оформлен — заказ в CRM-боте.']),
                'buttons': [[('К папке', 'ld:f:' + lead.folder)]]}
    actions = [(label, 'ld:st:%s:%s' % (status, lead.key)) for status, label in ACTIONS if status != state['status']]
    buttons = [actions, [('✏️ Заметка', 'ld:note:' + lead.key)], [('✅ Оформить договор', 'ld:contract:' + lead.key)],
               [('К папке', 'ld:f:' + lead.folder)]]
    return {'text': '\n'.join(lines), 'buttons': buttons}


ASK_NUMBER = 'Оформление договора · %s\n\nШаг 1 из 3. Напишите номер договора одним сообщением.'
ASK_FILE = 'Шаг 2 из 3. Пришлите файл договора: PDF или фото.'
BAD_FILE = 'Нужен файл договора: PDF, Word или фото (до 20 МБ).'
NOTE_PROMPT = 'Напишите заметку к лиду одним сообщением. Она заменит прежнюю. Чтобы отменить — нажмите любую кнопку.'


def confirm_view(lead, number):
    text = ('Шаг 3 из 3. Проверьте:\n<b>Клиент:</b> %s\n<b>Папка:</b> %s\n<b>Договор №</b> %s\n<b>Файл:</b> получен\n\n'
            'Оформить заказ? Он перейдёт в CRM-бот.' % (escape(lead.name), escape(folders.label(lead.folder)), escape(number)))
    return {'text': text, 'buttons': [[('✅ Оформить', 'ld:ok:' + lead.key), ('Отмена', 'ld:cancel:' + lead.key)]]}


def done_view(lead, number):
    return {'text': '✅ Заказ оформлен: договор № %s, %s.\nОн в CRM-боте → «Клиенты» → «%s».'
                    % (escape(number), escape(lead.name), escape(folders.label(lead.folder))),
            'buttons': [[('К папке', 'ld:f:' + lead.folder)]]}


def reminder(lead, kind):
    head = '⏰ Сегодня последний день ответа' if kind == 'last_day' else '🔴 Срок ответа прошёл'
    last = cal.deadline(lead.created_at) - datetime.timedelta(seconds=1)
    text = '%s\n%s · %s\nСрок: до конца дня %s. Дайте клиенту предварительный расчёт.' % (
        head, escape(lead.name), escape(folders.label(lead.folder)), _day(last))
    return {'text': text, 'buttons': [[('Открыть лид', 'ld:o:' + lead.key)]]}


def order_values(lead, number, file_name):
    """The order book's record of a lead with a signed contract."""
    return {'lead_key': lead.key, 'folder': lead.folder, 'contract_no': number.strip()[:60], 'contract_file': file_name,
            'name': lead.name, 'phone': lead.phone, 'telegram': lead.telegram, 'subject': lead.subject,
            'source': lead.source}
