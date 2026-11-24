#!/usr/bin/env python3
"""Read-only probe after the NEW-CAR-VIN-SPEC-INSTALL-20261113 halt: the install step did not find the backup folder
that the backup step had made. Lists, through the PythonAnywhere files API only, the release folders of the
NEW-CAR-VIN packages in the private inbox (names, then every path inside the newcarvin2 folders) and the always-on
task list (no commands kept, only whether a task runs a newcarvin bootstrap). Nothing is run on the server, nothing
is deleted or written there; the bot is not touched.
"""
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

PACKAGE = 'cloud/new_car_vin_probe_001'
TASKS = ('NEW-CAR-VIN-PROBE-20261114',)
ROOT = Path(__file__).resolve().parents[2]
API = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
INBOX = '/home/Carix/autopilot_inbox/cloud/task_068_ferry_vin'
FOLDER = re.compile(r'newcarvin2?-[0-9a-f]{64}')
BOOTSTRAP = re.compile(r'/newcarvin2?_bootstrap\.py\b')
BOT_ID = 266084


class ProbeError(RuntimeError):
    pass


def sha(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


class Api:
    def __init__(self, token):
        if not token or re.search(r'\s', token):
            raise ProbeError('TOKEN_UNAVAILABLE')
        self._token = token

    def get(self, endpoint):
        """GET only, on the always-on list, the inbox listing or a newcarvin folder tree."""
        allowed = (endpoint == 'always_on/' or endpoint == 'files/path' + INBOX + '/'
                   or re.fullmatch(r'files/tree/\?path=' + re.escape(urllib.parse.quote(INBOX + '/', safe='/'))
                                   + r'newcarvin2?-[0-9a-f]{64}/', endpoint))
        if not allowed:
            raise ProbeError('API_PATH_OUTSIDE_SCOPE')
        request = urllib.request.Request(API + endpoint, headers={'Authorization': 'Token ' + self._token,
                                                                 'User-Agent': 'uaart-new-car-vin-probe/1'})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, json.loads(response.read(8 * 1024 * 1024) or b'null')
        except urllib.error.HTTPError as error:
            error.close()
            return error.code, None


def collect(api):
    status, listing = api.get('files/path' + INBOX + '/')
    if status != 200 or not isinstance(listing, dict):
        raise ProbeError('INBOX_LISTING:%d' % status)
    folders = sorted(name for name in listing if FOLDER.fullmatch(name))
    trees = {}
    for name in folders:
        if name.startswith('newcarvin2-'):
            code, paths = api.get('files/tree/?path=' + urllib.parse.quote(INBOX + '/' + name + '/', safe='/'))
            prefix = INBOX + '/' + name + '/'
            trees[name] = {'http': code, 'paths': sorted(p[len(prefix):] for p in paths or [] if str(p).startswith(prefix)
                                                          and not str(p).endswith('.py'))}
    code, tasks = api.get('always_on/')
    short = [{'id': t.get('id'), 'enabled': t.get('enabled'), 'state': t.get('state'),
              'newcarvin_bootstrap': bool(BOOTSTRAP.search(str(t.get('command', ''))))}
             for t in tasks or [] if isinstance(t, dict)]
    return {'inbox_newcarvin_folders': folders, 'newcarvin2_trees': trees,
            'always_on': {'http': code, 'tasks': short}}


def validate_identity(env, root):
    if env.get('UAART_TASK_ID') not in TASKS or env.get('UAART_RECEIPT_PATH') != 'state/receipts/%s.json' % env.get('UAART_TASK_ID') \
            or env.get('UAART_REQUEST_PATH') != 'tasks/requests/%s.json' % env.get('UAART_TASK_ID'):
        raise ProbeError('IDENTITY')
    request = root/env['UAART_REQUEST_PATH']
    expected = env.get('UAART_REQUEST_SHA256', '')
    if sha(request.read_bytes()) != expected or not re.fullmatch(r'\d+', env.get('UAART_RUN_ID', '')):
        raise ProbeError('BINDING')
    if json.loads(request.read_bytes()).get('production_required') is not False:
        raise ProbeError('SCOPE')
    return expected, env['UAART_RUN_ID']


def dump(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, default=str)+'\n').encode()


def write(root, relative, data):
    target = root/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'xb') as handle:
        handle.write(data)


def execute(env, *, root=None, api=None):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    task = env['UAART_TASK_ID']
    result = collect(api or Api(env.get('PYTHONANYWHERE_API_TOKEN', '')))
    evidence = PACKAGE + '/evidence.json'
    write(root, evidence, dump({'task_id': task, 'run_id': run_id, **result}))
    receipt = {'task_id': task, 'status': 'FINISHED', 'task_class': 'STANDARD', 'target_environment': 'shadow',
               'live_source_environment': 'production', 'tests': 'PASS', 'tests_scope': 'READ_ONLY_PROBE',
               'unexpected_changes': 0, 'rollback_ready': True, 'rollback_ready_scope': 'NO_SITE_OR_CRM_WRITES',
               'production_required': False, 'request_sha256': request_sha, 'run_id': run_id, 'evidence_path': evidence}
    write(root, env['UAART_RECEIPT_PATH'], dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('NEW_CAR_VIN_PROBE_STOP:'+(str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
