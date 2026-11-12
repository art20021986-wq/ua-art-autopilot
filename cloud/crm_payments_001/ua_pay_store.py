"""Payments of an order and the bought car (CRM-PAYMENTS-001). Own tables in crm.db (created if missing, covered by the
daily CRM backup); crm_orders and every other table are only read. `connect` is db.connect (or sqlite3 in tests):
a context manager that commits. Dates are ISO strings in the tables and datetime.date in the returned rows.

purchased_cars(phone) is the read-only contract with the auction client cabinet (session 14): it opens crm.db itself.
"""
import datetime
import json
import sqlite3
import time

import ua_pay_rules as rules

DB_PATH = '/home/Carix/crm.db'
SCHEMA = (
    'CREATE TABLE IF NOT EXISTS crm_pay (order_id INTEGER NOT NULL, kind INTEGER NOT NULL, amount REAL NOT NULL, '
    'start TEXT, due TEXT, ferry TEXT, paid REAL NOT NULL DEFAULT 0, paid_at INTEGER, updated_at INTEGER NOT NULL, '
    'PRIMARY KEY (order_id, kind))',
    'CREATE TABLE IF NOT EXISTS crm_pay_car (order_id INTEGER PRIMARY KEY, lot_url TEXT, lot_id TEXT, vin TEXT, '
    'title TEXT, year TEXT, mileage TEXT, color TEXT, fuel TEXT, photos TEXT, price_krw INTEGER, price_usd INTEGER, '
    'confirmed INTEGER NOT NULL DEFAULT 0, done_by INTEGER, done_at INTEGER NOT NULL)',
    'CREATE TABLE IF NOT EXISTS crm_pay_log (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL, '
    'kind INTEGER, action TEXT NOT NULL, amount REAL, actor INTEGER, at INTEGER NOT NULL)',
    'CREATE TABLE IF NOT EXISTS crm_pay_reminders (key TEXT PRIMARY KEY, at INTEGER NOT NULL)',
    'CREATE TABLE IF NOT EXISTS crm_pay_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
)
CAR_FIELDS = ('lot_url', 'lot_id', 'vin', 'title', 'year', 'mileage', 'color', 'fuel', 'photos', 'price_krw',
              'price_usd')
STAGE_LABELS = {'contract': 'Договор подписан', 'bought': 'Авто выкуплено', 'transit': 'В пути',
                'georgia': 'В Грузии', 'ukraine': 'В Украине', 'delivered': 'Выдано клиенту'}


def _date(text):
    return datetime.date.fromisoformat(text) if text else None


def digits(phone):
    return ''.join(ch for ch in str(phone or '') if ch.isdigit())[-9:]


