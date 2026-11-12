"""Client bids on the Korea auction: requests from the site, placed by a person (JPAUTO-KOREA-001, owner 2026-11-12).

Owner 2026-11-12 (variant А): nothing is sent to the auction from the server. A bid is placed by the owner or a
manager themselves, in their own browser, as a personal click.
- request(): a logged-in client's bid from the site becomes a request ('requested'); the CRM bot shows it to the staff
  with «Открыть лот», «✅ Поставил», «❌ Не поставил»; mark() records the answer once ('placed' / 'not_placed').
- by_manager(): a manager's bid for a client from the CRM bot, placed by them on the auction, recorded as 'placed'.
check() refuses a bid before it is recorded: unknown lot, unknown start price, below start + 50 000 ₩, not a whole
10 000 ₩, or the account's 30 bids a day used up (placed and waiting ones count); the USD amount is by the NBU rate of
the lot list. Every bid keeps the lot's VIN, who started it (placed_by: 0 — the client on the site, otherwise the
manager's Telegram id) and who answered it (handled_by, handled_at). Older ledgers get the columns; their bids stay
as they were ('placed' / 'failed'). This module never talks to Telegram or to the auction.
"""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3

LOTS = Path('/home/Carix/video/korea/lots.json')
DB = Path('/home/Carix/auction_clients/bids.db')
LOT_URL = 'https://jpauto.auction/vehicle-detail/kr/%s'  # the lot page on the auction, opened by the person who bids
STEP_KRW = 10000          # the auction's bid field is in units of 10 000 ₩
MIN_ABOVE_START = 50000   # «Please Bid at least 50,000KRW higher than the start price»
DAY_LIMIT = 30            # the account's «Day Limit : 30»
KST = timezone(timedelta(hours=9))
SCHEMA = '''CREATE TABLE IF NOT EXISTS bids (
    id INTEGER PRIMARY KEY, phone TEXT NOT NULL, lot_id TEXT NOT NULL, title TEXT NOT NULL, krw INTEGER NOT NULL,
    usd INTEGER NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL,
    notified INTEGER NOT NULL DEFAULT 0, vin TEXT NOT NULL DEFAULT '', placed_by INTEGER NOT NULL DEFAULT 0,
    handled_by INTEGER NOT NULL DEFAULT 0, handled_at TEXT NOT NULL DEFAULT '')'''
# Columns added after the first ledgers: (name, definition).
ADDED = (('vin', "TEXT NOT NULL DEFAULT ''"), ('placed_by', 'INTEGER NOT NULL DEFAULT 0'),
         ('handled_by', 'INTEGER NOT NULL DEFAULT 0'), ('handled_at', "TEXT NOT NULL DEFAULT ''"))
# The staff messages of a request (one per chat), so an answer updates all of them.
NOTICES = 'CREATE TABLE IF NOT EXISTS notices (bid_id INTEGER NOT NULL, chat INTEGER NOT NULL, message_id INTEGER NOT NULL)'


class BidError(ValueError):
    """A refused bid; the message is a short code the page translates."""


