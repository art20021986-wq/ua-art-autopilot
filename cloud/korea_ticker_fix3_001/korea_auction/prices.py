"""Start prices of the lots on the site (owner 2026-11-10: no lot without a price).

The auction's results table has no start price; each lot page has it. Prices are read from the lot pages a few
hundred per run (the session keeps its pause between requests) and remembered in CACHE, so every lot page is read
once; lots that left the auction are forgotten. One responsibility: the price cache.
"""
import json
from pathlib import Path

from . import lots

CACHE = Path('/home/Carix/korea_auction_data/prices.json')
PER_RUN = 600


def load(path=None):
    path = path or CACHE
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return {str(k): int(v) for k, v in value.items()} if isinstance(value, dict) else {}


def save(prices, path=None):
    path = path or CACHE
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(prices, separators=(',', ':')), encoding='utf-8')
    temporary.replace(path)


def fill(session, day_lots, known, limit=PER_RUN):
    """Known prices for these lots, reading at most `limit` new lot pages. -> (prices, lots still unknown)."""
    current = {lot['id'] for lot in day_lots}
    prices = {k: v for k, v in known.items() if k in current}
    missing = [lot for lot in day_lots if lot['id'] not in prices]
    for lot in missing[:limit]:
        try:
            _, html = session.fetch(lot['detail_url'])
        except OSError:
            continue
        prices[lot['id']] = lots.parse_detail(html)['start_price_krw']
    return prices, sum(1 for lot in day_lots if lot['id'] not in prices)


def apply(day_lots, prices):
    """The lots with their known start prices."""
    return [dict(lot, start_price_krw=prices.get(lot['id'], lot['start_price_krw'])) for lot in day_lots]
