"""Read-only probe on the server for USA-LOTS-001 (owner 2026-11-27: the USA cars of Copart and IAAI on the site).

Which open addresses give the lots, their data and photos, without any login: the Copart Sales Data file (its first
2 MB: the columns and what the first rows hold), one Copart lot's photo list and one photo, the IAAI sitemap, one IAAI
lot page and one photo. About ten GET requests, 3 seconds apart. The report holds statuses, column names and counts
only — no VIN, no lot numbers, no full foreign addresses. Standard library only.
"""
import argparse
from collections import Counter
import csv
import http.cookiejar
import io
import json
import os
from pathlib import Path
import re
import resource
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
UA = 'UAArtAutopilot/1.0 (+https://uaart.com.ua)'  # honest name, no browser imitation (coordinator 27.11)
COPART_CSV = 'https://inventory.copart.io/FTPLSTDM/salesdata.cgi'
IAAI_SITEMAP = 'https://www.iaai.com/Xj9rDOVMEi0hc38S/sitemap_index.xml'  # named in iaai.com/robots.txt
CSV_BYTES = 2 * 1024 * 1024
PAGE_BYTES = 4 * 1024 * 1024
LONG_NUMBER = re.compile(r'\d{6,}')
VIN = re.compile(r'\b[A-HJ-NPR-Z0-9]{11,17}\b')
EMAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+')
URL = re.compile(r'https?://[^\s\'"<>)]+')
CHALLENGE = re.compile(r'(?i)_Incapsula_Resource|captcha|cf-chl|access denied|request unsuccessful')
LABELS = ('Primary Damage', 'Secondary Damage', 'Odometer', 'Start Code', 'Run & Drive', 'Key', 'Title', 'Auction Date',
          'Sale Date', 'Actual Cash Value', 'Buy Now', 'Engine', 'Fuel Type', 'Drive Line Type', 'Transmission',
          'Vehicle Location', 'Current Bid', 'Loss Type')


def clean(text):
    """No e-mail, no VIN, no long numbers (lot ids, tokens), no full foreign URLs (host and path are kept)."""
    text = EMAIL.sub('[EMAIL]', str(text))
    text = URL.sub(lambda m: '%s%s' % (urllib.parse.urlsplit(m.group(0)).netloc,
                                       LONG_NUMBER.sub('[N]', urllib.parse.urlsplit(m.group(0)).path)), text)
    return LONG_NUMBER.sub('[N]', VIN.sub('[VIN]', text))


def text(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(r'(?is)<(script|style)\b.*?</\1>', ' ', html))).strip()


class Browser:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.requests = 0

    def fetch(self, url, limit=PAGE_BYTES):
        """-> (status, content type, final host, body bytes up to limit); an HTTP error is a status, not a raise."""
        if self.requests:
            time.sleep(3)
        self.requests += 1
        request = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en-US,en'})
        try:
            with self.opener.open(request, timeout=90) as response:
                return (response.status, response.headers.get('Content-Type', ''),
                        urllib.parse.urlsplit(response.geturl()).netloc, response.read(limit))
        except urllib.error.HTTPError as error:
            return error.code, error.headers.get('Content-Type', ''), urllib.parse.urlsplit(url).netloc, error.read(65536)


def head(status, kind, host, body):
    page = body.decode('utf-8', 'replace')
    return {'http': status, 'type': kind.split(';')[0], 'host': host, 'bytes': len(body),
            'challenge': bool(CHALLENGE.search(page[:200000]))}


def top(counter, n=20):
    return [[clean(k), v] for k, v in counter.most_common(n)]


def csv_rows(body):
    """The complete rows of the file's first part (the last, cut row is dropped)."""
    data = body.decode('utf-8', 'replace')
    data = data[:data.rfind('\n')] if '\n' in data else data
    return list(csv.DictReader(io.StringIO(data)))


def column(row, *names):
    """A column's value by any of its known names (case and spaces ignored)."""
    wanted = {re.sub(r'\W', '', n).lower() for n in names}
    for key, value in row.items():
        if key and re.sub(r'\W', '', key).lower() in wanted:
            return (value or '').strip()
    return ''


