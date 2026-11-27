"""Hourly summary of the cars on the auctions for the home page search (SEARCH-HOME-001 B, owner «Да» 2026-11-27).

Only this: reads the lot lists the countries' pages already publish (video/<country>/lots.json) and writes one small
public file, video/auctions/summary.json:
    {"version": 1, "updated": "2026-11-27T06:00:00Z", "total": 1760,
     "countries": {"korea": {"total": 1717, "makers": {"kia": {"name": "Kia", "total": 563,
                                                               "models": {"K5": 69, ...}}, ...}}, ...}}
so the home page shows «Зараз на торгах» and the models of a make without loading the full lists. A country whose
list is missing or unreadable is left out (its chip says «скоро»); the write is atomic; nothing else is touched.
Standard library only; run by a PythonAnywhere hourly task.
"""
import datetime
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
SOURCES = (('korea', 'video/korea/lots.json'), ('japan', 'video/japan/lots.json'), ('usa', 'video/usa/lots.json'))
TARGET = 'video/auctions/summary.json'


def key(maker):
    return re.sub(r'[^a-z0-9]', '', str(maker or '').lower())


def model(lot):
    title, maker = str(lot.get('title') or ''), str(lot.get('maker') or '')
    return (title[len(maker):] if title.lower().startswith(maker.lower()) else title).strip()


def country(lots):
    makers = {}
    for lot in lots:
        k = key(lot.get('maker'))
        if not k:
            continue
        entry = makers.setdefault(k, {'name': str(lot['maker']), 'total': 0, 'models': {}})
        entry['total'] += 1
        name = model(lot)
        if name:
            entry['models'][name] = entry['models'].get(name, 0) + 1
    return {'total': sum(m['total'] for m in makers.values()), 'makers': makers}


def read(root, relative):
    try:
        data = json.loads((root/relative).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    lots = data.get('lots') if isinstance(data, dict) else None
    return lots if isinstance(lots, list) else None


def build(root=ROOT, now=None):
    countries = {}
    for name, relative in SOURCES:
        lots = read(root, relative)
        if lots is not None:
            countries[name] = country(lots)
    stamp = (now or datetime.datetime.now(datetime.timezone.utc)).strftime('%Y-%m-%dT%H:%M:%SZ')
    return {'version': 1, 'updated': stamp, 'total': sum(c['total'] for c in countries.values()),
            'countries': countries}


def write(value, root=ROOT):
    path = root/TARGET
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=str(path.parent), prefix='.summary-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        os.chmod(temporary, 0o644)  # public: the web server serves it
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    value = build()
    write(value)
    print('auction summary: %d cars' % value['total'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
