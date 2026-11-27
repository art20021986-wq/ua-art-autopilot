"""Reading IAAI's open pages (owner 2026-11-27: the USA lots from the open IAAI pages).

A make-and-model listing (www.iaai.com/Vehiclelisting/<MAKE>/<MODEL>/: up to 100 lots with their damage, odometer
and start code) and one lot page (www.iaai.com/VehicleDetail/<id>~US: auction date, values, the photo list address).
Pure functions of the page text: no network. One responsibility: turning a page into lot fields.
"""
from datetime import datetime, timedelta, timezone
import html as html_lib
import re

LABELS = ('Primary Damage', 'Secondary Damage', 'Odometer', 'Start Code', 'Key', 'Title/Sale Doc', 'Loss Type',
          'Engine', 'Fuel Type', 'Cylinders', 'Drive Line Type', 'Transmission', 'Vehicle Location', 'Selling Branch',
          'Auction Date and Time', 'Actual Cash Value', 'Buy Now Price', 'Restraint System', 'Airbags', 'Vehicle',
          'Body Style', 'Series', 'Exterior/Interior', 'Lane/Run #', 'Aisle/Stall')
LABEL = re.compile(r'(%s)\s*:' % '|'.join(re.escape(label) for label in sorted(LABELS, key=len, reverse=True)))
LOT = re.compile(r'(?i)/VehicleDetail/(\d{6,9})~US')
YEAR = re.compile(r'\b(19[89]\d|20[0-4]\d)\b')
MONEY = re.compile(r'\$\s*([\d,]+)')
MILES = re.compile(r'([\d,]+)\s*mi\b')
WHEN = re.compile(r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+(\d{1,2}),?\s+'
                  r'(\d{1,2}):(\d{2})\s*([ap]m)\s*\(\s*([A-Z]{2,4})\s*\)', re.I)
ZONES = {'EST': -5, 'EDT': -4, 'CST': -6, 'CDT': -5, 'MST': -7, 'MDT': -6, 'PST': -8, 'PDT': -7, 'AKST': -9,
         'AKDT': -8, 'HST': -10, 'AST': -4}
MONTHS = ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec')
PHOTO_LIST = re.compile(r'https?://vis\.iaai\.com/dimensions\?imageKeys=[^"\'\s<>]+')
PHOTO = 'https://vis.iaai.com/resizer?imageKeys=%s&width=845&height=633'


def text(page):
    page = re.sub(r'(?is)<(script|style)\b.*?</\1>', ' ', page)
    return re.sub(r'\s+', ' ', html_lib.unescape(re.sub(r'<[^>]+>', ' ', page))).strip()


TITLE = re.compile(r'title="([^"]*)"')


def titled(piece):
    """USA-LOTS-FIX (live 27.11: the listing writes each value in its item's title attribute,
    title="Primary Damage: Front End"): each known label's value from those attributes."""
    out = {}
    for m in TITLE.finditer(piece):
        label, _, value = html_lib.unescape(m.group(1)).partition(':')
        if _ and label.strip() in LABELS and value.strip():
            out.setdefault(label.strip(), value.strip())
    return out


def fields(plain):
    """Each label's value: the text from its «Label:» to the next known label (first occurrence wins)."""
    marks = list(LABEL.finditer(plain))
    out = {}
    for n, mark in enumerate(marks):
        end = marks[n + 1].start() if n + 1 < len(marks) else min(len(plain), mark.end() + 120)
        out.setdefault(mark.group(1), plain[mark.end():end].strip(' ·|-'))
    return out


def number(pattern, value):
    m = pattern.search(value or '')
    return int(m.group(1).replace(',', '')) if m else 0


def auction_start(value, now):
    """«Wed Dec 2, 9:30am (CST)» -> UTC ISO time (the year: the next such date from `now`), '' when unreadable."""
    m = WHEN.search(value or '')
    if not m or m.group(6).upper() not in ZONES:
        return ''
    month, day, hour, minute = MONTHS.index(m.group(1).lower()[:3]) + 1, int(m.group(2)), int(m.group(3)) % 12, int(m.group(4))
    hour += 12 if m.group(5).lower() == 'pm' else 0
    zone = timezone(timedelta(hours=ZONES[m.group(6).upper()]))
    for year in (now.year, now.year + 1):
        try:
            at = datetime(year, month, day, hour, minute, tzinfo=zone)
        except ValueError:
            return ''
        if at >= now - timedelta(days=2):
            return at.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')
    return ''


def common(values):
    start = values.get('Start Code', '')
    return {'damage': values.get('Primary Damage', '')[:40], 'secondary_damage': values.get('Secondary Damage', '')[:40],
            'odometer_mi': number(MILES, values.get('Odometer')), 'runs': 'run & drive' in start.lower(),
            'title_type': values.get('Title/Sale Doc', '')[:60], 'fuel': values.get('Fuel Type', '')[:20],
            'engine': values.get('Engine', '')[:40], 'drive': values.get('Drive Line Type', '')[:30],
            'transmission': values.get('Transmission', '')[:30]}


def listing(page, make, model):
    """A make-and-model listing -> its lots: {id, make, model, year, damage, ..., runs} (no photos yet).
    The page is cut into one piece per lot, from the lot's first link to the next lot's first link."""
    firsts = []
    for m in LOT.finditer(page):
        if not firsts or firsts[-1][0] != m.group(1):
            if m.group(1) not in {f[0] for f in firsts}:
                firsts.append((m.group(1), m.start()))
    lots = []
    for n, (lot_id, start) in enumerate(firsts):
        raw = page[start:firsts[n + 1][1] if n + 1 < len(firsts) else len(page)]
        piece = text(raw)
        year = YEAR.search(piece)
        values = dict(fields(piece), **titled(raw))  # the title attributes win
        lots.append(dict(common(values), id=lot_id, make=make, model=model, year=int(year.group(1)) if year else 0))
    return lots


def lot(page, now):
    """A lot page -> its auction start, values and photo list address."""
    values = dict(fields(text(page)), **titled(page))
    photos = PHOTO_LIST.search(page)
    return dict(common(values), auction_start=auction_start(values.get('Auction Date and Time', ''), now),
                actual_cash_value_usd=number(MONEY, values.get('Actual Cash Value')),
                buy_now_usd=number(MONEY, values.get('Buy Now Price')),
                location=values.get('Vehicle Location', '')[:40] or values.get('Selling Branch', '')[:40],
                photo_list=html_lib.unescape(photos.group(0)) if photos else '')


def photo_urls(answer):
    """The photo service's answer ({"keys": [{"K": ...}, ...]}) -> the photo addresses, in its order."""
    keys = answer.get('keys') if isinstance(answer, dict) else None
    return [PHOTO % k['K'] for k in keys or [] if isinstance(k, dict) and k.get('K')]