def csv_summary(rows):
    """What the Copart file holds, counted: makes, damage, runs and drives, years, titles, sale dates, photo links."""
    years = [int(y) for y in (column(r, 'Year') for r in rows) if y.isdigit()]
    images = [column(r, 'Image URL') for r in rows]
    thumbs = [column(r, 'Image Thumbnail') for r in rows]
    return {
        'columns': [clean(c) for c in (rows[0].keys() if rows else [])],
        'rows_read': len(rows),
        'makes': top(Counter(column(r, 'Make') for r in rows)),
        'damage': top(Counter(column(r, 'Damage Description') for r in rows)),
        'secondary_damage': top(Counter(column(r, 'Secondary Damage') for r in rows), 10),
        'runs_drives': top(Counter(column(r, 'Runs/Drives') for r in rows), 5),
        'vehicle_type': top(Counter(column(r, 'Vehicle Type') for r in rows), 8),
        'title_type': top(Counter(column(r, 'Sale Title Type') for r in rows), 8),
        'country': top(Counter(column(r, 'Location country') for r in rows), 5),
        'years': [min(years), max(years)] if years else [],
        'sale_dates': top(Counter(column(r, 'Sale Date M/D/CY') for r in rows), 8),
        'sale_time_samples': top(Counter('%s %s' % (column(r, 'Sale time (HHMM)'), column(r, 'Time Zone'))
                                         for r in rows), 5),
        'odometer_filled': sum(1 for r in rows if column(r, 'Odometer')),
        'retail_value_filled': sum(1 for r in rows if column(r, 'Est. Retail Value') not in ('', '0', '0.0')),
        'buy_now_filled': sum(1 for r in rows if column(r, 'Buy-It-Now Price') not in ('', '0', '0.0')),
        'high_bid_filled': sum(1 for r in rows if column(r, 'High Bid =non-vix,Sealed=Vix') not in ('', '0', '0.0')),
        'image_url_filled': sum(1 for i in images if i),
        'image_hosts': top(Counter(urllib.parse.urlsplit(i).netloc for i in images + thumbs if i), 5),
        'image_url_shape': clean(next((i for i in images if i), '')),
        'thumb_shape': clean(next((t for t in thumbs if t), '')),
    }


def image_list(body):
    """A Copart photo list (JSON): its keys and the photo addresses in it (full size first)."""
    try:
        value = json.loads(body)
    except ValueError:
        return {'json': False}, []
    found = re.findall(r'https?://[^"\s]+\.(?:jpe?g|png|webp)', json.dumps(value))
    full = [u for u in found if re.search(r'(?i)_ful|full|hrs|high', u)] or found
    shape = sorted(value.keys())[:20] if isinstance(value, dict) else type(value).__name__
    return {'json': True, 'keys': shape, 'photos': len(set(found)), 'photo_shape': clean(full[0]) if full else ''}, full


def probe_copart(browser):
    status, kind, host, body = browser.fetch(COPART_CSV, CSV_BYTES)
    value = {'file': head(status, kind, host, body)}
    if status != 200 or value['file']['challenge']:
        value['file']['text'] = clean(text(body.decode('utf-8', 'replace')))[:400]
        return value
    rows = csv_rows(body)
    value['file'].update(csv_summary(rows))
    link = next((column(r, 'Image URL') for r in rows if column(r, 'Image URL')), '')
    if link:
        status, kind, host, body = browser.fetch(link)
        value['photo_list'] = head(status, kind, host, body)
        summary, photos = image_list(body) if status == 200 else ({}, [])
        value['photo_list'].update(summary)
        if photos:
            value['photo'] = head(*browser.fetch(photos[0], 8 * 1024 * 1024))
    return value


def sitemap_links(body):
    return re.findall(r'<loc>\s*([^<\s]+)\s*</loc>', body.decode('utf-8', 'replace'))


def lot_page(html):
    """An IAAI lot page, counted: which labels it shows, data blocks, photo hosts and addresses (shapes only)."""
    page = text(html)
    photos = re.findall(r'https?://[^"\'\s]*(?:vis\.iaai\.com|anvis\.iaai\.com)[^"\'\s]*', html)
    return {'labels': [label for label in LABELS if label.lower() in page.lower()],
            'json_blocks': sorted(set(re.findall(r'(?:var|window\.)\s*([A-Za-z_]\w*)\s*=\s*\{', html)))[:20],
            'ld_json': html.count('application/ld+json'), 'photo_links': len(set(photos)),
            'photo_hosts': top(Counter(urllib.parse.urlsplit(p).netloc for p in photos), 5),
            'photo_shape': clean(photos[0]) if photos else '', 'title': clean(re.sub(r'\s+', ' ', ''.join(
                re.findall(r'(?is)<title>(.*?)</title>', html)[:1])))[:120]}, photos


def label_values(html):
    """R4: each known label's value as the page shows it («Primary Damage: Front End») — the parser's samples."""
    page = text(html)
    out = {}
    for label in LABELS:
        m = re.search(re.escape(label) + r'\s*:?\s*(.{0,60})', page, re.I)
        if m:
            out[label] = clean(m.group(1))
    return out


