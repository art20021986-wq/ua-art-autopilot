"""Texts and buttons of auction clients in the CRM bot (JPAUTO-KOREA-001). Pure functions, no I/O.

Buttons are (label, callback_data). Callback data: 'ac:home' («🔨 Клиенты аукциона», main menu), 'ac:new' (start),
'ac:city:<city>', 'ac:ok' / 'ac:cancel' (confirm the new client), 'ac:c:<phone>' (card), 'ac:pw:<phone>',
'ac:block:<phone>', 'ac:unblock:<phone>', 'ac:dep:<phone>', 'ac:list', 'ac:days' (bids by date),
'ac:day:<YYYY-MM-DD>' (the bids of one date), 'ac:mgrs' (bids by manager), 'ac:mgr:<telegram id>' (one manager),
'ac:bid:<phone>' (a manager's bid for the client), 'ac:bidok' (send it).
Who placed a bid (owner 2026-11-12): bid['placed_by'] 0 — the client on the site, otherwise the manager's Telegram id;
`staff` maps Telegram ids to the managers' names.
"""
from datetime import datetime
from html import escape

NEW = ('➕ Создать клиента', 'ac:new')
LIST = 'ac:list'
HOME = ('🔨 Клиенты аукциона', 'ac:home')
DAYS = ('📋 Ставки по датам', 'ac:days')
MANAGERS = ('👔 По менеджерам', 'ac:mgrs')
# A refused bid of the manager's dialogue (ua_auction_bids.BidError codes).
BID_ERRORS = {'lot': 'Лота нет в списке торгов. Проверьте номер.', 'amount': 'Сумма — целое число в вонах.',
              'no_start_price': 'У лота нет стартовой цены — ставка пока невозможна.',
              'step': 'Сумма должна быть кратна 10 000 ₩.', 'too_low': 'Минимум — старт + 50 000 ₩.',
              'day_limit': 'На сегодня ставки аккаунта исчерпаны (30), попробуйте завтра.',
              'blocked': 'Клиент заблокирован — ставка за него невозможна.'}
MENU = ('← Меню', 'menu')
WEEKDAYS = ('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс')
SHOWN_DATES = 40
SITE = 'https://www.uaart.com.ua/video/korea.html'
# The questions, in order: (field, question).
STEPS = (('phone', 'Телефон клиента (это его логин), например +380991112233:'),
         ('surname', 'Фамилия:'), ('name', 'Имя:'), ('email', 'Почта:'),
         ('city', 'Город (нажмите «Киев» или напишите другой):'),
         ('deposit_usd', 'Передоплата в $ (от 1 000 $, засчитывается в стоимость авто):'))
CITY = 'Киев'
FIELD_ERRORS = {'phone': 'Телефон не похож на номер. Пример: +380991112233',
                'phone_exists': 'Клиент с этим телефоном уже есть.',
                'surname': 'Напишите фамилию.', 'name': 'Напишите имя.', 'email': 'Почта должна содержать «@».',
                'city': 'Напишите город.', 'deposit': 'Передоплата — число от 1000, например 1000.',
                'not_found': 'Клиент не найден.'}
CANCEL_HINT = '\n\nОтмена — любая кнопка меню.'


def ask(step):
    field, question = STEPS[step]
    buttons = [[(CITY, 'ac:city:' + CITY)]] if field == 'city' else []
    return {'text': '<b>Новый клиент аукционов</b> · шаг %d из %d\n%s%s' % (step + 1, len(STEPS), question, CANCEL_HINT),
            'buttons': buttons}


def confirm(draft):
    lines = ['<b>Проверьте данные клиента</b>',
             'Телефон (логин): %s' % escape(draft['phone']), 'Фамилия: %s' % escape(draft['surname']),
             'Имя: %s' % escape(draft['name']), 'Почта: %s' % escape(draft['email']), 'Город: %s' % escape(draft['city']),
             'Депозит: %s $' % _money(draft['deposit_usd'])]
    return {'text': '\n'.join(lines), 'buttons': [[('✅ Создать', 'ac:ok'), ('✖ Отмена', 'ac:cancel')]]}


def _money(value):
    return '{:,}'.format(int(value)).replace(',', ' ')


def access_text(client, password):
    """The message to forward to the client (plain text, ready to copy)."""
    return ('Доступ до аукціонів Кореї — UA ART COMPANY\n'
            'Логін: %s\nПароль: %s\nВхід: %s → «Вхід для клієнтів»' % (client['phone'], password, SITE))


