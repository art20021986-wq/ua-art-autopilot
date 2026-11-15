"""Read-only probe on the server for VIN-KOREA-001 (owner 2026-11-15: a Korean VIN gave only «Hyundai»).

Korean domestic VINs (no check digit) are not decoded by NHTSA vPIC. This probe measures whether the Korea auction
data the server already reads (jpauto.auction, the owner's login file, the installed collector) can decode them:
  1. the whole Korea search once (model, model code, trim, year, engine cc, gearbox per lot) joined with the VINs
     already cached from lot pages (korea_auction_data/prices.json);
  2. how well the first VIN characters (WMI + VDS, positions 1-8, and the year letter, position 10) predict model,
     engine and gearbox: groups with one answer / with several;
  3. what the auction says for the VIN of the owner's screenshot and for the Korean VINs already in the CRM, side by
     side with what the CRM holds for them (crm.db opened read-only) — the owner-entered values are the check;
  4. up to 4 lot pages of the same VIN group (fuel, specs labels) and the account dashboard links (is there a purchase
     history with VINs).
Nothing is written except this receipt; no bid is placed. VINs are reported cut to 11 characters (no serial).
"""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import json
import os
from pathlib import Path
import re
import resource
import sqlite3
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/Carix')
TARGET = 'KMHL141EBNA246813'
VIN = re.compile(r'^[A-HJ-NPR-Z0-9]{17}$')
KOREAN = re.compile(r'^K[L-R]')
LONG_NUMBER = re.compile(r'\d{5,}')
WANTED = re.compile(r'(?i)vin|mark|brand|model|year|god|engine|obem|fuel|topl|gear|kpp|trans|drive|privod|trim|kompl')


def with_model_codes(lots, html_tools):
    """lots.parse_results, plus each lot's «Model Code» column (as LOT-PROBE R3)."""
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


def key(vin):
    """Positions 1-8 and the year letter (position 10): the model line, body, engine, model year."""
    return vin[:8] + '_' + vin[9]


def spec(lot):
    return (lot.get('maker', ''), lot.get('model', ''), lot.get('model_code', ''), lot.get('trim', ''),
            str(lot.get('year', '')), str(lot.get('engine_cc', '')), lot.get('transmission', ''))


def groups(lots):
    """VIN group -> Counter of (maker, model, code, engine, gearbox) and of the full spec."""
    found = defaultdict(Counter)
    for lot in lots:
        found[key(lot['vin'])][spec(lot)[:3] + spec(lot)[5:]] += 1
    return found


def consistency(found):
    sizes = Counter()
    for counter in found.values():
        n = sum(counter.values())
        if n >= 2:
            sizes['groups_2plus'] += 1
            sizes['one_answer' if len(counter) == 1 else 'several_answers'] += 1
            top = counter.most_common(1)[0][1]
            sizes['lots_in_2plus'] += n
            sizes['lots_matching_top'] += top
    return dict(sizes)


def lookup(vin, lots, found):
    exact = [spec(l) for l in lots if l['vin'] == vin]
    near8 = Counter(spec(l)[:3] + spec(l)[5:] for l in lots if l['vin'][:8] == vin[:8])
    return {'vin11': vin[:11], 'exact_lot': exact[:3], 'same_group': found.get(key(vin), Counter()).most_common(5),
            'same_first8_any_year': near8.most_common(5)}


def crm_cars():
    """Korean VIN cars in the CRM with the fields the owner entered (read-only)."""
    with closing(sqlite3.connect((ROOT / 'crm.db').as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
        columns = [row[1] for row in db.execute('PRAGMA table_info(cars)')]
        wanted = [c for c in columns if WANTED.search(c)]
        vin_column = next((c for c in columns if c.lower() == 'vin'), None)
        cars = []
        if vin_column:
            for row in db.execute('SELECT %s FROM cars' % ','.join('"%s"' % c for c in wanted)):
                car = dict(zip(wanted, row))
                vin = str(car.get(vin_column) or '').strip().upper()
                if VIN.match(vin) and KOREAN.match(vin):
                    car[vin_column] = vin
                    cars.append(car)
    return columns, vin_column, cars


def dashboard(browser):
    """Account pages: link shapes (numbers hidden) and whether a page lists VINs (purchase history)."""
    _, html = browser.fetch('/customers_dashboard')
    links = sorted({LONG_NUMBER.sub('[N]', h) for h in re.findall(r'href="(/[^"#?]*)', html)})
    pages = {}
    for link in [l for l in links if re.search(r'(?i)purchas|won|history|order|invoice|bought|my', l)][:4]:
        try:
            _, page = browser.fetch(link.replace('[N]', '1'))
        except OSError as error:
            pages[link] = type(error).__name__
            continue
        vins = set(re.findall(r'\b[A-HJ-NPR-Z0-9]{17}\b', page))
        pages[link] = {'vins': len(vins), 'target_present': TARGET in page, 'bytes': len(page)}
    return {'links': links[:80], 'pages': pages}


def detail_fields(lots_module, html):
    detail = lots_module.parse_detail(html)
    return {'spec_labels': sorted(detail['specs'])[:40], 'specs': {k: v for k, v in detail['specs'].items()
                                                                     if not VIN.match(v.strip().upper())},
            'fuel': detail['fuel'], 'body': detail['body']}


def report():
    sys.path.insert(0, str(ROOT))
    from korea_auction import collect, html_tools, job, lots, prices, session
    lots.parse_results = with_model_codes(lots, html_tools)
    cached = prices.load()
    browser = session.Session()
    browser.login(*job.read_login())
    total, all_lots = collect.fetch_all_lots(browser)
    with_vin = []
    for lot in all_lots:
        vin = str(cached.get(lot['id'], {}).get('vin', '')).strip().upper()
        if VIN.match(vin):
            with_vin.append(dict(lot, vin=vin))
    found = groups(with_vin)
    columns, vin_column, cars = crm_cars()
    checks = [dict(lookup(TARGET, with_vin, found), crm={})]
    for car in cars:
        vin = car[vin_column]
        checks.append(dict(lookup(vin, with_vin, found), crm={k: v for k, v in car.items() if k != vin_column}))
    pages = []
    for lot in [l for l in with_vin if key(l['vin']) == key(TARGET)][:2] + \
            [l for l in with_vin if l['vin'][:4] == TARGET[:4]][:2]:
        _, html = browser.fetch(lot['detail_url'])
        pages.append(dict(detail_fields(lots, html), vin11=lot['vin'][:11]))
    return {'status': 'PASS', 'no_bid_placed': True, 'lots_total': total, 'lots_parsed': len(all_lots),
            'cache_entries': len(cached), 'lots_with_vin': len(with_vin),
            'korean_vins': sum(1 for l in with_vin if KOREAN.match(l['vin'])),
            'makers_with_vin': Counter(l['maker'] for l in with_vin).most_common(30),
            'consistency': consistency(found), 'checks': checks, 'lot_pages': pages,
            'crm_columns': columns, 'crm_korean_cars': len(cars), 'dashboard': dashboard(browser),
            'requests': browser.requests}


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
