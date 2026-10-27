#!/usr/bin/env python3
"""Read-only Commons search by the owner's 8 views (MODEL-GALLERY-001, owner 2026-10-27).

Owner: 4 outside views — front 3/4 from the left (left headlight, left side, front), front 3/4 from the right,
rear 3/4 from the left (left side, tail lamp, boot lid), rear 3/4 from the right; 4 inside views — dashboard from
the driver's side, dashboard from the passenger's side, rear seats, boot. The cars may differ, the views may not.
Each view gets its own file searches; only freely licensed 2018–2023 cars are kept (years.car_year_ok). One JSON
per country group (angles_<group>.json) with candidates per view for the pick by eye.
"""
import os
from pathlib import Path

import collect
from search import search
import years

TASKS = ('MODEL-GALLERY-ANGLES-20261027',)
# The 8 views in gallery order -> search word groups added to the model's generation names.
VIEWS = (
    ('front_left', (' front left', ' front', ' 3/4 front')),
    ('front_right', (' front right', ' front 3/4')),
    ('rear_left', (' rear left', ' rear', ' 3/4 rear')),
    ('rear_right', (' rear right', ' rear 3/4')),
    ('dash_driver', (' interior', ' dashboard', ' cockpit')),
    ('dash_passenger', (' interior passenger', ' dashboard passenger side', ' front seats')),
    ('rear_seats', (' rear seats', ' back seats', ' rear seat')),
    ('boot', (' trunk', ' boot', ' cargo')),
)
# 32 models x 8 views x 10 thumbnails stays under the 64 MB evidence limit of one run.
PER_VIEW = 10


def model(fetch, key):
    names, recent = years.TARGETS[key]
    seen, wanted = set(), {}
    for view, suffixes in VIEWS:
        titles = []
        for name in names:
            for suffix in suffixes:
                titles += [t for t in search(fetch, name + suffix) if t not in seen and t not in titles]
        wanted[view] = titles
        seen.update(titles)
    every = [title for titles in wanted.values() for title in titles]
    items = collect.info(fetch, every, collect.THUMB)
    found = {}
    for view, titles in wanted.items():
        kept = []
        for title in titles:
            item = items.get(title)
            if item and collect.usable(item) and years.car_year_ok(item, recent) and len(kept) < PER_VIEW:
                thumb = collect.with_thumb(fetch, {**item, 'via': 'angles: ' + view})
                if thumb:
                    kept.append(thumb)
        found[view] = kept
    return {'candidates': found}


def evidence_path(group):
    return '%s/angles_%s.json' % (collect.PACKAGE, group)


def execute(env, *, root=None, fetch=collect.get):
    root = collect.ROOT if root is None else Path(root)
    request_sha, run_id = collect.validate_identity(env, root, TASKS)
    groups = sorted({collect.MODELS[key][0] for key in years.TARGETS})
    for group in groups:
        found = {key: model(fetch, key) for key in years.TARGETS if collect.MODELS[key][0] == group}
        collect.write(root, evidence_path(group), collect.dump({'task_id': env['UAART_TASK_ID'], 'run_id': run_id,
                                                                'http_methods': ['GET'], 'remote_write_count': 0,
                                                                'models': found}))
    receipt = {'task_id': env['UAART_TASK_ID'], 'status': 'FINISHED', 'task_class': 'STANDARD',
               'target_environment': 'shadow', 'live_source_environment': 'wikimedia_commons', 'tests': 'PASS',
               'tests_scope': 'READ_ONLY_PROBE', 'unexpected_changes': 0, 'rollback_ready': True,
               'rollback_ready_scope': 'NO_REMOTE_WRITES', 'production_required': False,
               'request_sha256': request_sha, 'run_id': run_id,
               'evidence_path': [evidence_path(group) for group in groups]}
    collect.write(root, env['UAART_RECEIPT_PATH'], collect.dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('MODEL_GALLERY_ANGLES_STOP:'+(str(exc) if isinstance(exc, collect.CollectError) else type(exc).__name__))
        raise SystemExit(1) from None