def _date(day):
    """'2026-11-11' -> 'Ср 11.11.2026'."""
    value = datetime.strptime(day, '%Y-%m-%d')
    return '%s %s' % (WEEKDAYS[value.weekday()], value.strftime('%d.%m.%Y'))


def _bid_line(bid, who=None):
    state = {'placed': '✅', 'requested': '⏳'}.get(bid['status'], '❌')
    head = '%s %s' % (state, escape(bid['created_at'][11:16]))
    if who is not None:
        head += ' · ' + escape(who)
    return '%s\n   🚗 %s · VIN %s · лот %s\n   ₩%s ≈ $%s' % (
        head, escape(bid['title']), escape(bid.get('vin') or '—'), escape(bid['lot_id']), _money(bid['krw']),
        _money(bid['usd']))


def staff_name(staff, manager):
    return staff.get(manager) or 'id %s' % manager


def _placed(bid, staff):
    """Who started the bid and, for a client's request, who answered it (variant А: a person places every bid)."""
    if bid.get('placed_by'):
        return 'ставил: менеджер %s' % staff_name(staff, bid['placed_by'])
    if bid['status'] == 'requested':
        return 'заявка клиента · ждёт менеджера'
    if bid.get('handled_by'):
        return 'заявка клиента · %s %s' % ('поставил' if bid['status'] == 'placed' else 'не поставил',
                                            staff_name(staff, bid['handled_by']))
    return 'сам'


def card(client, bids=(), staff=None):
    """The client's card; `bids` (newest first) are listed by date under it, each with who placed it."""
    staff = staff or {}
    state = '⛔ заблокирован' if client['blocked'] else '✅ доступ открыт'
    lines = ['<b>%s %s</b>' % (escape(client['surname']), escape(client['name'])),
             'Логин: %s' % escape(client['phone']),
             'Оформил: %s' % escape(staff_name(staff, client['created_by'])), 'Почта: %s' % escape(client['email']),
             'Город: %s' % escape(client['city']),
             'Депозит: %s $' % _money(client['deposit_usd']),
             'Статус: ' + state, '', '<b>Ставки</b> (время Кореи): %s' % (len(bids) if bids else 'пока нет')]
    day = None
    for bid in bids:
        if bid['created_at'][:10] != day:
            day = bid['created_at'][:10]
            lines.append('<b>%s</b>' % _date(day))
        lines.append(_bid_line(bid, _placed(bid, staff)))
    phone = client['phone']
    block = ('✅ Разблокировать', 'ac:unblock:' + phone) if client['blocked'] else ('⛔ Заблокировать', 'ac:block:' + phone)
    return {'text': _fit('\n'.join(lines)),
            'buttons': [[('🔁 Сменить пароль', 'ac:pw:' + phone), block], [('💵 Депозит', 'ac:dep:' + phone)],
                        [('🔨 Ставка за клиента', 'ac:bid:' + phone)], [('К списку клиентов', LIST)]]}


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
            'Депозиты: %s $\n\n'
            '<b>Ставки</b>\nСегодня: %d · за 7 дней: %d · всего: %d\n'
            'Клиенты сами: %d · менеджеры за клиентов: %d\n'
            'Поставлено на аукционе: %d · не прошло: %d\n'
            'Сумма поставленных за 7 дней: %s $'
            % (n['clients'], n['active'], n['blocked'], _money(n['deposit_usd']),
               n['bids_today'], n['bids_week'], n['bids_all'], n['bids_self'], n['bids_manager'], n['placed'], n['failed'], _money(n['placed_usd_week'])))
    return {'text': text, 'buttons': [[NEW], [('👥 Клиенты с доступом · %d' % n['clients'], LIST)], [DAYS],
                                      [MANAGERS], [MENU]]}


def days_view(dates):
    """The dates with bids, newest first; each opens that date's bids."""
    buttons = [[('%s · ставок: %d' % (_date(day), count), 'ac:day:' + day)] for day, count in dates[:SHOWN_DATES]]
    text = '<b>📋 Ставки по датам</b> (время Кореи)\n' + ('Выберите дату.' if dates else 'Ставок пока нет.')
    return {'text': text, 'buttons': buttons + [[('← Клиенты аукциона', HOME[1])]]}


