"""Texts and buttons of auction clients in the CRM bot (JPAUTO-KOREA-001). Pure functions, no I/O.

Buttons are (label, callback_data). Callback data: 'ac:home' («🔨 Клиенты аукциона», main menu), 'ac:new' (start),
'ac:city:<city>', 'ac:ok' / 'ac:cancel' (confirm the new client), 'ac:c:<phone>' (card), 'ac:pw:<phone>',
'ac:block:<phone>', 'ac:unblock:<phone>', 'ac:dep:<phone>', 'ac:list', 'ac:days' (bids by date),
'ac:day:<YYYY-MM-DD>' (the bids of one date).
"""
from datetime import datetime
from html import escape

NEW = ('➕ Создать клиента', 'ac:new')
LIST = 'ac:list'
HOME = ('🔨 Клиенты аукциона', 'ac:home')
DAYS = ('📋 Ставки по датам', 'ac:days')
MENU = ('← Меню', 'menu')
WEEKDAYS = ('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс')
SHOWN_DATES = 40
SITE = 'https://www.uaart.com.ua/video/korea.html'
# The questions, in order: (field, question).
STEPS = (('phone', 'Телефон клиента (это его логин), например +380991112233:'),
         ('surname', 'Фамилия:'), ('name', 'Имя:'), ('email', 'Почта:'),
         ('city', 'Город (нажмите «Киев» или напишите другой):'),
         ('deposit_usd', 'Депозит в $ (каждые 2 000 $ — лимит ставок 15 000 $):'))
CITY = 'Киев'
FIELD_ERRORS = {'phone': 'Телефон не похож на номер. Пример: +380991112233',
                'phone_exists': 'Клиент с этим телефоном уже есть.',
                'surname': 'Напишите фамилию.', 'name': 'Напишите имя.', 'email': 'Почта должна содержать «@».',
                'city': 'Напишите город.', 'deposit': 'Депозит — число от 2000, например 4000.',
                'not_found': 'Клиент не найден.'}
CANCEL_HINT = '\n\nОтмена — любая кнопка меню.'


def ask(step):
    field, question = STEPS[step]
    buttons = [[(CITY, 'ac:city:' + CITY)]] if field == 'city' else []
    return {'text': '<b>Новый клиент аукционов</b> · шаг %d из %d\n%s%s' % (step + 1, len(STEPS), question, CANCEL_HINT),
            'buttons': buttons}


def confirm(draft, limit):
    lines = ['<b>Проверьте данные клиента</b>',
             'Телефон (логин): %s' % escape(draft['phone']), 'Фамилия: %s' % escape(draft['surname']),
             'Имя: %s' % escape(draft['name']), 'Почта: %s' % escape(draft['email']), 'Город: %s' % escape(draft['city']),
             'Депозит: %s $ → лимит ставок %s $' % (_money(draft['deposit_usd']), _money(limit))]
    return {'text': '\n'.join(lines), 'buttons': [[('✅ Создать', 'ac:ok'), ('✖ Отмена', 'ac:cancel')]]}


def _money(value):
    return '{:,}'.format(int(value)).replace(',', ' ')


def access_text(client, password):
    """The message to forward to the client (plain text, ready to copy)."""
    return ('Доступ до аукціонів Кореї — UA ART COMPANY\n'
            'Логін: %s\nПароль: %s\nВхід: %s → «Вхід для клієнтів»\n'
            'Ліміт ставок: %s $' % (client['phone'], password, SITE, _money(client['limit_usd'])))


def _date(day):
    """'2026-11-11' -> 'Ср 11.11.2026'."""
    value = datetime.strptime(day, '%Y-%m-%d')
    return '%s %s' % (WEEKDAYS[value.weekday()], value.strftime('%d.%m.%Y'))


def _bid_line(bid, who=None):
    state = '✅' if bid['status'] == 'placed' else '❌'
    head = '%s %s' % (state, escape(bid['created_at'][11:16]))
    if who is not None:
        head += ' · ' + escape(who)
    return '%s\n   🚗 %s · VIN %s · лот %s\n   ₩%s ≈ $%s' % (
        head, escape(bid['title']), escape(bid.get('vin') or '—'), escape(bid['lot_id']), _money(bid['krw']),
        _money(bid['usd']))


