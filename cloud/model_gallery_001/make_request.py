#!/usr/bin/env python3
"""Write tasks/requests/MODEL-GALLERY-<KIND>-<suffix>.json and its launch marker (run from the repository root).

Usage: python3 cloud/model_gallery_001/make_request.py request collect|search|years|angles|w245|fetch 20261026   # after merge:
       python3 cloud/model_gallery_001/make_request.py launch collect|search|years|angles|w245|fetch 20261026
"""
import datetime
import hashlib
import json
import sys

P = 'cloud/model_gallery_001/'
# kind -> (task prefix, controller, evidence file prefix, description)
KINDS = {
    'collect': ('MODEL-GALLERY-COLLECT-', 'collect.py', 'candidates_',
                'starting from each model\'s current main photo file and its categories'),
    'search': ('MODEL-GALLERY-SEARCH-', 'search.py', 'search_',
               'file searches by model name and generation for interior and rear photos'),
    'years': ('MODEL-GALLERY-YEARS-', 'years.py', 'years_',
              'file searches for exterior, interior and trunk photos of 2018-2023 cars only'),
    'angles': ('MODEL-GALLERY-ANGLES-', 'angles.py', 'angles_',
               'file searches per owner view (front/rear 3/4 left and right, dashboard driver and passenger side, '
               'rear seats, boot) for 2018-2023 cars only'),
    'w245': ('MODEL-GALLERY-W245-', 'w245.py', 'w245_',
             'file searches per owner view for the Japan Mercedes-Benz B-Class card as a W245 of 2010-2011 '
             '(facelift 2008-2011 years only)'),
    'fetch': ('MODEL-GALLERY-FETCH-', 'fetch.py', 'photos_',
              'download 960 px wide of the photos picked by eye (picks.py), licence checked again'),
}
MODULES = ['collect.py', 'search.py', 'years.py', 'angles.py', 'w245.py', 'fetch.py', 'make_request.py', 'picks.py',
           'picks_w245.py']
TESTS = [P + 'test_collect.py', P + 'test_search.py', P + 'test_years.py', P + 'test_angles.py', P + 'test_w245.py',
         P + 'test_fetch.py']
GROUPS = ('canada', 'china', 'europe', 'georgia', 'japan', 'korea', 'usa')


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def request(kind, day):
    prefix, controller, stem, how = KINDS[kind]
    task = prefix + day
    controller = P + controller
    dependencies = [P + name for name in MODULES if P + name != controller]
    stem = {'20261026-R2': 'photos2_', '20261027': 'photos3_', '20261027-R2': 'photos4_',
            '20261030': 'photos5_'}.get(day, stem) if kind == 'fetch' else stem
    stem = {'20261030-R2': 'w245r2_', '20261030-R3': 'w245r3_'}.get(day, stem) if kind == 'w245' else stem
    # The W245 search and its fetch cover one Japan card only.
    one_card = kind == 'w245' or stem == 'photos5_'
    evidence = [P + stem + '%s.json' % group for group in (('japan',) if one_card else GROUPS)]
    value = {
        'ai_requested': False, 'changed_paths': evidence, 'complexity': 1, 'control_plane_version': 'TASK107-R2',
        'description': 'Read-only photo candidates for the order page model gallery (owner request 2026-10-26): GET of the '
                       'public Wikimedia Commons API and thumbnails only, ' + how + '; freely licensed files kept with author and licence. No token, no uaart.com.ua '
                       'request, no source, CRM, HTML, media or bot change.',
        'execution': {'controller_path': controller, 'controller_sha256': sha(controller), 'dependency_paths': dependencies,
                      'evidence_paths': evidence + ['state/receipts/%s.json' % task],
                      'file_sha256': {f: sha(f) for f in TESTS + dependencies}, 'production_required': False,
                      'receipt_path': 'state/receipts/%s.json' % task, 'test_paths': TESTS, 'timeout_seconds': 3600 if kind == 'angles' else 2400},
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
