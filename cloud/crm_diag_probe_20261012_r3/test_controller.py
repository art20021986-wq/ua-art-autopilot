#!/usr/bin/env python3
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402

MODULE = ("def save_media(row):\n    if row['status'] == 'pending':\n        return 'ждёт скачивания'\n"
          "def other():\n    return 1\n"
          "def leak():\n    token = 'iskhodnoe'\n")


def database():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'x.db'
        con = sqlite3.connect(path)
        con.executescript(
            "CREATE TABLE media(id INTEGER PRIMARY KEY, car_id INT, auto_number TEXT, vid TEXT, file_id TEXT,"
            " status TEXT, poryadok INT, primechanie TEXT);"
            "INSERT INTO media VALUES (1, 10, 'UA-0004', 'diag_video', 'SECRET-ID', 'quarantine', 1,"
            " 'file is too big chat 123456789');"
            "CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, published INT, status TEXT);"
            "INSERT INTO cars VALUES (10, 'UA-0004', 1, 'kr_bought');")
        con.commit()
        con.close()
        return path.read_bytes()


class Fake:
    def server(self, path):
        return {'': json.dumps({'cars_ui.py': {'type': 'file'}, 'crm.db': {'type': 'file'},
                                'video': {'type': 'directory'}}).encode(),
                'cars_ui.py': MODULE.encode(), 'crm.db': database(),
                'video/diag/UA-0004/': json.dumps({'01.jpg': {'type': 'file'}}).encode()}.get(path)


class ProbeTests(unittest.TestCase):
    def test_scope(self):
        reader = c.Reader('test-value', opener=object())
        for bad in ('../x', 'video/diag/UA-0004/1.mp4', 'site/', '.env', 'Cars.py'):
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
            evidence = json.loads((root / c.EVIDENCE).read_text())
            excerpt = (root / c.EXCERPTS).read_text()
        self.assertIn('save_media', excerpt)
        self.assertNotIn('def other', excerpt)
        self.assertNotIn('token', excerpt)
        self.assertEqual(evidence['modules_scanned'], {'cars_ui.py': 'MATCH'})
        self.assertEqual(evidence['diag_folders'], {'UA-0004': ['01.jpg']})
        media = evidence['crm']['diag_media'][0]
        self.assertEqual(media['primechanie'], 'file is too big chat [N]')
        self.assertNotIn('SECRET-ID', json.dumps(evidence))


if __name__ == '__main__':
    unittest.main()
