"""Менеджеры сайта в CRM-боте — тексты и кнопки (AUTOSEARCH-003, владелец 17.11, макет 33-AUTOSEARCH-MANAGERS.png, «Да»).
Чистые функции, без ввода-вывода.

«🧑‍💼 Менеджеры сайта · N» в «🔨 Клиенты аукциона» -> список с «➕ Создать менеджера» -> те же 5 шагов, что у клиента
(телефон-логин, фамилия, имя, почта, город) -> логин и пароль -> карточка (🔁 Сменить пароль, ⛔ Заблокировать).
Кнопки: (подпись, callback_data). Callback data: 'sm:list', 'sm:new', 'sm:city:<город>', 'sm:ok', 'sm:cancel',
'sm:c:<phone>' (карточка), 'sm:pw:<phone>', 'sm:block:<phone>', 'sm:unblock:<phone>'.
"""
from html import escape

LIST = 'sm:list'
HOME = ('← Клиенты аукциона', 'ac:home')
SITE = 'https://www.uaart.com.ua/video/korea.html'
STEPS = (('phone', 'Телефон менеджера (это его логин), например +380991112233:'),
         ('surname', 'Фамилия:'), ('name', 'Имя:'), ('email', 'Почта:'),
         ('city', 'Город (нажмите «Киев» или напишите другой):'))
CITY = 'Киев'
ERRORS = {'phone': 'Телефон не похож на номер. Пример: +380991112233',
          'phone_exists': 'Этот телефон уже занят (менеджер или клиент).',
          'surname': 'Напишите фамилию.', 'name': 'Напишите имя.', 'email': 'Почта должна содержать «@».',
          'city': 'Напишите город.', 'not_found': 'Менеджер не найден.'}
CANCEL_HINT = '\n\nОтмена — любая кнопка меню.'


def with_home(screen, count):
    """«🔨 Клиенты аукциона» с кнопкой «🧑‍💼 Менеджеры сайта · N» перед «← Меню»."""
    buttons = list(screen['buttons'])
    buttons.insert(len(buttons) - 1, [('🧑‍💼 Менеджеры сайта · %d' % count, LIST)])
    return dict(screen, buttons=buttons)


def list_view(managers, counts):
    """`counts`: телефон менеджера -> сколько у него клиентов."""
    text = ('<b>🧑‍💼 Менеджеры сайта</b>\nВходят на сайт и работают там: свои клиенты, запросы поиска, группы WhatsApp.\n'
            + ('Всего: %d' % len(managers) if managers else 'Пока нет менеджеров.'))
    rows = [[('➕ Создать менеджера', 'sm:new')]]
    rows += [[('%s%s %s · клиентов %d' % ('⛔ ' if m['blocked'] else '', m['surname'], m['name'], counts.get(m['phone'], 0)),
               'sm:c:' + m['phone'])] for m in managers[:40]]
    return {'text': text, 'buttons': rows + [[HOME]]}


def ask(step):
    field, question = STEPS[step]
    buttons = [[(CITY, 'sm:city:' + CITY)]] if field == 'city' else []
    return {'text': '<b>➕ Новый менеджер сайта</b> · шаг %d из %d\n%s%s' % (step + 1, len(STEPS), question, CANCEL_HINT),
            'buttons': buttons}


def confirm(draft):
    lines = ['<b>Проверьте данные менеджера</b>', 'Телефон (логин): %s' % escape(draft['phone']),
             'Фамилия: %s' % escape(draft['surname']), 'Имя: %s' % escape(draft['name']),
             'Почта: %s' % escape(draft['email']), 'Город: %s' % escape(draft['city'])]
    return {'text': '\n'.join(lines), 'buttons': [[('✅ Создать', 'sm:ok'), ('✖ Отмена', 'sm:cancel')]]}


def card(manager, clients=0, requests=0, created_by=''):
    state = '⛔ заблокирован' if manager['blocked'] else '✅ доступ открыт'
    lines = ['<b>%s %s</b> · менеджер сайта' % (escape(manager['surname']), escape(manager['name'])),
             'Логин: %s' % escape(manager['phone']), 'Создал: %s' % escape(created_by or str(manager['created_by'])),
             'Почта: %s' % escape(manager['email']), 'Город: %s' % escape(manager['city']),
             'Клиентов: %d · запросов: %d' % (clients, requests), 'Статус: ' + state]
    phone = manager['phone']
    block = ('✅ Разблокировать', 'sm:unblock:' + phone) if manager['blocked'] else ('⛔ Заблокировать', 'sm:block:' + phone)
    return {'text': '\n'.join(lines), 'buttons': [[('🔁 Сменить пароль', 'sm:pw:' + phone), block],
                                                  [('К списку менеджеров', LIST)]]}


def access_text(manager, password):
    """Сообщение для пересылки менеджеру (простой текст)."""
    return ('Доступ менеджера UA ART — сайт\nЛогін: %s\nПароль: %s\nВхід: %s → «Вхід для клієнтів» → «Мій кабінет»'
            % (manager['phone'], password, SITE))


def created(manager, password, created_by=''):
    view = card(manager, created_by=created_by)
    view['text'] = '✅ Менеджер создан. Перешлите ему сообщение ниже.\n\n' + view['text']
    return view, access_text(manager, password)


def password_changed(manager, password, clients=0, requests=0, created_by=''):
    view = card(manager, clients, requests, created_by)
    view['text'] = '🔁 Пароль изменён, старый больше не действует. Перешлите менеджеру сообщение ниже.\n\n' + view['text']
    return view, access_text(manager, password)
