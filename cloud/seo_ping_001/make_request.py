#!/usr/bin/env python3
"""Write tasks/requests/SEO-PING-20261104.json and its launch marker (run from the repository root).

Usage: python3 cloud/seo_ping_001/make_request.py request   # PR, merge, then:
       python3 cloud/seo_ping_001/make_request.py launch
"""
import datetime
import hashlib
import json
import sys

P = 'cloud/seo_ping_001/'
TASK = 'SEO-PING-20261104'
DEPENDENCIES = [P + 'ping_remote.py', P + 'bootstrap.py', P + 'make_request.py', P + 'transport.py']
TESTS = [P + 'test_seo_ping.py']


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def request():
    value = {
        'ai_requested': False, 'changed_paths': [P + 'report.json'], 'complexity': 1, 'control_plane_version': 'TASK107-R2',
        'description': 'Search engine notice for the two updated finance pages (owner «Да» 2026-11-04, FINANCE-OTP-001/002): '
                       'a bounded run in the existing private inbox (temporary always-on task removed after its receipt; never '
                       'the CRM bot) calls the site\'s own ua_indexnow (the two URLs) and ua_google_sitemap (Search Console '
                       're-reads the sitemap). No source, CRM, HTML, media or bot change.',
        'execution': {'controller_path': P + 'controller.py', 'controller_sha256': sha(P + 'controller.py'),
                      'dependency_paths': DEPENDENCIES, 'evidence_paths': [P + 'report.json', 'state/receipts/%s.json' % TASK],
                      'file_sha256': {f: sha(f) for f in DEPENDENCIES + TESTS}, 'production_required': False,
                      'receipt_path': 'state/receipts/%s.json' % TASK, 'test_paths': TESTS, 'timeout_seconds': 900},
        'production_required': False, 'read_only': False, 'requested_min_class': 'STANDARD',
        'storage_required_bytes': 33554432, 'task_id': TASK, 'title': 'finance pages search engine notice'}
    path = 'tasks/requests/%s.json' % TASK
    with open(path, 'x') as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(',', ':')))
    return path


def launch():
    path = 'tasks/requests/%s.json' % TASK
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    stamp = now.strftime('%Y%m%dT%H%M%SZ')
    value = {'action': 'RUN_EXACT_TASK', 'created_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
             'expires_at': (now + datetime.timedelta(minutes=115)).strftime('%Y-%m-%dT%H:%M:%SZ'),
             'mode_epoch': json.load(open('state/EXECUTION_MODE.json'))['mode_epoch'],
             'nonce': (TASK + '-' + stamp).lower(), 'owner_authorized': True, 'production_allowed': False,
             'request_path': path, 'request_sha256': sha(path), 'schema_version': 'UA-ART-AUTOSTART-LAUNCH-1', 'task_id': TASK}
    marker = 'tasks/launch/AUTO-%s-%s.json' % (TASK, stamp)
    with open(marker, 'x') as handle:
        handle.write(json.dumps(value, indent=2, sort_keys=True) + '\n')
    return marker


if __name__ == '__main__':
    print(request() if sys.argv[1] == 'request' else launch())
