#!/usr/bin/env python3
"""Read-only download of the picked gallery photos (MODEL-GALLERY-001), 960 px wide from Wikimedia Commons.

picks.json names, per model, the Commons files chosen by eye from the collected candidates. Each file's
licence is checked again; one JSON per country group keeps the photo (base64) with author and licence.
"""
import base64
import json
import os
from pathlib import Path

import collect

PICKS = Path(__file__).resolve().parent/'picks.json'
TASKS = ('MODEL-GALLERY-FETCH-20261026',)
WIDTH = 960


def evidence_path(group):
    return '%s/photos_%s.json' % (collect.PACKAGE, group)


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
    picks = json.loads(PICKS.read_text()) if picks is None else picks
    groups = sorted({collect.MODELS[key][0] for key in picks})
    for group in groups:
        found = {key: photos(fetch, titles) for key, titles in picks.items() if collect.MODELS[key][0] == group}
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
        print('MODEL_GALLERY_FETCH_STOP:'+(str(exc) if isinstance(exc, collect.CollectError) else type(exc).__name__))
        raise SystemExit(1) from None
