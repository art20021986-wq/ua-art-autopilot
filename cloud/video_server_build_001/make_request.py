#!/usr/bin/env python3
"""Write tasks/requests/VIDEO-SERVER-BUILD-<suffix>.json and its launch marker (run from the repository root).

Usage: python3 cloud/video_server_build_001/make_request.py request 20261025[-R2]   # after merge to main:
       python3 cloud/video_server_build_001/make_request.py launch 20261025[-R2]
"""
import datetime
import hashlib
import json
import sys

P = 'cloud/video_server_build_001/'
DEPENDENCIES = [P + 'source_remote.py', P + 'bootstrap.py', P + 'make_request.py', P + 'transport.py']
TESTS = [P + 'test_video_server_build.py']


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def request(day):
    task = 'VIDEO-SERVER-BUILD-' + day
    value = {
        'ai_requested': False, 'changed_paths': [P + day + '.json'], 'complexity': 1, 'control_plane_version': 'TASK107-R2',
        'description': 'VIDEO-LIMIT-001 stage A (owner 2026-11-19 «1 да»: build the official Telegram Bot API server on the '
                       'host; bot and site untouched). Bounded, resumable run in the existing private inbox: upload this package, '
                       'run source_remote.py once in a temporary always-on task (removed after its receipt; never the CRM bot) which, '
                       'inside the inbox folder videobuild_work only, builds gperf 3.1 (GNU tarball, sha256 checked) and '
                       'tdlib/telegram-bot-api at a pinned commit with cmake, one thread, lowest priority, at most 40 minutes per run '
                       '(the next run continues), and reports progress, disk use and the built program version. No application '
                       'source, CRM, HTML, media, bot state or Telegram change; nothing outside the inbox is written.',
        'execution': {'controller_path': P + 'controller.py', 'controller_sha256': sha(P + 'controller.py'),
                      'dependency_paths': DEPENDENCIES, 'evidence_paths': [P + day + '.json', 'state/receipts/%s.json' % task],
                      'file_sha256': {f: sha(f) for f in DEPENDENCIES + TESTS}, 'production_required': False,
                      'receipt_path': 'state/receipts/%s.json' % task, 'test_paths': TESTS, 'timeout_seconds': 3600},
        'production_required': False, 'read_only': False, 'requested_min_class': 'STANDARD',
        'storage_required_bytes': 1073741824, 'task_id': task, 'title': 'Video server build'}
    path = 'tasks/requests/%s.json' % task
    with open(path, 'x') as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(',', ':')))
    return path


def launch(day):
    task = 'VIDEO-SERVER-BUILD-' + day
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
