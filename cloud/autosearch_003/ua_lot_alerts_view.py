"""Автопоиск в CRM-боте — тексты и кнопки (AUTOSEARCH-003, владелец 17.11). Чистые функции, без ввода-вывода.

- with_home: блок «🔔 Автопоиск» в «🔨 Клиенты аукциона» и кнопка «🔔 Автопоиск · N» перед «← Меню»;
- screen: «🔔 Автопоиск» — что ищут чаще, что смотрят на сайте, запросы менеджеров сайта (клиент менеджера, условия,
  менеджер, отправлено в группу);
- with_card: в карточке клиента аукциона — лоты, которые он открывал на сайте (карточка — как до AUTOSEARCH-002).
Владелец и сотрудники CRM видят одинаково.
"""
from html import escape

import ua_lot_alerts as alerts

BUTTON = 'ac:alerts'
BACK = ('← Клиенты аукциона', 'ac:home')
LIMIT = 3900


def number(request_id):
    return '№%03d' % request_id


def with_home(screen, numbers):
    n = numbers
    block = ('\n\n<b>🔔 Автопоиск</b>\nЗапросов: %d · клиентов у менеджеров: %d\nОтправлено в группы за 7 дней: %d\n'
             'Смотрели лоты на сайте: %d' % (len(n['requests']), n['clients'], n['posted_week'], n['viewers']))
    buttons = list(screen['buttons'])
    buttons.insert(len(buttons) - 1, [('🔔 Автопоиск · %d' % len(n['requests']), BUTTON)])
    return {'text': screen['text'] + block, 'buttons': buttons}


def _people(count):
    return '%d %s' % (count, 'клиент' if count % 10 == 1 and count % 100 != 11 else
                      'клиента' if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14) else 'клиентов')


def screen(numbers, contacts, managers, counts):
    """`contacts`: id клиента менеджера -> ПІБ; `managers`: телефон менеджера -> имя; `counts`: id запроса -> отправлено."""
    n = numbers
    lines = ['<b>🔔 Автопоиск</b>', '', '<b>Что ищут чаще</b>']
    lines += ['%s — %s' % (escape(name), _people(count)) for name, count in n['top_wanted']] or ['пока нет']
    lines += ['', '<b>Что смотрят на сайте</b>']
    lines += ['%s — %s, просмотров %d' % (escape(v['title']), _people(v['clients']), v['views'])
              for v in n['top_viewed']] or ['пока нет']
    lines += ['', '<b>Запросы менеджеров сайта</b>']
    lines += ['%s · %s — %s · менеджер %s · отправлено %d' % (
        number(r['id']), escape(contacts.get(r['contact_id'], '?')), escape(alerts.describe(r['criteria'])),
        escape(managers.get(r['manager_phone'], r['manager_phone'])), counts.get(r['id'], 0))
        for r in n['requests']] or ['пока нет']
    return {'text': _fit('\n'.join(lines)), 'buttons': [[BACK]]}


def with_card(card, views):
    """Карточка клиента аукциона с лотами, которые он открывал на сайте."""
    if not views:
        return card
    block = '\n'.join(['', '<b>Смотрел на сайте</b>'] + ['%s — %d раз(а)' % (escape(v['title']), v['count']) for v in views])
    text, mark = card['text'], '\n\n<b>Ставки</b>'
    text = text.replace(mark, '\n' + block + mark, 1) if mark in text else text + '\n' + block
    return dict(card, text=_fit(text))


def _fit(text):
    if len(text) <= LIMIT:
        return text
    return text[:text.rfind('\n', 0, LIMIT)] + '\n…'