def json_shape(body):
    """R4: the photo service answer's shape: its keys and the first entry's keys (no values)."""
    try:
        value = json.loads(body)
    except ValueError:
        return {'json': False}
    first = None
    if isinstance(value, dict):
        lists = [v for v in value.values() if isinstance(v, list) and v]
        first = lists[0][0] if lists else None
        shape = {'keys': sorted(value.keys())[:20]}
    else:
        shape = {'type': type(value).__name__, 'length': len(value) if isinstance(value, list) else 0}
        first = value[0] if isinstance(value, list) and value else None
    if isinstance(first, dict):
        shape['entry_keys'] = sorted(first.keys())[:20]
        shape['entry_sample'] = {k: clean(v)[:60] for k, v in first.items() if isinstance(v, (str, int))}
    return shape


def model_page(browser, children):
    """R4: one make-and-model page from the IAAI sitemap (a popular model when listed): does it list lots?"""
    part = next((c for c in children if 'MakeModel1' in c), '')
    if not part:
        return {}
    status, kind, host, body = browser.fetch(part)
    pages = sitemap_links(body)
    pick = next((u for u in pages if re.search(r'(?i)toyota.*rav-?4', u)), pages[0] if pages else '')
    value = dict(head(status, kind, host, body), urls=len(pages), samples=sorted(set(clean(u) for u in pages))[:8])
    if pick:
        status, kind, host, body = browser.fetch(pick)
        html = body.decode('utf-8', 'replace')
        value['page'] = dict(head(status, kind, host, body), shape=clean(pick),
                             lot_links=len(set(re.findall(r'(?i)/vehicledetail/\d+', html))),
                             labels=[l for l in LABELS if l.lower() in text(html).lower()],
                             text=clean(text(html))[:700])
    return value


def probe_iaai(browser):
    status, kind, host, body = browser.fetch(IAAI_SITEMAP)
    value = {'sitemap': head(status, kind, host, body)}
    if status != 200 or value['sitemap']['challenge']:
        value['sitemap']['text'] = clean(text(body.decode('utf-8', 'replace')))[:400]
        return value
    children = sitemap_links(body)
    value['sitemap']['children'] = len(children)
    value['sitemap']['child_shapes'] = sorted(set(clean(c) for c in children))[:30]
    # R3 (R2 read ms-sitemapVehicleType1: no lots): the numbered parts (ms-sitemap1..N) hold the lot pages
    vehicle = next((c for c in children if re.search(r'sitemap\d+\.xml$', c)), '')
    if not vehicle:
        return value
    value['model_page'] = model_page(browser, children)  # R4
    status, kind, host, body = browser.fetch(vehicle)
    lots = [u for u in sitemap_links(body) if re.search(r'(?i)VehicleDetail', u)]
    value['vehicle_sitemap'] = dict(head(status, kind, host, body), urls=len(sitemap_links(body)), lots=len(lots),
                                    lot_shape=clean(lots[0]) if lots else '')
    if lots:
        status, kind, host, body = browser.fetch(lots[0])
        value['lot_page'] = head(status, kind, host, body)
        if status == 200 and not value['lot_page']['challenge']:
            html = body.decode('utf-8', 'replace')
            summary, photos = lot_page(html)
            value['lot_page'].update(summary, values=label_values(html),
                                     photo_shapes=sorted(set(clean(p) for p in photos))[:6])
            if photos:
                status, kind, host, body = browser.fetch(photos[0].replace('&amp;', '&'), 8 * 1024 * 1024)
                value['photo'] = dict(head(status, kind, host, body), answer=json_shape(body))
        else:
            value['lot_page']['text'] = clean(text(body.decode('utf-8', 'replace')))[:400]
    return value


STATE = Path('/home/Carix/usa_auction_data/state.json')


def masked(raw):
    """Raw HTML with numbers, addresses and long words masked: only the tag structure and labels stay."""
    raw = re.sub(r'(?is)<(script|style)\b.*?</\1>', '', raw)
    return clean(re.sub(r'\s+', ' ', raw))


