#!/usr/bin/env python3
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


class FakeAPI:
    def __init__(self, report):
        self.report, self.calls = report, []

    def run(self, mode, run_id, bundle):
        self.calls.append((mode, run_id, bundle))
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'LEAD-DESK-PROBE-20261025'

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
                         ('PASS', 'cloud/lead_desk_probe_001/20261025.json'))

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

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


class RemoteTests(unittest.TestCase):
    def test_returns_crm_sources_sanitized(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'video').mkdir()
            (home / 'video/index.html').write_text("TOKEN = 'abc'\nasync def clients_screen():\n    phone = '+380 99 222 20 02'\n"
                                             "x = 'https://evil.example/p'\n")
            (home / 'ua_order').mkdir()
            (home / 'vitrina.py').write_text("TOKEN = 'abc'\nx = 'https://evil.example/p'\n")
            value = remote.report(home)
        guard = value['files']['vitrina.py']['source']
        self.assertIn('[REDACTED]', guard)
        self.assertIn('[URL]', guard)
        self.assertIsNone(value['files']['publikaciya.py'])
        self.assertIsNone(value['lead_desk'])
        hits = json.loads(value['files']['_card_button_hits']['source'])
        self.assertEqual(hits, [])
        self.assertEqual(value['zone_kyiv'], 'OK')

    def test_counts_only_no_client_rows(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            with sqlite3.connect(home / 'crm.db') as c:
                c.execute('CREATE TABLE clients (name, phone, source, stage, created_at)')
                c.execute("INSERT INTO clients VALUES ('Ivan', '+380992222002', 'Instagram', 'new', '2026-11-06T10:00')")
                c.execute('CREATE TABLE lead_desk_meta (key, value)')
                c.execute("INSERT INTO lead_desk_meta VALUES ('track_from', '1')")
            value = remote.report(home)
        dumped = json.dumps(value['lead_desk'])
        self.assertNotIn('Ivan', dumped)
        self.assertNotIn('380992222002', dumped)
        self.assertEqual(value['lead_desk']['aggregates']['clients_by_source'], [['Instagram', 1]])
        self.assertEqual(value['lead_desk']['aggregates']['lead_desk_by_status'], 'OperationalError')


if __name__ == '__main__':
    unittest.main()
