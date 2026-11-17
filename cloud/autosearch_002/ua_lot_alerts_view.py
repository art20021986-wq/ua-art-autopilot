"""Автопоиск в CRM-боте — тексты и кнопки (AUTOSEARCH-002, владелец 17.11, макеты 33-AUTOSEARCH-CRM / -MANAGER /
-ROLE, «Да»). Чистые функции, без ввода-вывода.

- with_home: блок «🔔 Автопоиск» в «🔨 Клиенты аукциона» и кнопка «🔔 Автопоиск · N» перед «← Меню»;
- screen: «🔔 Автопоиск» — что ищут чаще, что смотрят на сайте, запросы (клиент, условия, менеджер, найдено);
  кнопка с именем клиента открывает его карточку ('ac:c:<phone>');
- with_card: в карточке клиента — права менеджера сайта, его запросы, просмотренные лоты; владельцу — кнопка
  «👔 Права менеджера на сайте» или «✖️ Снять права менеджера»;
- role_screen: выбор сотрудника CRM для логина ('ac:roleset:<phone>:<id>').
Менеджер видит запросы своих клиентов, владелец — все (это решает вызывающий: какие запросы передать).
"""
from html import escape

import ua_lot_alerts as alerts

BUTTON = 'ac:alerts'
BACK = ('← Клиенты аукциона', 'ac:home')
SHOWN = 40
LIMIT = 3900


def number(request_id):
    return '№%03d' % request_id


def with_home(screen, numbers):
    n = numbers
    block = ('\n\n<b>🔔 Автопоиск</b>\nЗапросов: %d · клиентов: %d\nНайдено авто за 7 дней: %d\n'
             'Смотрели лоты на сайте: %d' % (len(n['requests']), n['clients'], n['found_week'], n['viewers']))
    buttons = list(screen['buttons'])
    buttons.insert(len(buttons) - 1, [('🔔 Автопоиск · %d' % len(n['requests']), BUTTON)])
    return {'text': screen['text'] + block, 'buttons': buttons}


def _people(count):
    return '%d %s' % (count, 'клиент' if count % 10 == 1 and count % 100 != 11 else
                      'клиента' if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14) else 'клиентов')


def screen(numbers, names, staff, counts):
    """`names`: телефон -> «Фамилия Имя»; `staff`: Telegram id -> имя сотрудника; `counts`: id запроса -> найдено."""
    n = numbers
    lines = ['<b>🔔 Автопоиск</b>', '', '<b>Что ищут чаще</b>']
    lines += ['%s — %s' % (escape(name), _people(count)) for name, count in n['top_wanted']] or ['пока нет']
    lines += ['', '<b>Что смотрят на сайте</b>']
    lines += ['%s — %s, просмотров %d' % (escape(v['title']), _people(v['clients']), v['views'])
              for v in n['top_viewed']] or ['пока нет']
    lines += ['', '<b>Запросы</b>']
    lines += ['%s · %s — %s · менеджер %s · найдено %d' % (
        number(r['id']), escape(names.get(r['client_phone'], r['client_phone'])), escape(alerts.describe(r['criteria'])),
        escape(staff.get(r['staff_id'], str(r['staff_id']))), counts.get(r['id'], 0)) for r in n['requests']] or ['пока нет']
    people = []
    for r in n['requests']:
        if r['client_phone'] not in people:
            people.append(r['client_phone'])
    buttons = [[('%s · %d' % (names.get(p, p), sum(r['client_phone'] == p for r in n['requests'])), 'ac:c:' + p)]
               for p in people[:SHOWN]]
    return {'text': _fit('\n'.join(lines)), 'buttons': buttons + [[BACK]]}


def with_card(card, phone, requests, counts, views, right, owner):
    """Карточка клиента с автопоиском; `right` — права менеджера этого логина или None; `owner` — смотрит владелец."""
    lines = ['']
    if right:
        lines.append('<b>👔 Менеджер сайта:</b> %s · видит %s' % (
            escape(right['staff_name']), 'всех клиентов' if right['sees_all'] else 'своих клиентов'))
    lines.append('<b>🔔 Автопоиск</b>')
    lines += ['%s · %s — найдено %d' % (number(r['id']), escape(alerts.describe(r['criteria'])), counts.get(r['id'], 0))
              for r in requests] or ['запросов нет']
    if views:
        lines += ['<b>Смотрел на сайте</b>'] + ['%s — %d раз(а)' % (escape(v['title']), v['count']) for v in views]
    block = '\n'.join(lines)
    text, mark = card['text'], '\n\n<b>Ставки</b>'
    text = text.replace(mark, '\n' + block + mark, 1) if mark in text else text + '\n' + block
    buttons = list(card['buttons'])
    if owner:
        role = ('✖️ Снять права менеджера', 'ac:roleoff:' + phone) if right else \
            ('👔 Права менеджера на сайте', 'ac:role:' + phone)
        buttons.insert(len(buttons) - 1, [role])
    return dict(card, text=_fit(text), buttons=buttons)


def role_screen(client, staff, owners):
    """Выбор сотрудника CRM для логина сайта; `staff` — активные сотрудники CRM (user_id, full_name, username)."""
    text = ('<b>👔 Права менеджера на сайте</b>\nЛогин %s будет входить на сайт как менеджер. Выберите сотрудника '
            'CRM — ему будут приходить запросы его клиентов и кнопки «📲 Отправить в группу WhatsApp».'
            % escape(client['phone']))
    rows = []
    for person in staff:
        label = person.get('full_name') or ('@' + person['username'] if person.get('username') else str(person['user_id']))
        if person.get('username') and person.get('full_name'):
            label += ' (@%s)' % person['username']
        if person['user_id'] in owners:
            label += ' — владелец'
        rows.append([(label, 'ac:roleset:%s:%d' % (client['phone'], person['user_id']))])
    return {'text': text, 'buttons': rows + [[('← Карточка', 'ac:c:' + client['phone'])]]}


def _fit(text):
    if len(text) <= LIMIT:
        return text
    return text[:text.rfind('\n', 0, LIMIT)] + '\n…'
