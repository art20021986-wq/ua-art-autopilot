#!/usr/bin/env python3
import datetime
import json
from pathlib import Path
import re
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
    TASK = 'CRM-VOICE-PROBE-20261101'

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
                         ('PASS', 'cloud/crm_voice_probe_001/probe_20261101.json'))

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
        for path in HERE.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z0-9_]+\.py'))


class RemoteTests(unittest.TestCase):
    def test_sources_sanitized_and_hash_only(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'cars_ui.py').write_text("KEY = 'sk-abcdefghijklmnop'\nOWNER = 380501234567\nprint(1)\n")
            (home / 'team_bot.py').write_text('print(2)\n')
            files = remote.sources(home)
        self.assertEqual(files['cars_ui.py']['source'], '[REDACTED]\nOWNER = [N]\nprint(1)')
        self.assertEqual(set(files['team_bot.py']), {'sha256'})
        self.assertIsNone(files['ai.py'])

    def test_bot_log_today_without_publisher_noise(self):
        today = datetime.date(2026, 11, 1)
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / 'bot.log'
            log.write_text('Oct 31 10:00:00 old\n'
                           'Nov  1 14:00:00 ERROR ua_crm_public_sync: CRM sync failed; retry pending: UA-0006\n'
                           'Nov  1 14:00:00 Traceback (most recent call last):\n'
                           'Nov  1 14:00:00     raise RuntimeError(str(message)[:500])\n'
                           'Nov  1 14:05:01 WARNING CRM voice timeout card=17\n'
                           'Nov  1 14:05:02 Traceback (most recent call last):\n'
                           'Nov  1 14:05:02 KeyError: x\n'
                           'Nov  1 14:06:00 sent token = abc\n')
            value = remote.bot_log(today, log)
        self.assertEqual(value['lines'], ['Nov  1 14:05:01 WARNING CRM voice timeout card=17',
                                          'Nov  1 14:05:02 Traceback (most recent call last):',
                                          'Nov  1 14:05:02 KeyError: x', '[REDACTED]'])

    def test_guard_events_today_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'events.jsonl'
            path.write_text('{"at": "2026-10-31T10:00:00Z", "action": "crm_voice"}\n'
                            '{"at": "2026-11-01T14:20:00Z", "kind": "timing", "action": "crm_voice", '
                            '"status": "empty", "elapsed_seconds": 16.2}\n'
                            '{"at": "2026-11-01T14:20:01Z", "kind": "heartbeat"}\nnot json\n')
            value = remote.guard_events(datetime.date(2026, 11, 1), path)
        self.assertEqual(value, [{'at': '2026-11-01T14:20:00Z', 'kind': 'timing', 'action': 'crm_voice',
                                  'status': 'empty', 'elapsed_seconds': '16.2'}])

    def test_crm_sizes_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'crm.db'
            con = sqlite3.connect(path)
            con.executescript(
                "CREATE TABLE inbox(id INTEGER PRIMARY KEY, kind TEXT, status TEXT, text TEXT, created_at TEXT);"
                "CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT);"
                "CREATE TABLE audit(id INTEGER PRIMARY KEY, action TEXT, entity_type TEXT, entity_id INT, field TEXT,"
                " old_value TEXT, new_value TEXT, created_at TEXT);"
                "INSERT INTO cars VALUES (3, 'UA-0003');"
                "INSERT INTO inbox VALUES (1, 'voice', 'new', 'PRIVATE', '2026-11-01T14:05:00');"
                "INSERT INTO inbox VALUES (2, 'text', 'new', 'OLD', '2026-10-31T14:05:00');"
                "INSERT INTO audit VALUES (1, 'update', 'cars', 3, 'drive', '', 'SECRET', '2026-11-01T14:05:03');")
            con.commit()
            con.close()
            value = remote.crm(datetime.date(2026, 11, 1), path)
        self.assertEqual(value['inbox'], [{'id': 1, 'kind': 'voice', 'status': 'new', 'text_chars': 7,
                                           'created_at': '2026-11-01T14:05:00'}])
        self.assertEqual(value['audit'][0]['auto_number'], 'UA-0003')
        self.assertNotIn('SECRET', json.dumps(value))


if __name__ == '__main__':
    unittest.main()
