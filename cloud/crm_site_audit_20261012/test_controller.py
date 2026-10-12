#!/usr/bin/env python3
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import controller as c  # noqa: E402
from fixture_public import CATALOG, PRICES  # noqa: E402


def database():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'x.db'
        con = sqlite3.connect(path)
        con.execute('CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, published INT, status TEXT,'
                    ' price_uah INT, client_id INT)')
        con.execute("INSERT INTO cars VALUES (32, 'UA-0022', 1, 'kr_bought', 21200, 5)")
        con.commit()
        con.close()
        return path.read_bytes()


class FakeReader:
    def __init__(self):
        self.calls = []

    def server(self, path):
        self.calls.append(('server', path))
        if path == 'crm.db':
            return database()
        if path == 'video/':
            return json.dumps({'UA-0022.html': {}, 'UA-0008.html': {}, 'foto': {}}).encode()
        return CATALOG.encode() if path == 'video/katalog.html' else None

    def public(self, path):
        self.calls.append(('public', path))
        if path.endswith('.json'):
            return json.dumps(PRICES).encode()
        return b'stale'


class ControllerTests(unittest.TestCase):
    def test_scope_is_fixed_and_get_only(self):
        reader = c.Reader('test-value', opener=object())
        for bad in ('../x', 'crm.db.bak', 'video/../crm.db', '.env', 'video/foto/1.jpg'):
            with self.assertRaises(c.ProbeError):
                reader.server(bad)
        with self.assertRaises(c.ProbeError):
            reader.public('video/../crm.db')

    def test_execute_writes_report_without_private_columns(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = root / c.REQUEST
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'task_id': c.TASK_ID, 'production_required': False, 'read_only': True}))
            env = {'UAART_TASK_ID': c.TASK_ID, 'UAART_TASK_CLASS': 'STANDARD', 'UAART_REQUEST_PATH': c.REQUEST,
                   'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '1',
                   'UAART_RECEIPT_PATH': c.RECEIPT}
            reader = FakeReader()
            receipt = c.execute(env, root=root, reader=reader)
            evidence = json.loads((root / c.EVIDENCE).read_text())
        self.assertEqual(receipt['status'], 'FINISHED')
        self.assertEqual(evidence['summary']['served_bytes_differ_from_server'], ['video/katalog.html'])
        self.assertEqual(evidence['summary']['card_pages_without_crm_car'], ['UA-0008.html'])
        self.assertNotIn('client_id', json.dumps(evidence))
        self.assertTrue(all(kind in ('server', 'public') for kind, _ in reader.calls))


if __name__ == '__main__':
    unittest.main()
