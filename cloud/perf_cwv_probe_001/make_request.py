#!/usr/bin/env python3
"""Write tasks/requests/PERF-CWV-PROBE-<suffix>.json and its launch marker (run from the repository root).

Usage: python3 cloud/perf_cwv_probe_001/make_request.py request 20261025[-R2]   # after merge to main:
       python3 cloud/perf_cwv_probe_001/make_request.py launch 20261025[-R2]
"""
import datetime
import hashlib
import json
import sys

P = 'cloud/perf_cwv_probe_001/'
DEPENDENCIES = [P + 'source_remote.py', P + 'bootstrap.py', P + 'make_request.py', P + 'transport.py']
TESTS = [P + 'test_perf_cwv_probe.py']


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def request(day):
    task = 'PERF-CWV-PROBE-' + day
    value = {
        'ai_requested': False, 'changed_paths': [P + day + '.json'], 'complexity': 1, 'control_plane_version': 'TASK107-R2',
        'description': 'Read-only probe for PERF-CWV-001 (owner 2026-11-26: page speed, layout shifts and phone comfort). '
                       'Bounded run in the existing private inbox: upload this package, run source_remote.py once in a '
                       'temporary always-on task (removed after its receipt; never the CRM bot) which reads, read-only: which '
                       'server .py and template files (and usercustomize.py) contain the home Korea ticker, card header style, '
                       'language switcher, card stage labels and catalog photo markers (line numbers), the sanitized full '
                       'source of the most relevant ones, whether Pillow can write WebP, whether ffmpeg exists, and the size '
                       'of video/opt. R2: also the writers of the blocks appended at the end of the cards (UA-BRAND-HOME and others), '
                       'the photo gallery and the callers of ua_korea_home; archive, sandbox and spec_* copies skipped. No CRM read. No source, CRM, HTML, media or bot change.',
        'execution': {'controller_path': P + 'controller.py', 'controller_sha256': sha(P + 'controller.py'),
                      'dependency_paths': DEPENDENCIES, 'evidence_paths': [P + day + '.json', 'state/receipts/%s.json' % task],
                      'file_sha256': {f: sha(f) for f in DEPENDENCIES + TESTS}, 'production_required': False,
                      'receipt_path': 'state/receipts/%s.json' % task, 'test_paths': TESTS, 'timeout_seconds': 900},
        'production_required': False, 'read_only': False, 'requested_min_class': 'STANDARD',
        'storage_required_bytes': 33554432, 'task_id': task, 'title': 'PERF-CWV probe'}
    path = 'tasks/requests/%s.json' % task
    with open(path, 'x') as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(',', ':')))
    return path


def launch(day):
    task = 'PERF-CWV-PROBE-' + day
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
    day = sys.argv[2]
    print(request(day) if action == 'request' else launch(day))
