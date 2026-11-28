"""What the site shows of the chosen IAAI lots: video/usa/lots.json (the USA page and the home search summary) and
video/usa/feed.json (the home ticker's USA cards).

Pure functions: no network. Photos are referred to by their copies on the site, never by the auction's addresses.
Same core fields as the Korea and Japan lists (id, title, maker, year, mileage_km, photos, start_usd), so the home
search summary (ua_auction_summary.py) counts them as it counts the other countries.
"""
from . import pages  # USA-LOTS-FIX-005: a value IAAI wrote twice, once (lot pages read before the fix too)

PHOTO_URL = '/video/usa/lots/'
LIST_PHOTOS = 3
MILE_KM = 1.609344


def km(miles):
    return int(round((miles or 0) * MILE_KM, -2))


MAKES = {'bmw': 'BMW', 'mercedes-benz': 'Mercedes-Benz', 'volkswagen': 'Volkswagen'}


def make_name(make):
    """USA-LOTS-FIX-005: IAAI writes makes in capitals («BMW», «TOYOTA»): the usual spelling."""
    return MAKES.get((make or '').lower(), (make or '').title())


def model_name(model):
    """USA-LOTS-FIX-005 (live 28.11: «ROGUE», «MALIBU»): words of letters only in title case; model codes with a digit
    or of up to 3 letters as written («RAV4», «XC90», «CR-V», «X3», «ES»)."""
    def word(w):
        parts = w.split('-')
        if any(c.isdigit() for c in w) or all(len(p) <= 3 for p in parts):
            return w
        return '-'.join(p.capitalize() for p in parts)
    return ' '.join(word(w) for w in (model or '').split())


def lot_view(lot, photos):
    """One lot as the site shows it; `photos` are the copied photo names. start_usd: «Buy Now» price when the lot
    has one, otherwise 0 (the card then shows the US market value, actual_cash_value_usd)."""
    title = ('%s %s' % (make_name(lot['make']), model_name(lot['model']))).strip()
    return {
        'id': lot['id'], 'title': title, 'maker': make_name(lot['make']), 'model': model_name(lot['model']), 'year': lot['year'],
        'mileage_km': km(lot.get('odometer_mi')), 'damage': pages.once(lot.get('damage', '')), 'runs': bool(lot.get('runs')),
        'fuel': lot.get('fuel', ''), 'engine': lot.get('engine', ''), 'drive': lot.get('drive', ''),
        'transmission': lot.get('transmission', ''), 'location': lot.get('location', ''),
        'auction_start': lot.get('auction_start', ''), 'auction': 'IAAI',
        'start_usd': lot.get('buy_now_usd') or 0, 'value_usd': lot.get('actual_cash_value_usd') or 0,
        'photos': [PHOTO_URL + name for name in photos[:LIST_PHOTOS]],
    }


def gallery(photos):
    return {'photos': [PHOTO_URL + name for name in photos]}


def build(lots, photos, generated_at):
    """lots.json: the given lots that have at least one copied photo, soonest auction first."""
    shown = [lot_view(lot, photos[lot['id']]) for lot in lots if photos.get(lot['id'])]
    shown.sort(key=lambda v: (v['auction_start'] or '9', v['id']))
    return {'generated_at': generated_at, 'source': 'IAAI', 'lots': shown}


def feed(views, generated_at):
    """feed.json for the home ticker: the USA cards (as the Japan feed's items)."""
    return {'generated_at': generated_at,
            'items': [{'id': v['id'], 'title': v['title'], 'year': v['year'], 'mileage_km': v['mileage_km'],
                       'damage': v['damage'], 'runs': v['runs'], 'fuel': v['fuel'], 'photo': v['photos'][0],
                       'auction_start': v['auction_start'], 'start_price_usd': v['start_usd'],
                       'value_usd': v['value_usd']} for v in views if v['photos']]}
