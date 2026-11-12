"""Bought car data from an auction lot link (CRM-PAYMENTS-001): the manager pastes the lot link (or its number), the
bot opens the lot page under the owner's auction login and fills title, year, VIN, mileage, color, fuel, photos and
the price. Reuses the installed collector (/home/Carix/korea_auction, session «Аукционы Кореи»): session.Session,
job.read_login, lots.parse_detail, html_tools.text, nbu rates. Nothing here writes to the site or to the cars table.
The final price is read when the page shows it; the manager always confirms the price before payment 2 is issued.
"""
import re

LOT_URL = 'https://jpauto.auction/vehicle-detail/kr/%s'
_LOT = re.compile(r'(?:vehicle-detail/kr/)?(\d{8,20})')


def lot_id(text):
    """'https://jpauto.auction/vehicle-detail/kr/20261106043479' or the bare number -> '20261106043479'."""
    match = _LOT.search((text or '').strip())
    if not match:
        raise ValueError('LOT_LINK')
    return match.group(1)


def _krw(text):
    digits = re.sub(r'\D', '', text or '')
    return int(digits) if digits else 0


def car_from_page(lot, detail, page_text, rates=None):
    """parse_detail() result + the page as text -> the car fields of ua_pay_store (pure)."""
    specs = detail.get('specs') or {}

    def spec(*names):
        for name in names:
            for key, value in specs.items():
                if key.startswith(name) and value and value.strip() not in ('-', ''):
                    return value.strip()
        return ''

    final = re.search(r'Final Price\s*:?\s*([\d,]{4,})', page_text or '')
    krw = _krw(final.group(1)) if final else 0
    title = ' '.join(part for part in (spec('Manufacturer'), spec('Model'), spec('Trim')) if part)
    usd = round(krw * rates['KRW'] / rates['USD']) if krw and rates else None
    return {'lot_url': LOT_URL % lot, 'lot_id': lot, 'vin': detail.get('vin') or '', 'title': title,
            'year': spec('Model Year')[:4], 'mileage': spec('Mileage'), 'color': spec('Color'),
            'fuel': detail.get('fuel') or '', 'photos': list(detail.get('photos') or [])[:30],
            'price_krw': krw or None, 'price_usd': usd}


def fetch(text):
    """Server only: open the lot page with the owner's login and return the car fields. Raises on failure."""
    from korea_auction import html_tools, job, lots, nbu, session
    lot = lot_id(text)
    browser = session.Session(pause=1.0)
    browser.login(*job.read_login())
    _, html = browser.fetch('/vehicle-detail/kr/%s' % lot)
    detail = lots.parse_detail(html)
    if not (detail.get('vin') or detail.get('specs')):
        raise RuntimeError('LOT_PAGE_EMPTY')
    try:
        rates = nbu.fetch_rates()
    except Exception:
        rates = None
    return car_from_page(lot, detail, html_tools.text(html), rates)
