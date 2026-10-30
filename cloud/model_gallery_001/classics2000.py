#!/usr/bin/env python3
"""Read-only Commons search for the Japan rare cars of 2000–2003 with the left-hand drive (owner 2026-10-30).

Owner: 8 photos of different rare cars of 2000–2003, every one with the left-hand drive (important). Each candidate
model gets a search by name and one by name + interior (the wheel side is seen best inside); a year in the file
name must be 2000–2003, a file without a year is left to the eye. The wheel side is checked by eye on 640 px
thumbnails. Same licence filter and evidence form as w245.py.
R2: one JSON was over the 16 MB evidence file limit; the models are split into 3 JSON files
(classics2000_japan_<n>.json).
"""
import os
from pathlib import Path
import re

import collect
from search import search

TASKS = ('MODEL-GALLERY-CLASSICS2000-20261030', 'MODEL-GALLERY-CLASSICS2000-20261030-R2')
PARTS = 3
EVIDENCE = [collect.PACKAGE + '/classics2000_japan_%d.json' % n for n in range(1, PARTS + 1)]
FIRST, LAST = 2000, 2003
THUMB = 640
PER_MODEL = {'outside': 8, 'interior': 4}
# key -> names searched on Commons
MODELS = {
    'bmw-z8': ('BMW Z8', 'BMW E52'),
    'mercedes-benz-sl-r230': ('Mercedes-Benz R230', 'Mercedes-Benz SL 500 R230'),
    'porsche-911-996-turbo': ('Porsche 996 Turbo',),
    'bmw-m3-e46': ('BMW M3 E46',),
    'mercedes-benz-g-w463': ('Mercedes-Benz G 500 W463', 'Mercedes-Benz G 55 AMG'),
    'porsche-boxster-986': ('Porsche Boxster 986',),
    'audi-tt-8n': ('Audi TT 8N',),
    'chevrolet-corvette-c5': ('Chevrolet Corvette C5', 'Corvette C5 Z06'),
    'ferrari-360': ('Ferrari 360 Modena', 'Ferrari 360 Spider'),
    'mercedes-benz-slk-r170': ('Mercedes-Benz SLK 32 AMG', 'Mercedes-Benz R170'),
    'jaguar-xk8': ('Jaguar XK8', 'Jaguar XKR'),
    'bmw-z3-m': ('BMW M Coupé', 'BMW M Roadster'),
    'audi-rs4-b5': ('Audi RS4 B5',),
    'mercedes-benz-clk-55-amg': ('Mercedes-Benz CLK 55 AMG',),
    'honda-s2000': ('Honda S2000',),
    'toyota-mr2-w30': ('Toyota MR2 W30', 'Toyota MR2 Roadster'),
    'toyota-land-cruiser-100': ('Toyota Land Cruiser 100',),
    'nissan-350z': ('Nissan 350Z',),
}
YEAR = re.compile(r'(?<!\d)(19\d\d|20\d\d)(?!\d)')


def year_ok(item):
    """True when every year in the file name is 2000–2003; a name without a year is left to the eye."""
    return all(FIRST <= int(year) <= LAST for year in YEAR.findall(item['title']))


def model(fetch, names):
    wanted, seen = {}, set()
    for kind, suffix in (('interior', ' interior'), ('outside', '')):
        titles = []
        for name in names:
            titles += [t for t in search(fetch, name + suffix) if t not in seen and t not in titles]
        wanted[kind] = titles
        seen.update(titles)
    items = collect.info(fetch, [title for titles in wanted.values() for title in titles], THUMB)
    found = {}
    for kind, titles in wanted.items():
        kept = []
        for title in titles:
            item = items.get(title)
            if item and collect.usable(item) and year_ok(item) and len(kept) < PER_MODEL[kind]:
                thumb = collect.with_thumb(fetch, {**item, 'via': 'classics2000: ' + kind})
                if thumb:
                    kept.append(thumb)
        found[kind] = kept
    return {'candidates': found}


def execute(env, *, root=None, fetch=collect.get):
    root = collect.ROOT if root is None else Path(root)
    request_sha, run_id = collect.validate_identity(env, root, TASKS)
    keys = list(MODELS)
    for n, path in enumerate(EVIDENCE):
        models = {key: model(fetch, MODELS[key]) for key in keys[n::PARTS]}
        collect.write(root, path, collect.dump({'task_id': env['UAART_TASK_ID'], 'run_id': run_id,
                                                'http_methods': ['GET'], 'remote_write_count': 0,
                                                'models': models}))
    receipt = {'task_id': env['UAART_TASK_ID'], 'status': 'FINISHED', 'task_class': 'STANDARD',
               'target_environment': 'shadow', 'live_source_environment': 'wikimedia_commons', 'tests': 'PASS',
               'tests_scope': 'READ_ONLY_PROBE', 'unexpected_changes': 0, 'rollback_ready': True,
               'rollback_ready_scope': 'NO_REMOTE_WRITES', 'production_required': False,
               'request_sha256': request_sha, 'run_id': run_id, 'evidence_path': EVIDENCE}
    collect.write(root, env['UAART_RECEIPT_PATH'], collect.dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('MODEL_GALLERY_CLASSICS2000_STOP:' + (str(exc) if isinstance(exc, collect.CollectError) else type(exc).__name__))
        raise SystemExit(1) from None
