"""Автопоиск лотов Кореи (AUTOSEARCH-001, владелец 17.11): записи и сверка, без Telegram и без веба.

Владелец: «автопоиск автомобиль с аукционов в личном кабинете с уведомлением … До 10 сохраненных поисков»;
статистика в CRM «кто что смотрит … кто на что подписан» (17.11, «Да»).
- поиски клиента (до 10): марка, модель, год от/до, пробег до, цена до $, топливо, цвет — как фильтры korea.html;
- привязка Telegram: одноразовый код из кабинета (хранится только хеш, 15 мин) -> чат клиентского бота;
- журнал отправленных лотов (один лот — одному клиенту один раз);
- просмотры лотов на korea.html вошедшими клиентами (лот, название, сколько раз, когда последний).
Одна база /home/Carix/auction_clients/alerts.db (SQLite, стандартная библиотека). Сверка — чистая функция matches().
"""
from contextlib import closing
import datetime
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3

DB = Path('/home/Carix/auction_clients/alerts.db')
LOTS = Path('/home/Carix/video/korea/lots.json')
MAX_SEARCHES = 10
CODE_SECONDS = 15 * 60
CODE_PREFIX = 'as-'  # t.me/<бот>?start=as-<код>: 3 + 24 знака из A-Z a-z 0-9 _ - (Telegram допускает до 64)
FUELS = ('gasoline', 'diesel', 'hybrid', 'lpg', 'electric', 'hydrogen')
COLORS = ('white', 'black', 'gray', 'silver', 'blue', 'red', 'brown', 'beige', 'green', 'yellow', 'orange', 'other')
NUMBERS = ('year_from', 'year_to', 'km_max', 'usd_max')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS searches (id INTEGER PRIMARY KEY, phone TEXT NOT NULL, criteria TEXT NOT NULL,
                                     created_at TEXT NOT NULL, lots_at TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS searches_phone ON searches(phone);
CREATE TABLE IF NOT EXISTS links (phone TEXT PRIMARY KEY, chat_id INTEGER NOT NULL, linked_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS codes (hash TEXT PRIMARY KEY, phone TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sent (phone TEXT NOT NULL, lot_id TEXT NOT NULL, search_id INTEGER NOT NULL,
                                 sent_at TEXT NOT NULL, PRIMARY KEY (phone, lot_id));
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
    connection.execute('PRAGMA journal_mode=WAL')
    connection.executescript(SCHEMA)
    return connection


def _text(value, limit=60):
    value = ' '.join(str(value or '').split())
    if len(value) > limit:
        raise AlertError('criteria')
    return value


def criteria(data):
    """Проверенные условия поиска из запроса кабинета; пустое поле — «любой». Хотя бы марка или модель."""
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
    «цена до» (в сообщении — «ціна уточнюється»), чтобы клиент его не пропустил (макет, владелец 17.11)."""
    usd = lot.get('start_usd') or 0
    return ((not rule['maker'] or lot.get('maker') == rule['maker'])
            and (not rule['title'] or lot.get('title') == rule['title'])
            and (not rule['year_from'] or (lot.get('year') or 0) >= rule['year_from'])
            and (not rule['year_to'] or (lot.get('year') or 0) <= rule['year_to'])
            and (not rule['km_max'] or (lot.get('mileage_km') or 0) <= rule['km_max'])
            and (not rule['usd_max'] or not usd or usd <= rule['usd_max'])
            and (not rule['fuel'] or lot.get('fuel') == rule['fuel'])
            and (not rule['color'] or lot.get('color') == rule['color']))


# --- поиски ---

def _search(row):
    return {'id': row['id'], 'phone': row['phone'], 'criteria': json.loads(row['criteria']),
            'created_at': row['created_at'], 'lots_at': row['lots_at']}


def searches(phone=None, db=None):
    with closing(_connect(db)) as connection:
        if phone is None:
            rows = connection.execute('SELECT * FROM searches ORDER BY phone, id').fetchall()
        else:
            rows = connection.execute('SELECT * FROM searches WHERE phone = ? ORDER BY id', (phone,)).fetchall()
    return [_search(row) for row in rows]


def add_search(phone, data, db=None):
    rule = criteria(data)
    with closing(_connect(db)) as connection, connection:
        connection.execute('BEGIN IMMEDIATE')
        if connection.execute('SELECT COUNT(*) FROM searches WHERE phone = ?', (phone,)).fetchone()[0] >= MAX_SEARCHES:
            raise AlertError('limit')
        cursor = connection.execute('INSERT INTO searches (phone, criteria, created_at) VALUES (?, ?, ?)',
                                    (phone, json.dumps(rule, ensure_ascii=False, sort_keys=True), _now()))
    return cursor.lastrowid


def delete_search(phone, search_id, db=None):
    with closing(_connect(db)) as connection, connection:
        return connection.execute('DELETE FROM searches WHERE id = ? AND phone = ?', (int(search_id), phone)).rowcount


def mark_checked(search_id, lots_at, db=None):
    with closing(_connect(db)) as connection, connection:
        connection.execute('UPDATE searches SET lots_at = ? WHERE id = ?', (lots_at, search_id))


# --- Telegram ---

def _digest(code):
    return hashlib.sha256(code.encode()).hexdigest()


def new_code(phone, db=None, now=None):
    """Одноразовый код для ссылки t.me/<бот>?start=<код>; хранится только хеш; прежние коды клиента гаснут."""
    now = datetime.datetime.now().timestamp() if now is None else now
    code = CODE_PREFIX + secrets.token_urlsafe(18)
    with closing(_connect(db)) as connection, connection:
        connection.execute('DELETE FROM codes WHERE phone = ? OR expires < ?', (phone, now))
        connection.execute('INSERT INTO codes VALUES (?, ?, ?)', (_digest(code), phone, now + CODE_SECONDS))
    return code


def link(code, chat_id, db=None, now=None):
    """Телефон клиента для верного, неистёкшего кода (код гаснет сразу), иначе None; чат привязывается к клиенту."""
    now = datetime.datetime.now().timestamp() if now is None else now
    with closing(_connect(db)) as connection, connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute('SELECT phone, expires FROM codes WHERE hash = ?', (_digest(str(code)),)).fetchone()
        if row is None:
            return None
        connection.execute('DELETE FROM codes WHERE hash = ?', (_digest(str(code)),))
        if row['expires'] < now:
            return None
        connection.execute('INSERT OR REPLACE INTO links VALUES (?, ?, ?)', (row['phone'], int(chat_id), _now()))
    return row['phone']


def unlink(phone, db=None):
    with closing(_connect(db)) as connection, connection:
        return connection.execute('DELETE FROM links WHERE phone = ?', (phone,)).rowcount


def chat(phone, db=None):
    with closing(_connect(db)) as connection:
        row = connection.execute('SELECT chat_id FROM links WHERE phone = ?', (phone,)).fetchone()
    return row['chat_id'] if row else None


# --- отправленные и просмотры ---

def unsent(phone, lot_ids, db=None):
    """Лоты из списка, о которых клиенту ещё не писали, в том же порядке."""
    with closing(_connect(db)) as connection:
        done = {row[0] for row in connection.execute('SELECT lot_id FROM sent WHERE phone = ?', (phone,))}
    return [lot_id for lot_id in lot_ids if lot_id not in done]


def record_sent(phone, search_id, lot_ids, db=None):
    stamp = _now()
    with closing(_connect(db)) as connection, connection:
        connection.executemany('INSERT OR IGNORE INTO sent VALUES (?, ?, ?, ?)',
                               [(phone, lot_id, search_id, stamp) for lot_id in lot_ids])


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


def sent_counts(phone, db=None):
    """{id поиска: сколько лотов по нему отправлено}."""
    with closing(_connect(db)) as connection:
        return {row[0]: row[1] for row in connection.execute(
            'SELECT search_id, COUNT(*) FROM sent WHERE phone = ? GROUP BY search_id', (phone,))}


def summary(db=None, now=None):
    """Цифры для «🔨 Клиенты аукциона» и экрана «🔔 Автопоиск»."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    week = (now - datetime.timedelta(days=7)).replace(microsecond=0).isoformat()
    with closing(_connect(db)) as connection:
        one = lambda sql, *args: connection.execute(sql, args).fetchone()[0]
        rows = connection.execute('SELECT phone, criteria FROM searches').fetchall()
        value = {'clients': one('SELECT COUNT(DISTINCT phone) FROM searches'), 'searches': len(rows),
                 'telegram': one('SELECT COUNT(*) FROM links'),
                 'sent_week': one('SELECT COUNT(*) FROM sent WHERE sent_at >= ?', week),
                 'viewers': one('SELECT COUNT(DISTINCT phone) FROM views'),
                 'by_client': {row[0]: row[1] for row in connection.execute(
                     'SELECT phone, COUNT(*) FROM searches GROUP BY phone')},
                 'linked': {row[0] for row in connection.execute('SELECT phone FROM links')},
                 'top_viewed': [dict(row) for row in connection.execute(
                     'SELECT title, SUM(count) AS views, COUNT(DISTINCT phone) AS clients FROM views '
                     'GROUP BY title ORDER BY clients DESC, views DESC LIMIT 10')]}
    wanted = {}
    for phone, text in rows:
        rule = json.loads(text)
        wanted.setdefault(rule['title'] or rule['maker'], set()).add(phone)
    value['top_wanted'] = sorted(((name, len(people)) for name, people in wanted.items()), key=lambda x: (-x[1], x[0]))[:10]
    return value


# слова топлива и цвета: как в окне лота korea.html (uk, ru)
WORDS = {'gasoline': ('бензин', 'бензин'), 'diesel': ('дизель', 'дизель'), 'hybrid': ('гібрид', 'гибрид'),
         'lpg': ('газ (LPG)', 'газ (LPG)'), 'electric': ('електро', 'электро'), 'hydrogen': ('водень', 'водород'),
         'white': ('білий', 'белый'), 'black': ('чорний', 'черный'), 'gray': ('сірий', 'серый'),
         'silver': ('сріблястий', 'серебристый'), 'blue': ('синій', 'синий'), 'red': ('червоний', 'красный'),
         'brown': ('коричневий', 'коричневый'), 'beige': ('бежевий', 'бежевый'), 'green': ('зелений', 'зеленый'),
         'yellow': ('жовтий', 'желтый'), 'orange': ('помаранчевий', 'оранжевый'), 'other': ('інший колір', 'другой цвет')}


def _n(number):
    return '{:,}'.format(int(number)).replace(',', ' ')


def describe(rule, lang=0):
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
