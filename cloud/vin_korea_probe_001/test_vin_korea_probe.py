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


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'VIN-KOREA-PROBE-20261115'

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
                         ('PASS', 'cloud/vin_korea_probe_001/20261115.json'))

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
        self.assertIn('vinkrprobe-', Path(transport.__file__).read_text())

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


LOT = {'maker': 'HYUNDAI', 'model': 'SONATA', 'model_code': 'DN8', 'trim': 'LPI', 'year': 2022, 'engine_cc': 1999,
       'transmission': 'AT', 'vin': 'KMHL141EBNA111111'}


class RemoteTests(unittest.TestCase):
    def test_groups_and_consistency(self):
        lots = [LOT, dict(LOT, vin='KMHL141EBNA222222'), dict(LOT, vin='KNAG541BBNA333333', model='K5'),
                dict(LOT, vin='KNAG541BBNA444444', model='K5', engine_cc=1598)]
        found = remote.groups(lots)
        self.assertEqual(remote.consistency(found), {'groups_2plus': 2, 'one_answer': 1, 'several_answers': 1,
                                                     'lots_in_2plus': 4, 'lots_matching_top': 3})
        value = remote.lookup('KMHL141EBNA246813', lots, found)
        self.assertEqual(value['vin11'], 'KMHL141EBNA')
        self.assertEqual(value['same_group'], [(('HYUNDAI', 'SONATA', 'DN8', '1999', 'AT'), 2)])
        self.assertEqual(value['exact_lot'], [])

    def test_crm_cars_read_only_korean_only(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(remote, 'ROOT', Path(temp)):
            with sqlite3.connect(Path(temp) / 'crm.db') as db:
                db.execute('CREATE TABLE cars(id INTEGER, vin TEXT, model TEXT, year INTEGER, price INTEGER)')
                db.execute("INSERT INTO cars VALUES(1,'kmhl341dbna241966','Sonata',2022,9000)")
                db.execute("INSERT INTO cars VALUES(2,'WDDZF4KB1KA596783','E 220',2019,9000)")
            columns, vin_column, cars = remote.crm_cars()
        self.assertEqual(vin_column, 'vin')
        self.assertEqual(cars, [{'vin': 'KMHL341DBNA241966', 'model': 'Sonata', 'year': 2022}])


if __name__ == '__main__':
    unittest.main()
