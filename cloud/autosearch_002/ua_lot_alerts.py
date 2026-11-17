"""Автопоиск лотов Кореи — записи и сверка (AUTOSEARCH-002, владелец 17.11), без Telegram, WhatsApp и веба.

Владелец 17.11: менеджер на сайте сохраняет для своего клиента критерии поиска и ссылку на группу WhatsApp; первое
сообщение — приветствие, дальше — ссылка на каждый подходящий лот; «До 10 сохраненных поисков»; менеджер видит своих
клиентов, владелец — всех; статистика в CRM «кто что смотрит … кто на что подписан».
- managers: логин сайта (телефон) -> сотрудник CRM (Telegram id); «видит всех» — у владельца;
- requests: запрос на поиск: клиент, сотрудник, ссылка на группу WhatsApp, критерии (как фильтры korea.html);
- found: какие лоты по запросу уже отданы менеджеру (каждый лот — один раз);
- views: какие лоты открывали на korea.html вошедшие клиенты.
Одна база /home/Carix/auction_clients/alerts.db (SQLite, без WAL — сетевой диск). Сверка — чистая функция matches().
Таблицы AUTOSEARCH-001 (поиски клиентов, привязка Telegram) убраны: владелец 17.11 — клиенту «не надо».
"""
from contextlib import closing
import datetime
import json
from pathlib import Path
import re
import sqlite3

DB = Path('/home/Carix/auction_clients/alerts.db')
LOTS = Path('/home/Carix/video/korea/lots.json')
MAX_REQUESTS = 10  # на одного клиента (владелец 17.11: «До 10 сохраненных поисков»)
FUELS = ('gasoline', 'diesel', 'hybrid', 'lpg', 'electric', 'hydrogen')
COLORS = ('white', 'black', 'gray', 'silver', 'blue', 'red', 'brown', 'beige', 'green', 'yellow', 'orange', 'other')
NUMBERS = ('year_from', 'year_to', 'km_max', 'usd_max')
# Ссылка-приглашение в группу WhatsApp — официальный вид https://chat.whatsapp.com/<код>.
GROUP_LINK = re.compile(r'^https://chat\.whatsapp\.com/[A-Za-z0-9]{10,40}$')
SCHEMA = '''
DROP TABLE IF EXISTS searches;
DROP TABLE IF EXISTS links;
DROP TABLE IF EXISTS codes;
DROP TABLE IF EXISTS sent;
CREATE TABLE IF NOT EXISTS managers (phone TEXT PRIMARY KEY, staff_id INTEGER NOT NULL, staff_name TEXT NOT NULL,
                                     sees_all INTEGER NOT NULL, set_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY, client_phone TEXT NOT NULL, staff_id INTEGER NOT NULL,
                                     group_link TEXT NOT NULL, criteria TEXT NOT NULL, created_at TEXT NOT NULL,
                                     welcomed INTEGER NOT NULL DEFAULT 0, lots_at TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS requests_client ON requests(client_phone);
CREATE TABLE IF NOT EXISTS found (request_id INTEGER NOT NULL, lot_id TEXT NOT NULL, found_at TEXT NOT NULL,
                                  PRIMARY KEY (request_id, lot_id));
CREATE TABLE IF NOT EXISTS views (phone TEXT NOT NULL, lot_id TEXT NOT NULL, title TEXT NOT NULL, count INTEGER NOT NULL,
                                  last_at TEXT NOT NULL, PRIMARY KEY (phone, lot_id));
'''


class AlertError(ValueError):
    pass


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _connect(db=None):
    path = Path(db or DB)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


def _text(value, limit=60):
    value = ' '.join(str(value or '').split())
    if len(value) > limit:
        raise AlertError('criteria')
    return value


def criteria(data):
    """Проверенные условия поиска; пустое поле — «любой». Хотя бы марка или модель."""
    if not isinstance(data, dict):
        raise AlertError('criteria')
    value = {'maker': _text(data.get('maker')), 'title': _text(data.get('title'))}
    for key in NUMBERS:
        raw = data.get(key)
        if raw in (None, '', 0, '0'):
            value[key] = 0
            continue
        try:
            number = int(raw)
        except (TypeError, ValueError):
            raise AlertError('criteria')
        if not 0 < number <= 10**7:
            raise AlertError('criteria')
        value[key] = number
    value['fuel'] = data.get('fuel') or ''
    value['color'] = data.get('color') or ''
    if value['fuel'] not in FUELS + ('',) or value['color'] not in COLORS + ('',):
        raise AlertError('criteria')
    if not (value['maker'] or value['title']):
        raise AlertError('maker')
    if value['year_from'] and value['year_to'] and value['year_from'] > value['year_to']:
        value['year_from'], value['year_to'] = value['year_to'], value['year_from']
    return value


