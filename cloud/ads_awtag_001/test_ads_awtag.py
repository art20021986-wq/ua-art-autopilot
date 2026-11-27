#!/usr/bin/env python3
"""ADS-AWTAG: one website conversion action (secondary), its tag read; never twice."""
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
        self.actions = []
        self.calls = []

    def __call__(self, request, timeout=None):
        if request.full_url == remote.check.TOKEN_ENDPOINT:
            return Response(json.dumps({'access_token': 'ya' + '29.' + 'a' * 30}).encode())
        body = json.loads(request.data)
        self.calls.append((request.full_url, body))
        if request.full_url.endswith('googleAds:mutate'):
            c = body['mutateOperations'][0]['conversionActionOperation']['create']
            self.actions.append({'conversionAction': {'name': c['name'], 'status': 'ENABLED', 'type': c['type'],
                                                      'primaryForGoal': c['primaryForGoal'], 'tagSnippets': [
                {'type': 'WEBPAGE', 'globalSiteTag': "gtag('config', 'AW-17001234');",
                 'eventSnippet': "gtag('event', 'conversion', {'send_to': 'AW-17001234/AbCd_12-x'});"}]}})
            return Response(b'{}')
        return Response(json.dumps({'results': self.actions}).encode())


class RemoteTests(unittest.TestCase):
    def keys_file(self, temp):
        path = Path(temp) / 'keys.json'
        path.write_text(json.dumps(KEYS))
        return path

    def test_action_once_and_tag_read(self):
        google = Google()
        with tempfile.TemporaryDirectory() as temp:
            first = json.loads(remote.report(self.keys_file(temp), google))
            second = json.loads(remote.report(self.keys_file(temp), google))
        self.assertEqual((first['status'], second['status'], second['operations'], second['existed']),
                         ('PASS', 'PASS', 0, True))
        self.assertEqual((first['tag_id'], first['send_to']), ('AW-17001234', 'AW-17001234/AbCd_12-x'))
        mutates = [b for u, b in google.calls if u.endswith(':mutate')]
        self.assertEqual(len(mutates), 1)
        create = mutates[0]['mutateOperations'][0]['conversionActionOperation']['create']
        self.assertEqual((create['type'], create['category'], create['primaryForGoal']), ('WEBPAGE', 'SUBMIT_LEAD_FORM', False))


class FakeAPI:
    def run(self, mode, run_id, bundle):
        return {'status': 'PASS'}


class ControllerTests(unittest.TestCase):
    TASK = 'ADS-AWTAG-20261127'

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
        self.assertEqual(receipt['evidence_path'], 'cloud/ads_awtag_001/20261127.json')


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_own_prefix(self):
        self.assertIn('adsawtag-', Path(transport.__file__).read_text())

    def test_bundle_names(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
