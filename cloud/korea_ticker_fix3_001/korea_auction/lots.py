"""Parse auction lot data: the Korea search results table and a lot detail page."""
import re

from . import html_tools

_COLUMNS = ('start', 'close', 'house_lot', 'score', 'mileage', 'year', 'start_price',
            'photo', 'maker', 'model', 'model_code', 'trim', 'engine', 'transmission')


def _int(value):
    digits = re.sub(r'[^\d]', '', value or '')
    return int(digits) if digits else 0


def parse_results(html):
    """Results page -> list of lots (dicts). Only rows with a lot id are returned."""
    table = html_tools.table_containing(html, 'Close Time')
    lots = []
    for row in html_tools.table_rows(table):
        if len(row) < len(_COLUMNS) or row[0]['tag'] != 'td':
            continue
        cells = dict(zip(_COLUMNS, row))
        lot_id = cells['photo']['attrs'].get('data-lot-id')
        if not lot_id:
            continue
        house = re.match(r'(.*?)\s*\((\w+)\)\s*$', cells['house_lot']['text'])
        lots.append({
            'id': lot_id,
            'auction_start': cells['start']['text'],      # 'YYYY/MM/DD HH:MM' (JST)
            'bidding_close': cells['close']['text'],
            'house': house.group(1) if house else cells['house_lot']['text'],
            'lot_no': house.group(2) if house else '',
            'detail_url': (cells['house_lot']['links'] or [''])[0].split('?')[0],
            'score': cells['score']['text'],
            'mileage_km': _int(cells['mileage']['text']),
            'year': _int(cells['year']['text']),
            'start_price_krw': _int(cells['start_price']['text']),
            'photos': cells['photo']['imgs'],
            'maker': cells['maker']['text'],
            'model': cells['model']['text'],
            'trim': cells['trim']['text'],
            'engine_cc': _int(cells['engine']['text']),
            'transmission': cells['transmission']['text'],
        })
    return lots


def _pairs(table_html):
    """Label/value table (th followed by td) -> dict."""
    out = {}
    for row in html_tools.table_rows(table_html):
        for label, value in zip(row, row[1:]):
            if label['tag'] == 'th' and value['tag'] == 'td':
                out[label['text']] = value['text']
    return out


def parse_detail(html):
    """Lot detail page -> start price, specs, photos, market sold prices."""
    page = html_tools.text(html)
    prices = [_int(p) for p in re.findall(r'Starting Price ([\d,]+) KRW', page)]
    specs = _pairs(html_tools.table_containing(html, 'Chassis No.'))
    stop = r'(?= (?:Engine|Fuel|Vehicle History|Type|Mission|Electric|Lower Body|Auction Sheet)\b|$)'
    extra = dict(re.findall(r'(Fuel|Vehicle History|Type): (.+?)' + stop, page))
    market = []
    for row in html_tools.table_rows(html_tools.table_containing(html, 'Sold Price')):
        if len(row) >= 6 and row[0]['tag'] == 'td':
            sold = _int(row[5]['text'])
            if sold:
                market.append(sold)
    photos = []
    for src in re.findall(r'<img[^>]+src="(https://image-cdn-hub\.beforward\.jp/[^"]+)"', html):
        if src not in photos:
            photos.append(src)
    return {'start_price_krw': max(prices or [0]), 'specs': specs,
            'fuel': extra.get('Fuel', '').strip(), 'history': extra.get('Vehicle History', '').strip(),
            'body': extra.get('Type', '').strip(), 'market_sold_krw': market, 'photos': photos}
