"""Read-only probe on the server for JPAUTO-KOREA-001 (owner 2026-11-11: auction day choice, VIN and all photos).

R5 (2026-11-17, KOREA-DRIVE-001, owner: a colour filter): color_report() reads the first Korea search page and up to
COLOR_PAGES lot pages and reports, per lot, the value the page text gives after «Color» (up to «Mileage») and the
markup around the «Color» and «Trim Level» labels (tags kept, text values over 40 characters cut, long numbers and
VIN-like codes masked) — to read the colour from the page's own field. Nothing is written except this receipt.

R4 (2026-11-17, KOREA-DRIVE-001, owner: «в карточках аукциона добавить привод»): drive_report() reads the first Korea
search page and up to 8 lot pages of different models (SUVs first) and reports, per lot, the labels and values of the
lot page specs table, the «Label:» words of the page text and every line that names a drive (drive, 2WD/4WD/AWD,
4x4, xDrive, 4MATIC, quattro, HTRAC, 구동), with the trim of the search row — to learn whether the auction writes the
drive explicitly. VIN-like codes and long numbers are masked. Nothing is written except this receipt; no bid is placed.

R3 (2026-11-12, owner: real Korea auction lots in the order page model carousels): report() reads the whole Korea
search once (as the hourly job does, no lot page) and reports, for the five Korea order models (K5, Sonata, Tucson,
Sportage, Santa Fe), the model names, model codes (the «Model Code» column) and years as the auction writes them,
the auction grade formats, lots per day, photos per lot and start price presence. Nothing is written except this
receipt; no bid is placed.

R2 (2026-11-11): the lot page markup differs from the collector's pattern, so every image address shape,
the table labels and the chassis/VIN lines (a 17-character VIN masked as [VIN17]) are reported too.
Uses the collector already installed on the server (/home/Carix/korea_auction) with the owner's login file, as the
hourly job does: reads the whole Korea search (lots per auction day), three lot pages (how many photos, whether the
specs have the chassis number — only its length is reported) and downloads three photos of one lot to measure their
size (kept in memory, never saved). Also reports the published lot list and photo folder sizes. Nothing is written
except this receipt; no bid is placed.
"""
import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import re
import resource
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/Carix')
LONG_NUMBER = re.compile(r'\d{5,}')


def folder_size(path):
    files = [p for p in path.glob('*') if p.is_file()]
    return {'files': len(files), 'bytes': sum(p.stat().st_size for p in files)}


