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

NOW = 1795000000


class RemoteTests(unittest.TestCase):
    def home(self, temp):
        home = Path(temp)
        stamp = remote.time.strftime('%Y-%m-%d %H:%M:%S', remote.time.gmtime(NOW - 60))
        (home / 'media_log.txt').write_text(
            '2020-01-01 00:00:00  UA-0001 · photos · принято fast-path · AgACAgIAAxkBAAIabcdefghij\n'
            + stamp + '  UA-0030 · photos · принято fast-path · AgACAgIAAxkBAAIabcdefghij\n'
            + stamp + '  UA-0030 · videos · ОТКАЗ размер 99 байт\n', encoding='utf-8')
        (home / '.crm_media_spool.jsonl').write_text(
            json.dumps({'key': 'k1', 'card_id': 30, 'target': 'photos', 'file_id': 'AgACAgIAAxkBAAIabcdefghij',
                        'accepted_at': NOW - 500}) + '\nnot json\n', encoding='utf-8')
        (home / '.crm_media_receipts.jsonl').write_text(
            ''.join(json.dumps({'key': 'k%d' % n, 'card_id': 30, 'target': 'photos', 'saved_at': NOW - n}) + '\n'
                    for n in range(3)), encoding='utf-8')
        with sqlite3.connect(home / 'crm.db') as con:
            con.execute('CREATE TABLE cars (id INTEGER, auto_number TEXT, status TEXT, photos TEXT, phone TEXT)')
            con.execute("INSERT INTO cars VALUES (30, 'UA-0030', 'stock', '[\"a\", \"b\"]', '+380501234567')")
            con.execute('CREATE TABLE media (car_id INTEGER, vid TEXT, status TEXT, kogda TEXT)')
            con.execute("INSERT INTO media VALUES (30, 'foto', 'pending', '2026-11-19')")
        (home / 'video/foto/UA-0030').mkdir(parents=True)
        (home / 'video/foto/UA-0030/1.jpg').write_bytes(b'x')
        (home / 'cars_ui.py').write_text('PHOTO_LIMIT = 99\nBOT_TOKEN = "1"\n', encoding='utf-8')
        return home

    def test_report_counts_without_ids_or_client_data(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(remote, 'HOME', self.home(temp)), patch.object(remote, 'BOT_LOG', Path(temp) / 'none.log'):
                value = remote.report(NOW)
        text = json.dumps(value, ensure_ascii=False)
        self.assertEqual(value['media_log']['recent_lines'], 2)
        self.assertEqual(value['spool']['per_card_section']['30:photos']['count'], 1)
        self.assertEqual(value['spool']['invalid_lines'], 1)
        self.assertEqual(value['ledger']['per_card_section']['30:photos']['count'], 3)
        self.assertEqual(value['crm']['cars'][0]['photos'], 2)
        self.assertEqual(value['crm']['media'][0]['n'], 1)
        self.assertEqual(value['published'], {'UA-0030': 1})
        self.assertIn('PHOTO_LIMIT = 99', value['sources']['cars_ui.py']['source'])
        self.assertIsNone(value['bot_log'])
        for leak in ('AgACAgIAAxkBAAIabcdefghij', '380501234567', 'BOT_TOKEN'):
            self.assertNotIn(leak, text)

    def test_database_opened_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(remote, 'HOME', self.home(temp)):
                before = (Path(temp) / 'crm.db').read_bytes()
                remote.crm()
                self.assertEqual(before, (Path(temp) / 'crm.db').read_bytes())


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'PHOTO-ADD-PROBE-20261119'

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
                         ('PASS', 'cloud/photo_add_probe_001/20261119.json'))

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
        text = Path(transport.__file__).read_text() + Path(__file__).with_name('bootstrap.py').read_text()
        self.assertIn('photoaddprobe-', text)
        self.assertNotIn('weekprobetwo', text)

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
