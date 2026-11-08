#!/usr/bin/env python3
"""Finish OWN-COUNTER-INSTALL-20261107: reload the web app so /ua/a.js serves the installed analitika_yadro.py.

The install wrote all planned files (ANALYTICS-AUDIT-PROBE-20261108: hashes equal the plan) but stopped before its
reload. This task only asks PythonAnywhere to reload the web app and then reads the public script until it carries
the fix. No file, CRM or bot change.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

TASK = re.compile(r'WEBAPP-RELOAD-(20[0-9]{6}(?:-R[0-9])?)')
PACKAGE = 'cloud/webapp_reload_001'
ROOT = Path(__file__).resolve().parents[2]
RELOAD = 'https://www.pythonanywhere.com/api/v0/user/Carix/webapps/www.uaart.com.ua/reload/'
SCRIPT = 'https://www.uaart.com.ua/ua/a.js?v=1&check=%d'
MARK = 'UA-OWN-COUNTER-001'


class ReloadError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_identity(env, root):
    task = env.get('UAART_TASK_ID', '')
    if not TASK.fullmatch(task) or env.get('UAART_RECEIPT_PATH') != 'state/receipts/%s.json' % task \
            or env.get('UAART_REQUEST_PATH') != 'tasks/requests/%s.json' % task:
        raise ReloadError('IDENTITY')
    request = root / env['UAART_REQUEST_PATH']
    expected = env.get('UAART_REQUEST_SHA256', '')
    if sha(request.read_bytes()) != expected or not re.fullmatch(r'\d+', env.get('UAART_RUN_ID', '')):
        raise ReloadError('BINDING')
    if json.loads(request.read_bytes()).get('production_required') is not False:
        raise ReloadError('SCOPE')
    return expected, env['UAART_RUN_ID']


def reload(token):
    if not token or re.search(r'\s', token):
        raise ReloadError('TOKEN_UNAVAILABLE')
    request = urllib.request.Request(RELOAD, data=b'', method='POST', headers={'Authorization': 'Token ' + token})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return 'HTTP_%d' % response.status
    except urllib.error.HTTPError as error:
        return 'HTTP_%d' % error.code
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return 'UNCONFIRMED:' + type(error).__name__


def script_fixed():
    request = urllib.request.Request(SCRIPT % int(time.time()), headers={'Cache-Control': 'no-cache',
                                                                         'User-Agent': 'UAART-Reload-Verify/1'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status == 200 and MARK in response.read(256 * 1024).decode('utf-8', 'replace')


def wait_fixed(deadline_seconds=300, pause=15):
    deadline = time.monotonic() + deadline_seconds
    while True:
        try:
            if script_fixed():
                return True
        except OSError:
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(pause)


def write(root, relative, value):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'x') as handle:
        handle.write(json.dumps(value, sort_keys=True, indent=2) + '\n')


def execute(env, *, root=None, do_reload=reload, wait=wait_fixed):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    task = env['UAART_TASK_ID']
    before = wait(0, 0)
    result = do_reload(env.get('PYTHONANYWHERE_API_TOKEN', '')) if not before else 'SKIPPED_ALREADY_LIVE'
    fixed = before or wait()
    evidence = '%s/%s.json' % (PACKAGE, TASK.fullmatch(task).group(1))
    write(root, evidence, {'task_id': task, 'run_id': run_id, 'script_fixed_before': before, 'reload': result,
                           'script_fixed_after': fixed, 'file_writes': 0, 'crm_write': False})
    if not fixed:
        raise ReloadError('SCRIPT_NOT_LIVE:' + result)
    receipt = {'task_id': task, 'status': 'FINISHED', 'task_class': 'STANDARD', 'target_environment': 'shadow',
               'live_source_environment': 'production', 'tests': 'PASS', 'tests_scope': 'WEBAPP_RELOAD_ONLY',
               'unexpected_changes': 0, 'rollback_ready': True, 'rollback_ready_scope': 'NO_FILE_OR_CRM_WRITES',
               'production_required': False, 'request_sha256': request_sha, 'run_id': run_id,
               'evidence_path': evidence, 'reload': result}
    write(root, env['UAART_RECEIPT_PATH'], receipt)
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('WEBAPP_RELOAD_STOP:' + (str(exc) if isinstance(exc, ReloadError) else type(exc).__name__))
        raise SystemExit(1) from None
