#!/usr/bin/env python3
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402


def database():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'x.db'
        con = sqlite3.connect(path)
        con.executescript(
            "CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, status TEXT, videos TEXT,"
            " condition_videos TEXT);"
            "INSERT INTO cars VALUES (26, 'UA-0017', 'ge_waiting', '[{\"file_id\":\"BAACAgIAAxkBAAIBTELEGRAMID\"}]', '[]');"
            "CREATE TABLE media(id INTEGER PRIMARY KEY, car_id INT, vid TEXT, file_id TEXT, status TEXT,"
            " poryadok INT, primechanie TEXT);"
            "INSERT INTO media VALUES (5, 26, 'video', 'SECRETFILEID', 'quarantine', 1,"
            " 'не скачать BAACAgIAAxkBAAIBTELEGRAMID: 400');"
            "INSERT INTO media VALUES (6, 26, 'foto', 'X', 'ready', 1, '');"
            "CREATE TABLE inbox(id INTEGER PRIMARY KEY, from_user_id INT, kind TEXT, text TEXT, file_id TEXT,"
            " status TEXT, card_type TEXT, card_id INT, created_at TEXT);"
            "INSERT INTO inbox VALUES (9, 123456789, 'video', 'private words', 'FID', 'new', NULL, NULL, '2026-10-10');")
        con.commit()
        con.close()
        return path.read_bytes()


class Fake:
    def server(self, path):
        return {'crm.db': database(),
                'video/': json.dumps({'UA-0017.html': {}, 'UA-0017.mp4': {}, 'UA-0001.mp4': {}}).encode()}.get(path)


class ProbeTests(unittest.TestCase):
    def test_scope(self):
        reader = c.Reader('test-value', opener=object())
        for bad in ('../x', 'video/UA-0017.mp4', 'cars_ui.py', ''):
            with self.assertRaises(c.ProbeError):
                reader.server(bad)

    def test_execute_without_identifiers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / c.REQUEST).parent.mkdir(parents=True)
            (root / c.REQUEST).write_text(json.dumps({'read_only': True, 'production_required': False}))
            env = {'UAART_TASK_ID': c.TASK_ID, 'UAART_RECEIPT_PATH': c.RECEIPT, 'UAART_REQUEST_PATH': c.REQUEST,
                   'UAART_REQUEST_SHA256': c.sha((root / c.REQUEST).read_bytes()), 'UAART_RUN_ID': '1'}
            c.execute(env, root=root, reader=Fake())
            text = (root / c.EVIDENCE).read_text()
        evidence = json.loads(text)
        audi = evidence['cars']['UA-0017']
        self.assertEqual(audi['fields']['videos'], {'count': 1, 'entry_keys': ['file_id']})
        self.assertEqual(audi['media_by_vid_status'], {'foto/ready': 1, 'video/quarantine': 1})
        self.assertEqual(evidence['site_video_files']['UA-0017'], ['UA-0017.mp4'])
        self.assertEqual(len(evidence['unlinked_inbox_videos_or_documents']), 1)
        for secret in ('TELEGRAMID', 'SECRETFILEID', '123456789', 'private words', 'FID"'):
            self.assertNotIn(secret, text)


if __name__ == '__main__':
    unittest.main()