class PayStore:
    def __init__(self, connect, *, clock=time.time):
        self.connect, self.clock = connect, clock

    def initialize(self):
        with self.connect() as c:
            for statement in SCHEMA:
                c.execute(statement)

    # --- payments --------------------------------------------------------------------------------------------
    def payments(self, order_id):
        """{kind: {'amount', 'paid', 'start', 'due', 'ferry', 'paid_at'}} — payment 1 always present."""
        self.ensure_first(order_id)
        with self.connect() as c:
            rows = c.execute('SELECT kind, amount, paid, start, due, ferry, paid_at FROM crm_pay WHERE order_id=?',
                             (int(order_id),)).fetchall()
        return {kind: {'amount': amount, 'paid': paid, 'start': _date(start), 'due': _date(due), 'ferry': _date(ferry),
                       'paid_at': paid_at} for kind, amount, paid, start, due, ferry, paid_at in rows}

    def ensure_first(self, order_id):
        with self.connect() as c:
            c.execute('INSERT OR IGNORE INTO crm_pay (order_id, kind, amount, updated_at) VALUES (?, 1, ?, ?)',
                      (int(order_id), rules.SERVICE_USD + rules.PREPAY_USD, int(self.clock())))

    def issue(self, order_id, kind, amount, start, actor, ferry=None):
        """Issue (or re-issue) payment 2–4: amount and the due date counted from `start` (a date)."""
        if kind not in (2, 3, 4) or amount <= 0:
            raise ValueError('payment')
        due = rules.due_date(kind, start, ferry)
        now = int(self.clock())
        with self.connect() as c:
            c.execute('INSERT INTO crm_pay (order_id, kind, amount, start, due, ferry, updated_at) '
                      'VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(order_id, kind) DO UPDATE SET amount=excluded.amount, '
                      'start=excluded.start, due=excluded.due, ferry=excluded.ferry, updated_at=excluded.updated_at',
                      (int(order_id), kind, float(amount), start.isoformat(), due.isoformat(),
                       ferry.isoformat() if ferry else None, now))
            self._log(c, order_id, kind, 'issue', amount, actor, now)
        return due

    def pay(self, order_id, kind, amount, actor):
        """Add a payment (USD) to `kind`; returns the payment after it."""
        if amount <= 0:
            raise ValueError('amount')
        now = int(self.clock())
        with self.connect() as c:
            row = c.execute('SELECT amount, paid FROM crm_pay WHERE order_id=? AND kind=?',
                            (int(order_id), kind)).fetchone()
            if row is None:
                raise LookupError('payment')
            paid = round(row[1] + float(amount), 2)
            c.execute('UPDATE crm_pay SET paid=?, paid_at=CASE WHEN ? >= amount THEN ? ELSE paid_at END, updated_at=? '
                      'WHERE order_id=? AND kind=?', (paid, paid, now, now, int(order_id), kind))
            self._log(c, order_id, kind, 'pay', amount, actor, now)
        return self.payments(order_id)[kind]

    def _log(self, c, order_id, kind, action, amount, actor, now):
        c.execute('INSERT INTO crm_pay_log (order_id, kind, action, amount, actor, at) VALUES (?, ?, ?, ?, ?, ?)',
                  (int(order_id), kind, action, amount, actor, now))

    def history(self, order_id, limit=30):
        with self.connect() as c:
            return c.execute('SELECT kind, action, amount, actor, at FROM crm_pay_log WHERE order_id=? '
                             'ORDER BY id DESC LIMIT ?', (int(order_id), limit)).fetchall()

    # --- the bought car ---------------------------------------------------------------------------------------
    def car(self, order_id):
        with self.connect() as c:
            row = c.execute('SELECT %s, confirmed FROM crm_pay_car WHERE order_id=?' % ', '.join(CAR_FIELDS),
                            (int(order_id),)).fetchone()
        if row is None:
            return None
        car = dict(zip(CAR_FIELDS + ('confirmed',), row))
        car['photos'] = json.loads(car['photos'] or '[]')
        return car

    def set_car(self, order_id, data, actor):
        values = dict(data, photos=json.dumps(list(data.get('photos') or [])[:30]))
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO crm_pay_car (order_id, %s, confirmed, done_by, done_at) '
                      'VALUES (?, %s, 0, ?, ?)' % (', '.join(CAR_FIELDS), ', '.join('?' * len(CAR_FIELDS))),
                      (int(order_id),) + tuple(values.get(f) for f in CAR_FIELDS) + (actor, int(self.clock())))
            self._log(c, order_id, None, 'car', data.get('price_usd'), actor, int(self.clock()))

    def confirm_price(self, order_id, price_usd, start, actor):
        """The manager confirms the purchase price: the car is fixed and payment 2 is issued from `start`."""
        with self.connect() as c:
            if c.execute('UPDATE crm_pay_car SET price_usd=?, confirmed=1 WHERE order_id=?',
                         (int(price_usd), int(order_id))).rowcount != 1:
                raise LookupError('car')
        return self.issue(order_id, 2, max(int(price_usd) - rules.PREPAY_USD, 1), start, actor)

    # --- orders, reminders, settings --------------------------------------------------------------------------
    def orders(self):
        """Open orders (not delivered): id, contract_no, name, phone, stage, created_by."""
        with self.connect() as c:
            rows = c.execute("SELECT id, contract_no, name, phone, stage, created_by FROM crm_orders "
                             "WHERE stage != 'delivered' ORDER BY id").fetchall()
        return [dict(zip(('id', 'contract_no', 'name', 'phone', 'stage', 'created_by'), row)) for row in rows]

    def claim_reminder(self, key):
        """True the first time `key` is claimed (each reminder is sent once)."""
        with self.connect() as c:
            return c.execute('INSERT OR IGNORE INTO crm_pay_reminders (key, at) VALUES (?, ?)',
                             (key, int(self.clock()))).rowcount == 1

    def meta(self, key, default=None):
        with self.connect() as c:
            row = c.execute('SELECT value FROM crm_pay_meta WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def set_meta(self, key, value):
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO crm_pay_meta (key, value) VALUES (?, ?)', (key, str(value)))


def purchased_cars(phone, path=DB_PATH):
    """Read-only, for the client cabinet: the cars bought for this phone (last 9 digits), newest first.
    Shows no money (owner: sums only after his decision). [] when nothing is entered yet."""
    key = digits(phone)
    if len(key) < 9:
        return []
    try:
        con = sqlite3.connect('file:%s?mode=ro' % path, uri=True, timeout=10)
    except sqlite3.Error:
        return []
    try:
        rows = con.execute('SELECT o.phone, o.stage, c.title, c.year, c.vin, c.lot_id, c.photos FROM crm_pay_car c '
                           'JOIN crm_orders o ON o.id = c.order_id ORDER BY c.order_id DESC').fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    out = []
    for phone_db, stage, title, year, vin, lot_id, photos in rows:
        if digits(phone_db) == key:
            first = (json.loads(photos or '[]') or [''])[0]
            out.append({'title': title or '', 'year': year or '', 'vin': vin or '', 'lot_id': lot_id or '',
                        'stage': stage, 'stage_label': STAGE_LABELS.get(stage, stage), 'photo': first})
    return out
