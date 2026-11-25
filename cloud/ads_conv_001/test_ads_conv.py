#!/usr/bin/env python3
"""ADS-CONV: only the two lead actions change, validate-only by default, before-state kept, no key in the report."""
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
ACCESS = 'ya' + '29.' + 'a' * 40
R = 'customers/4680747874/conversionActions/'
ROWS = [
    {'resourceName': R + '1', 'name': 'UA ART (web) generate_lead', 'status': 'HIDDEN',
     'type': 'GOOGLE_ANALYTICS_4_GENERATE_LEAD', 'countingType': 'MANY_PER_CLICK'},
    {'resourceName': R + '2', 'name': 'UA ART (web) contact', 'status': 'HIDDEN', 'type': 'GOOGLE_ANALYTICS_4_CUSTOM',
     'countingType': 'MANY_PER_CLICK'},
    {'resourceName': R + '3', 'name': 'UA ART (web) purchase', 'status': 'HIDDEN', 'type': 'GOOGLE_ANALYTICS_4_PURCHASE'},
    {'resourceName': R + '4', 'name': 'Other custom', 'status': 'HIDDEN', 'type': 'GOOGLE_ANALYTICS_4_CUSTOM'},
]


class Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Google:
    def __init__(self, saves=True):
        self.rows, self.calls, self.saves = json.loads(json.dumps(ROWS)), [], saves

    def __call__(self, request, timeout=None):
        body = json.loads(request.data) if request.data and request.full_url != remote.check.TOKEN_ENDPOINT else None
        self.calls.append((request.full_url, body))
        if request.full_url == remote.check.TOKEN_ENDPOINT:
            return Response(json.dumps({'access_token': ACCESS}).encode())
        if request.full_url.endswith('conversionActions:mutate'):
            if self.saves and not body['validateOnly']:
                for op in body['operations']:
                    row = next(r for r in self.rows if r['resourceName'] == op['update']['resourceName'])
                    row.update({k: v for k, v in op['update'].items() if k != 'resourceName'})
            return Response(json.dumps({'results': [{'resourceName': o['update']['resourceName']}
                                                    for o in body['operations']]}).encode())
        return Response(json.dumps({'results': [{'conversionAction': r} for r in self.rows]}).encode())


class RemoteTests(unittest.TestCase):
    def keys_file(self, temp):
        path = Path(temp) / 'keys.json'
        path.write_text(json.dumps(KEYS))
        return path

    def test_validate_only(self):
        self.assertTrue(remote.APPLY)  # R2: saved
        google = Google()
        with tempfile.TemporaryDirectory() as temp:
            text = remote.report(self.keys_file(temp), apply=False, opener=google)
        value = json.loads(text)
        mutate = [b for u, b in google.calls if u.endswith(':mutate')]
        self.assertEqual(len(mutate), 1)
        self.assertTrue(mutate[0]['validateOnly'])
        self.assertEqual(value['status'], 'PASS')
        self.assertEqual(value['after'], ROWS)  # nothing saved
        for secret in list(KEYS.values())[:4] + [ACCESS]:
            self.assertNotIn(secret, text)

    def test_apply_changes_only_the_two_lead_actions(self):
        google = Google()
        with tempfile.TemporaryDirectory() as temp:
            value = json.loads(remote.report(self.keys_file(temp), apply=True, opener=google))
        ops = [b for u, b in google.calls if u.endswith(':mutate')][0]
        self.assertFalse(ops['validateOnly'])
        self.assertEqual([o['update']['resourceName'] for o in ops['operations']], [R + '1', R + '2'])
        self.assertEqual(ops['operations'][0]['updateMask'], 'primary_for_goal,status')
        self.assertEqual(ops['operations'][1]['update'], {'resourceName': R + '2', 'status': 'ENABLED'})
        self.assertEqual((value['status'], value['left'], value['before']), ('PASS', [], ROWS))
        after = {r['resourceName']: r for r in value['after']}
        self.assertEqual((after[R + '1']['status'], after[R + '1']['primaryForGoal']), ('ENABLED', True))
        self.assertEqual(after[R + '3']['status'], 'HIDDEN')
        self.assertEqual(after[R + '4']['status'], 'HIDDEN')

    def test_second_apply_is_a_no_op(self):
        google = Google()
        with tempfile.TemporaryDirectory() as temp:
            remote.report(self.keys_file(temp), apply=True, opener=google)
            google.calls.clear()
            value = json.loads(remote.report(self.keys_file(temp), apply=True, opener=google))
        self.assertEqual((value['operations'], value['status']), ([], 'PASS'))
        self.assertFalse([u for u, _ in google.calls if u.endswith(':mutate')])

    def test_not_saved_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            value = json.loads(remote.report(self.keys_file(temp), apply=True, opener=Google(saves=False)))
        self.assertEqual(value['status'], 'NOT_APPLIED')

    def test_no_campaign_or_budget_call(self):
        text = Path(remote.__file__).read_text()
        self.assertNotIn('campaigns:mutate', text)
        self.assertNotIn('campaignBudgets', text)


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'ADS-CONV-20261125'

    def test_report_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = root / 'tasks/requests' / (self.TASK + '.json')
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'production_required': False}))
            env = {'UAART_TASK_ID': self.TASK, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % self.TASK,
                   'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % self.TASK,
                   'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '7'}
            receipt = c.execute(env, root=temp, api=FakeAPI({'status': 'PASS'}), upload=lambda a: 'b' * 64)
        self.assertEqual(receipt['evidence_path'], 'cloud/ads_conv_001/20261125.json')


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_own_server_prefix(self):
        text = Path(transport.__file__).read_text() + Path(__file__).with_name('bootstrap.py').read_text()
        self.assertIn('adsconv-', text)
        self.assertNotIn('adscheck', text)

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
