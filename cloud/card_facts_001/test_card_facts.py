#!/usr/bin/env python3
"""Card facts fix: the plan, compare-and-set write and rollback on a real SQLite file, the whole lifecycle, page check."""
from contextlib import closing, contextmanager
import datetime
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import card_facts  # noqa: E402
import deployment_controller as controller  # noqa: E402
import deployment_remote as remote  # noqa: E402

TODAY = datetime.date(2026, 11, 17)
SCHEMA = ('CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, vin TEXT, published INTEGER, model TEXT, '
          'year TEXT, status TEXT, eta_manual TEXT, sea_date_out TEXT, opisanie TEXT, opisanie_uk TEXT, price_uah)')
K5_TEXT = 'Kia K5 2022 — эффектный чёрный седан\nКомплектация 2022 года'
ROWS = [(21, 'UA-0021', card_facts.SONATA_VIN, 1, 'Sonata', '2022', 'ge_customs', '2026-10-27', '2026-08-10',
         'Sonata 2022', None, 19500),
        (23, 'UA-0023', card_facts.K5_VIN, 1, 'K5', '2021', 'ua_kyiv', None, None, K5_TEXT,
         'Kia K5 2022 — ефектний чорний седан', 17000),
        (7, 'UA-0007', 'WDD2452322J660244', 1, 'B 180', '2012', 'ua_kyiv', '2026-10-01', None, 'Kia K5 2022', None, 9900)]
COLUMNS = ('id', 'auto_number', 'vin', 'published', 'model', 'year', 'status', 'eta_manual', 'sea_date_out',
           'opisanie', 'opisanie_uk', 'price_uah')


def as_rows(*rows):
    return [dict(zip(COLUMNS, row)) for row in rows]


class PlanTests(unittest.TestCase):
    def test_plan_lists_exactly_the_approved_changes(self):
        plan = card_facts.plan_for(as_rows(*ROWS), TODAY)
        self.assertEqual([(c['auto_number'], c['field'], c['before'], c['after']) for c in plan['changes']], [
            ('UA-0021', 'eta_manual', '2026-10-27', None),
            ('UA-0023', 'opisanie', K5_TEXT, K5_TEXT.replace('K5 2022', 'K5 2021')),
            ('UA-0023', 'opisanie_uk', 'Kia K5 2022 — ефектний чорний седан', 'Kia K5 2021 — ефектний чорний седан')])
        self.assertEqual(plan['sonata_context']['status'], 'ge_customs')
        self.assertEqual(plan['k5_year'], '2021')
        # «2022 года» stays: only «K5 2022» is the owner's fix; the field is still reported
        self.assertIn('2022 года', plan['changes'][1]['after'])

    def test_future_or_missing_date_is_kept(self):
        for value in ('2026-12-01', '', None, 'скоро'):
            row = as_rows(ROWS[0])[0]
            row['eta_manual'] = value
            self.assertEqual(card_facts.sonata_changes(row, TODAY), [])
        row = as_rows(ROWS[0])[0]
        row['eta_manual'] = '27.10.2026'
        self.assertEqual(len(card_facts.sonata_changes(row, TODAY)), 1)

    def test_cards_are_found_by_vin_once(self):
        with self.assertRaisesRegex(ValueError, 'CARD_IDENTITY'):
            card_facts.plan_for(as_rows(ROWS[0], ROWS[2]), TODAY)
        with self.assertRaisesRegex(ValueError, 'CARD_IDENTITY'):
            card_facts.plan_for(as_rows(ROWS[0], ROWS[1], ROWS[1]), TODAY)

    def test_only_approved_edits_are_allowed(self):
        plan = card_facts.plan_for(as_rows(*ROWS), TODAY)
        self.assertTrue(all(card_facts.allowed(c) for c in plan['changes']))
        bad = [dict(plan['changes'][0], field='price_uah'), dict(plan['changes'][0], after='2026-12-01'),
               dict(plan['changes'][1], after='free text'), dict(plan['changes'][1], field='vin'),
               dict(plan['changes'][1], vin='WDD2452322J660244')]
        self.assertFalse(any(card_facts.allowed(c) for c in bad))


class CrmWriteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name)/'crm.db'
        with closing(sqlite3.connect(self.db)) as con:
            con.execute(SCHEMA)
            con.executemany('INSERT INTO cars VALUES(%s)' % ','.join('?' * len(COLUMNS)), ROWS)
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
        plan = remote.prepare(TODAY)
        self.assertEqual(len(plan['changes']), 3)
        rows = {r['id']: r for r in self.all_rows()}
        self.assertEqual(plan['rows_before_sha256'], {'21': remote.row_digest(rows[21]), '23': remote.row_digest(rows[23])})
        self.assertNotEqual(plan['rows_after_sha256']['23'], plan['rows_before_sha256']['23'])
        self.assertEqual(plan['sonata_release_memory'], {'.srok_gruzia.json': None, '.sroki_gruzia.json': None})

    def test_apply_writes_only_the_listed_fields_and_rollback_restores(self):
        before = self.all_rows()
        changes = remote.prepare(TODAY)['changes']
        with self.connect() as con:
            remote.apply(con, changes, True)
            con.commit()
        after = {r['auto_number']: r for r in self.all_rows()}
        self.assertIsNone(after['UA-0021']['eta_manual'])
        self.assertTrue(after['UA-0023']['opisanie'].startswith('Kia K5 2021'))
        self.assertEqual(after['UA-0007'], {r['auto_number']: r for r in before}['UA-0007'])
        with self.connect() as con:
            remote.apply(con, changes, True)  # idempotent
            remote.apply(con, changes, False)
            con.commit()
        self.assertEqual(self.all_rows(), before)

    def test_concurrent_edit_refused(self):
        changes = remote.prepare(TODAY)['changes']
        with self.connect() as con:
            con.execute("UPDATE cars SET eta_manual='2026-12-05' WHERE id=21")
            with self.assertRaisesRegex(remote.DeploymentError, 'CONCURRENT_CHANGE:eta_manual'):
                remote.apply(con, changes, True)

    def test_field_outside_scope_refused(self):
        changes = remote.prepare(TODAY)['changes']
        changes[0]['field'] = 'price_uah'
        with self.connect() as con:
            with self.assertRaisesRegex(remote.DeploymentError, 'FIELD_SCOPE'):
                remote.apply(con, changes, True)

    def test_other_value_change_refused(self):
        changes = remote.prepare(TODAY)['changes']
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
        plan = remote.prepare(TODAY)
        result = self.run_lifecycle('install', plan)
        self.assertTrue(result['installed'])
        rows = {str(r['id']): r for r in self.all_rows()}
        self.assertEqual({i: remote.row_digest(rows[i]) for i in ('21', '23')}, plan['rows_after_sha256'])
        result = self.run_lifecycle('rollback', plan)
        self.assertTrue(result['restored'])
        self.assertEqual(self.all_rows(), before)
        self.assertEqual(self.events, [False, True, False, True])


class PublicVerifyTests(unittest.TestCase):
    CHANGES = card_facts.plan_for(as_rows(*ROWS), TODAY)['changes']

    def pages(self, sonata, k5):
        return lambda name: ('x' * 2000 + (sonata if 'UA-0021' in name else k5 if 'UA-0023' in name else ''))

    def test_marks_cover_every_version_of_both_cards(self):
        marks = controller.stale_marks(self.CHANGES)
        self.assertEqual(marks['ua/UA-0021.html'], {'27 октября 2026'})
        self.assertEqual(sorted(marks), ['UA-0021.html', 'UA-0023.html', 'ru/UA-0021.html', 'ru/UA-0023.html',
                                         'ua/UA-0021.html', 'ua/UA-0023.html'])

    def test_install_waits_until_the_stale_text_is_gone(self):
        fixed = self.pages('Дата прибытия уточняется', 'Kia K5 2021')
        result = controller.public_verify(self.CHANGES, fetch=fixed, sleep=None, clock=lambda: 0)
        self.assertEqual(set(result.values()), {'PASS'})
        stale = self.pages('Ориентировочная дата — 27 октября 2026', 'Kia K5 2021')
        with self.assertRaisesRegex(RuntimeError, 'REPUBLISH_TIMEOUT:UA-0021.html,ru/UA-0021.html,ua/UA-0021.html'):
            controller.public_verify(self.CHANGES, fetch=stale, sleep=lambda s: None, clock=iter([0, 10**6]).__next__)

    def test_rollback_waits_until_the_old_text_is_back(self):
        old = self.pages('27 октября 2026', 'Kia K5 2022')
        result = controller.public_verify(self.CHANGES, forward=False, fetch=old, sleep=None, clock=lambda: 0)
        self.assertEqual(set(result.values()), {'PASS'})


if __name__ == '__main__':
    unittest.main()
