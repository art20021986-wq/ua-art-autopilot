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
            "CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, brand TEXT, model TEXT, published INT,"
            " status TEXT, videos TEXT, condition_videos TEXT);"
            "INSERT INTO cars VALUES (30, 'UA-0020', 'Kia', 'K5', 1, 'ua_arrived', '[]',"
            " '[{\"file_id\":\"BAACAgIAAxkBAAIBTELEGRAMID\"}]');"
            "INSERT INTO cars VALUES (27, 'UA-0017', 'Audi', 'A6', 1, 'kr_bought', '[]', '[]');"
            "INSERT INTO cars VALUES (5, 'UA-0005', 'Hyundai', 'X', 1, 'kr_bought', '[]', '[]');"
            "CREATE TABLE media(id INTEGER PRIMARY KEY, car_id INT, vid TEXT, file_id TEXT, status TEXT,"
            " poryadok INT, kogda TEXT, primechanie TEXT);"
            "INSERT INTO media VALUES (5, 30, 'diag_video', 'SECRETFILEID', 'pending', 1, '2026-10-12', '');"
            "CREATE TABLE audit(id INTEGER PRIMARY KEY, actor_id INT, action TEXT, entity_type TEXT, entity_id INT,"
            " field TEXT, old_value TEXT, new_value TEXT, created_at TEXT);"
            "INSERT INTO audit VALUES (1, 123456789, 'card_edit', 'cars', 30, 'condition_videos', '',"
            " '[BAACAgIAAxkBAAIBTELEGRAMID]', '2026-10-12T04:23:55');"
            "CREATE TABLE inbox(id INTEGER PRIMARY KEY, kind TEXT, card_type TEXT, card_id INT, created_at TEXT);")
        con.commit()
        con.close()
        return path.read_bytes()


class Fake:
    def server(self, path):
        return {'crm.db': database(),
                'video/': json.dumps({'UA-0020.html': {}, 'UA-0020.mp4': {}}).encode(),
                'video/diag/UA-0020/': json.dumps({'01.mp4': {'type': 'file', 'size': 900, 'url': 'x'}}).encode(),
                'video/UA-0020.html': b'<a href="UA-0020-diag.html">x</a><video src="UA-0020.mp4">',
                'video/UA-0020-diag.html': b'<p>\xd0\xbd\xd0\xb5 \xd0\xb4\xd0\xbe\xd0\xb1\xd0\xb0\xd0\xb2\xd0\xbb\xd0\xb5\xd0\xbd</p>',
                '.crm_public_sync_state.json': json.dumps({'revisions': {'UA-0020': 'r1', 'UA-0001': 'r2'},
                                                           'retries': {}}).encode()}.get(path)


class ProbeTests(unittest.TestCase):
    def test_scope(self):
        reader = c.Reader('test-value', opener=object())
        for bad in ('../x', 'video/UA-0007.mp4', 'cars_ui.py', '', 'video/diag/UA-0020/01.mp4'):
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
        self.assertEqual(sorted(evidence['cars']), ['UA-0017', 'UA-0020'])
        car = evidence['cars']['UA-0020']
        self.assertEqual(car['fields']['condition_videos']['count'], 1)
        self.assertEqual(car['media_by_vid_status'], {'diag_video/pending': 1})
        self.assertEqual(car['audit_media_fields'][0]['field'], 'condition_videos')
        self.assertEqual(evidence['diag_folders']['UA-0020'], {'01.mp4': {'type': 'file', 'size': 900}})
        self.assertEqual(evidence['pages']['UA-0020']['card']['diag_links'], 1)
        self.assertTrue(evidence['pages']['UA-0020']['diag']['placeholder_not_added'])
        self.assertEqual(evidence['sync_state']['entries_for_codes'], {'revisions': {'UA-0020': 'r1'}})
        for secret in ('TELEGRAMID', 'SECRETFILEID', '123456789'):
            self.assertNotIn(secret, text)


if __name__ == '__main__':
    unittest.main()
