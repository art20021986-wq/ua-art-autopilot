#!/usr/bin/env python3
"""ADS-SCHED: round the clock (the schedule removed), nothing else; never twice."""
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
        self.name = remote.NEW_NAME
        self.slots = {'s/%d' % n: (d, a, b) for n, (d, (a, b)) in enumerate((d, s) for d in remote.DAYS
                                                                             for s in ((9, 24), (0, 2)))}
        self.calls = []

    def __call__(self, request, timeout=None):
        if request.full_url == remote.check.TOKEN_ENDPOINT:
            return Response(json.dumps({'access_token': 'ya' + '29.' + 'a' * 30}).encode())
        body = json.loads(request.data)
        self.calls.append((request.full_url, body))
        if request.full_url.endswith('googleAds:mutate'):
            for op in body['mutateOperations']:
                if 'campaignOperation' in op:
                    self.name = op['campaignOperation']['update']['name']
                elif 'remove' in op['campaignCriterionOperation']:
                    del self.slots[op['campaignCriterionOperation']['remove']]
                else:
                    a = op['campaignCriterionOperation']['create']['adSchedule']
                    self.slots['s/%d' % (len(self.slots) + 100)] = (a['dayOfWeek'], a['startHour'], a['endHour'])
            return Response(b'{}')
        q = body['query']
        if ("'%s'" % self.name) not in q:
            return Response(b'{"results": []}')
        if 'FROM campaign_criterion' in q:
            rows = [{'campaign': {'resourceName': 'c/9', 'name': self.name}, 'campaignCriterion': {
                'resourceName': k, 'adSchedule': {'dayOfWeek': d, 'startHour': a, 'endHour': b}}} for k, (d, a, b) in self.slots.items()]
        else:
            rows = [{'campaign': {'resourceName': 'c/9', 'name': self.name, 'status': 'ENABLED'}}]
        return Response(json.dumps({'results': rows}).encode())


class RemoteTests(unittest.TestCase):
    def keys_file(self, temp):
        path = Path(temp) / 'keys.json'
        path.write_text(json.dumps(KEYS))
        return path

    def test_schedule_and_name_once(self):
        google = Google()
        with tempfile.TemporaryDirectory() as temp:
            first = json.loads(remote.report(self.keys_file(temp), google))
            second = json.loads(remote.report(self.keys_file(temp), google))
        self.assertEqual((first['status'], second['status'], second['operations']), ('PASS', 'PASS', 0))
        self.assertEqual(first['after']['name'], remote.NEW_NAME)
        self.assertEqual((len(first['before']['slots']), first['after']['slots']), (14, []))
        body = [b for u, b in google.calls if u.endswith(':mutate')][0]
        self.assertTrue(all('remove' in o['campaignCriterionOperation'] for o in body['mutateOperations']))
        self.assertEqual(len([u for u, _ in google.calls if u.endswith(':mutate')]), 1)
        body = [b for u, b in google.calls if u.endswith(':mutate')][0]
        self.assertFalse([o for o in body['mutateOperations'] if 'campaignBudgetOperation' in o])


class FakeAPI:
    def run(self, mode, run_id, bundle):
        return {'status': 'PASS'}


class ControllerTests(unittest.TestCase):
    TASK = 'ADS-SCHED-20261126'

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
        self.assertEqual(receipt['evidence_path'], 'cloud/ads_schedule_001/20261126.json')


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_own_prefix(self):
        self.assertIn('adssched-', Path(transport.__file__).read_text())

    def test_bundle_names(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
