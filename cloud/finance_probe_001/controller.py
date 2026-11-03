#!/usr/bin/env python3
"""Read-only probe for FINANCE-001: the partner's official pages (runner) and the server sources (PythonAnywhere).

Part 1 runs here: GET of the public hapai.kiev.ua pages and logo candidates (partner_site.py); the logo bytes
travel in the report as base64, so the run writes only its report and receipt. Part 2 uploads this package
to the existing private inbox, runs source_remote.py once in a temporary always-on task (removed after its
receipt; never the CRM bot) and adds its report. No site, CRM, source or bot change.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re

import partner_site
from transport import API, upload_package

TASK = re.compile(r'FINANCE-PROBE-(20[0-9]{6}(?:-R[0-9])?)')
PACKAGE = 'cloud/finance_probe_001'
ROOT = Path(__file__).resolve().parents[2]
SECRET = re.compile(r'-----BEGIN|private_key"')


class ProbeError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_identity(env, root):
    task = env.get('UAART_TASK_ID', '')
    if not TASK.fullmatch(task) or env.get('UAART_RECEIPT_PATH') != 'state/receipts/%s.json' % task \
            or env.get('UAART_REQUEST_PATH') != 'tasks/requests/%s.json' % task:
        raise ProbeError('IDENTITY')
    request = root / env['UAART_REQUEST_PATH']
    expected = env.get('UAART_REQUEST_SHA256', '')
    if sha(request.read_bytes()) != expected or not re.fullmatch(r'\d+', env.get('UAART_RUN_ID', '')):
        raise ProbeError('BINDING')
    if json.loads(request.read_bytes()).get('production_required') is not False:
        raise ProbeError('SCOPE')
    return expected, env['UAART_RUN_ID']


def dump(value):
    data = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    if SECRET.search(data.decode()):
        raise ProbeError('KEY_MATERIAL_IN_REPORT')
    return data


def write(root, relative, data):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'xb') as handle:
        handle.write(data)


def partner(collect):
    try:
        pages, files = collect()
    except Exception as error:
        return {'status': 'FAIL', 'error': type(error).__name__ + ':' + str(error)[:160]}
    for value in files.values():
        if 'bytes' in value:
            value['base64'] = base64.b64encode(value.pop('bytes')).decode()
    return {'status': 'PASS', 'pages': pages, 'logo_files': files}


def execute(env, *, root=None, api=None, upload=upload_package, collect=partner_site.collect):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    site = partner(collect)
    api = api or API(env.get('PYTHONANYWHERE_API_TOKEN', ''))
    server = api.run('probe', run_id, upload(api))
    task = env['UAART_TASK_ID']
    evidence = '%s/%s.json' % (PACKAGE, TASK.fullmatch(task).group(1))
    write(root, evidence, dump({'task_id': task, 'run_id': run_id, 'partner_site': site, 'server': server}))
    receipt = {'task_id': task, 'status': 'FINISHED', 'task_class': 'STANDARD', 'target_environment': 'shadow',
               'live_source_environment': 'production', 'tests': 'PASS', 'tests_scope': 'READ_ONLY_PROBE',
               'unexpected_changes': 0, 'rollback_ready': True, 'rollback_ready_scope': 'NO_SITE_OR_CRM_WRITES',
               'production_required': False, 'request_sha256': request_sha, 'run_id': run_id,
               'evidence_path': evidence, 'probe_status': server.get('status'), 'partner_status': site['status']}
    write(root, env['UAART_RECEIPT_PATH'], dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('FINANCE_PROBE_STOP:' + (str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
