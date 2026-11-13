"""Choose ticker lots: next auction day, models popular in Ukraine, random order."""
import random
import re
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))  # the auction site shows Japan time; Korea is the same offset

# Korean models in demand in Ukraine (owner-approved list, 2026-11-10).
TOP_MODELS = ('TUCSON', 'SPORTAGE', 'SANTA FE', 'SORENTO', 'SONATA', 'K5', 'PALISADE', 'CARNIVAL',
              'IONIQ 5', 'IONIQ 6', 'EV6', 'KONA', 'NIRO', 'G80', 'GV70')
_TOP = [(m, re.compile(r'(?<![\w])' + re.escape(m) + r'(?![\w])')) for m in TOP_MODELS]


def top_model(lot):
    """Canonical top-model name for a lot, or None."""
    name = lot['model'].upper()
    return next((m for m, rx in _TOP if rx.search(name)), None)


def auction_date(lot):
    return lot['auction_start'][:10]  # 'YYYY/MM/DD'


def upcoming(lots, now=None):
    """The lots of today's and the coming auction days (Japan/Korea time), as the ticker (TICKER-FIX2-001) shows."""
    today = (now or datetime.now(JST)).strftime('%Y/%m/%d')
    return [lot for lot in lots if auction_date(lot) >= today]


def next_auction_date(lots, now=None):
    """Earliest auction date after today (Japan/Korea time); while the next day's lots are not listed yet, today if it
    has lots — started ones too: their countdown hides itself (TICKER-FIX2-001: the ticker must never stall); else None."""
    today = (now or datetime.now(JST)).strftime('%Y/%m/%d')
    dates = sorted({auction_date(l) for l in lots if auction_date(l) > today})
    if dates:
        return dates[0]
    return today if any(auction_date(l) == today for l in lots) else None


def ticker_dates(lots, now=None):
    """TICKER-FIX6-001: the dates the ticker takes cars from, in order — the next auction days, then today (a freshly
    listed next day may have no popular car with a photo and price yet; the ticker must never stay empty)."""
    today = (now or datetime.now(JST)).strftime('%Y/%m/%d')
    dates = {auction_date(l) for l in lots}
    return sorted(d for d in dates if d > today) + ([today] if today in dates else [])


NEXT_DAYS = 3  # owner 2026-11-13: the yellow tile lists the 3 nearest auction days after today


def today_and_next_days(lots, now=None, days=NEXT_DAYS):
    """Today's date and the nearest auction days after today with their listed car counts:
    ('YYYY/MM/DD', [('YYYY/MM/DD', n), ...]) — at most `days`, fewer when the auction lists fewer."""
    today = (now or datetime.now(JST)).strftime('%Y/%m/%d')
    counts = {}
    for lot in lots:
        if auction_date(lot) > today:
            counts[auction_date(lot)] = counts.get(auction_date(lot), 0) + 1
    return today, sorted(counts.items())[:days]


def day_after(date):
    return (datetime.strptime(date, '%Y/%m/%d') + timedelta(days=1)).strftime('%Y/%m/%d')


def candidates(lots, date, is_own=lambda lot: False, rng=random):
    """Lots of that date: the owner's models first, then other top models; each group shuffled."""
    day = [l for l in lots if auction_date(l) == date and l['photos']]
    own = [l for l in day if is_own(l)]
    top = [l for l in day if not is_own(l) and top_model(l)]
    rng.shuffle(own)
    rng.shuffle(top)
    return own + top


def is_hot(start_price, market_sold):
    """Below the usual price: start price under 85% of the median of recent sales (>=2 sales)."""
    if start_price <= 0 or len(market_sold) < 2:
        return False
    sold = sorted(market_sold)
    mid = len(sold) // 2
    median = sold[mid] if len(sold) % 2 else (sold[mid - 1] + sold[mid]) / 2
    return start_price < 0.85 * median
