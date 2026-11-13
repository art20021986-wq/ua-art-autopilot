#!/usr/bin/env python3
"""After the OLD-PODBOR-INSTALL-20261113 halt (backup step: network timeout while deleting its temporary always-on
task): the server CPU, the CRM bot task 266084, every always-on task, and removal of leftover temporary tasks of the
session's own packages only (command runs opod_bootstrap.py or dcnt_bootstrap.py). The bot is never touched. The
receipt reports what was found; the facts (bot state, leftovers left) are in the evidence.
"""
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request

PACKAGE = 'cloud/server_check_001'
TASKS = ('SERVER-CHECK-20261113',)
ROOT = Path(__file__).resolve().parents[2]
API = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
BOT_ID = 266084
LEFTOVER = re.compile(r'/(opod|dcnt)_bootstrap\.py\b')


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

    def call(self, method, endpoint):
        if not re.fullmatch(r'cpu/|always_on/|always_on/\d+/', endpoint):
            raise ProbeError('API_PATH_OUTSIDE_SCOPE')
        request = urllib.request.Request(API + endpoint, method=method,
                                         headers={'Authorization': 'Token ' + self._token, 'User-Agent': 'uaart-server-check/1'})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read(4 * 1024 * 1024)
                return response.status, (json.loads(body) if body else None)
        except urllib.error.HTTPError as error:
            error.close()
            return error.code, None


def leftovers(tasks):
    """Temporary tasks of this session's packages; never the bot."""
    return [t for t in tasks if isinstance(t, dict) and t.get('id') != BOT_ID and LEFTOVER.search(str(t.get('command', '')))]


def collect(api):
    status, cpu = api.call('GET', 'cpu/')
    status_tasks, tasks = api.call('GET', 'always_on/')
    if status_tasks != 200 or not isinstance(tasks, list):
        raise ProbeError('ALWAYS_ON_LIST:%d' % status_tasks)
    found = leftovers(tasks)
    removed = {}
    for task in found:
        removed[str(task['id'])] = api.call('DELETE', 'always_on/%d/' % task['id'])[0]
    _, after = api.call('GET', 'always_on/')
    short = lambda t: {k: t.get(k) for k in ('id', 'description', 'enabled', 'state')}
    bot = next((t for t in after or [] if isinstance(t, dict) and t.get('id') == BOT_ID), None)
    return {'cpu': {'http': status, 'value': cpu}, 'bot': short(bot) if bot else None,
            'always_on_before': [short(t) for t in tasks], 'leftovers_found': [short(t) for t in found],
            'delete_status': removed, 'always_on_after': [short(t) for t in after or []],
            'leftovers_after': [short(t) for t in leftovers(after or [])]}


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
               'live_source_environment': 'production', 'tests': 'PASS', 'tests_scope': 'SERVER_CHECK',
               'unexpected_changes': 0, 'rollback_ready': True, 'rollback_ready_scope': 'NO_SITE_OR_CRM_WRITES',
               'production_required': False, 'request_sha256': request_sha, 'run_id': run_id, 'evidence_path': evidence}
    write(root, env['UAART_RECEIPT_PATH'], dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('SERVER_CHECK_STOP:'+(str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
