#!/usr/bin/env python3
"""Write tasks/requests/ADS-BULK-<suffix>.json and its launch marker (run from the repository root).

Usage: python3 cloud/ads_bulk_001/make_request.py request 20261025[-R2]   # after merge to main:
       python3 cloud/ads_bulk_001/make_request.py launch 20261025[-R2]
       python3 cloud/ads_bulk_001/make_request.py request 20261128-BIG --limit 12000   # one big run (Basic access)
"""
import argparse
import datetime
import hashlib
import json

P = 'cloud/ads_bulk_001/'
DEPENDENCIES = [P + 'source_remote.py', P + 'source_check.py', P + 'plan.py', P + 'keywords.py', P + 'keywords_jpus.py', P + 'usa.py', P + 'bootstrap.py', P + 'make_request.py', P + 'transport.py']
TESTS = [P + 'test_ads_bulk.py']


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def request(day, limit=None):
    task = 'ADS-BULK-' + day
    value = {
        'ai_requested': False, 'changed_paths': [P + day + '.json'], 'complexity': 1, 'control_plane_version': 'TASK107-R2',
        'description': 'Owner 2026-11-26 via the coordinator («поисковых запросов 5000 …»; «Все да» to «model + year from Korea», '
                       '«да» in this chat). Bounded run in the existing private inbox: upload this package, run source_remote.py '
                       'once in a temporary always-on task (removed after its receipt; never the CRM bot) which keeps the click '
                       'ceiling at 4,55 UAH, adds negative phrases, the missing brand and auction groups (one ad each, to the '
                       '«під ключ» or auction lots page) and tonight\'s part (up to 2 400) of the generated buyer keywords uk + '
                       'ru (phrase, partialFailure, nothing twice); budget unchanged. Owner 2026-11-28 «да»: the same for '
                       'the existing campaign «Пошук — США (UA ART)» (up to 40 new groups a night with one ad each to '
                       'usa.html, then its keywords); tonight\'s 2 400 shared 1 200 + 1 200, all to one country when the '
                       'other has nothing left; its budget, ceiling and negatives unchanged. No site, CRM or bot change.',
        'execution': {'controller_path': P + 'controller.py', 'controller_sha256': sha(P + 'controller.py'),
                      'dependency_paths': DEPENDENCIES, 'evidence_paths': [P + day + '.json', 'state/receipts/%s.json' % task],
                      'file_sha256': {f: sha(f) for f in DEPENDENCIES + TESTS}, 'production_required': False,
                      'receipt_path': 'state/receipts/%s.json' % task, 'test_paths': TESTS, 'timeout_seconds': 900},
        'production_required': False, 'read_only': False, 'requested_min_class': 'STANDARD',
        'storage_required_bytes': 33554432, 'task_id': task, 'title': 'Google Ads bulk keywords Korea + USA, 4,55 UAH'}
    if limit is not None:
        if not 1 <= limit <= 12000:
            raise SystemExit('LIMIT')
        value['keyword_limit'] = limit
        value['title'] += ', %d keywords at once' % limit
        value['description'] += (' Basic access (15 000 operations a day): this run\'s limit is %d keywords (keyword_limit), '
                                 'shared by the same rule, and all missing USA groups with their ad are created now; a '
                                 'quota answer from Google stops sending at once (PASS_PARTIAL, EXPLORER_LIMIT_REACHED). '
                                 'Japan not included.' % limit)
    path = 'tasks/requests/%s.json' % task
    with open(path, 'x') as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(',', ':')))
    return path


def launch(day):
    task = 'ADS-BULK-' + day
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
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('request', 'launch'))
    parser.add_argument('day')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    print(request(args.day, args.limit) if args.action == 'request' else launch(args.day))
