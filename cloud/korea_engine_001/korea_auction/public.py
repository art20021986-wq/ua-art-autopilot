"""Public lot list for the site: every lot of the coming auction days, open to every visitor.

Pure function of the collected lots: no network, no account data. Photos are referred to by their copies
on the site (photo_name), never by the auction's own addresses.
"""
import hashlib

from . import fuel, nbu
from .collect import display_name

PHOTO_URL = '/video/korea/lots/'
# KOREA-ENGINE-001 (owner 2026-11-13: every photo in the lot card): the lot list keeps the first photos, so it stays
# light for every visitor; each lot's whole set is its own small file (job.publish_galleries ->
# /video/korea/gallery/<id>.json), read when its card opens.
LIST_PHOTOS = 3


def photo_name(lot_id, url):
    """The site copy of one lot photo: named by its address, so a copy stays right when the photo list grows."""
    return '%s-%s.jpg' % (lot_id, hashlib.sha256(url.encode('utf-8')).hexdigest()[:12])


def lot_view(lot, rates, photos):
    """One lot as the site shows it; `photos` are the site photo names that were copied."""
    price = lot['start_price_krw']
    return {
        'id': lot['id'], 'title': display_name(lot['maker'], lot['model']), 'maker': lot['maker'].title(),
        'trim': lot['trim'], 'year': lot['year'], 'mileage_km': lot['mileage_km'], 'score': lot['score'],
        'engine_cc': lot['engine_cc'], 'fuel': fuel.key(lot.get('fuel')) or '', 'transmission': lot['transmission'],
        'house': lot['house'], 'lot_no': lot['lot_no'], 'auction_start': lot['auction_start'],
        'start_krw': price, 'start_usd': nbu.krw_to_usd(price, rates) if price else 0, 'vin': lot.get('vin', ''),
        'photos': [PHOTO_URL + name for name in photos[:LIST_PHOTOS]],
    }


def gallery(photos):
    """One lot's gallery file: every copied photo, in the lot page's order."""
    return {'photos': [PHOTO_URL + name for name in photos]}


def build(lots, date, rates, photos, generated_at):
    """Site JSON: the given lots that have at least one copied photo, in auction order; `date` is the next day."""
    shown = [lot_view(lot, rates, photos[lot['id']]) for lot in lots if photos.get(lot['id'])]
    shown.sort(key=lambda v: (v['auction_start'], v['house'], v['lot_no']))
    return {'generated_at': generated_at, 'auction_date': date,
            'nbu': {'date': rates['date'], 'usd_uah': rates['USD'], 'krw_uah': rates['KRW']}, 'lots': shown}
