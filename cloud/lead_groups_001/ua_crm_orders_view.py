"""Texts and buttons of orders in the CRM bot «Клиенты» (LEAD-FOLDERS-001). Pure functions, no I/O.

An order is a ua_order_book row. Buttons are (label, callback_data) tuples. Callback data: 'co:g:<group>', 'co:f:<folder>',
'co:o:<id>', 'co:next:<id>:<stage seen>', 'co:note:<id>', 'co:file:<id>'; the screen itself is 'cards_clients'.
"""
import datetime
from html import escape

import ua_lead_folders as folders
from ua_order_book import STAGE_KEYS, STAGE_LABELS, next_stage

HOME = 'cards_clients'


def _date(moment, zone):
    return datetime.datetime.fromtimestamp(moment, zone).strftime('%d.%m.%Y')


def stats(orders, now, zone):
    month = datetime.datetime.fromtimestamp(now, zone).strftime('%Y-%m')
    delivered = sum(order['stage'] == 'delivered' for order in orders)
    this_month = sum(datetime.datetime.fromtimestamp(order['created_at'], zone).strftime('%Y-%m') == month
                     for order in orders)
    return ('<b>Клиенты</b> — заказы по договорам\nВсего: %d · в работе: %d · выдано: %d · за месяц: %d'
            % (len(orders), len(orders) - delivered, delivered, this_month))


def _counts(orders):
    counts = {folder: 0 for folder in folders.ALL_FOLDERS}
    for order in orders:
        counts[order['folder'] if order['folder'] in counts else folders.GENERAL] += 1
    return counts


def home(orders, now, zone, extra_rows):
    """Statistics, the two groups (owner 2026-11-10), then the screen's other buttons (search, finance, back)."""
    counts = _counts(orders)
    buttons = [[('%s · %d' % (folders.group_label(group), sum(counts[f] for f in members)), 'co:g:' + group)]
               for group, members in folders.GROUPS.items()]
    return {'text': stats(orders, now, zone), 'buttons': buttons + list(extra_rows)}


def group_view(group, orders):
    """The folders of one group with their order counts, as the folder list was before."""
    counts = _counts(orders)
    buttons = [[('%s · %d' % (folders.label(folder), counts[folder]), 'co:f:' + folder)]
               for folder in folders.GROUPS[group]]
    buttons.append([('К разделам', HOME)])
    return {'text': '<b>%s</b>\nВыберите папку.' % escape(folders.group_label(group)), 'buttons': buttons}


def list_view(folder, orders):
    buttons = [[('№%s · %s · %s' % (order['contract_no'][:16], (order['name'] or '')[:22], STAGE_LABELS[order['stage']]),
                 'co:o:%d' % order['id'])] for order in orders[:40]]
    buttons.append([('К папкам', 'co:g:' + folders.group_of(folder))])
    text = '<b>%s</b>\n%s' % (escape(folders.label(folder)), 'Заказов: %d' % len(orders) if orders else 'Пока нет заказов')
    return {'text': text, 'buttons': buttons}


def detail_view(order, zone):
    fields = [('Договор №', order['contract_no']), ('Клиент', order['name']), ('Телефон', order['phone']),
              ('Telegram', order['telegram']), ('Авто', order['subject']), ('Папка', folders.label(order['folder'])),
              ('Откуда', order['source']), ('Оформлен', _date(order['created_at'], zone))]
    lines = ['<b>%s:</b> %s' % (escape(key), escape(str(value))) for key, value in fields if value]
    lines += ['', '<b>Этапы</b>']
    for stage in STAGE_KEYS:
        done = order['stages'].get(stage)
        lines.append('%s %s%s' % ('✅' if done else '▫️', STAGE_LABELS[stage], ' — ' + _date(done, zone) if done else ''))
    lines += ['', '<b>Заметка:</b> ' + (escape(order['note']) if order['note'] else '—')]
    following = next_stage(order['stage'])
    buttons = []
    if following:
        buttons.append([('➡️ ' + STAGE_LABELS[following], 'co:next:%d:%s' % (order['id'], order['stage']))])
    buttons += [[('✏️ Заметка', 'co:note:%d' % order['id']), ('📎 Договор', 'co:file:%d' % order['id'])],
                [('К папке', 'co:f:' + order['folder'])]]
    return {'text': '\n'.join(lines), 'buttons': buttons}


NOTE_PROMPT = 'Напишите заметку к заказу одним сообщением. Она заменит прежнюю. Чтобы отменить — нажмите любую кнопку.'
