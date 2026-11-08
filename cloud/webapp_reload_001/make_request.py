#!/usr/bin/env python3
"""Write tasks/requests/WEBAPP-RELOAD-<suffix>.json and its launch marker (run from the repository root).

Usage: python3 cloud/webapp_reload_001/make_request.py request 20261108   # after merge to main:
       python3 cloud/webapp_reload_001/make_request.py launch 20261108
"""
import datetime
import hashlib
import json
import sys

P = 'cloud/webapp_reload_001/'
DEPENDENCIES = [P + 'make_request.py']
TESTS = [P + 'test_reload.py']


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def request(day):
    task = 'WEBAPP-RELOAD-' + day
    value = {
        'ai_requested': False, 'changed_paths': [P + day + '.json'], 'complexity': 1, 'control_plane_version': 'TASK107-R2',
        'description': 'Finish OWN-COUNTER-INSTALL-20261107 (owner «Да» 2026-11-07; halt lifted on owner permission '
                       '2026-11-08): all planned files are installed (ANALYTICS-AUDIT-PROBE-20261108: hashes equal the '
                       'plan) but the install stopped before its web app reload, so /ua/a.js still serves the old script. '
                       'Reload the web app once and read the public script until it carries UA-OWN-COUNTER-001. '
                       'No file, CRM, HTML or bot change.',
        'execution': {'controller_path': P + 'controller.py', 'controller_sha256': sha(P + 'controller.py'),
                      'dependency_paths': DEPENDENCIES, 'evidence_paths': [P + day + '.json', 'state/receipts/%s.json' % task],
                      'file_sha256': {f: sha(f) for f in DEPENDENCIES + TESTS}, 'production_required': False,
                      'receipt_path': 'state/receipts/%s.json' % task, 'test_paths': TESTS, 'timeout_seconds': 900},
        'production_required': False, 'read_only': False, 'requested_min_class': 'STANDARD',
        'storage_required_bytes': 33554432, 'task_id': task, 'title': 'Web app reload after own counter install'}
    path = 'tasks/requests/%s.json' % task
    with open(path, 'x') as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(',', ':')))
    return path


def launch(day):
    task = 'WEBAPP-RELOAD-' + day
    path = 'tasks/requests/%s.json' % task
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    stamp = now.strftime('%Y%m%dT%H%M%SZ')
    value = {'action': 'RUN_EXACT_TASK', 'created_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
             'expires_at': (now + datetime.timedelta(minutes=115)).strftime('%Y-%m-%dT%H:%M:%SZ'),
             'mode_epoch': json.load(open('state/EXECUTION_MODE.json'))['mode_epoch'],
             'nonce': (task + '-' + stamp).lower(), 'owner_authorized': True, 'production_allowed': False,
             'request_path': path, 'request_sha256': sha(path), 'schema_version': 'UA-ART-AUTOSTART-LAUNCH-1', 'task_id': task}
    marker = 'tasks/launch/AUTO-%s-%s.json' % (task, stamp)
    with open(marker, 'x') as handle:
        handle.write(json.dumps(value, indent=2, sort_keys=True) + '\n')
    return marker


if __name__ == '__main__':
    print(request(sys.argv[2]) if sys.argv[1] == 'request' else launch(sys.argv[2]))
