#!/usr/bin/env python3
"""UA-0025 VIN fill: only empty fields, compare-and-set write and rollback on a real SQLite file, public check."""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deployment_controller as controller  # noqa: E402
import deployment_remote as remote  # noqa: E402
import vin_fill  # noqa: E402

VIN = vin_fill.VIN
# The owner's VIN decoded by the installed ua_vin_decode on the server (preview NEW-CAR-VIN-SPEC-PREFLIGHT-20261114-B).
DECODED = {'model': 'E-Class', 'year': 2019, 'engine_cc': 2000, 'fuel': 'бензин', 'gearbox': 'автомат', 'drive': 'полный'}
SCHEMA = ('CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, vin TEXT, published INTEGER, brand TEXT, '
          'model TEXT, year TEXT, engine_cc, fuel TEXT, gearbox, drive, color TEXT, price_uah)')
ROWS = [(25, 'UA-0025', VIN, 0, 'Mercedes-Benz', None, None, None, None, None, None, None, None),
        (7, 'UA-0007', 'WDD2452322J660244', 1, 'Mercedes-Benz', 'B 180', '2012', 1700, 'бензин', 'автомат', 'передний',
         'чёрный', 9900)]


class PlanTests(unittest.TestCase):
    def row(self, **values):
        return dict(zip(('id', 'auto_number', 'vin', 'published', 'brand', 'model', 'year', 'engine_cc', 'fuel',
                         'gearbox', 'drive', 'color', 'price_uah'), ROWS[0]), **values)

    def test_every_empty_field_is_listed(self):
        changes = vin_fill.changes_for(self.row(), DECODED)
        self.assertEqual([(c['field'], c['before'], c['after']) for c in changes],
                         [(f, None, DECODED[f]) for f in vin_fill.FIELDS])

    def test_filled_fields_are_never_touched(self):
        changes = vin_fill.changes_for(self.row(model='E 300', year='', gearbox='механика', engine_cc=0), DECODED)
        self.assertEqual([c['field'] for c in changes], ['year', 'engine_cc', 'fuel', 'drive'])

    def test_other_card_refused(self):
        for values in ({'auto_number': 'UA-0026'}, {'vin': 'WDD2452322J660244'}):
            with self.assertRaisesRegex(ValueError, 'CARD_IDENTITY'):
                vin_fill.changes_for(self.row(**values), DECODED)


class CrmWriteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name)/'crm.db'
        with closing(sqlite3.connect(self.db)) as con:
            con.execute(SCHEMA)
            con.executemany('INSERT INTO cars VALUES(%s)' % ','.join('?' * len(ROWS[0])), ROWS)
            con.commit()
        patcher = patch.object(remote, 'ROOT', Path(self.temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def connect(self):
        return closing(sqlite3.connect(self.db))

    def all_rows(self):
        with self.connect() as con:
            return remote.rows(con)

    def test_prepare_lists_changes_and_row_hashes(self):
        with patch.object(remote, 'decoded', return_value=DECODED):
            plan = remote.prepare()
        self.assertEqual(len(plan['changes']), 6)
        self.assertEqual(plan['row_before_sha256'], remote.row_digest(self.all_rows()[1]))
        self.assertNotEqual(plan['row_after_sha256'], plan['row_before_sha256'])

    def test_apply_fills_only_the_listed_fields_and_rollback_restores(self):
        before = self.all_rows()
        changes = vin_fill.changes_for(before[1], DECODED)
        with self.connect() as con:
            remote.apply(con, changes, True)
            con.commit()
        after = {r['auto_number']: r for r in self.all_rows()}
        self.assertEqual(after['UA-0025']['year'], '2019')  # TEXT column keeps the year as text
        self.assertEqual((after['UA-0025']['model'], after['UA-0025']['engine_cc'], after['UA-0025']['drive']),
                         ('E-Class', 2000, 'полный'))
        self.assertEqual(after['UA-0007'], {r['auto_number']: r for r in before}['UA-0007'])
        self.assertEqual(after['UA-0025']['brand'], 'Mercedes-Benz')
        with self.connect() as con:
            remote.apply(con, changes, True)  # idempotent
            remote.apply(con, changes, False)
            con.commit()
        self.assertEqual(self.all_rows(), before)

    def test_concurrent_edit_refused(self):
        changes = vin_fill.changes_for(self.all_rows()[1], DECODED)
        with self.connect() as con:
            con.execute("UPDATE cars SET gearbox='механика' WHERE id=25")
            with self.assertRaisesRegex(remote.DeploymentError, 'CONCURRENT_CHANGE:gearbox'):
                remote.apply(con, changes, True)

    def test_unknown_field_refused(self):
        changes = vin_fill.changes_for(self.all_rows()[1], DECODED)
        changes[0]['field'] = 'price_uah'
        with self.connect() as con:
            with self.assertRaisesRegex(remote.DeploymentError, 'FIELD_SCOPE'):
                remote.apply(con, changes, True)

    def test_other_value_change_refused(self):
        changes = vin_fill.changes_for(self.all_rows()[1], DECODED)
        real = remote.rows

        def rows_with_drift(connection, calls=[]):
            calls.append(1)
            if len(calls) == 2:
                connection.execute('UPDATE cars SET price_uah=1 WHERE id=7')
            return real(connection)
        with self.connect() as con, patch.object(remote, 'rows', side_effect=rows_with_drift):
            with self.assertRaisesRegex(remote.DeploymentError, 'UNEXPECTED_CRM_CHANGE'):
                remote.apply(con, changes, True)


class LifecycleTests(CrmWriteTests):
    """The whole install and rollback lifecycle on this package's real plan (bot pause, locks, journal, resume)."""

    def run_lifecycle(self, mode, plan):
        from contextlib import contextmanager
        events = self.events

        class FakeApi:
            enabled = True

            def __init__(self, token):
                pass

            def bot(self):
                return {'enabled': FakeApi.enabled, 'state': 'running' if FakeApi.enabled else 'stopped'}

            def set_bot(self, enabled):
                FakeApi.enabled = enabled
                events.append(enabled)
                return self.bot()

        @contextmanager
        def writer():
            with self.connect() as con:
                con.execute('BEGIN IMMEDIATE')
                try:
                    yield con
                finally:
                    con.rollback()
        manifest = {'plan': plan, 'plan_sha256': remote.sha(remote.canonical(plan)), 'run_id': '1'}
        with patch.object(remote, 'API', FakeApi), patch.object(remote, 'load_backup', return_value=(self.saved, manifest)), \
                patch.object(remote, 'writer_exclusion', writer), patch.object(remote, 'no_bot_processes'), \
                patch.object(remote, 'pending_pages', return_value={}):
            return remote.lifecycle(mode, '1', manifest['plan_sha256'], 'a' * 64)

    def test_install_then_rollback(self):
        self.saved = Path(self.temp.name)/'backup'
        self.saved.mkdir()
        self.events = []
        before = self.all_rows()
        with patch.object(remote, 'decoded', return_value=DECODED):
            plan = remote.prepare()
        result = self.run_lifecycle('install', plan)
        self.assertTrue(result['installed'])
        self.assertEqual(remote.row_digest({r['auto_number']: r for r in self.all_rows()}['UA-0025']),
                         plan['row_after_sha256'])
        filled = {r['auto_number']: r for r in self.all_rows()}['UA-0025']
        self.assertEqual((filled['model'], filled['year'], filled['gearbox']), ('E-Class', '2019', 'автомат'))
        result = self.run_lifecycle('rollback', plan)
        self.assertTrue(result['restored'])
        self.assertEqual(self.all_rows(), before)
        self.assertEqual(self.events, [False, True, False, True])


class PublicVerifyTests(unittest.TestCase):
    def test_unpublished_card_needs_page_health_only(self):
        changes = [{'auto_number': 'UA-0025', 'published': 0, 'field': 'model', 'before': None, 'after': 'E-Class'}]
        result = controller.public_verify(changes, fetch=lambda name: 'x' * 2000, sleep=None, clock=lambda: 0)
        self.assertEqual(result, {'/video/katalog.html': 'PASS', '/video/index.html': 'PASS'})


if __name__ == '__main__':
    unittest.main()
