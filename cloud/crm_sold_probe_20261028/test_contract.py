#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('sold_probe', HERE / 'controller.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class Response:
    status = 200

    def __init__(self, url, payload=b'x'):
        self.url, self.payload = url, payload

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        value, self.payload = self.payload[:size], self.payload[size:]
        return value


class Opener:
    def __init__(self):
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request.get_method(), request.full_url, request.data))
        return Response(request.full_url)


def sample_db(path):
    con = sqlite3.connect(path)
    con.executescript('''
        CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, brand TEXT, model TEXT, status TEXT, published INT);
        CREATE TABLE media(id INTEGER PRIMARY KEY, car_id INT REFERENCES cars(id), path TEXT);
        CREATE TABLE log(id INTEGER PRIMARY KEY, user_id INT, action TEXT, record_id INT, new_value TEXT);
        INSERT INTO cars VALUES (7, 'UA-0017', 'Audi', 'A6', 'sold', 0);
        INSERT INTO cars VALUES (8, 'UA-0008', 'Kia', 'K5', 'kr_bought', 1);
        INSERT INTO media VALUES (1, 7, 'a.jpg'), (2, 7, 'b.jpg');
        INSERT INTO log VALUES (1, 123456789, 'car_sold', 7, '+380 67 123 45 67');
        INSERT INTO log VALUES (2, 123456789, 'card_delete', 8, 'x');
    ''')
    con.commit()
    con.close()


class ContractTests(unittest.TestCase):
    def test_get_only_fixed_allowlist(self):
        op = Opener()
        api = c.ReadOnlyAPI('test-value', opener=op)
        api.read('files/path/home/Carix/cars_ui.py')
        self.assertEqual(op.calls, [('GET', c.BASE + 'files/path/home/Carix/cars_ui.py', None)])
        for endpoint in ('files/path/home/Carix/.env', 'always_on/', '../x', 'https://evil.invalid/'):
            with self.assertRaises(c.ProbeError):
                api.read(endpoint)
        self.assertEqual(len(op.calls), 1)

    def test_source_selection_and_secret_skip(self):
        raw = (b'def other():\n    return "private"\n'
               b'async def mark_sold_ok(u, c):\n    return 1\n'
               b'def leak():\n    token = "abc"\n    return obnovit_katalog()\n')
        facts, excerpt = c.inspect_source(raw, '/home/Carix/cars_ui.py')
        self.assertIn('mark_sold_ok', excerpt)
        self.assertNotIn('private', excerpt)
        self.assertNotIn('abc', excerpt)
        self.assertEqual([d['excerpt'] for d in facts['definitions']], ['EXPORTED', 'OMITTED_SENSITIVE'])
        facts, excerpt = c.inspect_source(raw, '/home/Carix/ua_crm_public_sync.py')
        self.assertIn('def other', excerpt)
        self.assertNotIn('abc', excerpt)

    def test_scope_is_fixed_read_list(self):
        self.assertEqual(len(c.ENDPOINTS), 9)
        self.assertEqual(c.ENDPOINTS[-3:], ('files/path/home/Carix/video/katalog.html',
                                            'files/path/var/log/alwayson-log-266084.log',
                                            'files/path/home/Carix/crm.db'))
        self.assertTrue(all(e.startswith('files/path/home/Carix/') and e.endswith('.py') for e in c.ENDPOINTS[:-3]))

    def test_catalog_numbers(self):
        raw = b'<a href="UA-0017.html">x</a><a href=\'/video/UA-0020.html\'>y</a><a href="UA-0017.html">'
        self.assertEqual(c.inspect_catalog(raw)['car_numbers'], ['UA-0017', 'UA-0020'])

    def test_log_keeps_delete_context_and_redacts_numbers(self):
        raw = ('noise\n' * 50 + 'WARNING CRM sync failed; retry pending: UA-0017\n'
               'phone +380 67 123 45 67\nTOKEN=secret\n').encode()
        facts = c.inspect_log(raw)
        text = '\n'.join(facts['lines'])
        self.assertIn('CRM sync failed', text)
        self.assertNotIn('123 45 67', text)
        self.assertNotIn('secret', text)
        self.assertLess(facts['matched_lines_exported'], 20)

    def test_database_facts_without_private_columns(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'src.db'
            sample_db(path)
            payload = path.read_bytes()
            facts = c.inspect_database(payload, temp)
            self.assertFalse((Path(temp) / 'crm_copy.db').exists())
        self.assertEqual([(car['auto_number'], car['status']) for car in facts['all_cars']],
                         [('UA-0017', 'sold'), ('UA-0008', 'kr_bought')])
        self.assertEqual(facts['foreign_keys'][0]['to_table'], 'cars')
        dumped = json.dumps(facts)
        self.assertNotIn('123456789', dumped)
        self.assertNotIn('45 67', dumped)
        self.assertEqual([r['action'] for r in facts['status_actions'][0]['rows']], ['car_sold'])

    def test_execute_records_partial_failures_without_claims(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = root / c.REQUEST
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'task_id': c.TASK_ID, 'production_required': False, 'read_only': True}))
            env = {'UAART_TASK_ID': c.TASK_ID, 'UAART_TASK_CLASS': 'STANDARD', 'UAART_REQUEST_PATH': c.REQUEST,
                   'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '1',
                   'UAART_RECEIPT_PATH': c.RECEIPT}

            class Partial:
                def read(self, endpoint):
                    if endpoint.endswith('cars_ui.py'):
                        return b'async def mark_sold_ok():\n    return None\n'
                    raise c.ProbeError('HTTP_404')
            receipt = c.execute(env, root=root, api=Partial())
            evidence = json.loads((root / c.EVIDENCE).read_text())
            self.assertFalse(receipt['deletion_performed'])
            self.assertEqual(evidence['remote_write_count'], 0)
            self.assertEqual(len(evidence['path_status']), len(c.ENDPOINTS))
            self.assertEqual(len(receipt['unavailable_paths']), len(c.ENDPOINTS) - 1)
            with self.assertRaises(c.ProbeError):
                c.execute(env, root=root, api=Partial())

    def test_identity_mismatch_refused(self):
        with self.assertRaises(c.ProbeError):
            c.execute({'UAART_TASK_ID': 'OTHER'}, root='/nonexistent', api=object())


if __name__ == '__main__':
    unittest.main()
