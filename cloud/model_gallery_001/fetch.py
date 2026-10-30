#!/usr/bin/env python3
"""Read-only download of the picked gallery photos (MODEL-GALLERY-001), 960 px wide from Wikimedia Commons.

picks.py names, per model, the Commons files chosen by eye from the collected candidates
(per view; R2: 2018–2023 cars only; 20261027: one photo per owner's view). Each file's
licence is checked again; one JSON per country group keeps the photo (base64) with author and licence.
"""
import base64
import os
from pathlib import Path

import collect
import picks as chosen
import picks_w245

TASKS = ('MODEL-GALLERY-FETCH-20261026', 'MODEL-GALLERY-FETCH-20261026-R2', 'MODEL-GALLERY-FETCH-20261027',
         'MODEL-GALLERY-FETCH-20261027-R2', 'MODEL-GALLERY-FETCH-20261030')
WIDTH = 960


# Each run writes its own files, never over an earlier run's: photos, photos2 (2018–2023), photos3 (owner's views),
# photos4 (views with the side checked), photos5 (the Japan B-Class card as W245, owner 2026-10-30).
STEMS = dict(zip(TASKS, ('photos', 'photos2', 'photos3', 'photos4', 'photos5')))
# A run that fetches other picks than picks.py.
TASK_PICKS = {'MODEL-GALLERY-FETCH-20261030': picks_w245.PICKS}


def evidence_path(group, task=TASKS[-1]):
    return '%s/%s_%s.json' % (collect.PACKAGE, STEMS[task], group)


def photos(fetch, titles):
    found = collect.info(fetch, titles, WIDTH)
    result = []
    for title in titles:
        item = found.get(title)
        if not item or not collect.FREE.match(item['license'] or '') or not item['thumb']:
            raise collect.CollectError('PICK_UNUSABLE:' + title)
        data = fetch(item['thumb'])
        if not data:
            raise collect.CollectError('PICK_DOWNLOAD:' + title)
        result.append({**item, 'sha256': collect.sha(data), 'b64': base64.b64encode(data).decode()})
    return result


def execute(env, *, root=None, fetch=collect.get, picks=None):
    root = collect.ROOT if root is None else Path(root)
    request_sha, run_id = collect.validate_identity(env, root, TASKS)
    picks = TASK_PICKS.get(env['UAART_TASK_ID'], chosen.PICKS) if picks is None else picks
    groups = sorted({collect.MODELS[key][0] for key in picks})
    for group in groups:
        found = {key: {kind: photos(fetch, titles) for kind, titles in views.items()}
                 for key, views in picks.items() if collect.MODELS[key][0] == group}
        collect.write(root, evidence_path(group, env['UAART_TASK_ID']), collect.dump({'task_id': env['UAART_TASK_ID'], 'run_id': run_id,
                                                                'http_methods': ['GET'], 'remote_write_count': 0,
                                                                'models': found}))
    receipt = {'task_id': env['UAART_TASK_ID'], 'status': 'FINISHED', 'task_class': 'STANDARD',
               'target_environment': 'shadow', 'live_source_environment': 'wikimedia_commons', 'tests': 'PASS',
               'tests_scope': 'READ_ONLY_PROBE', 'unexpected_changes': 0, 'rollback_ready': True,
               'rollback_ready_scope': 'NO_REMOTE_WRITES', 'production_required': False,
               'request_sha256': request_sha, 'run_id': run_id,
               'evidence_path': [evidence_path(group, env['UAART_TASK_ID']) for group in groups]}
    collect.write(root, env['UAART_RECEIPT_PATH'], collect.dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('MODEL_GALLERY_FETCH_STOP:'+(str(exc) if isinstance(exc, collect.CollectError) else type(exc).__name__))
        raise SystemExit(1) from None