def _connect(db=None):
    db = db or DB
    db.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = sqlite3.connect(db, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute(SCHEMA)
    connection.execute(NOTICES)
    columns = {row[1] for row in connection.execute('PRAGMA table_info(bids)')}
    for name, definition in ADDED:
        if name not in columns:
            connection.execute('ALTER TABLE bids ADD COLUMN %s %s' % (name, definition))
    return connection


def _now(now=None):
    return (now or datetime.now(KST)).astimezone(KST).isoformat(timespec='seconds')


def lot_info(lot_id, lots_path=None):
    """(lot, nbu) from the public lot list, or BidError('lot')."""
    data = json.loads((lots_path or LOTS).read_text(encoding='utf-8'))
    for lot in data.get('lots', []):
        if lot['id'] == lot_id:
            return lot, data['nbu']
    raise BidError('lot')


def usd(krw, nbu):
    return round(krw * nbu['krw_uah'] / nbu['usd_uah'])


def today_count(db=None, now=None):
    """Today's bids (Korea time) that use the account's day limit: placed ones and those still waiting."""
    day = _now(now)[:10]
    with closing(_connect(db)) as connection:
        return connection.execute("SELECT count(*) FROM bids WHERE status IN ('placed', 'requested') "
                                  "AND substr(created_at, 1, 10) = ?", (day,)).fetchone()[0]


def check(client, lot_id, krw, lots_path=None, db=None, now=None):
    """The validated bid {'lot', 'krw', 'usd'} or BidError."""
    if not re.fullmatch(r'[0-9]{6,20}', str(lot_id)):
        raise BidError('lot')
    lot, nbu = lot_info(str(lot_id), lots_path)
    try:
        krw = int(krw)
    except (TypeError, ValueError):
        raise BidError('amount') from None
    if not lot.get('start_krw'):
        raise BidError('no_start_price')
    if krw % STEP_KRW:
        raise BidError('step')
    if krw < lot['start_krw'] + MIN_ABOVE_START:
        raise BidError('too_low')
    amount_usd = usd(krw, nbu)
    if today_count(db, now) >= DAY_LIMIT:
        raise BidError('day_limit')
    return {'lot': lot, 'krw': krw, 'usd': amount_usd}


def _insert(client, bid, status, placed_by, handled_by, db, now):
    stamp = _now(now)
    with closing(_connect(db)) as connection, connection:
        return connection.execute(
            'INSERT INTO bids (phone, lot_id, title, krw, usd, status, message, created_at, vin, placed_by, handled_by, '
            'handled_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (client['phone'], bid['lot']['id'], '%s %s' % (bid['lot']['title'], bid['lot']['year']), bid['krw'],
             bid['usd'], status, '', stamp, str(bid['lot'].get('vin') or '')[:40], int(placed_by), int(handled_by),
             stamp if handled_by else '')).lastrowid


def request(client, bid, db=None, now=None):
    """A client's checked bid from the site, waiting for a person to place it; -> its id."""
    return _insert(client, bid, 'requested', 0, 0, db, now)


def by_manager(client, bid, manager, db=None, now=None):
    """A manager's checked bid for a client, placed by them on the auction; -> its id."""
    return _insert(client, bid, 'placed', manager, manager, db, now)


def mark(bid_id, manager, placed, db=None, now=None):
    """A person's answer to a waiting request; True only for the first answer (a second tap changes nothing)."""
    with closing(_connect(db)) as connection, connection:
        return connection.execute(
            "UPDATE bids SET status = ?, handled_by = ?, handled_at = ? WHERE id = ? AND status = 'requested'",
            ('placed' if placed else 'not_placed', int(manager), _now(now), int(bid_id))).rowcount == 1


def get(bid_id, db=None):
    with closing(_connect(db)) as connection:
        row = connection.execute('SELECT * FROM bids WHERE id = ?', (int(bid_id),)).fetchone()
        return dict(row) if row else None


def unnotified(db=None):
    with closing(_connect(db)) as connection:
        return [dict(row) for row in connection.execute('SELECT * FROM bids WHERE notified = 0 ORDER BY id')]


def mark_notified(bid_id, db=None):
    with closing(_connect(db)) as connection, connection:
        connection.execute('UPDATE bids SET notified = 1 WHERE id = ?', (bid_id,))


def add_notice(bid_id, chat, message_id, db=None):
    with closing(_connect(db)) as connection, connection:
        connection.execute('INSERT INTO notices (bid_id, chat, message_id) VALUES (?,?,?)',
                           (int(bid_id), int(chat), int(message_id)))


def notices(bid_id, db=None):
    """[(chat, message_id)] of the staff messages of a request."""
    with closing(_connect(db)) as connection:
        return [(r['chat'], r['message_id']) for r in connection.execute(
            'SELECT chat, message_id FROM notices WHERE bid_id = ?', (int(bid_id),))]
