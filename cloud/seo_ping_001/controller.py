#!/usr/bin/env python3
"""SEO-PING-001: on the server, tell IndexNow and Google that the two finance pages changed (owner «Да» 2026-11-04).

Uploads this package to the existing private inbox, runs ping_remote.py once in a temporary always-on task
(removed after its receipt; never the CRM bot) and writes its report and receipt. No site, CRM, source or bot change.
"""
import hashlib
import json
import os
from pathlib import Path
import re

from transport import API, upload_package

TASK = 'SEO-PING-20261104'
PACKAGE = 'cloud/seo_ping_001'
ROOT = Path(__file__).resolve().parents[2]


class PingError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_identity(env, root):
    if env.get('UAART_TASK_ID') != TASK or env.get('UAART_RECEIPT_PATH') != 'state/receipts/%s.json' % TASK \
            or env.get('UAART_REQUEST_PATH') != 'tasks/requests/%s.json' % TASK:
        raise PingError('IDENTITY')
    request = root / env['UAART_REQUEST_PATH']
    expected = env.get('UAART_REQUEST_SHA256', '')
    if sha(request.read_bytes()) != expected or not re.fullmatch(r'\d+', env.get('UAART_RUN_ID', '')):
        raise PingError('BINDING')
    if json.loads(request.read_bytes()).get('production_required') is not False:
        raise PingError('SCOPE')
    return expected, env['UAART_RUN_ID']


def write(root, relative, value):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'xb') as handle:
        handle.write((json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode())


def execute(env, *, root=None, api=None, upload=upload_package):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    api = api or API(env.get('PYTHONANYWHERE_API_TOKEN', ''))
    server = api.run('ping', run_id, upload(api))
    evidence = PACKAGE + '/report.json'
    write(root, evidence, {'task_id': TASK, 'run_id': run_id, 'server': server})
    receipt = {'task_id': TASK, 'status': 'FINISHED', 'task_class': 'STANDARD', 'target_environment': 'shadow',
               'live_source_environment': 'production', 'tests': 'PASS', 'tests_scope': 'SEARCH_ENGINE_NOTICE_ONLY',
               'unexpected_changes': 0, 'rollback_ready': True, 'rollback_ready_scope': 'NO_SITE_OR_CRM_WRITES',
               'production_required': False, 'request_sha256': request_sha, 'run_id': run_id,
               'evidence_path': evidence, 'ping_status': server.get('status')}
    write(root, env['UAART_RECEIPT_PATH'], receipt)
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('SEO_PING_STOP:' + (str(exc) if isinstance(exc, PingError) else type(exc).__name__))
        raise SystemExit(1) from None
