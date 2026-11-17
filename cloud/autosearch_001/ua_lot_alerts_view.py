"""Автопоиск в CRM-боте (AUTOSEARCH-001, владелец 17.11: «видел общую статистику кто что смотрит и … кто на что
подписан»; макет cloud/photos/33-AUTOSEARCH-CRM.png, «Да»). Чистые функции, без ввода-вывода.

- with_home: блок «🔔 Автопоиск» в «🔨 Клиенты аукциона» и кнопка «🔔 Автопоиск · N» перед «← Меню»;
- screen: «🔔 Автопоиск» — что ищут чаще, что смотрят чаще, кто на что подписан (имя -> карточка клиента 'ac:c:<phone>');
- with_card: в карточке клиента его поиски (сколько отправлено), Telegram и последние просмотренные лоты.
Владелец и менеджер видят одинаково (те же права, что у «🔨 Клиенты аукциона»).
"""
from html import escape

import ua_lot_alerts as alerts

BUTTON = 'ac:alerts'
BACK = ('← Клиенты аукциона', 'ac:home')
SHOWN_CLIENTS = 40
LIMIT = 3900


def with_home(screen, numbers):
    n = numbers
    block = ('\n\n<b>🔔 Автопоиск</b>\nКлиентов с поиском: %d · поисков: %d\nTelegram подключён: %d\n'
             'Отправлено авто за 7 дней: %d\nСмотрели лоты на сайте: %d' % (n['clients'], n['searches'], n['telegram'],
                                                                         n['sent_week'], n['viewers']))
    buttons = list(screen['buttons'])
    buttons.insert(len(buttons) - 1, [('🔔 Автопоиск · %d' % n['searches'], BUTTON)])
    return {'text': screen['text'] + block, 'buttons': buttons}


def _people(count):
    return '%d %s' % (count, 'клиент' if count % 10 == 1 and count % 100 != 11 else
                      'клиента' if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14) else 'клиентов')


def screen(numbers, names):
    """`names`: телефон -> «Фамилия Имя» клиентов аукциона."""
    n = numbers
    lines = ['<b>🔔 Автопоиск</b>', '', '<b>Что ищут чаще</b>']
    lines += ['%s — %s' % (escape(name), _people(count)) for name, count in n['top_wanted']] or ['пока нет']
    lines += ['', '<b>Что смотрят на сайте</b>']
    lines += ['%s — %s, просмотров %d' % (escape(v['title']), _people(v['clients']), v['views'])
              for v in n['top_viewed']] or ['пока нет']
    people = sorted(set(n['by_client']) | set(n['linked']), key=lambda p: names.get(p, p))
    lines += ['', '<b>Кто на что подписан</b>']
    lines += ['%s — поисков %d · TG %s' % (escape(names.get(p, p)), n['by_client'].get(p, 0),
                                           '✅' if p in n['linked'] else '❌') for p in people] or ['пока нет']
    buttons = [[('%s · %d' % (names.get(p, p), n['by_client'].get(p, 0)), 'ac:c:' + p)] for p in people[:SHOWN_CLIENTS]]
    return {'text': _fit('\n'.join(lines)), 'buttons': buttons + [[BACK]]}


def with_card(card, searches, sent, linked, views):
    lines = ['', '<b>🔔 Автопоиск</b> · Telegram %s' % ('✅' if linked else '❌')]
    lines += ['%d. %s — отправлено %d' % (i, escape(alerts.describe(s['criteria'], 1)), sent.get(s['id'], 0))
              for i, s in enumerate(searches, 1)] or ['поисков нет']
    if views:
        lines += ['<b>Смотрел на сайте</b>'] + ['%s — %d раз(а)' % (escape(v['title']), v['count']) for v in views]
    block = '\n'.join(lines)
    text = card['text']
    mark = '\n\n<b>Ставки</b>'
    text = text.replace(mark, '\n' + block + mark, 1) if mark in text else text + '\n' + block
    return dict(card, text=_fit(text))


def _fit(text):
    if len(text) <= LIMIT:
        return text
    return text[:text.rfind('\n', 0, LIMIT)] + '\n…'
