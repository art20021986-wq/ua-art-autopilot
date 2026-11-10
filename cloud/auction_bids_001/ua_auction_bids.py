"""Client bids on the Korea auction from the owner's account (JPAUTO-KOREA-001 step В, owner 2026-11-10).

check() refuses a bid before anything is sent: unknown lot, unknown start price, below start + 50 000 ₩, not a whole
10 000 ₩, above the client's limit (in USD by the NBU rate of the lot list), or the account's 30 bids a day used up.
place() then sends it from the owner's auction account (the lot page's own bid form), reads the account's Korea
orders page to confirm it, and writes every attempt to the ledger. The CRM bot reads the ledger to tell the manager
(ua_auction_bids_bot); this module never talks to Telegram.
"""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3

LOTS = Path('/home/Carix/video/korea/lots.json')
DB = Path('/home/Carix/auction_clients/bids.db')
STEP_KRW = 10000          # the auction's bid field is in units of 10 000 ₩ (its page script adds "0000")
MIN_ABOVE_START = 50000   # «Please Bid at least 50,000KRW higher than the start price»
DAY_LIMIT = 30            # the account's «Day Limit : 30»
KST = timezone(timedelta(hours=9))
SCHEMA = '''CREATE TABLE IF NOT EXISTS bids (
    id INTEGER PRIMARY KEY, phone TEXT NOT NULL, lot_id TEXT NOT NULL, title TEXT NOT NULL, krw INTEGER NOT NULL,
    usd INTEGER NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL,
    notified INTEGER NOT NULL DEFAULT 0)'''


class BidError(ValueError):
    """A refused bid; the message is a short code the page translates."""


def _connect(db=None):
    db = db or DB
    db.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = sqlite3.connect(db, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute(SCHEMA)
    return connection


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
    day = (now or datetime.now(KST)).astimezone(KST).strftime('%Y-%m-%d')
    with closing(_connect(db)) as connection:
        return connection.execute("SELECT count(*) FROM bids WHERE status = 'placed' AND substr(created_at, 1, 10) = ?",
                                  (day,)).fetchone()[0]


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
    if amount_usd > client['limit_usd']:
        raise BidError('limit')
    if today_count(db, now) >= DAY_LIMIT:
        raise BidError('day_limit')
    return {'lot': lot, 'krw': krw, 'usd': amount_usd}


def bid_form(html, lot_id):
    """The lot page's bid form: (action, hidden fields), or BidError('form')."""
    found = re.search(r'<form[^>]*action="(/bids/bid/%s/?)"[^>]*id="bidding"[^>]*>(.*?)</form>' % re.escape(lot_id),
                      html, re.S)
    if not found:
        raise BidError('form')
    fields = []
    for tag in re.findall(r'<input[^>]*type="hidden"[^>]*>', found.group(2)):
        name = re.search(r'name="([^"]+)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name:
            fields.append((name.group(1), value.group(1) if value else ''))
    return found.group(1), fields


def confirmed(orders_html, lot_id, krw):
    """Whether the account's Korea orders page lists this lot with this amount."""
    at = orders_html.find(lot_id)
    if at < 0:
        return False
    near = orders_html[at + len(lot_id):at + len(lot_id) + 2000]  # the row of that lot
    amounts = {int(a.replace(',', '')) for a in re.findall(r'([0-9][0-9,]{2,})', near)}
    return krw in amounts or krw // 1000 in amounts or krw // STEP_KRW in amounts


def record(client, bid, status, message, db=None, now=None):
    with closing(_connect(db)) as connection, connection:
        cursor = connection.execute(
            'INSERT INTO bids (phone, lot_id, title, krw, usd, status, message, created_at) VALUES (?,?,?,?,?,?,?,?)',
            (client['phone'], bid['lot']['id'], '%s %s' % (bid['lot']['title'], bid['lot']['year']), bid['krw'],
             bid['usd'], status, message[:200], (now or datetime.now(KST)).astimezone(KST).isoformat(timespec='seconds')))
        return cursor.lastrowid


def place(client, bid, browser, login, db=None):
    """Send the checked bid from the owner's account; -> 'placed' or 'failed'. Every attempt is in the ledger."""
    lot_id = bid['lot']['id']
    try:
        browser.login(*login)
        _, page = browser.fetch('/vehicle-detail/kr/%s' % lot_id)
        action, fields = bid_form(page, lot_id)
        fields = [(k, v) for k, v in fields] + [('bid_price', str(bid['krw'] // STEP_KRW))]
        browser.fetch(action, fields)
        _, orders = browser.fetch('/bids/kr/')
        ok = confirmed(orders, lot_id, bid['krw'])
        status, message = ('placed', '') if ok else ('failed', 'not_confirmed')
    except BidError as error:
        status, message = 'failed', str(error)
    except Exception as error:  # network or site errors are reported, never raised to the page
        status, message = 'failed', type(error).__name__
    record(client, bid, status, message, db)
    return status, message


def unnotified(db=None):
    with closing(_connect(db)) as connection:
        return [dict(row) for row in connection.execute('SELECT * FROM bids WHERE notified = 0 ORDER BY id')]


def mark_notified(bid_id, db=None):
    with closing(_connect(db)) as connection, connection:
        connection.execute('UPDATE bids SET notified = 1 WHERE id = ?', (bid_id,))
