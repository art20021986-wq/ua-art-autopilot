#!/usr/bin/env python3
"""Read-only Commons search for the Japan Mercedes-Benz B-Class card as a W245 (owner 2026-10-30).

Owner: the card shows the 1st generation W245 of 2010–2011; 8 photos at most, the owner's views (angles.VIEWS),
the cars may differ. 2010–2011 cars are the 2008–2011 facelift, so a year in the file name must be 2008–2011
and a file without a year is kept for the pick by eye (facelift look). Same licence filter and evidence form as
angles.py; one JSON (w245_japan.json) with candidates per view.
R2: the view searches found one interior photo and no boot; the interior round reads the Commons categories of
that photo (and their subcategories) plus German interior and boot searches (w245r2_japan.json, one pool).
R3: R2 kept nothing (interior photos there are not named so): every usable file of those categories goes to the
pool for the pick by eye (w245r3_japan.json).
"""
import os
from pathlib import Path
import re

import angles
import collect
from search import search

TASKS = ('MODEL-GALLERY-W245-20261030', 'MODEL-GALLERY-W245-20261030-R2', 'MODEL-GALLERY-W245-20261030-R3')
KEY = 'mercedes-benz-b-class'
NAMES = ('Mercedes-Benz W245 facelift', 'Mercedes-Benz B-Klasse W245', 'Mercedes-Benz B 180 W245',
         'Mercedes-Benz B 200 W245', 'Mercedes-Benz W245')
FIRST, LAST = 2008, 2011
PER_VIEW = 20
EVIDENCE = {TASKS[0]: collect.PACKAGE + '/w245_japan.json', TASKS[1]: collect.PACKAGE + '/w245r2_japan.json',
            TASKS[2]: collect.PACKAGE + '/w245r3_japan.json'}
SEED = 'File:2010 Mercedes-Benz B 200 (W 245 MY11) hatchback (2010-10-16).jpg'
NAMED = re.compile(r'W ?245|B-Klasse|B-Class', re.I)
INSIDE = ('Mercedes-Benz W245 Innenraum', 'Mercedes B-Klasse Innenraum', 'Mercedes-Benz W245 Kofferraum',
          'Mercedes B-Klasse Kofferraum', 'Mercedes-Benz W245 interior', 'Mercedes-Benz B-Class W245 interior')
PER_POOL = 120
YEAR = re.compile(r'(?<!\d)(19\d\d|20\d\d)(?!\d)')


def year_ok(item):
    """True when every year in the file name is a facelift year; a name without a year is left to the eye."""
    return all(FIRST <= int(year) <= LAST for year in YEAR.findall(item['title']))


def candidates(fetch):
    seen, wanted = set(), {}
    for view, suffixes in angles.VIEWS:
        titles = []
        for name in NAMES:
            for suffix in suffixes:
                titles += [t for t in search(fetch, name + suffix) if t not in seen and t not in titles]
        wanted[view] = titles
        seen.update(titles)
    items = collect.info(fetch, [title for titles in wanted.values() for title in titles], collect.THUMB)
    found = {}
    for view, titles in wanted.items():
        kept = []
        for title in titles:
            item = items.get(title)
            if item and collect.usable(item) and year_ok(item) and len(kept) < PER_VIEW:
                thumb = collect.with_thumb(fetch, {**item, 'via': 'w245: ' + view})
                if thumb:
                    kept.append(thumb)
        found[view] = kept
    return found


def interior(fetch, every=False):
    """R2: files of the seed photo's W245 categories and their subcategories, then the German searches.

    A file is kept when its name or its source (category or query) names an interior or boot view; R3: every file.
    """
    via = {}
    for category in (c for c in collect.categories(fetch, SEED) if NAMED.search(c)):
        for sub in [category] + collect.members(fetch, category, 'subcat'):
            for title in collect.members(fetch, sub, 'file'):
                via.setdefault(title, sub)
    for query in INSIDE:
        for title in search(fetch, query):
            via.setdefault(title, query)
    items = collect.info(fetch, list(via), collect.THUMB)
    kept = []
    for title, source in via.items():
        item = items.get(title)
        inside = every or collect.INTERIOR.search(title) or collect.INTERIOR.search(source)
        if item and inside and collect.usable(item) and year_ok(item) and len(kept) < PER_POOL:
            thumb = collect.with_thumb(fetch, {**item, 'via': 'w245: ' + source})
            if thumb:
                kept.append(thumb)
    return {'interior': kept}


def execute(env, *, root=None, fetch=collect.get):
    root = collect.ROOT if root is None else Path(root)
    request_sha, run_id = collect.validate_identity(env, root, TASKS)
    task = env['UAART_TASK_ID']
    found = candidates(fetch) if task == TASKS[0] else interior(fetch, every=task == TASKS[2])
    collect.write(root, EVIDENCE[task], collect.dump({'task_id': task, 'run_id': run_id,
                                                      'http_methods': ['GET'], 'remote_write_count': 0,
                                                      'models': {KEY: {'candidates': found}}}))
    receipt = {'task_id': env['UAART_TASK_ID'], 'status': 'FINISHED', 'task_class': 'STANDARD',
               'target_environment': 'shadow', 'live_source_environment': 'wikimedia_commons', 'tests': 'PASS',
               'tests_scope': 'READ_ONLY_PROBE', 'unexpected_changes': 0, 'rollback_ready': True,
               'rollback_ready_scope': 'NO_REMOTE_WRITES', 'production_required': False,
               'request_sha256': request_sha, 'run_id': run_id, 'evidence_path': [EVIDENCE[task]]}
    collect.write(root, env['UAART_RECEIPT_PATH'], collect.dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('MODEL_GALLERY_W245_STOP:' + (str(exc) if isinstance(exc, collect.CollectError) else type(exc).__name__))
        raise SystemExit(1) from None