def matches(rule, lot):
    """Подходит ли лот под поиск — те же правила, что фильтр korea.html; лот без стартовой цены подходит и при
    «цена до» (в сообщении — «цена уточняется»), чтобы клиент его не пропустил."""
    usd = lot.get('start_usd') or 0
    return ((not rule['maker'] or lot.get('maker') == rule['maker'])
            and (not rule['title'] or lot.get('title') == rule['title'])
            and (not rule['year_from'] or (lot.get('year') or 0) >= rule['year_from'])
            and (not rule['year_to'] or (lot.get('year') or 0) <= rule['year_to'])
            and (not rule['km_max'] or (lot.get('mileage_km') or 0) <= rule['km_max'])
            and (not rule['usd_max'] or not usd or usd <= rule['usd_max'])
            and (not rule['fuel'] or lot.get('fuel') == rule['fuel'])
            and (not rule['color'] or lot.get('color') == rule['color']))


# --- менеджеры сайта ---

def set_manager(phone, staff_id, staff_name, sees_all, db=None):
    with closing(_connect(db)) as connection, connection:
        connection.execute('INSERT OR REPLACE INTO managers VALUES (?, ?, ?, ?, ?)',
                           (phone, int(staff_id), _text(staff_name, 80), 1 if sees_all else 0, _now()))


def unset_manager(phone, db=None):
    with closing(_connect(db)) as connection, connection:
        return connection.execute('DELETE FROM managers WHERE phone = ?', (phone,)).rowcount


def manager(phone, db=None):
    """Права менеджера для логина сайта: {'phone', 'staff_id', 'staff_name', 'sees_all', 'set_at'} или None."""
    with closing(_connect(db)) as connection:
        row = connection.execute('SELECT * FROM managers WHERE phone = ?', (phone,)).fetchone()
    return dict(row) if row else None


def manager_phones(db=None):
    with closing(_connect(db)) as connection:
        return {row[0] for row in connection.execute('SELECT phone FROM managers')}


def own_clients(right, people, managers):
    """Клиенты, которых видит менеджер: оформленные его сотрудником CRM, или все — у владельца; логины менеджеров — нет."""
    return [c for c in people if c['phone'] not in managers
            and (right['sees_all'] or c['created_by'] == right['staff_id'])]


# --- запросы на поиск ---

def _request(row):
    value = dict(row)
    value['criteria'] = json.loads(value['criteria'])
    return value


def requests(client_phone=None, staff_id=None, db=None):
    sql, args = 'SELECT * FROM requests', ()
    if client_phone is not None:
        sql, args = sql + ' WHERE client_phone = ?', (client_phone,)
    elif staff_id is not None:
        sql, args = sql + ' WHERE staff_id = ?', (int(staff_id),)
    with closing(_connect(db)) as connection:
        return [_request(row) for row in connection.execute(sql + ' ORDER BY id', args)]


def add_request(client_phone, staff_id, group_link, data, db=None):
    rule = criteria(data)
    link = str(group_link or '').strip()
    if not GROUP_LINK.match(link):
        raise AlertError('group_link')
    with closing(_connect(db)) as connection, connection:
        connection.execute('BEGIN IMMEDIATE')
        if connection.execute('SELECT COUNT(*) FROM requests WHERE client_phone = ?',
                              (client_phone,)).fetchone()[0] >= MAX_REQUESTS:
            raise AlertError('limit')
        cursor = connection.execute(
            'INSERT INTO requests (client_phone, staff_id, group_link, criteria, created_at) VALUES (?, ?, ?, ?, ?)',
            (client_phone, int(staff_id), link, json.dumps(rule, ensure_ascii=False, sort_keys=True), _now()))
    return cursor.lastrowid


def delete_request(request_id, allowed_phones, db=None):
    """Удалить запрос, если его клиент — среди клиентов этого менеджера."""
    with closing(_connect(db)) as connection, connection:
        row = connection.execute('SELECT client_phone FROM requests WHERE id = ?', (int(request_id),)).fetchone()
        if row is None or row[0] not in allowed_phones:
            return 0
        connection.execute('DELETE FROM found WHERE request_id = ?', (int(request_id),))
        return connection.execute('DELETE FROM requests WHERE id = ?', (int(request_id),)).rowcount


def mark_welcomed(request_id, db=None):
    with closing(_connect(db)) as connection, connection:
        connection.execute('UPDATE requests SET welcomed = 1 WHERE id = ?', (request_id,))


def mark_checked(request_id, lots_at, db=None):
    with closing(_connect(db)) as connection, connection:
        connection.execute('UPDATE requests SET lots_at = ? WHERE id = ?', (lots_at, request_id))


def unfound(request_id, lot_ids, db=None):
    """Лоты из списка, которые по этому запросу ещё не отдавали, в том же порядке."""
    with closing(_connect(db)) as connection:
        done = {row[0] for row in connection.execute('SELECT lot_id FROM found WHERE request_id = ?', (request_id,))}
    return [lot_id for lot_id in lot_ids if lot_id not in done]


def record_found(request_id, lot_ids, db=None):
    stamp = _now()
    with closing(_connect(db)) as connection, connection:
        connection.executemany('INSERT OR IGNORE INTO found VALUES (?, ?, ?)',
                               [(request_id, lot_id, stamp) for lot_id in lot_ids])


