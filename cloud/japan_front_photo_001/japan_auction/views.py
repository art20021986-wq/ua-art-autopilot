"""What the site shows of the Japan left-hand-drive lots: the lot list (video/japan/lots.json), each lot's gallery and the
feed for the home ticker (video/japan/feed.json: the week for the «Японія» tab and the ticker cards).

Pure functions of the collected lots: no network, no account data. Photos are referred to by their copies on the site
(photos.name), never by the auction's own addresses. Same fields as the Korea list, with the
start price in yen (start_jpy) instead of won.
"""
from korea_auction import color, drive, fuel, week_tile
from korea_auction.collect import display_name
from korea_auction.selection import auction_date

from . import money

PHOTO_URL = '/video/japan/lots/'
LIST_PHOTOS = 3  # as the Korea list: the first photos; the whole set is the lot's gallery file
TICKER_SIZE = 30  # the Japan cars in the home ticker (owner 2026-11-27: Japan cars in the common ticker)


def lot_view(lot, rates, photos):
    """One lot as the site shows it; `photos` are the site photo names that were copied."""
    price = lot['start_price_jpy']
    title = display_name(lot['maker'], lot['model'])
    return {
        'id': lot['id'], 'title': title, 'maker': lot['maker'].title(), 'trim': lot['trim'], 'year': lot['year'],
        'mileage_km': lot['mileage_km'], 'score': lot['score'], 'engine_cc': lot['engine_cc'],
        'fuel': fuel.key(lot.get('fuel')) or '', 'transmission': lot['transmission'],
        'drive': drive.key(lot['trim'], title) or '', 'color': color.key(lot.get('color')) or '',
        'house': lot['house'], 'lot_no': lot['lot_no'], 'auction_start': lot['auction_start'],
        'start_jpy': price, 'start_usd': money.jpy_to_usd(price, rates) if price else 0, 'vin': lot.get('vin', ''),
        'photos': [PHOTO_URL + name for name in photos[:LIST_PHOTOS]],
    }


def gallery(photos):
    """One lot's gallery file: every copied photo, in the lot page's order."""
    return {'photos': [PHOTO_URL + name for name in photos]}


def build(lots, rates, photos, generated_at):
    """lots.json: the given lots that have at least one copied photo, in auction order."""
    shown = [lot_view(lot, rates, photos[lot['id']]) for lot in lots if photos.get(lot['id'])]
    shown.sort(key=lambda view: (view['auction_start'], view['house'], view['lot_no']))
    return {'generated_at': generated_at,
            'nbu': {'date': rates['date'], 'usd_uah': rates['USD'], 'jpy_uah': rates['JPY']}, 'lots': shown}


def ticker_items(views, today):
    """The ticker cards: listed lots from `today` on with a start price and a photo, in auction order."""
    return [{'id': v['id'], 'title': v['title'], 'year': v['year'], 'mileage_km': v['mileage_km'],
             'score': v['score'], 'fuel': v['fuel'], 'start_price_jpy': v['start_jpy'], 'start_price_usd': v['start_usd'],
             'photo': v['photos'][0], 'auction_start_jst': v['auction_start']}
            for v in views if v['start_usd'] and v['photos'] and auction_date(v) >= today][:TICKER_SIZE]


def week(views, today, history=None):
    """The «Японія» tab week (as the Korea tab: today and the next 6 days, each with its car count and auction houses;
    no Korea holidays). JAPAN-DAYS-001: a coming day without lots shows the houses seen on that weekday (history)."""
    return week_tile.week(views, None, today, holidays={}, history=history)


def planned(days):
    """{'YYYY/MM/DD': [{'name', 'start'?}]}: the week's coming days without lots yet and their expected auctions (the
    Japan page day buttons show them, as the Korea page does with lots.json `planned`)."""
    return {day['date']: day['houses'] for day in days if day['state'] == 'soon' and day['houses']}


def feed(views, today, generated_at, history=None):
    """feed.json for the home ticker: the «Японія» tab week and the ticker cards."""
    return {'generated_at': generated_at, 'week': week(views, today, history), 'items': ticker_items(views, today)}
