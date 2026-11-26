#!/usr/bin/env python3
"""JAPAN-STOCK-PROBE: marker scan, full sources and CRM schema, without secrets or personal data."""
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
        (self.home / 'ua_delivery_status.py').write_text(
            'TOKEN = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"\nCHOICES = (("korea", "kr_bought", 1, "В Корее"),)\n'
            'PHONE = "+380 99 222 2002"\n', encoding='utf-8')
        (self.home / 'other.py').write_text('print(1)\n', encoding='utf-8')
        (self.home / 'video').mkdir()
        (self.home / 'video/gen.py').write_text('kr_bought\n', encoding='utf-8')
        (self.home / 'shablon.html').write_text('<div class="filter-row"></div>\n', encoding='utf-8')
        with sqlite3.connect(self.home / 'crm.db') as connection:
            connection.execute('CREATE TABLE cars(id INTEGER, status TEXT, published INTEGER, client_phone TEXT, vin TEXT)')
            connection.execute("INSERT INTO cars VALUES(1,'kr_bought',1,'+380992222002','VINX')")

    def report(self):
        with patch.object(remote, 'HOME', self.home):
            return remote.report()

    def test_report_reads_markers_without_secrets(self):
        value = self.report()
        text = json.dumps(value, ensure_ascii=False)
        self.assertIn('CHOICES', value['full_sources']['ua_delivery_status.py'])
        self.assertEqual(value['files']['ua_delivery_status.py']['hits']['kr_bought'], [2])
        self.assertIn('shablon.html', value['files'])
        self.assertNotIn('other.py', value['files'])
        self.assertNotIn('video/gen.py', value['files'])
        for secret in ('AAAAAAAA', '222 2002', '380992222002', 'VINX'):
            self.assertNotIn(secret, text)
        self.assertNotIn('_text', text)
        self.assertEqual(value['crm_schema']['status_published_counts'], [['kr_bought', 1, 1]])
        self.assertIn('vin', value['crm_schema']['cars_columns'])

    def test_main_writes_only_its_receipt(self):
        with patch.object(remote, 'HOME', self.home), patch.object(remote, 'HERE', self.home / 'pkg'), \
             patch.object(remote.resource, 'setrlimit'), patch.object(sys, 'argv', ['x', '--run', '7']):
            self.assertEqual(remote.main(), 0)
        receipt = json.loads((self.home / 'pkg/runs/7/receipt-probe.json').read_text())
        self.assertEqual((receipt['status'], receipt['remote_write_count']), ('PASS', 0))


class ControllerTests(unittest.TestCase):
    TASK = 'JAPAN-STOCK-PROBE-20261126'

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
                             ('PASS', 'cloud/japan_stock_probe_001/20261126.json'))

    def test_wrong_task_is_refused(self):
        with self.assertRaises(c.ProbeError):
            c.validate_identity({'UAART_TASK_ID': 'OTHER-1'}, Path('.'))


if __name__ == '__main__':
    unittest.main()
