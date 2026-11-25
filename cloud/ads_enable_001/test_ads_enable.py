#!/usr/bin/env python3
"""ADS-ENABLE: only the Kyiv campaign's budget (300 UAH) and status (ENABLED) change, both verified after."""
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
    def __init__(self, campaigns=1):
        self.row = {'campaign': {'resourceName': 'customers/1/campaigns/9', 'status': 'PAUSED'},
                    'campaignBudget': {'resourceName': 'customers/1/campaignBudgets/8', 'amountMicros': '500000000'}}
        self.campaigns, self.calls = campaigns, []

    def __call__(self, request, timeout=None):
        if request.full_url == remote.check.TOKEN_ENDPOINT:
            return Response(json.dumps({'access_token': 'ya' + '29.' + 'a' * 30}).encode())
        body = json.loads(request.data)
        self.calls.append((request.full_url, body))
        if request.full_url.endswith('googleAds:mutate'):
            for op in body['mutateOperations']:
                if 'campaignOperation' in op:
                    self.row['campaign']['status'] = op['campaignOperation']['update']['status']
                else:
                    self.row['campaignBudget']['amountMicros'] = op['campaignBudgetOperation']['update']['amountMicros']
            return Response(b'{}')
        return Response(json.dumps({'results': [self.row] * self.campaigns}).encode())


class RemoteTests(unittest.TestCase):
    def keys_file(self, temp):
        path = Path(temp) / 'keys.json'
        path.write_text(json.dumps(KEYS))
        return path

    def test_budget_and_status(self):
        google = Google()
        with tempfile.TemporaryDirectory() as temp:
            text = remote.report(self.keys_file(temp), google)
        value = json.loads(text)
        self.assertEqual(value['status'], 'PASS')
        self.assertEqual(value['before']['campaign']['status'], 'PAUSED')
        self.assertEqual((value['after']['campaign']['status'], value['after']['budget']['amountMicros']),
                         ('ENABLED', '300000000'))
        mutate = [b for u, b in google.calls if u.endswith(':mutate')]
        self.assertEqual(len(mutate), 1)
        self.assertNotIn('validateOnly', mutate[0])
        for secret in list(KEYS.values())[:4]:
            self.assertNotIn(secret, text)

    def test_second_run_changes_nothing(self):
        google = Google()
        with tempfile.TemporaryDirectory() as temp:
            remote.report(self.keys_file(temp), google)
            google.calls.clear()
            value = json.loads(remote.report(self.keys_file(temp), google))
        self.assertEqual((value['operations'], value['status']), ([], 'PASS'))

    def test_never_more_than_one_campaign(self):
        with tempfile.TemporaryDirectory() as temp:
            value = json.loads(remote.report(self.keys_file(temp), Google(campaigns=2)))
        self.assertEqual((value['status'], value['error']), ('FAIL', 'CAMPAIGNS_2'))


class FakeAPI:
    def run(self, mode, run_id, bundle):
        return {'status': 'PASS'}


class ControllerTests(unittest.TestCase):
    TASK = 'ADS-ENABLE-20261125'

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
        self.assertEqual(receipt['evidence_path'], 'cloud/ads_enable_001/20261125.json')


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_own_prefix(self):
        self.assertIn('adsenable-', Path(transport.__file__).read_text())

    def test_bundle_names(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
