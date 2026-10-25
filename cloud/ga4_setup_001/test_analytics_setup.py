#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analytics_remote as remote  # noqa: E402
import controller as c  # noqa: E402
import transport  # noqa: E402

PROP = 'properties/123'


class FakeAPI:
    def __init__(self, report):
        self.report, self.calls = report, []

    def run(self, mode, run_id, bundle):
        self.calls.append((mode, run_id, bundle))
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'GA4-SETUP-20261025'

    def env(self, root):
        request = root / 'tasks/requests' / (self.TASK + '.json')
        request.parent.mkdir(parents=True)
        request.write_text(json.dumps({'read_only': False, 'production_required': False}))
        return {'UAART_TASK_ID': self.TASK, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % self.TASK,
                'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % self.TASK,
                'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '7'}

    def test_report_saved(self):
        api = FakeAPI({'status': 'PASS', 'stream': {'measurementId': 'G-ABC123'}})
        with tempfile.TemporaryDirectory() as temp:
            receipt = c.execute(self.env(Path(temp)), root=temp, api=api, upload=lambda a: 'b' * 64)
            evidence = json.loads((Path(temp) / receipt['evidence_path']).read_text())
        self.assertEqual(api.calls, [('probe', '7', 'b' * 64)])
        self.assertEqual((receipt['ga4_status'], evidence['stream']['measurementId']), ('PASS', 'G-ABC123'))
        self.assertEqual(receipt['evidence_path'], 'cloud/ga4_setup_001/20261025.json')

    def test_key_material_never_saved(self):
        api = FakeAPI({'status': 'PASS', 'leak': '"private_key": "-----BEGIN PRIVATE KEY-----"'})
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(c.ProbeError, 'KEY_MATERIAL'):
                c.execute(self.env(Path(temp)), root=temp, api=api, upload=lambda a: 'b' * 64)

    def test_wrong_task_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            env = dict(self.env(Path(temp)), UAART_TASK_ID='GSC-REPORT-20261025')
            with self.assertRaisesRegex(c.ProbeError, 'IDENTITY'):
                c.execute(env, root=temp, api=FakeAPI({}), upload=lambda a: 'b' * 64)


class TransportTests(unittest.TestCase):
    def test_only_probe_mode_and_never_the_bot(self):
        api = transport.API('test-token')
        for args in (('install', '1', 'a' * 64), ('probe', 'x', 'a' * 64), ('probe', '1', 'short')):
            with self.assertRaises(transport.TransportError):
                api.run(*args)
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_bundle_names_pass_bootstrap_filter(self):
        import re
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


class RemoteTests(unittest.TestCase):
    def run_report(self, answers):
        calls = []

        def call(bearer, url, body=None, method=None):
            calls.append((method or ('POST' if body is not None else 'GET'), url, body))
            for (verb, suffix), answer in answers.items():
                if calls[-1][0] == verb and url.endswith(suffix):
                    return answer
            raise AssertionError(url)
        with tempfile.TemporaryDirectory() as temp:
            key = Path(temp) / 'uaart-autopilot-110fb4d36d23'
            key.write_text('{}')
            with patch.object(remote, 'KEYS', (key,)), patch.object(remote, 'token', return_value=('sa@x', 'proj', 't')), \
                 patch.object(remote, 'call', side_effect=call):
                return remote.report(), calls

    SUMMARY = (200, {'accountSummaries': [{'account': 'accounts/1', 'displayName': 'UA ART',
                                           'propertySummaries': [{'property': PROP, 'displayName': 'UA ART'}]}]})

    def test_creates_missing_stream_and_retention(self):
        created = {'name': PROP + '/dataStreams/9', 'type': 'WEB_DATA_STREAM', 'displayName': remote.STREAM_NAME,
                   'webStreamData': {'defaultUri': remote.SITE, 'measurementId': 'G-XYZ789'}}
        value, calls = self.run_report({
            ('GET', 'accountSummaries'): self.SUMMARY, ('GET', PROP): (200, {'timeZone': 'Europe/Kiev'}),
            ('GET', '/dataStreams'): (200, {}), ('POST', '/dataStreams'): (200, created),
            ('GET', '/dataRetentionSettings'): (200, {'eventDataRetention': 'TWO_MONTHS'}),
            ('PATCH', 'eventDataRetention'): (200, {'eventDataRetention': 'FOURTEEN_MONTHS'})})
        self.assertEqual((value['status'], value['stream']['measurementId']), ('PASS', 'G-XYZ789'))
        self.assertEqual(value['analytics_writes'], ['data_stream_created', 'retention_14_months'])
        self.assertEqual(calls[3][2], {'type': 'WEB_DATA_STREAM', 'displayName': remote.STREAM_NAME,
                                       'webStreamData': {'defaultUri': 'https://www.uaart.com.ua'}})

    def test_existing_stream_is_not_duplicated(self):
        stream = {'name': PROP + '/dataStreams/9', 'type': 'WEB_DATA_STREAM',
                  'webStreamData': {'defaultUri': 'https://www.uaart.com.ua/', 'measurementId': 'G-XYZ789'}}
        value, calls = self.run_report({
            ('GET', 'accountSummaries'): self.SUMMARY, ('GET', PROP): (200, {}),
            ('GET', '/dataStreams'): (200, {'dataStreams': [stream]}),
            ('GET', '/dataRetentionSettings'): (200, {'eventDataRetention': 'FOURTEEN_MONTHS'})})
        self.assertEqual((value['status'], value['analytics_writes']), ('PASS', []))
        self.assertFalse([c for c in calls if c[0] != 'GET'])

    def test_no_access_writes_nothing(self):
        value, calls = self.run_report({('GET', 'accountSummaries'): (200, {})})
        self.assertEqual((value['status'], value['error']), ('FAIL', 'PROPERTY_NOT_FOUND'))
        self.assertEqual(len(calls), 1)

    def test_disabled_api_is_enabled_once(self):
        value, calls = self.run_report({
            ('GET', 'accountSummaries'): (403, {'error': '... SERVICE_DISABLED ...'}),
            ('POST', ':enable'): (403, {'error': 'PERMISSION_DENIED'})})
        self.assertEqual(value['error'], 'ADMIN_API_HTTP_403')
        self.assertEqual(value['detail']['enable_attempt']['http'], 403)
        self.assertIn('projects/proj/services/analyticsadmin.googleapis.com:enable', calls[1][1])


if __name__ == '__main__':
    unittest.main()
