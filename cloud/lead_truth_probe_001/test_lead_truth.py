#!/usr/bin/env python3
"""LEAD-TRUTH: read-only; no names or phones leave the server; never the CRM bot."""
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


class RemoteTests(unittest.TestCase):
    def test_order_rows_carry_no_personal_data(self):
        self.assertNotIn("'customer_name':", remote.ORDERS.split('rows.append')[1].split('})')[0])
        self.assertIn("'test_mark'", remote.ORDERS)
        self.assertTrue(remote.TEST.search('ТЕСТ реклама (Claude)'))
        self.assertFalse(remote.TEST.search('Олександр'))

    def test_nothing_written(self):
        text = Path(remote.__file__).read_text()
        for word in ('.write(', 'INSERT', 'UPDATE ', 'DELETE', 'set_bot'):
            self.assertNotIn(word, text.split('def main')[0])

    def test_own_counter_sample_hides_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            con = remote.sqlite3.connect(home / 'analytics.db')
            con.execute('CREATE TABLE events (ts INTEGER, tip TEXT, stranica TEXT, vid TEXT, sid TEXT)')
            for i in range(5):
                con.execute('INSERT INTO events VALUES (?, "page", "/video/index.html", "secret-visitor", "secret-session")', (i,))
            con.commit()
            con.close()
            with patch.object(remote, 'HOME', home):
                value = remote.own_counter()
        text = json.dumps(value)
        self.assertEqual(value['tables']['events']['rows'], 5)
        self.assertNotIn('secret-', text)
        self.assertIn('visitor-0', text)

    def test_links_fail_softly(self):
        with patch.object(remote.urllib.request, 'urlopen', side_effect=OSError('offline')):
            value = remote.links()
        self.assertEqual(set(value), set(remote.LINKS))
        self.assertTrue(all('error' in v for v in value.values()))


class FakeAPI:
    def run(self, mode, run_id, bundle):
        return {'status': 'PASS'}


class ControllerTests(unittest.TestCase):
    TASK = 'LEAD-TRUTH-PROBE-20261126'

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
        self.assertEqual(receipt['evidence_path'], 'cloud/lead_truth_probe_001/20261126.json')


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_own_prefix(self):
        self.assertIn('leadtruth-', Path(transport.__file__).read_text())

    def test_bundle_names(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
