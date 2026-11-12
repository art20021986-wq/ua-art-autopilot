"""What the site shows from each lot page: start price, VIN and all photos (owner 2026-11-10/11/12).

The auction's results table has no start price, no VIN and only 3 photos; each lot page has them. Lot pages are read
a few hundred per run (the session keeps its pause between requests) and remembered in CACHE, so every lot page is
read once; lots that left the auction are forgotten. One responsibility: the lot page cache.
Cache entry: {'krw': start price, 'vin': chassis number, 'photos': [photo addresses]}; an older entry holding only
the price is read again once.
"""
import json
from pathlib import Path

from . import lots

CACHE = Path('/home/Carix/korea_auction_data/prices.json')
PER_RUN = 600
MAX_PHOTOS = None  # every photo of the lot page (owner 2026-11-12: «все фотографии, которые представлены»)


def load(path=None):
    path = path or CACHE
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {str(k): v for k, v in value.items() if isinstance(v, dict)}


def save(known, path=None):
    path = path or CACHE
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(known, separators=(',', ':')), encoding='utf-8')
    temporary.replace(path)


def entry(html):
    detail = lots.parse_detail(html)
    return {'krw': detail['start_price_krw'], 'vin': detail['vin'],
            'photos': detail['photos'][:MAX_PHOTOS]}


def fill(session, current_lots, known, limit=PER_RUN):
    """Known lot pages for these lots, reading at most `limit` new ones. -> (known, lots still unread)."""
    current = {lot['id'] for lot in current_lots}
    known = {k: v for k, v in known.items() if k in current}
    missing = [lot for lot in current_lots if lot['id'] not in known]
    for lot in missing[:limit]:
        try:
            _, html = session.fetch(lot['detail_url'])
        except OSError:
            continue
        known[lot['id']] = entry(html)
    return known, sum(1 for lot in current_lots if lot['id'] not in known)


def apply(current_lots, known):
    """The lots with their start price, VIN and photos from the lot pages (the table's own while unread)."""
    result = []
    for lot in current_lots:
        page = known.get(lot['id'], {})
        result.append(dict(lot, start_price_krw=page.get('krw') or lot['start_price_krw'], vin=page.get('vin', ''),
                           photos=page.get('photos') or lot['photos']))
    return result
