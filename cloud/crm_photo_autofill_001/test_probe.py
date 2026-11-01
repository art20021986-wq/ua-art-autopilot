#!/usr/bin/env python3
import datetime
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import controller as c  # noqa: E402
import source_remote as remote  # noqa: E402
import transport  # noqa: E402


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'CRM-PHOTO-PROBE-20261101'

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
                         ('PASS', 'cloud/crm_photo_autofill_001/probe_20261101.json'))

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
        for path in HERE.iterdir():
            if path.suffix in ('.py', '.jpg'):
                self.assertRegex(path.name, re.compile(r'[a-z0-9_]+\.(?:py|jpg)'))
                self.assertLess(path.stat().st_size, 1048576)


class RemoteTests(unittest.TestCase):
    def test_sources_sanitized(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'team_bot.py').write_text("TOKEN = 'x'\nOWNER = 380501234567\nprint(1)\n")
            with patch.object(remote, 'HOME', home):
                files = remote.sources()
        self.assertEqual(files['team_bot.py']['source'], '[REDACTED]\nOWNER = [N]\nprint(1)')
        self.assertIsNone(files['local_ocr.py'])

    def test_crm_count_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'crm.db'
            con = sqlite3.connect(path)
            con.executescript("CREATE TABLE cars(id INTEGER PRIMARY KEY, vin TEXT, owner TEXT);"
                              "INSERT INTO cars(vin, owner) VALUES ('wdd 2452322j660244', 'PRIVATE');")
            con.commit()
            con.close()
            value = remote.crm(path)
        self.assertEqual(value, {'cars_columns': ['id', 'vin', 'owner'], 'sample_vin_cards': 1})

    def test_bot_log_today_topics_only(self):
        today = datetime.date(2026, 11, 1)
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / 'bot.log'
            log.write_text('Oct 31 10:00:00 Local OCR failed\nNov 01 14:17:01 Local OCR hard timeout inbox=5\n'
                           'Nov 01 14:17:02 unrelated\nNov 01 14:18:00 sent token = abc\n')
            with patch.object(remote, 'LOG', log):
                value = remote.bot_log(today)
        self.assertEqual(value, {'today_lines': 1, 'lines': ['Nov 01 14:17:01 Local OCR hard timeout inbox=5']})

    @unittest.skipUnless(shutil.which('tesseract') and Path('/tmp/w/local_ocr.py').exists(), 'local OCR fixture')
    def test_sample_through_live_ocr(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'runs').mkdir()
            with patch.object(remote, 'HERE', Path(temp)):
                value = remote.ocr(HERE / remote.SAMPLE, home='/tmp/w')
        self.assertTrue(value['live']['vin_in_text'])
        self.assertEqual(len(value['passes']), 9)


if __name__ == '__main__':
    unittest.main()
