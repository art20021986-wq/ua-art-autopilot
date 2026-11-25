#!/usr/bin/env python3
"""PAGES-LAG-001 read-only probe: sources, state files and CRM/page times, without secrets or personal data."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402
import source_remote as remote  # noqa: E402


class RemoteTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name)
        (self.home / 'samokontrol.py').write_text(
            'TOKEN = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"\ndef stranicy_otstali():\n    return 1\n'
            'PHONE = "+380 99 222 2002"\n', encoding='utf-8')
        (self.home / 'run_all.py').write_text('import samokontrol\nsamokontrol.shag()\n', encoding='utf-8')
        (self.home / 'samokontrol.log').write_text('2026-11-20 ok\n2026-11-25 08:53 sborka FAIL Traceback x@y.com\n',
                                                   encoding='utf-8')
        (self.home / '.crm_public_sync_state.json').write_text('{"retry": {"10": {"error": "BASE"}}}', encoding='utf-8')
        (self.home / 'video').mkdir()
        (self.home / 'video/UA-0011.html').write_text('x', encoding='utf-8')
        with sqlite3.connect(self.home / 'crm.db') as connection:
            connection.execute('CREATE TABLE cars(id INTEGER, auto_number TEXT, status TEXT, published INTEGER, '
                               'updated_at TEXT, client_phone TEXT, vin TEXT)')
            connection.execute("INSERT INTO cars VALUES(1,'UA-0011','ua_ready',1,'2026-11-25 08:50:00','+380992222002','VINX')")

    def report(self):
        with patch.object(remote, 'HOME', self.home):
            return remote.report()

    def test_report_reads_everything_without_secrets(self):
        value = self.report()
        text = json.dumps(value, ensure_ascii=False)
        self.assertIn('def stranicy_otstali', value['full_sources']['samokontrol.py']['source'])
        self.assertNotIn('AAAAAAAA', text)
        self.assertNotIn('222 2002', text)
        self.assertNotIn('x@y.com', text)
        self.assertNotIn('VINX', text)
        self.assertNotIn('380992222002', text)
        self.assertEqual(value['callers']['run_all.py'][0]['line'], 1)
        self.assertEqual(value['state_files']['samokontrol.log']['matching_lines'],
                         ['2026-11-25 08:53 sborka FAIL Traceback [EMAIL]'])
        self.assertIn('retry', ''.join(value['state_files']['.crm_public_sync_state.json']['content']))
        car = value['crm_and_pages']['cars'][0]
        self.assertEqual((car['auto_number'], car['updated_at']), ('UA-0011', '2026-11-25 08:50:00'))
        self.assertIn('video', car['pages'])
        self.assertIsNone(value['full_sources']['ua_public_freshness.py'])

    def test_main_writes_only_its_receipt(self):
        with patch.object(remote, 'HOME', self.home), patch.object(remote, 'HERE', self.home / 'pkg'), \
             patch.object(remote.resource, 'setrlimit'), patch.object(sys, 'argv', ['x', '--run', '7']):
            self.assertEqual(remote.main(), 0)
        receipt = json.loads((self.home / 'pkg/runs/7/receipt-probe.json').read_text())
        self.assertEqual((receipt['status'], receipt['remote_write_count']), ('PASS', 0))


class ControllerTests(unittest.TestCase):
    TASK = 'PAGES-LAG-PROBE-20261125'

    def test_execute_writes_evidence_and_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = root / ('tasks/requests/%s.json' % self.TASK)
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'production_required': False}))
            env = {'UAART_TASK_ID': self.TASK, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % self.TASK,
                   'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % self.TASK, 'UAART_RUN_ID': '42',
                   'UAART_REQUEST_SHA256': c.sha(request.read_bytes())}

            class FakeAPI:
                def run(self, mode, run_id, bundle):
                    return {'status': 'PASS', 'mode': mode}

                def json(self, method, path):
                    return {'daily_cpu_limit_seconds': 1}

            receipt = c.execute(env, root=root, api=FakeAPI(), upload=lambda api: 'b' * 64)
            self.assertEqual((receipt['probe_status'], receipt['evidence_path']),
                             ('PASS', 'cloud/pages_lag_probe_001/20261125.json'))

    def test_wrong_task_is_refused(self):
        with self.assertRaises(c.ProbeError):
            c.validate_identity({'UAART_TASK_ID': 'OTHER-1'}, Path('.'))


if __name__ == '__main__':
    unittest.main()