def day_view(day, bids, names, staff=None):
    """All bids of one date: time, client, who placed it, car, lot, amount, placed or not.
    `names`: phone -> 'Фамилия Имя'."""
    staff = staff or {}
    lines = ['<b>Ставки за %s</b> (время Кореи): %d' % (_date(day), len(bids))]
    lines += [_bid_line(bid, '%s (%s) · %s' % (names.get(bid['phone'], ''), bid['phone'], _placed(bid, staff)))
              for bid in bids]
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
    buttons += [[('Назад', back)]]  # «➕ Создать клиента» is on «🔨 Клиенты аукциона» (no duplicates)
    text = '<b>Клиенты аукционов онлайн</b>\n%s' % ('Всего: %d' % len(clients) if clients else 'Пока нет клиентов')
    return {'text': text, 'buttons': buttons}


def deposit_prompt(client):
    return {'text': 'Новый депозит клиента %s %s в $ (сейчас %s $).%s'
                    % (escape(client['surname']), escape(client['name']), _money(client['deposit_usd']), CANCEL_HINT),
            'buttons': []}


def managers_view(rows, staff):
    """«👔 По менеджерам»: clients each manager created, bids for clients, bids their clients placed themselves."""
    lines = ['<b>👔 Ставки по менеджерам</b>']
    for m in rows:
        lines += ['', '<b>%s</b> — оформил клиентов: %d' % (escape(staff_name(staff, m['id'])), m['clients']),
                  ' ставок за клиентов: %d · ставки его клиентов сами: %d' % (m['for_clients'], m['clients_self'])]
    if not rows:
        lines.append('Пока нет клиентов и ставок.')
    buttons = [[('%s · %d' % (staff_name(staff, m['id']), m['for_clients'] + m['clients_self']), 'ac:mgr:%s' % m['id'])]
               for m in rows[:40]]
    return {'text': _fit('\n'.join(lines)), 'buttons': buttons + [[('← Назад', HOME[1])]]}


def manager_view(manager, own, bids, names, staff):
    """One manager: `own` clients they created and their bids by date (for whom, or the client alone).
    `names`: phone -> 'Фамилия Имя'."""
    lines = ['<b>%s</b> · клиентов: %d' % (escape(staff_name(staff, manager)), own)]
    day = None
    for bid in bids:
        if bid['created_at'][:10] != day:
            day = bid['created_at'][:10]
            lines.append('<b>%s</b>' % _date(day))
        who = names.get(bid['phone']) or bid['phone']
        lines.append(_bid_line(bid, ('за ' if bid.get('placed_by') else 'сам клиент ') + who))
    if not bids:
        lines.append('Ставок пока нет.')
    return {'text': _fit('\n'.join(lines)), 'buttons': [[('← По менеджерам', MANAGERS[1])]]}


def bid_lot_prompt(client):
    return {'text': '<b>🔨 Ставка за %s %s</b>\nШаг 1 из 2: номер лота (из списка торгов на сайте).%s'
                    % (escape(client['surname']), escape(client['name']), CANCEL_HINT), 'buttons': []}


def bid_amount_prompt(client, lot):
    return {'text': '<b>🔨 Ставка за %s %s</b>\n🚗 %s %s · лот %s · старт ₩%s\n'
                    'Шаг 2 из 2: сумма в ₩ (кратно 10 000, от ₩%s).%s'
                    % (escape(client['surname']), escape(client['name']), escape(str(lot['title'])), escape(str(lot['year'])),
                       escape(lot['id']), _money(lot['start_krw']), _money(lot['start_krw'] + 50000), CANCEL_HINT),
            'buttons': []}


def bid_confirm(client, bid, lot_url):
    """The checked bid: the manager opens the lot, places it themselves on the auction, then «✅ Поставил»."""
    lot = bid['lot']
    return {'text': '<b>Проверьте ставку за %s %s</b>\n🚗 %s %s · лот %s\n₩%s ≈ $%s\n'
                    '→ поставьте сами на аукционе, затем нажмите «✅ Поставил»'
                    % (escape(client['surname']), escape(client['name']), escape(str(lot['title'])), escape(str(lot['year'])),
                       escape(lot['id']), _money(bid['krw']), _money(bid['usd'])),
            'buttons': [[('🔗 Открыть лот на аукционе', lot_url)],
                        [('✅ Поставил', 'ac:bidok'), ('✖ Отмена', 'ac:c:' + client['phone'])]]}


BID_RECORDED = '✅ Ставка записана как ваша.\n\n'
