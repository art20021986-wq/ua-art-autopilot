#!/usr/bin/env python3
"""ADS-EXPAND: ceiling 7 UAH, extra keywords to the hub groups, two new groups; nothing twice; texts within limits."""
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402
import source_remote as remote  # noqa: E402
import transport  # noqa: E402

KEYS = {'developer_token': 'DEVTOKEN' + 'x' * 14, 'client_id': '1' * 12 + '-abc.apps.' + 'googleusercontent.com',
        'client_secret': 'GOC' + 'SPX-' + 'q' * 28, 'refresh_token': '1//' + 'r' * 40,
        'login_customer_id': '9054959760', 'customer_id': '4680747874'}


class Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Google:
    def __init__(self):
        self.campaign = {'resourceName': 'customers/1/campaigns/9', 'targetSpend': {'cpcBidCeilingMicros': '15000000'}}
        self.groups = {'UA — Корея під ключ': 'customers/1/adGroups/1', 'RU — Корея под ключ': 'customers/1/adGroups/2'}
        self.keywords = {('UA — Корея під ключ', 'авто з кореї', 'PHRASE')}
        self.calls = []

    def name(self, resource):
        return next(n for n, r in self.groups.items() if r == resource)

    def __call__(self, request, timeout=None):
        if request.full_url == remote.check.TOKEN_ENDPOINT:
            return Response(json.dumps({'access_token': 'ya' + '29.' + 'a' * 30}).encode())
        body = json.loads(request.data)
        self.calls.append((request.full_url, body))
        if request.full_url.endswith('googleAds:mutate'):
            temp = {}
            for op in body['mutateOperations']:
                if 'campaignOperation' in op:
                    self.campaign['targetSpend'] = op['campaignOperation']['update']['targetSpend']
                elif 'adGroupOperation' in op:
                    new = op['adGroupOperation']['create']
                    temp[new['resourceName']] = 'customers/1/adGroups/%d' % (10 + len(self.groups))
                    self.groups[new['name']] = temp[new['resourceName']]
                elif 'adGroupCriterionOperation' in op:
                    k = op['adGroupCriterionOperation']['create']
                    group = temp.get(k['adGroup'], k['adGroup'])
                    self.keywords.add((self.name(group), k['keyword']['text'], k['keyword']['matchType']))
            return Response(b'{}')
        query = body['query']
        if 'FROM ad_group_criterion' in query:
            return Response(json.dumps({'results': [{'adGroup': {'name': g}, 'adGroupCriterion': {'keyword': {
                'text': t, 'matchType': m}}} for g, t, m in self.keywords]}).encode())
        if 'FROM ad_group ' in query:
            return Response(json.dumps({'results': [{'adGroup': {'name': n, 'resourceName': r}}
                                                    for n, r in self.groups.items()]}).encode())
        return Response(json.dumps({'results': [{'campaign': self.campaign}]}).encode())


class RemoteTests(unittest.TestCase):
    def keys_file(self, temp):
        path = Path(temp) / 'keys.json'
        path.write_text(json.dumps(KEYS))
        return path

    def test_expand_once(self):
        google = Google()
        with tempfile.TemporaryDirectory() as temp:
            first = json.loads(remote.report(self.keys_file(temp), google))
            second = json.loads(remote.report(self.keys_file(temp), google))
        self.assertEqual((first['status'], first['left'], second['operation_count']), ('PASS', 0, 0))
        self.assertEqual(first['after']['ceiling'], {'cpcBidCeilingMicros': '7000000'})
        self.assertIn('UA — Будь-яка модель з Кореї', first['after']['groups'])
        body = [b for u, b in google.calls if u.endswith(':mutate')][0]
        self.assertTrue(body['partialFailure'])
        texts = [o['adGroupCriterionOperation']['create']['keyword']['text'] for o in body['mutateOperations']
                 if 'adGroupCriterionOperation' in o]
        self.assertEqual(texts.count('авто з кореї'), 0)  # already there
        self.assertEqual(len(texts), len(set((t, i % 2) for i, t in enumerate(texts))))

    def test_texts_within_limits(self):
        for group in remote.NEW_GROUPS:
            self.assertLessEqual(len(group['headlines']), 15)
            self.assertEqual(len(group['headlines']), len(set(group['headlines'])))
            self.assertTrue(all(len(h) <= 30 for h in group['headlines']))
            self.assertTrue(all(len(k) <= 80 and len(k.split()) <= 10 for k in group['keywords']))
            self.assertFalse(any('LPi' in h or 'AUTO.RIA' in h or 'Отримайте пропозицію' in h for h in group['headlines']))


class FakeAPI:
    def run(self, mode, run_id, bundle):
        return {'status': 'PASS'}


class ControllerTests(unittest.TestCase):
    TASK = 'ADS-EXPAND-20261126'

    def test_report_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = root / 'tasks/requests' / (self.TASK + '.json')
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'production_required': False}))
            env = {'UAART_TASK_ID': self.TASK, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % self.TASK,
                   'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % self.TASK,
                   'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '7'}
            receipt = c.execute(env, root=temp, api=FakeAPI(), upload=lambda a: 'b' * 64)
        self.assertEqual(receipt['evidence_path'], 'cloud/ads_expand_001/20261126.json')


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_own_prefix(self):
        self.assertIn('adsexpand-', Path(transport.__file__).read_text())

    def test_bundle_names(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
