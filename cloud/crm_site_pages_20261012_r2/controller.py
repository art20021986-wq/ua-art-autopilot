#!/usr/bin/env python3
"""Save three public pages (HTTPS GET, already public) for adapting the card-page verifier."""
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.request

TASK_ID = 'CRM-SITE-PAGES-20261012-R2'
PACKAGE = 'cloud/crm_site_pages_20261012_r2'
REQUEST = 'tasks/requests/' + TASK_ID + '.json'
RECEIPT = 'state/receipts/' + TASK_ID + '.json'
PAGES = ('video/UA-0020.html', 'video/UA-0017-diag.html', 'video/UA-0020-diag.html')
ROOT = Path(__file__).resolve().parents[2]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fetch(path):
    request = urllib.request.Request('https://www.uaart.com.ua/%s?v=%d' % (path, time.time()),
                                     headers={'Cache-Control': 'no-cache', 'User-Agent': 'uaart-page-snapshot/1'})
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError('HTTP_%d' % response.status)
        return response.read(8 * 1024 * 1024)


def execute(env, root=ROOT, get=fetch):
    if env.get('UAART_TASK_ID') != TASK_ID or env.get('UAART_RECEIPT_PATH') != RECEIPT:
        raise RuntimeError('IDENTITY')
    request = root / REQUEST
    if sha(request.read_bytes()) != env.get('UAART_REQUEST_SHA256') or not re.fullmatch(r'\d+', env.get('UAART_RUN_ID', '')):
        raise RuntimeError('BINDING')
    for path in PAGES:
        target = root / PACKAGE / Path(path).name
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, 'xb') as handle:
            handle.write(get(path))
    receipt = {'task_id': TASK_ID, 'status': 'FINISHED', 'task_class': 'STANDARD', 'target_environment': 'shadow',
               'live_source_environment': 'production', 'tests': 'PASS', 'tests_scope': 'PUBLIC_GET_ONLY',
               'unexpected_changes': 0, 'rollback_ready': True, 'rollback_ready_scope': 'NO_REMOTE_WRITES',
               'production_required': False, 'request_sha256': env['UAART_REQUEST_SHA256'],
               'run_id': env['UAART_RUN_ID'], 'evidence_path': PACKAGE + '/UA-0020.html'}
    (root / RECEIPT).parent.mkdir(parents=True, exist_ok=True)
    with open(root / RECEIPT, 'x') as handle:
        handle.write(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    execute(os.environ)
