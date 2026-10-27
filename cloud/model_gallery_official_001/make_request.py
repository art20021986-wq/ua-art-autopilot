#!/usr/bin/env python3
"""Write tasks/requests/MODEL-GALLERY-<KIND>-<suffix>.json and its launch marker (run from the repository root).

Usage: python3 cloud/model_gallery_official_001/make_request.py request discover|candidates|archive 20261026   # after merge to main:
       python3 cloud/model_gallery_official_001/make_request.py launch discover|candidates|archive 20261026
"""
import datetime
import hashlib
import json
import sys

P = 'cloud/model_gallery_official_001/'
# kind -> (task prefix, controller, evidence file prefix, description)
KINDS = {
    'discover': ('MODEL-GALLERY-DISCOVER-', 'discover.py', 'discover_',
                 'bounded crawl of the manufacturers\' official press and model pages for each model\'s photo gallery '
                 '(pages and image addresses only, no image download)'),
    'candidates': ('MODEL-GALLERY-CANDIDATES-', 'candidates.py', 'candidates_',
                   'download of the official photo series listed in sources.py (manufacturers\' image stores only) and '
                   'the text of their press pages'),
    'archive': ('MODEL-GALLERY-ARCHIVE-', 'archive.py', 'archive_',
                'bounded crawl of the brands\' press and model archives in several countries for 2018-2023 photos, '
                'download of the matching photos from the brands\' image hosts'),
}
MODULES = ['discover.py', 'candidates.py', 'sources.py', 'archive.py', 'make_request.py']
TESTS = [P + 'test_discover.py', P + 'test_candidates.py', P + 'test_archive.py']
GROUPS = ('canada', 'china', 'europe', 'georgia', 'japan', 'korea', 'usa')


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def request(kind, day):
    prefix, controller, stem, how = KINDS[kind]
    task = prefix + day
    controller = P + controller
    dependencies = [P + name for name in MODULES if P + name != controller]
    sys.path.insert(0, P)
    from sources import SOURCES
    import archive
    names = sorted(SOURCES) if kind == 'candidates' else archive.part_keys(day[-1]) if kind == 'archive' else GROUPS
    evidence = [P + stem + '%s.json' % name for name in names]
    value = {
        'ai_requested': False, 'changed_paths': evidence, 'complexity': 1, 'control_plane_version': 'TASK107-R2',
        'description': 'Read-only photo candidates for the order page model gallery (owner request 2026-10-26): GET of the '
                       'public official manufacturer sites only, ' + how + '. No token, no uaart.com.ua '
                       'request, no source, CRM, HTML, media or bot change.',
        'execution': {'controller_path': controller, 'controller_sha256': sha(controller), 'dependency_paths': dependencies,
                      'evidence_paths': evidence + ['state/receipts/%s.json' % task],
                      'file_sha256': {f: sha(f) for f in TESTS + dependencies}, 'production_required': False,
                      'receipt_path': 'state/receipts/%s.json' % task, 'test_paths': TESTS, 'timeout_seconds': 3600},
        'production_required': False, 'read_only': True, 'requested_min_class': 'STANDARD',
        'storage_required_bytes': 268435456, 'task_id': task, 'title': 'Model gallery photo candidates'}
    path = 'tasks/requests/%s.json' % task
    with open(path, 'x') as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(',', ':')))
    return path


def launch(kind, day):
    task = KINDS[kind][0] + day
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
    print((request if sys.argv[1] == 'request' else launch)(sys.argv[2], sys.argv[3]))