def found_counts(db=None):
    """{id запроса: сколько лотов по нему отдано}."""
    with closing(_connect(db)) as connection:
        return {row[0]: row[1] for row in connection.execute(
            'SELECT request_id, COUNT(*) FROM found GROUP BY request_id')}


# --- просмотры ---

def record_view(phone, lot_id, title, db=None):
    lot_id, title = _text(lot_id, 40), _text(title, 80)
    if not lot_id:
        raise AlertError('lot')
    with closing(_connect(db)) as connection, connection:
        connection.execute('INSERT INTO views VALUES (?, ?, ?, 1, ?) ON CONFLICT(phone, lot_id) DO UPDATE SET '
                           'count = count + 1, title = excluded.title, last_at = excluded.last_at',
                           (phone, lot_id, title, _now()))


def views(phone, limit=10, db=None):
    with closing(_connect(db)) as connection:
        rows = connection.execute('SELECT * FROM views WHERE phone = ? ORDER BY last_at DESC LIMIT ?',
                                  (phone, limit)).fetchall()
    return [dict(row) for row in rows]


def summary(staff_id=None, db=None, now=None):
    """Цифры для CRM: все запросы (владелец, staff_id None) или запросы одного сотрудника (менеджер)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    week = (now - datetime.timedelta(days=7)).replace(microsecond=0).isoformat()
    own = requests(staff_id=staff_id, db=db) if staff_id is not None else requests(db=db)
    ids = {r['id'] for r in own}
    with closing(_connect(db)) as connection:
        found_week = sum(1 for row in connection.execute('SELECT request_id FROM found WHERE found_at >= ?', (week,))
                         if row[0] in ids)
        top_viewed = [dict(row) for row in connection.execute(
            'SELECT title, SUM(count) AS views, COUNT(DISTINCT phone) AS clients FROM views '
            'GROUP BY title ORDER BY clients DESC, views DESC LIMIT 10')]
        viewers = connection.execute('SELECT COUNT(DISTINCT phone) FROM views').fetchone()[0]
    wanted = {}
    for request in own:
        rule = request['criteria']
        wanted.setdefault(rule['title'] or rule['maker'], set()).add(request['client_phone'])
    return {'requests': own, 'clients': len({r['client_phone'] for r in own}), 'found_week': found_week,
            'viewers': viewers, 'top_viewed': top_viewed,
            'top_wanted': sorted(((n, len(p)) for n, p in wanted.items()), key=lambda x: (-x[1], x[0]))[:10]}


# слова топлива и цвета: как в окне лота korea.html (uk, ru)
WORDS = {'gasoline': ('бензин', 'бензин'), 'diesel': ('дизель', 'дизель'), 'hybrid': ('гібрид', 'гибрид'),
         'lpg': ('газ (LPG)', 'газ (LPG)'), 'electric': ('електро', 'электро'), 'hydrogen': ('водень', 'водород'),
         'white': ('білий', 'белый'), 'black': ('чорний', 'черный'), 'gray': ('сірий', 'серый'),
         'silver': ('сріблястий', 'серебристый'), 'blue': ('синій', 'синий'), 'red': ('червоний', 'красный'),
         'brown': ('коричневий', 'коричневый'), 'beige': ('бежевий', 'бежевый'), 'green': ('зелений', 'зеленый'),
         'yellow': ('жовтий', 'желтый'), 'orange': ('помаранчевий', 'оранжевый'), 'other': ('інший колір', 'другой цвет')}


def _n(number):
    return '{:,}'.format(int(number)).replace(',', ' ')


def describe(rule, lang=1):
    """Одна строка условий: «Kia K5 · 2020–2023 · до 100 000 км · до 15 000 $ · бензин»; lang 0 — uk, 1 — ru."""
    since, until, upto = ('від', 'до', 'до') if lang == 0 else ('от', 'до', 'до')
    parts = [rule['title'] or rule['maker']]
    if rule['year_from'] and rule['year_to']:
        parts.append('%d–%d' % (rule['year_from'], rule['year_to']) if rule['year_from'] != rule['year_to']
                     else str(rule['year_from']))
    elif rule['year_from']:
        parts.append('%s %d' % (since, rule['year_from']))
    elif rule['year_to']:
        parts.append('%s %d' % (until, rule['year_to']))
    if rule['km_max']:
        parts.append('%s %s км' % (upto, _n(rule['km_max'])))
    if rule['usd_max']:
        parts.append('%s %s $' % (upto, _n(rule['usd_max'])))
    for key in ('fuel', 'color'):
        if rule[key]:
            parts.append(WORDS[rule[key]][lang])
    return ' · '.join(parts)


def read_lots(path=None):
    """(generated_at, лоты) опубликованного списка korea.html; (None, []) если файла нет или он не читается."""
    try:
        value = json.loads(Path(path or LOTS).read_bytes())
        return value['generated_at'], value['lots']
    except (OSError, ValueError, KeyError, TypeError):
        return None, []
