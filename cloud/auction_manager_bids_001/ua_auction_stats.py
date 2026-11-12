"""Auction clients' statistics and bids by date for the CRM bot (JPAUTO-KOREA-001, owner 2026-11-11).

Read only: the clients (ua_auction_clients) and the bids ledger (ua_auction_bids). Dates are the ledger's own
(Korea time, as the auction). Pure queries; texts are in ua_auction_clients_view.
Who placed a bid (owner 2026-11-12): placed_by 0 — the client on the site, otherwise the manager's Telegram id; a
client belongs to the manager who created it (clients.created_by). A ledger without the column reads as all 0.
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
    rows = _rows('SELECT *, substr(created_at, 1, 10) AS day FROM bids', db=db)
    return {'clients': len(people), 'active': sum(1 for c in people if not c['blocked']),
            'blocked': sum(1 for c in people if c['blocked']),
            'deposit_usd': sum(c['deposit_usd'] for c in people),
            'bids_today': sum(1 for r in rows if r['day'] == today),
            'bids_week': sum(1 for r in rows if r['day'] >= week), 'bids_all': len(rows),
            'bids_self': sum(1 for r in rows if not _by(r)), 'bids_manager': sum(1 for r in rows if _by(r)),
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


def _by(row):
    """The manager who placed a bid (Telegram id), 0 for the client on the site."""
    return row.get('placed_by') or 0


def managers(people=None, db=None):
    """[{'id', 'clients', 'for_clients', 'clients_self'}] for every manager who created a client or placed a bid:
    clients they created, bids they placed for clients, and bids their clients placed themselves; most active first."""
    people = clients.all_clients() if people is None else people
    owner = {c['phone']: c['created_by'] for c in people}
    rows = _rows('SELECT * FROM bids', db=db)
    table = {}
    def entry(manager):
        return table.setdefault(manager, {'id': manager, 'clients': 0, 'for_clients': 0, 'clients_self': 0})
    for c in people:
        entry(c['created_by'])['clients'] += 1
    for r in rows:
        if _by(r):
            entry(_by(r))['for_clients'] += 1
        elif owner.get(r['phone']):
            entry(owner[r['phone']])['clients_self'] += 1
    return sorted(table.values(), key=lambda m: (-(m['for_clients'] + m['clients_self']), -m['clients'], m['id']))


def of_manager(manager, people=None, db=None):
    """A manager's bids, newest first: those placed for clients, and those their clients placed themselves."""
    people = clients.all_clients() if people is None else people
    own = {c['phone'] for c in people if c['created_by'] == manager}
    return [r for r in _rows('SELECT * FROM bids ORDER BY created_at DESC, id DESC', db=db)
            if _by(r) == manager or (not _by(r) and r['phone'] in own)]

