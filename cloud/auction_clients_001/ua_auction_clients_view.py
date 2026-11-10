"""Texts and buttons of auction clients in the CRM bot (JPAUTO-KOREA-001). Pure functions, no I/O.

Buttons are (label, callback_data). Callback data: 'ac:new' (start), 'ac:city:<city>', 'ac:ok' / 'ac:cancel'
(confirm the new client), 'ac:c:<phone>' (card), 'ac:pw:<phone>', 'ac:block:<phone>', 'ac:unblock:<phone>',
'ac:dep:<phone>', 'ac:list'.
"""
from html import escape

NEW = ('➕ Создать клиента', 'ac:new')
LIST = 'ac:list'
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


def card(client):
    state = '⛔ заблокирован' if client['blocked'] else '✅ доступ открыт'
    lines = ['<b>%s %s</b>' % (escape(client['surname']), escape(client['name'])),
             'Логин: %s' % escape(client['phone']), 'Почта: %s' % escape(client['email']),
             'Город: %s' % escape(client['city']),
             'Депозит: %s $ · лимит ставок: %s $' % (_money(client['deposit_usd']), _money(client['limit_usd'])),
             'Статус: ' + state]
    phone = client['phone']
    block = ('✅ Разблокировать', 'ac:unblock:' + phone) if client['blocked'] else ('⛔ Заблокировать', 'ac:block:' + phone)
    return {'text': '\n'.join(lines),
            'buttons': [[('🔁 Сменить пароль', 'ac:pw:' + phone), block], [('💵 Депозит', 'ac:dep:' + phone)],
                        [('К списку клиентов', LIST)]]}


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
