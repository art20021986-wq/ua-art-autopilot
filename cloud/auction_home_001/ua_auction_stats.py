"""Auction clients' statistics and bids by date for the CRM bot (JPAUTO-KOREA-001, owner 2026-11-11).

Read only: the clients (ua_auction_clients) and the bids ledger (ua_auction_bids). Dates are the ledger's own
(Korea time, as the auction). Pure queries; texts are in ua_auction_clients_view.
"""
from contextlib import closing
from datetime import datetime, timedelta
import sqlite3

import ua_auction_bids as bids
import ua_auction_clients as clients


def _rows(sql, args=(), db=None):
    path = db or bids.DB
    if not path.exists():
        return []
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=10)) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(sql, args)]


def summary(now=None, db=None, people=None):
    """Numbers for the «🔨 Клиенты аукциона» screen."""
    people = clients.all_clients() if people is None else people
    now = (now or datetime.now(bids.KST)).astimezone(bids.KST)
    today, week = now.strftime('%Y-%m-%d'), (now - timedelta(days=6)).strftime('%Y-%m-%d')
    rows = _rows('SELECT status, krw, usd, substr(created_at, 1, 10) AS day FROM bids', db=db)
    return {'clients': len(people), 'active': sum(1 for c in people if not c['blocked']),
            'blocked': sum(1 for c in people if c['blocked']),
            'deposit_usd': sum(c['deposit_usd'] for c in people), 'limit_usd': sum(c['limit_usd'] for c in people),
            'bids_today': sum(1 for r in rows if r['day'] == today),
            'bids_week': sum(1 for r in rows if r['day'] >= week), 'bids_all': len(rows),
            'placed': sum(1 for r in rows if r['status'] == 'placed'),
            'failed': sum(1 for r in rows if r['status'] != 'placed'),
            'placed_usd_week': sum(r['usd'] for r in rows if r['day'] >= week and r['status'] == 'placed')}


def days(db=None):
    """[(date 'YYYY-MM-DD', number of bids)] of all clients, newest first."""
    return [(r['day'], r['n']) for r in _rows(
        'SELECT substr(created_at, 1, 10) AS day, count(*) AS n FROM bids GROUP BY day ORDER BY day DESC', db=db)]


def on_day(day, db=None):
    """All clients' bids of one date, in time order."""
    return _rows('SELECT * FROM bids WHERE substr(created_at, 1, 10) = ? ORDER BY created_at, id', (day,), db)


def of_client(phone, db=None):
    """One client's bids, newest first."""
    return _rows('SELECT * FROM bids WHERE phone = ? ORDER BY created_at DESC, id DESC', (phone,), db)
