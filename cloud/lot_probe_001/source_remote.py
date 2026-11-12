"""Read-only probe on the server for JPAUTO-KOREA-001 (owner 2026-11-11: auction day choice, VIN and all photos).

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
        value = report()
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