def card(client, bids=()):
    """The client's card; `bids` (newest first) are listed by date under it."""
    state = '⛔ заблокирован' if client['blocked'] else '✅ доступ открыт'
    lines = ['<b>%s %s</b>' % (escape(client['surname']), escape(client['name'])),
             'Логин: %s' % escape(client['phone']), 'Почта: %s' % escape(client['email']),
             'Город: %s' % escape(client['city']),
             'Депозит: %s $ · лимит ставок: %s $' % (_money(client['deposit_usd']), _money(client['limit_usd'])),
             'Статус: ' + state, '', '<b>Ставки</b> (время Кореи): %s' % (len(bids) if bids else 'пока нет')]
    day = None
    for bid in bids:
        if bid['created_at'][:10] != day:
            day = bid['created_at'][:10]
            lines.append('<b>%s</b>' % _date(day))
        lines.append(_bid_line(bid))
    phone = client['phone']
    block = ('✅ Разблокировать', 'ac:unblock:' + phone) if client['blocked'] else ('⛔ Заблокировать', 'ac:block:' + phone)
    return {'text': _fit('\n'.join(lines)),
            'buttons': [[('🔁 Сменить пароль', 'ac:pw:' + phone), block], [('💵 Депозит', 'ac:dep:' + phone)],
                        [('К списку клиентов', LIST)]]}


def _fit(text, limit=3900):
    """Telegram takes up to 4096 characters: a long history is cut at a whole line."""
    if len(text) <= limit:
        return text
    return text[:text.rfind('\n', 0, limit)] + '\n…'


def home(numbers):
    """«🔨 Клиенты аукциона»: the statistics and the buttons."""
    n = numbers
    text = ('<b>🔨 Клиенты аукциона</b>\n'
            'Клиентов: %d (активных %d, заблокировано %d)\n'
            'Депозиты: %s $ · лимит ставок: %s $\n\n'
            '<b>Ставки</b>\nСегодня: %d · за 7 дней: %d · всего: %d\n'
            'Поставлено на аукционе: %d · не прошло: %d\n'
            'Сумма поставленных за 7 дней: %s $'
            % (n['clients'], n['active'], n['blocked'], _money(n['deposit_usd']), _money(n['limit_usd']),
               n['bids_today'], n['bids_week'], n['bids_all'], n['placed'], n['failed'], _money(n['placed_usd_week'])))
    return {'text': text, 'buttons': [[NEW], [('👥 Клиенты с доступом · %d' % n['clients'], LIST)], [DAYS],
                                      [MENU]]}


def days_view(dates):
    """The dates with bids, newest first; each opens that date's bids."""
    buttons = [[('%s · ставок: %d' % (_date(day), count), 'ac:day:' + day)] for day, count in dates[:SHOWN_DATES]]
    text = '<b>📋 Ставки по датам</b> (время Кореи)\n' + ('Выберите дату.' if dates else 'Ставок пока нет.')
    return {'text': text, 'buttons': buttons + [[('← Клиенты аукциона', HOME[1])]]}


def day_view(day, bids, names):
    """All bids of one date: time, client, car, lot, amount, placed or not. `names`: phone -> 'Фамилия Имя'."""
    lines = ['<b>Ставки за %s</b> (время Кореи): %d' % (_date(day), len(bids))]
    lines += [_bid_line(bid, '%s (%s)' % (names.get(bid['phone'], ''), bid['phone'])) for bid in bids]
    return {'text': _fit('\n'.join(lines)), 'buttons': [[('← Ставки по датам', DAYS[1])], [('← Клиенты аукциона', HOME[1])]]}


def created(client, password):
    view = card(client)
    view['text'] = ('✅ Клиент создан. Перешлите клиенту сообщение ниже.\n\n' + view['text'])
    return view, access_text(client, password)


def password_changed(client, password):
    view = card(client)
    view['text'] = '🔁 Пароль изменён, старый больше не действует. Перешлите клиенту сообщение ниже.\n\n' + view['text']
    return view, access_text(client, password)


def list_view(clients, back):
    buttons = [[('%s%s %s · %s' % ('⛔ ' if c['blocked'] else '', c['surname'], c['name'], c['phone']),
                 'ac:c:' + c['phone'])] for c in clients[:40]]
    buttons += [[NEW], [('Назад', back)]]
    text = '<b>Клиенты аукционов онлайн</b>\n%s' % ('Всего: %d' % len(clients) if clients else 'Пока нет клиентов')
    return {'text': text, 'buttons': buttons}


def deposit_prompt(client):
    return {'text': 'Новый депозит клиента %s %s в $ (сейчас %s $). Лимит пересчитается сам.%s'
                    % (escape(client['surname']), escape(client['name']), _money(client['deposit_usd']), CANCEL_HINT),
            'buttons': []}
