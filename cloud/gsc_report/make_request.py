#!/usr/bin/env python3
"""Write tasks/requests/GSC-REPORT-<date>.json and its launch marker (run from the repository root).

Usage: python3 cloud/gsc_report/make_request.py request [YYYYMMDD]   # after merge to main:
       python3 cloud/gsc_report/make_request.py launch YYYYMMDD
"""
import datetime
import hashlib
import json
import sys

P = 'cloud/gsc_report/'
DEPENDENCIES = [P + 'bootstrap.py', P + 'gsc_remote.py', P + 'transport.py']
TESTS = [P + 'test_gsc_report.py']


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def request(day):
    task = 'GSC-REPORT-' + day
    value = {
        'ai_requested': False, 'changed_paths': [P + day + '.json'], 'complexity': 1, 'control_plane_version': 'TASK107-R2',
        'description': 'Weekly Search Console report (owner request 2026-10-20). Bounded run in the existing private inbox: '
                       'upload this package, run gsc_remote.py once in a temporary always-on task (removed after its receipt; '
                       'never the CRM bot) which reads the server-held service account key and only GETs/queries Search Console '
                       '(permission, sitemaps, top queries/pages for 28 days, index status of every sitemap page). The key never '
                       'leaves the server; the report is checked for key material. No source, CRM, HTML, media or bot change.',
        'execution': {'controller_path': P + 'controller.py', 'controller_sha256': sha(P + 'controller.py'),
                      'dependency_paths': DEPENDENCIES, 'evidence_paths': [P + day + '.json', 'state/receipts/%s.json' % task],
                      'file_sha256': {f: sha(f) for f in DEPENDENCIES + TESTS}, 'production_required': False,
                      'receipt_path': 'state/receipts/%s.json' % task, 'test_paths': TESTS, 'timeout_seconds': 900},
        'production_required': False, 'read_only': False, 'requested_min_class': 'STANDARD',
        'storage_required_bytes': 33554432, 'task_id': task, 'title': 'Weekly Search Console report'}
    path = 'tasks/requests/%s.json' % task
    with open(path, 'x') as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(',', ':')))
    return path


def launch(day):
    task = 'GSC-REPORT-' + day
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
    action = sys.argv[1]
    day = sys.argv[2] if len(sys.argv) > 2 else datetime.date.today().strftime('%Y%m%d')
    print(request(day) if action == 'request' else launch(day))
