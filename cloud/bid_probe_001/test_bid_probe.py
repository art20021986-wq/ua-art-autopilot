#!/usr/bin/env python3
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402
import source_remote as remote  # noqa: E402
import transport  # noqa: E402


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'BID-PROBE-20261105'

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
                         ('PASS', 'cloud/bid_probe_001/20261105.json'))

    def test_key_material_never_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(c.ProbeError, 'KEY_MATERIAL'):
                c.execute(self.env(Path(temp)), root=temp, api=FakeAPI({'x': '-----BEGIN PRIVATE KEY'}),
                          upload=lambda a: 'b' * 64)


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_own_server_prefix(self):
        self.assertIn('bidprobe-', Path(transport.__file__).read_text())
        self.assertNotIn('crmprobe', Path(transport.__file__).read_text())

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


class RemoteTests(unittest.TestCase):
    PAGE = ('<form action="/bid/place/20261111000123" method="post" id="bidForm">'
            '<input type="hidden" name="data[_Token][key]" value="secret-token-value">'
            '<input type="text" name="data[Bid][amount]" value=""><button type="submit">Place Bid</button></form>'
            '<p>Contact owner@example.com about lot 20261111000123</p>'
            '<script>$.post("/api/bid/confirm", {lot: 20261111000123});</script>')

    def test_form_is_described_without_values(self):
        found = remote.forms(self.PAGE)[0]
        self.assertEqual((found['action'], found['method'], found['mentions_bid']), ('/bid/place/[N]', 'post', True))
        names = [(c['name'], c['type'], c['value_length']) for c in found['controls']]
        self.assertIn(('data[_Token][key]', 'hidden', 18), names)
        self.assertNotIn('secret-token-value', json.dumps(found))

    def test_lines_and_endpoints_are_cleaned(self):
        lines = remote.bid_lines(self.PAGE)
        self.assertTrue(lines)
        self.assertNotIn('owner@example.com', ' '.join(lines))
        self.assertNotIn('20261111000123', ' '.join(lines))
        self.assertEqual(remote.endpoints(self.PAGE), ['/api/bid/confirm', '/bid/place/[N]'])

    def test_login_file_is_needed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'login.txt'
            path.write_text('only-one-line')
            with patch.object(remote, 'LOGIN', path):
                with self.assertRaisesRegex(RuntimeError, 'LOGIN_FILE_INCOMPLETE'):
                    remote.login_pair()


if __name__ == '__main__':
    unittest.main()
