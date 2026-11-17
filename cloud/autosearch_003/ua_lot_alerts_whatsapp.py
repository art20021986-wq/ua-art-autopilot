"""Канал WhatsApp автопоиска (AUTOSEARCH-002, владелец 17.11): тексты для группы клиента и ссылка «отправить».

Одна ответственность — что и как уходит в группу WhatsApp; поиск и CRM этот модуль не знает. Чистые функции.
По правилам Meta бот не пишет в группу, созданную вручную (Groups API — только у Official Business Account, группа
создаётся бизнес-номером), поэтому отправляет менеджер одним нажатием: официальная ссылка https://wa.me/?text=<текст>
открывает WhatsApp с готовым текстом, менеджер выбирает группу клиента и жмёт «Отправить».
Тексты — владельца (17.11), по-русски.
"""
import urllib.parse

SITE = 'https://www.uaart.com.ua/video/korea.html'
SHARE = 'https://wa.me/?text='


def welcome(criteria_line):
    """Первое сообщение в группу после сохранения запроса (текст владельца)."""
    return ('Здравствуйте! Создан запрос на поиск вашего авто: %s. Как только подходящий автомобиль появится на '
            'аукционе, мы сразу пришлём сюда всю информацию.' % criteria_line)


def _n(number):
    return '{:,}'.format(int(number)).replace(',', ' ')


def _date(start):
    """«2026/11/18 12:00» -> «18.11»."""
    return '%s.%s' % (start[8:10], start[5:7]) if len(start) >= 10 else ''


def lot(item):
    """Сообщение о подходящем лоте: авто, пробег, цена, день торгов и ссылка на карточку лота на сайте."""
    price = '≈ %s $' % _n(item['start_usd']) if item.get('start_usd') else 'цена уточняется'
    lines = ['🚗 %s %s · %s км · %s' % (item['title'], item['year'], _n(item.get('mileage_km') or 0), price)]
    day = _date(item.get('auction_start', ''))
    if day:
        lines.append('Торги %s' % day)
    lines.append('%s#lot-%s' % (SITE, urllib.parse.quote(str(item['id']), safe='')))
    return '\n'.join(lines)


def share_url(text):
    """Официальная ссылка WhatsApp «поделиться»: открывает WhatsApp с этим текстом, получателя выбирает человек."""
    return SHARE + urllib.parse.quote(text, safe='')
