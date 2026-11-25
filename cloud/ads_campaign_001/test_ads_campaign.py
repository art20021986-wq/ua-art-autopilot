#!/usr/bin/env python3
"""ADS-CAMP: the campaign is PAUSED, Kyiv only, texts within Google limits, validate-only by default, never twice."""
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
import plan  # noqa: E402
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
    def __init__(self, existing=()):
        self.existing, self.calls = list(existing), []

    def __call__(self, request, timeout=None):
        if request.full_url == remote.check.TOKEN_ENDPOINT:
            return Response(json.dumps({'access_token': 'ya' + '29.' + 'a' * 30}).encode())
        body = json.loads(request.data)
        self.calls.append((request.full_url, body))
        if request.full_url.endswith('googleAds:mutate'):
            if not body['validateOnly']:
                self.existing.append({'resourceName': 'customers/1/campaigns/9', 'status': 'PAUSED'})
            return Response(json.dumps({'mutateOperationResponses': [{} for _ in body['mutateOperations']]}).encode())
        return Response(json.dumps({'results': [{'campaign': x} for x in self.existing]}).encode())


class PlanTests(unittest.TestCase):
    def test_flagged_pair_absent(self):
        for group in plan.groups():
            self.assertFalse('Отримайте пропозицію' in group['headlines']
                             and any(d.startswith('Залиште заявку') for d in group['descriptions']), group['name'])
            self.assertFalse(any('LPi' in t or 'AUTO.RIA' in t for t in group['headlines'] + group['descriptions']))

    def test_text_limits(self):
        for group in plan.groups():
            self.assertTrue(3 <= len(group['headlines']) <= 15, group['name'])
            self.assertTrue(2 <= len(group['descriptions']) <= 4)
            self.assertEqual(len(set(group['headlines'])), len(group['headlines']), group['name'])
            for h in group['headlines']:
                self.assertLessEqual(len(h), 30, h)
            for d in group['descriptions']:
                self.assertLessEqual(len(d), 90, d)
            self.assertTrue(all(len(p) <= 15 for p in group['path']), group['path'])
            self.assertTrue(group['url'].startswith(plan.SITE))
            self.assertTrue(all(len(k.split()) <= 10 and len(k) <= 80 for k in group['keywords']))
        for text, d1, d2, _ in plan.SITELINKS:
            self.assertTrue(len(text) <= 25 and len(d1) <= 35 and len(d2) <= 35, text)
        self.assertTrue(all(len(t) <= 25 for t in plan.CALLOUTS))

    def test_every_landing_page_is_live_list(self):
        urls = {g['url'] for g in plan.groups()} | {s[3] for s in plan.SITELINKS}
        self.assertEqual(len(plan.groups()), 14)
        self.assertTrue(all(re.fullmatch(r'https://www\.uaart\.com\.ua/video/[a-z0-9/._-]+\.html', u) for u in urls))

    def test_campaign_paused_kyiv_search_only(self):
        ops = remote.operations('4680747874')
        campaign = ops[1]['campaignOperation']['create']
        self.assertEqual((campaign['status'], campaign['advertisingChannelType']), ('PAUSED', 'SEARCH'))
        self.assertEqual(campaign['geoTargetTypeSetting']['positiveGeoTargetType'], 'PRESENCE')
        self.assertFalse(campaign['networkSettings']['targetContentNetwork'])
        self.assertFalse(campaign['networkSettings']['targetSearchNetwork'])
        self.assertEqual(campaign['targetSpend']['cpcBidCeilingMicros'], '25000000')
        self.assertEqual(ops[0]['campaignBudgetOperation']['create']['amountMicros'], '500000000')
        crit = [o['campaignCriterionOperation']['create'] for o in ops if 'campaignCriterionOperation' in o]
        self.assertEqual([x['location']['geoTargetConstant'] for x in crit if 'location' in x], list(plan.LOCATIONS))
        schedule = [x['adSchedule'] for x in crit if 'adSchedule' in x]
        self.assertEqual(len(schedule), 7)
        self.assertTrue(all((s['startHour'], s['endHour']) == (9, 20) for s in schedule))
        self.assertTrue(all(o['adGroupAdOperation']['create']['ad']['responsiveSearchAd']
                            for o in ops if 'adGroupAdOperation' in o))
        self.assertEqual(len(ops), len({json.dumps(o, sort_keys=True) for o in ops}))


class RemoteTests(unittest.TestCase):
    def keys_file(self, temp):
        path = Path(temp) / 'keys.json'
        path.write_text(json.dumps(KEYS))
        return path

    def test_validate_only(self):
        self.assertTrue(remote.APPLY)  # R5: saved, PAUSED
        google = Google()
        with tempfile.TemporaryDirectory() as temp:
            text = remote.report(self.keys_file(temp), apply=False, opener=google)
        value = json.loads(text)
        self.assertEqual(value['status'], 'PASS')
        self.assertTrue([b for u, b in google.calls if u.endswith(':mutate')][0]['validateOnly'])
        for secret in list(KEYS.values())[:4]:
            self.assertNotIn(secret, text)

    @patch.object(remote, 'DIAG', True)
    def test_diag_never_saves(self):
        google = Google()
        with tempfile.TemporaryDirectory() as temp:
            value = json.loads(remote.report(self.keys_file(temp), apply=True, opener=google))
        self.assertTrue([b for u, b in google.calls if u.endswith(':mutate')][0]['validateOnly'])
        self.assertEqual(len(value['candidates']), len(set(value['candidates'])))

    def test_apply_creates_paused_once(self):
        self.assertFalse(remote.DIAG)
        google = Google()
        with tempfile.TemporaryDirectory() as temp:
            first = json.loads(remote.report(self.keys_file(temp), apply=True, opener=google))
            second = json.loads(remote.report(self.keys_file(temp), apply=True, opener=google))
        self.assertEqual((first['status'], second['status']), ('PASS', 'ALREADY_THERE'))
        self.assertEqual(len([u for u, _ in google.calls if u.endswith(':mutate')]), 1)


class FindingTests(unittest.TestCase):
    def test_policy_findings_listed(self):
        answer = {'error': {'details': [{'errors': [{'errorCode': {'policyFindingError': 'POLICY_FINDING'}, 'message': 'x',
                  'location': {'fieldPathElements': [{'fieldName': 'mutate_operations', 'index': 76}]},
                  'details': {'policyFindingDetails': {'policyTopicEntries': [{'type': 'PROHIBITED', 'topic': 'CAPITALIZATION',
                              'evidences': [{'textList': {'texts': ['LPi']}}]}]}}}]}]}}
        self.assertEqual(remote.findings(answer)[0]['topics'], [('PROHIBITED', 'CAPITALIZATION', ['LPi'])])
        self.assertEqual(remote.findings(answer)[0]['index'], 76)


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'ADS-CAMP-20261125'

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
        self.assertEqual(receipt['evidence_path'], 'cloud/ads_campaign_001/20261125.json')


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_own_server_prefix(self):
        text = Path(transport.__file__).read_text() + Path(__file__).with_name('bootstrap.py').read_text()
        self.assertIn('adscamp-', text)
        self.assertNotIn('adsconv', text)

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
