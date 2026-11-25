#!/usr/bin/env python3
"""ADS-CHECK: only reading calls, no key value in the report, the CRM bot is never the trigger."""
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402
import source_remote as remote  # noqa: E402
import transport  # noqa: E402

KEYS = {'developer_token': 'DEVTOKEN' + 'x' * 14, 'client_id': '1' * 12 + '-abc.apps.' + 'googleusercontent.com',
        'client_secret': 'GOC' + 'SPX-' + 'q' * 28, 'refresh_token': '1//' + 'r' * 40,
        'login_customer_id': '9054959760', 'customer_id': '4680747874'}
ACCESS = 'ya' + '29.' + 'a' * 40


class Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Google:
    """Stands in for Google: records every call."""

    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def __call__(self, request, timeout=None):
        self.calls.append((request.get_method(), request.full_url, dict(request.header_items()), request.data))
        if request.full_url == remote.TOKEN_ENDPOINT:
            return Response(json.dumps({'access_token': ACCESS, 'scope': 'https://www.googleapis.com/auth/adwords'}).encode())
        if self.fail and self.fail in request.full_url:
            body = {'error': {'status': 'PERMISSION_DENIED', 'message': 'denied', 'details': [
                {'errors': [{'errorCode': {'authorizationError': 'DEVELOPER_TOKEN_NOT_APPROVED'}, 'message': 'x'}]}]}}
            raise urllib.error.HTTPError(request.full_url, 403, 'x', {}, io.BytesIO(json.dumps(body).encode()))
        if 'listAccessibleCustomers' in request.full_url:
            return Response(b'{"resourceNames": ["customers/4680747874"]}')
        return Response(b'{"results": [{"customer": {"descriptiveName": "UA ART"}}]}')


class RemoteTests(unittest.TestCase):
    def keys_file(self, temp, keys=KEYS):
        path = Path(temp) / 'keys.json'
        path.write_text(json.dumps(keys))
        path.chmod(0o600)
        return path

    def test_reading_calls_only_and_no_key_in_report(self):
        google = Google()
        with tempfile.TemporaryDirectory() as temp:
            text = remote.report(self.keys_file(temp), google)
        value = json.loads(text)
        self.assertEqual(value['status'], 'PASS')
        self.assertEqual(value['google_ads']['accessible'], ['customers/4680747874'])
        self.assertEqual(set(value['google_ads']) - {'token', 'scope', 'accessible'}, set(remote.QUERIES))
        for secret in list(KEYS.values())[:4] + [ACCESS]:
            self.assertNotIn(secret, text)
        urls = [url for _, url, _, _ in google.calls]
        self.assertFalse([u for u in urls if 'mutate' in u.lower()])
        self.assertTrue(all(u == remote.TOKEN_ENDPOINT or u.startswith(remote.API) for u in urls))
        search = [h for _, u, h, _ in google.calls if 'googleAds:search' in u]
        self.assertTrue(all(h['Login-customer-id'] == '9054959760' for h in search))
        self.assertNotIn('mutate', Path(remote.__file__).read_text().lower().replace('no mutate call', ''))

    def test_google_error_code_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            value = json.loads(remote.report(self.keys_file(temp), Google(fail='googleAds:search')))
        self.assertEqual(value['google_ads']['account']['http'], 403)
        self.assertIn('DEVELOPER_TOKEN_NOT_APPROVED', json.dumps(value))

    def test_missing_refresh_token(self):
        with tempfile.TemporaryDirectory() as temp:
            keys = dict(KEYS, refresh_token='')
            value = json.loads(remote.report(self.keys_file(temp, keys), Google()))
        self.assertEqual((value['status'], value['keys_present']['refresh_token']), ('KEYS_INCOMPLETE', False))

    def test_key_in_report_stops(self):
        with self.assertRaisesRegex(remote.CheckError, 'KEY_IN_REPORT'):
            remote.clean({'x': KEYS['client_secret']}, KEYS)


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'ADS-CHECK-20261125'

    def env(self, root):
        request = root / 'tasks/requests' / (self.TASK + '.json')
        request.parent.mkdir(parents=True)
        request.write_text(json.dumps({'production_required': False}))
        return {'UAART_TASK_ID': self.TASK, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % self.TASK,
                'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % self.TASK,
                'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '7'}

    def test_report_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt = c.execute(self.env(Path(temp)), root=temp, api=FakeAPI({'status': 'PASS'}), upload=lambda a: 'b' * 64)
        self.assertEqual((receipt['probe_status'], receipt['evidence_path']),
                         ('PASS', 'cloud/ads_check_001/20261125.json'))


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_own_server_prefix(self):
        text = Path(transport.__file__).read_text() + Path(__file__).with_name('bootstrap.py').read_text()
        self.assertIn('adscheck-', text)
        self.assertNotIn('videoprobe', text)

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
