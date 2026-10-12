#!/usr/bin/env python3
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402

LOG = ('Oct 12 04:10:00 old line\n'
       'Oct 12 04:41:02 CRM voice watchdog failed card=17 error=Timeout\n'
       'Oct 12 04:41:03 token = abcdef\n'
       'Oct 12 04:42:00 sent http://reportview.example/x?id=SECRETX to 380501234567\n'
       'Oct 12 05:30:00 later line\n')


def database():
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'x.db'
        con = sqlite3.connect(path)
        con.executescript(
            "CREATE TABLE audit(id INTEGER PRIMARY KEY, actor_id INT, action TEXT, entity_type TEXT, entity_id INT,"
            " field TEXT, old_value TEXT, new_value TEXT, created_at TEXT);"
            "CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT);"
            "INSERT INTO cars VALUES (17, 'UA-0017');"
            "INSERT INTO audit VALUES (1, 555, 'update', 'cars', 17, 'diag_text', '', 'PRIVATE TEXT', '2026-10-12T04:41:05');"
            "INSERT INTO audit VALUES (2, 555, 'update', 'cars', 17, 'vin', '', 'X', '2026-10-11T04:41:05');")
        con.commit()
        con.close()
        return path.read_bytes()


class Fake:
    def server(self, path):
        return {c.DATABASE: database(), c.LOG: LOG.encode()}.get(path)


class ProbeTests(unittest.TestCase):
    def test_scope(self):
        reader = c.Reader('test-value', opener=object())
        for bad in ('', '/home/Carix/cars_ui.py', '/var/log/other.log', 'crm.db'):
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
        self.assertEqual(evidence['log']['window_lines'], 3)
        self.assertIn('voice watchdog failed', evidence['log']['lines'][0])
        self.assertEqual(evidence['log']['lines'][1], '[REDACTED]')
        self.assertEqual(evidence['audit'], [{'action': 'update', 'entity_type': 'cars', 'entity_id': 17,
                                              'field': 'diag_text', 'old_chars': 0, 'new_chars': 12,
                                              'created_at': '2026-10-12T04:41:05', 'auto_number': 'UA-0017'}])
        for secret in ('SECRETX', '380501234567', 'PRIVATE TEXT', 'abcdef', '555'):
            self.assertNotIn(secret, raw)


if __name__ == '__main__':
    unittest.main()
