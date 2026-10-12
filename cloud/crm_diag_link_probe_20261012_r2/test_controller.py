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
            "CREATE TABLE inbox(id INTEGER PRIMARY KEY, from_user_id INT, kind TEXT, text TEXT, file_id TEXT,"
            " created_at TEXT);"
            "INSERT INTO inbox VALUES (1, 555, 'text', 'http://example/report?id=SECRETX', NULL, '2026-10-12 04:24');"
            "INSERT INTO inbox VALUES (2, 555, 'voice', NULL, 'FILE-SECRET', '2026-10-12 04:40');")
        con.commit()
        con.close()
        return path.read_bytes()


class Fake:
    def server(self, path):
        return database() if path == 'crm.db' else None


class ProbeTests(unittest.TestCase):
    def test_scope(self):
        reader = c.Reader('test-value', opener=object())
        for bad in ('', '../x', 'cars_ui.py', 'video/'):
            with self.assertRaises(c.ProbeError):
                reader.server(bad)

    def test_execute(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / c.REQUEST).parent.mkdir(parents=True)
            (root / c.REQUEST).write_text(json.dumps({'read_only': True, 'production_required': False}))
            env = {'UAART_TASK_ID': c.TASK_ID, 'UAART_RECEIPT_PATH': c.RECEIPT, 'UAART_REQUEST_PATH': c.REQUEST,
                   'UAART_REQUEST_SHA256': c.sha((root / c.REQUEST).read_bytes()), 'UAART_RUN_ID': '1'}
            c.execute(env, root=root, reader=Fake())
            raw = (root / c.EVIDENCE).read_text()
        evidence = json.loads(raw)
        first, second = evidence['inbox_latest']
        self.assertEqual((first['kind'], first['has_file']), ('voice', True))
        self.assertTrue(second['text_is_url'])
        self.assertEqual(second['created_at'], '2026-10-12 04:24')
        for secret in ('SECRETX', 'FILE-SECRET', '555'):
            self.assertNotIn(secret, raw)


if __name__ == '__main__':
    unittest.main()