def published():
    """The lot list now on the site (read only)."""
    try:
        data = json.loads((ROOT / 'video/korea/lots.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        return {'error': type(error).__name__}
    lots = data.get('lots', [])
    return {'auction_date': data.get('auction_date'), 'lots': len(lots),
            'priced': sum(1 for lot in lots if lot.get('start_krw')),
            'photos_per_lot': dict(Counter(len(lot.get('photos', [])) for lot in lots)),
            'keys': sorted(lots[0]) if lots else []}


def shape(url):
    """The photo address without host and numbers: shows whether it is a thumbnail or the full photo."""
    path = re.sub(r'^https?://[^/]+', '', url)
    return LONG_NUMBER.sub('[N]', path)[:120]


TARGETS = (('KIA', 'K5'), ('HYUNDAI', 'SONATA'), ('HYUNDAI', 'TUCSON'), ('KIA', 'SPORTAGE'), ('HYUNDAI', 'SANTA'))


def with_model_codes(lots, html_tools):
    """lots.parse_results, plus each lot's «Model Code» column (the collector does not keep it yet)."""
    original = lots.parse_results

    def parse(html):
        found = original(html)
        codes = {}
        for row in html_tools.table_rows(html_tools.table_containing(html, 'Close Time')):
            if len(row) >= len(lots._COLUMNS) and row[0]['tag'] == 'td':
                cells = dict(zip(lots._COLUMNS, row))
                if cells['photo']['attrs'].get('data-lot-id'):
                    codes[cells['photo']['attrs']['data-lot-id']] = cells['model_code']['text']
        return [dict(lot, model_code=codes.get(lot['id'], '')) for lot in found]
    return parse


def model_report(all_lots):
    value = {}
    for maker, word in TARGETS:
        chosen = [l for l in all_lots if l['maker'].upper().startswith(maker) and word in l['model'].upper()]
        value[maker + ' ' + word] = {
            'lots': len(chosen),
            'name_code_year': [[n, c, y, k] for (n, c, y), k in Counter(
                (l['model'], l['model_code'], l['year']) for l in chosen).most_common(60)],
            'scores': Counter(l['score'] for l in chosen).most_common(20),
            'days': sorted(Counter(selection_day(l) for l in chosen).items()),
            'with_price': sum(1 for l in chosen if l['start_price_krw']),
            'photos': dict(Counter(len(l['photos']) for l in chosen))}
    return value


def selection_day(lot):
    return lot['auction_start'][:10]


def report():
    sys.path.insert(0, str(ROOT))
    from korea_auction import collect, html_tools, job, lots, session
    lots.parse_results = with_model_codes(lots, html_tools)
    browser = session.Session()
    browser.login(*job.read_login())
    total, all_lots = collect.fetch_all_lots(browser)
    days = Counter(selection_day(lot) for lot in all_lots)
    return {'status': 'PASS', 'no_bid_placed': True, 'lots_total': total, 'lots_parsed': len(all_lots),
            'days': [{'date': day, 'weekday': datetime.strptime(day, '%Y/%m/%d').strftime('%a'), 'lots': n}
                     for day, n in sorted(days.items())],
            'scores_all': Counter(l['score'] for l in all_lots).most_common(40),
            'models': model_report(all_lots), 'requests': browser.requests}


DRIVE = re.compile(r'(?i)drive|\b[24]wd\b|\bawd\b|\bfwd\b|\brwd\b|4x4|4matic|quattro|htrac|구동')
VIN17 = re.compile(r'\b[A-HJ-NPR-Z0-9]{17}\b')
WANTED = ('SORENTO', 'SANTA', 'GV80', 'PALISADE', 'TUCSON', 'SPORTAGE', 'X', 'K5')
DRIVE_PAGES = 8


def mask(text):
    return LONG_NUMBER.sub('[N]', VIN17.sub('[VIN17]', str(text)))[:200]


def lot_drive(html, html_tools, lots):
    """One lot page: its specs table, the «Label:» words of its text and the lines naming a drive."""
    detail = lots.parse_detail(html)
    page = html_tools.text(html)
    labels = list(dict.fromkeys(re.findall(r'\b([A-Z][A-Za-z ]{1,25}):\s', page)))[:60]
    lines = [mask(page[max(0, m.start() - 60):m.end() + 60]) for m in DRIVE.finditer(page)][:12]
    return {'specs': {k: mask(v) for k, v in detail['specs'].items()}, 'labels': labels, 'drive_lines': lines,
            'fuel': detail['fuel'], 'body': detail['body']}


def chosen(found):
    """Up to DRIVE_PAGES lots of different models, SUVs first, then any others."""
    picked, seen = [], set()
    for word in WANTED:
        for lot in found:
            name = (lot['maker'] + ' ' + lot['model']).upper()
            if word in name.split() or (len(word) > 1 and word in name):
                if lot['id'] not in seen:
                    picked.append(lot); seen.add(lot['id'])
                break
    for lot in found:
        if len(picked) >= DRIVE_PAGES:
            break
        if lot['id'] not in seen:
            picked.append(lot); seen.add(lot['id'])
    return picked[:DRIVE_PAGES]


def drive_report():
    sys.path.insert(0, str(ROOT))
    from korea_auction import collect, html_tools, job, lots, session
    browser = session.Session()
    browser.login(*job.read_login())
    _, page = browser.fetch(collect.SEARCH_PAGE)
    action, data = collect._search_form_data(page)
    _, html = browser.fetch(action, data)
    found = lots.parse_results(html)
    out = []
    for lot in chosen(found):
        _, detail = browser.fetch(lot['detail_url'])
        out.append(dict(lot_drive(detail, html_tools, lots), model=lot['maker'] + ' ' + lot['model'],
                        trim=mask(lot['trim']), year=lot['year']))
    return {'status': 'PASS', 'no_bid_placed': True, 'first_page_lots': len(found), 'lots': out,
            'requests': browser.requests}


COLOR_PAGES = 40
COLOR_TEXT = re.compile(r'\bColor\s+(.*?)\s+Mileage\b')


def markup(html, label):
    """The markup around the first `label` (300 characters each side), masked."""
    at = html.find(label)
    return mask(html[max(0, at - 300):at + 300]) if at >= 0 else ''


def lot_color(html, html_tools):
    page = html_tools.text(html)
    found = COLOR_TEXT.search(page)
    return {'color_text': mask(found.group(1))[:40] if found else None,
            'color_markup': markup(html, 'Color'), 'trim_markup': markup(html, 'Trim Level')}


def color_report():
    sys.path.insert(0, str(ROOT))
    from korea_auction import collect, html_tools, job, lots, session
    browser = session.Session()
    browser.login(*job.read_login())
    _, page = browser.fetch(collect.SEARCH_PAGE)
    action, data = collect._search_form_data(page)
    _, html = browser.fetch(action, data)
    found = lots.parse_results(html)
    out = []
    for n, lot in enumerate(found[:COLOR_PAGES]):
        _, detail = browser.fetch(lot['detail_url'])
        value = lot_color(detail, html_tools)
        if n >= 3:  # the markup of three pages is enough
            value.pop('color_markup'); value.pop('trim_markup')
        out.append(dict(value, model=lot['maker'] + ' ' + lot['model'], year=lot['year']))
    return {'status': 'PASS', 'no_bid_placed': True, 'first_page_lots': len(found), 'lots': out,
            'colors': Counter(v['color_text'] for v in out).most_common(), 'requests': browser.requests}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (120, 130))
    work = HERE / 'runs' / args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work / 'receipt-probe.json'
    if receipt.exists():
        return 0
    try:
        value = color_report()
    except Exception as error:
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + LONG_NUMBER.sub('[N]', str(error))[:160]}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