def diagnose(browser):
    """USA-LOTS-DIAG (after USA-LOTS-INSTALL: 0 lots): what the collector saved, and one listing page's structure."""
    try:
        state = json.loads(STATE.read_bytes())
    except (OSError, ValueError) as error:
        return {'state': 'UNREADABLE:' + type(error).__name__}
    listings = state.get('listings', {})
    lots = [lot for entry in listings.values() for lot in entry.get('lots', [])]
    value = {'models': len(state.get('models', {})), 'model_keys': sorted(state.get('models', {}))[:80],
             'listings': {k: len(v.get('lots', [])) for k, v in listings.items()}, 'pages': len(state.get('pages', {})),
             'lots': len(lots),
             'filled': {f: sum(1 for l in lots if l.get(f)) for f in ('year', 'damage', 'odometer_mi', 'runs',
                                                                      'title_type', 'secondary_damage')},
             'damage': top(Counter(l.get('damage', '') for l in lots), 15),
             'samples': [{k: clean(v) for k, v in l.items() if k != 'id'} for l in lots[:3]]}
    # R6 (after USA-LOTS-FIX: still 0 lots): the chosen lots' pages and photo copies; no IAAI request
    import sys as _sys
    _sys.path.insert(0, '/home/Carix')
    try:
        from usa_auction import selection as _sel
        value['kept'] = sum(1 for l in lots if _sel.keep(l))
        value['why_not'] = {'popular': sum(1 for l in lots if _sel.popular(l.get('make'), l.get('model'))),
                            'year': sum(1 for l in lots if l.get('year', 0) >= _sel.MIN_YEAR),
                            'runs': sum(1 for l in lots if l.get('runs')),
                            'minimal': sum(1 for l in lots if any(w in l.get('damage', '').lower()
                                                                for w in _sel.MINIMAL_DAMAGE))}
    except Exception as error:
        value['kept'] = 'IMPORT:' + type(error).__name__
    lot_pages = list(state.get('pages', {}).values())
    value['lot_pages'] = {'count': len(lot_pages),
                          'filled': {f: sum(1 for p in lot_pages if p.get(f)) for f in
                                     ('auction_start', 'photos', 'actual_cash_value_usd', 'buy_now_usd', 'damage')},
                          'photos_per_lot': [len(p.get('photos') or []) for p in lot_pages][:30],
                          'auction_starts': sorted(str(p.get('auction_start', '')) for p in lot_pages)[:10],
                          'samples': [{k: clean(v)[:60] for k, v in p.items() if k != 'photos'} for p in lot_pages[:2]],
                          'photo_shape': clean(next((p['photos'][0] for p in lot_pages if p.get('photos')), ''))}
    # R8 (after USA-LOTS-FIX-003): the last run's own report, the run lock, the published files' times
    data = Path('/home/Carix/usa_auction_data')
    try:
        value['last_run'] = json.loads((data / 'last_run.json').read_bytes())
    except (OSError, ValueError) as error:
        value['last_run'] = 'MISSING:' + type(error).__name__
    now = time.time()
    lock = Path('/home/Carix/.usa_auction_job.lock')
    value['lock_age_min'] = round((now - lock.stat().st_mtime) / 60, 1) if lock.exists() else -1
    for name in ('state.json',):
        target = data / name
        value[name + '_age_min'] = round((now - target.stat().st_mtime) / 60, 1) if target.exists() else -1
    for name in ('lots.json', 'feed.json'):
        target = Path('/home/Carix/video/usa') / name
        value[name + '_age_min'] = round((now - target.stat().st_mtime) / 60, 1) if target.exists() else -1
    try:
        import fcntl as _fcntl
        if not lock.exists():
            raise FileNotFoundError('no lock file')  # read-only: never created here
        with open(lock, 'r') as handle:
            try:
                _fcntl.flock(handle, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
                _fcntl.flock(handle, _fcntl.LOCK_UN)
                value['lock_held'] = False
            except BlockingIOError:
                value['lock_held'] = True  # a USA run is working now
    except OSError as error:
        value['lock_held'] = 'ERROR:' + type(error).__name__
    value['running_pages'] = sum(1 for p in state.get('pages', {}).values() if p.get('runs'))
    copies = Path('/home/Carix/video/usa/lots')
    value['photo_copies'] = len(list(copies.iterdir())) if copies.is_dir() else -1
    url = ''  # R6: no IAAI request
    if url:
        status, kind, host, body = browser.fetch(url)
        html = body.decode('utf-8', 'replace')
        value['page'] = head(status, kind, host, body)
        at = html.find('Primary Damage')
        value['page']['around_damage'] = masked(html[max(0, at - 1500):at + 1500]) if at >= 0 else ''
        first = re.search(r'(?i)/VehicleDetail/', html)
        value['page']['around_first_lot'] = masked(html[first.start() - 300:first.start() + 2500]) if first else ''
        value['page']['lot_link_forms'] = sorted(set(clean(m) for m in re.findall(r'(?i)href="([^"]*vehicledetail[^"]*)"', html)))[:5]
    return value


STEPS = (('diagnose', 'diagnose'),)  # R5: after the install, the collector's own state


def report(browser=None, steps=None):
    browser = browser or Browser()
    value = {'status': 'PASS', 'no_login': True, 'no_bid_placed': True}
    for name, step in steps or [(n, globals()[f]) for n, f in STEPS]:
        try:
            value[name] = step(browser)
        except Exception as error:  # one source failing must not hide the other
            value[name] = {'error': type(error).__name__ + ':' + clean(str(error))[:160]}
    value['requests'] = browser.requests
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (150, 160))
    work = HERE / 'runs' / args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work / 'receipt-probe.json'
    if receipt.exists():
        return 0
    try:
        value = report()
    except Exception as error:
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + clean(str(error))[:160]}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
