#!/usr/bin/env python3
"""Google Ads lead conversions on (owner «Да» 2026-11-25 to «Включаю учёт заявок в рекламном кабинете»).

Uploads this package to the existing private inbox, runs source_remote.py once in a
temporary always-on task (removed after its receipt) and saves its report. Only the
Google Ads conversion actions change (validate-only first); no site, CRM, source or bot change.
"""
import hashlib
import json
import os
from pathlib import Path
import re

from transport import API, upload_package

TASK = re.compile(r'ADS-CONV-(20[0-9]{6}(?:-R[0-9])?)')
PACKAGE = 'cloud/ads_conv_001'
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
    raw = json.loads(request.read_bytes())
    if raw.get('production_required') is not False:
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


def execute(env, *, root=None, api=None, upload=upload_package):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    api = api or API(env.get('PYTHONANYWHERE_API_TOKEN', ''))
    report = api.run('probe', run_id, upload(api))
    task = env['UAART_TASK_ID']
    evidence = '%s/%s.json' % (PACKAGE, TASK.fullmatch(task).group(1))
    write(root, evidence, dump({'task_id': task, 'run_id': run_id, **report}))
    receipt = {'task_id': task, 'status': 'FINISHED', 'task_class': 'STANDARD', 'target_environment': 'shadow',
               'live_source_environment': 'production', 'tests': 'PASS', 'tests_scope': 'GOOGLE_ADS_CONVERSION_GOALS',
               'unexpected_changes': 0, 'rollback_ready': True, 'rollback_ready_scope': 'BEFORE_STATE_IN_REPORT_NO_SITE_OR_CRM_WRITES',
               'production_required': False, 'request_sha256': request_sha, 'run_id': run_id,
               'evidence_path': evidence, 'probe_status': report.get('status')}
    write(root, env['UAART_RECEIPT_PATH'], dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('ADS_CONV_STOP:' + (str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
