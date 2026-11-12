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


def next_auction_date(lots, now=None):
    """Earliest auction date after today (Japan/Korea time); before the next day's lots are listed (mornings), today
    while some of today's lots have not started yet (TICKER-FIX-001); else None."""
    now = now or datetime.now(JST)
    today = now.strftime('%Y/%m/%d')
    dates = sorted({auction_date(l) for l in lots if auction_date(l) > today})
    if dates:
        return dates[0]
    stamp = now.strftime('%Y/%m/%d %H:%M')
    return today if any(auction_date(l) == today and l['auction_start'][:16] > stamp for l in lots) else None


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
