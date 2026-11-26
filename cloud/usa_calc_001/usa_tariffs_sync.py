"""Weekly copy of US yard -> Poti shipping prices for the USA calculator (SEARCH-HOME-001, owner 2026-11-26).

Only collecting: asks the partner's public calculator, the same requests its page makes, slowly, and writes one
JSON file the page reads:
    {"version": 1, "updated": "YYYY-MM-DD", "costs": {...usa_costs.public()},
     "yards": [["Martinez", "CA", 2160, 2260, "martinez 94553"], ...]}   # name, state, car $, suv $, search words
One package (Standard), two car types (1 car, 2 SUV). A yard listed by several auctions keeps the highest price.
Any failure or a suspiciously small result keeps the previous file (exit code 1); the write is atomic.
Standard library only.
"""
import datetime
import html
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import urllib.parse
import urllib.request

import usa_costs

BASE = 'https://newshipping.2mcars.ge/conf/'
PACKAGE = 2                                   # Standard
AUCTIONS = (1, 3, 2, 4)                      # Copart, IAAI, Manheim, Adesa (sublots/pipeline are street addresses)
TYPES = (1, 2)                                # car, SUV
PAUSE = 0.5                                   # seconds between requests
MIN_YARDS = 300                               # fewer means the source changed: keep the old file
PATH = Path(__file__).resolve().parent / 'video' / 'usa' / 'tariffs.json'
OPTION = re.compile(r'<option value="(\d+)"[^>]*>([^<]*)')
PRICE = re.compile(r'PORT\s+\w+\s*:\s*([\d.,]+)')


class SyncError(RuntimeError):
    pass


def post(name, data, opener=urllib.request.urlopen):
    time.sleep(PAUSE)
    body = urllib.parse.urlencode(data).encode()
    request = urllib.request.Request(BASE + name, body, {'User-Agent': 'Mozilla/5.0 (tariff copy, weekly)'})
    with opener(request, timeout=30) as response:
        return response.read().decode('utf-8', 'replace')


def options(text):
    return [(int(v), html.unescape(label).strip()) for v, label in OPTION.findall(text) if int(v) > 0]


def price(text):
    match = PRICE.search(re.sub(r'<[^>]+>', ' ', text))
    if not match:
        return None
    value = int(re.sub(r'[.,]', '', match.group(1)))
    return value if 100 <= value <= 20000 else None


def yard(label, state):
    """'Martinez / MARTINEZ / 94553' -> ('Martinez', 'martinez 94553 ca'); a street address -> None."""
    parts = [p.strip().strip('"') for p in label.split('/')]
    name = parts[0].title()
    if not name or name[0].isdigit() or ',' in name:
        return None
    words = ' '.join(dict.fromkeys(p.lower() for p in parts if p))
    return name, '%s %s' % (words, state.lower())


def collect(ask=post):
    yards = {}
    for auction in AUCTIONS:
        for state_id, state in options(ask('getState.php', {'auc_id': auction})):
            for city_id, label in options(ask('city.php', {'state_id': state_id, 'auc_id': auction})):
                prices = []
                for kind in TYPES:
                    n = PACKAGE
                    prices.append(price(ask('data%d.php' % n, {'auc_id_%d' % n: auction, 'state_id_%d' % n: state_id,
                                                              'city_id_%d' % n: city_id, 'type_id_%d' % n: kind})))
                if None in prices:
                    continue
                found = yard(label, state)
                if found is None:
                    continue
                name, words = found
                old = yards.setdefault((name, state), [name, state, 0, 0, ''])
                old[2], old[3] = max(old[2], prices[0]), max(old[3], prices[1])
                old[4] = ' '.join(dict.fromkeys((old[4] + ' ' + words).split()))
    return sorted(yards.values(), key=lambda y: (y[0], y[1]))


def write(yards, today=None, path=None):
    path = path or PATH
    if len(yards) < MIN_YARDS:
        raise SyncError('too few yards: %d' % len(yards))
    data = {'version': 1, 'updated': (today or datetime.date.today()).isoformat(), 'costs': usa_costs.public(),
            'yards': yards}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=str(path.parent), prefix='.tariffs.')
    with os.fdopen(fd, 'w', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, separators=(',', ':'))
    os.chmod(temp, 0o644)
    os.replace(temp, path)


def main():
    try:
        yards = collect()
        write(yards)
    except Exception as error:  # keep the previous file whatever went wrong
        print('usa tariffs: kept the old file:', error, file=sys.stderr)
        return 1
    print('usa tariffs: %d yards' % len(yards))
    return 0


if __name__ == '__main__':
    sys.exit(main())
