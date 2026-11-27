#!/usr/bin/env python3
"""ADS-USA: the USA campaign, 50 UAH/day, 2 UAH ceiling, Search only; never twice."""
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
        self.campaigns = {'Пошук — Україна — Корея (UA ART)': 'ENABLED'}
        self.calls = []

    def __call__(self, request, timeout=None):
        if request.full_url == remote.check.TOKEN_ENDPOINT:
            return Response(json.dumps({'access_token': 'ya' + '29.' + 'a' * 30}).encode())
        body = json.loads(request.data)
        self.calls.append((request.full_url, body))
        if request.full_url.endswith('googleAds:mutate'):
            for op in body['mutateOperations']:
                if 'campaignOperation' in op:
                    c = op['campaignOperation']['create']
                    self.campaigns[c['name']] = c['status']
            return Response(b'{}')
        q = body['query']
        if 'FROM campaign_criterion' in q:
            rows = [{'campaignCriterion': {'type': 'LOCATION', 'negative': False,
                                           'location': {'geoTargetConstant': 'geoTargetConstants/21118'}}},
                    {'campaignCriterion': {'type': 'LANGUAGE', 'language': {'languageConstant': 'languageConstants/1036'}}},
                    {'campaignCriterion': {'type': 'AD_SCHEDULE', 'adSchedule': {'dayOfWeek': 'MONDAY', 'startHour': 9,
                                                                                 'endHour': 24}}},
                    {'campaignCriterion': {'type': 'KEYWORD', 'negative': True,
                                           'keyword': {'text': 'olx', 'matchType': 'PHRASE'}}}]
        elif "campaign.name = 'Пошук — США (UA ART)'" in q:
            rows = [{'campaign': {'name': remote.NAME}}] if remote.NAME in self.campaigns else []
        else:
            rows = [{'campaign': {'name': n, 'status': s}, 'campaignBudget': {'amountMicros': '1'}}
                    for n, s in sorted(self.campaigns.items())]
        return Response(json.dumps({'results': rows}).encode())


class RemoteTests(unittest.TestCase):
    def keys_file(self, temp):
        path = Path(temp) / 'keys.json'
        path.write_text(json.dumps(KEYS))
        return path

    def test_campaign_once(self):
        google = Google()
        with tempfile.TemporaryDirectory() as temp:
            first = json.loads(remote.report(self.keys_file(temp), google))
            second = json.loads(remote.report(self.keys_file(temp), google))
        self.assertEqual((first['status'], second['status']), ('PASS', 'ALREADY_THERE'))
        self.assertEqual(first['copied'], {'location': 1, 'language': 1, 'adSchedule': 1, 'keyword': 1})
        mutates = [b for u, b in google.calls if u.endswith(':mutate')]
        self.assertEqual(len(mutates), 1)
        self.assertNotIn('partialFailure', mutates[0])
        ops = mutates[0]['mutateOperations']
        camp = [o['campaignOperation']['create'] for o in ops if 'campaignOperation' in o][0]
        self.assertEqual((camp['targetSpend'], camp['networkSettings']['targetContentNetwork'],
                          camp['networkSettings']['targetSearchNetwork']),
                         ({'cpcBidCeilingMicros': '2000000'}, False, False))
        budget = [o['campaignBudgetOperation']['create'] for o in ops if 'campaignBudgetOperation' in o][0]
        self.assertEqual(budget['amountMicros'], '50000000')
        self.assertFalse([o for o in ops if 'update' in json.dumps(o)[:40]])

    def test_texts_within_limits(self):
        for name, head, desc, words in remote.GROUPS:
            self.assertTrue(3 <= len(head) <= 15 and all(len(h) <= 30 for h in head), name)
            self.assertTrue(2 <= len(desc) <= 4 and all(len(d) <= 90 for d in desc), name)
            self.assertFalse([h for h in head + desc if 'IAAI' in h or 'Ставка' in h])
            self.assertEqual(len(words), len(set(words)))


class FakeAPI:
    def run(self, mode, run_id, bundle):
        return {'status': 'PASS'}


class ControllerTests(unittest.TestCase):
    TASK = 'ADS-USA-20261127'

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
        self.assertEqual(receipt['evidence_path'], 'cloud/ads_usa_001/20261127.json')


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_own_prefix(self):
        self.assertIn('adsusa-', Path(transport.__file__).read_text())

    def test_bundle_names(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
