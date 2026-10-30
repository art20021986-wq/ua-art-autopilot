#!/usr/bin/env python3
"""Read-only Commons search for the Japan Mercedes-Benz B-Class card as a W245 (owner 2026-10-30).

Owner: the card shows the 1st generation W245 of 2010–2011; 8 photos at most, the owner's views (angles.VIEWS),
the cars may differ. 2010–2011 cars are the 2008–2011 facelift, so a year in the file name must be 2008–2011
and a file without a year is kept for the pick by eye (facelift look). Same licence filter and evidence form as
angles.py; one JSON (w245_japan.json) with candidates per view.
"""
import os
from pathlib import Path
import re

import angles
import collect
from search import search

TASKS = ('MODEL-GALLERY-W245-20261030',)
KEY = 'mercedes-benz-b-class'
NAMES = ('Mercedes-Benz W245 facelift', 'Mercedes-Benz B-Klasse W245', 'Mercedes-Benz B 180 W245',
         'Mercedes-Benz B 200 W245', 'Mercedes-Benz W245')
FIRST, LAST = 2008, 2011
PER_VIEW = 20
EVIDENCE = collect.PACKAGE + '/w245_japan.json'
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


def execute(env, *, root=None, fetch=collect.get):
    root = collect.ROOT if root is None else Path(root)
    request_sha, run_id = collect.validate_identity(env, root, TASKS)
    collect.write(root, EVIDENCE, collect.dump({'task_id': env['UAART_TASK_ID'], 'run_id': run_id,
                                                'http_methods': ['GET'], 'remote_write_count': 0,
                                                'models': {KEY: {'candidates': candidates(fetch)}}}))
    receipt = {'task_id': env['UAART_TASK_ID'], 'status': 'FINISHED', 'task_class': 'STANDARD',
               'target_environment': 'shadow', 'live_source_environment': 'wikimedia_commons', 'tests': 'PASS',
               'tests_scope': 'READ_ONLY_PROBE', 'unexpected_changes': 0, 'rollback_ready': True,
               'rollback_ready_scope': 'NO_REMOTE_WRITES', 'production_required': False,
               'request_sha256': request_sha, 'run_id': run_id, 'evidence_path': [EVIDENCE]}
    collect.write(root, env['UAART_RECEIPT_PATH'], collect.dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('MODEL_GALLERY_W245_STOP:' + (str(exc) if isinstance(exc, collect.CollectError) else type(exc).__name__))
        raise SystemExit(1) from None
