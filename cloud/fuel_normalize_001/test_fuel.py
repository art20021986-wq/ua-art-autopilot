#!/usr/bin/env python3
"""Fuel vocabulary, the compare-and-set CRM change, its rollback and the public check."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deployment_controller as controller  # noqa: E402
import deployment_remote as remote  # noqa: E402
from fuel_vocabulary import normalize  # noqa: E402

ROWS = [(1, 'UA-0017', 1, 'diesel', 21000), (2, 'UA-0005', 1, 'Дизель', 11500), (3, 'UA-0020', 1, 'дизель', 17700),
        (4, 'UA-0022', 1, 'LPI', 20200), (5, 'UA-0018', 1, 'газ', 19300), (6, 'UA-0002', 0, 'Diesel ', 9000),
        (7, 'UA-0030', 1, 'гибрид', 30000), (8, 'UA-0031', 1, None, 1)]


class VocabularyTests(unittest.TestCase):
    def test_owner_vocabulary(self):
        for raw, name in (('diesel', 'дизель'), ('Дизель', 'дизель'), (' DIESEL ', 'дизель'), ('LPI', 'LPI'),
                          ('lpi', 'LPI'), ('ЛПИ', 'LPI'), ('LPG', 'газ'), ('Газ', 'газ'), ('Petrol', 'бензин'),
                          ('бензин', 'бензин')):
            self.assertEqual(normalize(raw), name)
        for raw in ('гибрид', '', None, 'газ/бензин'):
            self.assertIsNone(normalize(raw))


class CrmChangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name)/'crm.db'
        with closing(sqlite3.connect(self.db)) as con:
            con.execute('CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, published INTEGER, fuel TEXT, price INTEGER)')
            con.executemany('INSERT INTO cars VALUES(?,?,?,?,?)', ROWS)
            con.commit()

    def connect(self):
        return closing(sqlite3.connect(self.db))

    def fuels(self):
        with self.connect() as con:
            return dict(con.execute('SELECT auto_number, fuel FROM cars'))

    def test_plan_lists_only_other_spellings(self):
        with self.connect() as con:
            changes = remote.changes_for(remote.rows(con))
        self.assertEqual([(c['auto_number'], c['before'], c['after'], c['published']) for c in changes],
                         [('UA-0017', 'diesel', 'дизель', 1), ('UA-0005', 'Дизель', 'дизель', 1),
                          ('UA-0002', 'Diesel ', 'дизель', 0)])

    def test_apply_and_rollback_touch_only_fuel(self):
        with self.connect() as con:
            changes = remote.changes_for(remote.rows(con))
            remote.apply(con, changes, True)
            con.commit()
        after = self.fuels()
        self.assertEqual((after['UA-0017'], after['UA-0005'], after['UA-0002'], after['UA-0030']),
                         ('дизель', 'дизель', 'дизель', 'гибрид'))
        with self.connect() as con:
            remote.apply(con, changes, True)  # idempotent
            remote.apply(con, changes, False)
            con.commit()
        self.assertEqual(self.fuels(), {r[1]: r[3] for r in ROWS})

    def test_concurrent_edit_refused(self):
        with self.connect() as con:
            changes = remote.changes_for(remote.rows(con))
            con.execute("UPDATE cars SET fuel='бензин' WHERE auto_number='UA-0005'")
            with self.assertRaisesRegex(remote.DeploymentError, 'CONCURRENT_CHANGE:UA-0005'):
                remote.apply(con, changes, True)

    def test_other_value_change_refused(self):
        with self.connect() as con:
            changes = remote.changes_for(remote.rows(con))
            changes[0]['after'] = 'дизель'
            real = remote.rows
            def rows_with_drift(connection, calls=[]):
                calls.append(1)
                if len(calls) == 2:
                    connection.execute('UPDATE cars SET price=1 WHERE id=3')
                return real(connection)
            with patch.object(remote, 'rows', side_effect=rows_with_drift):
                with self.assertRaisesRegex(remote.DeploymentError, 'UNEXPECTED_CRM_CHANGE'):
                    remote.apply(con, changes, True)


def catalog(fuels):
    cards = ''.join('<article class="catalog-card" data-stage="x"><div class="catalog-top"><span>%s</span></div>'
                    '<p>118000 км · 2967 см³ · %s · автомат</p></article>' % (code, fuel) for code, fuel in fuels.items())
    return '<html>' + 'x' * 1000 + cards + '</html>'


class PublicVerifyTests(unittest.TestCase):
    CHANGES = [{'auto_number': 'UA-0017', 'published': 1, 'before': 'diesel', 'after': 'дизель'},
               {'auto_number': 'UA-0002', 'published': 0, 'before': 'Diesel', 'after': 'дизель'}]

    def test_waits_for_republication(self):
        pages = iter([catalog({'UA-0017': 'diesel'}), catalog({'UA-0017': 'дизель'})])
        def fetch(name):
            return next(pages) if name == 'katalog.html' else 'x' * 1000 + 'дизель'
        sleeps = []
        result = controller.public_verify(self.CHANGES, fetch=fetch, sleep=sleeps.append, clock=lambda: 0)
        self.assertEqual(result, {'/video/katalog.html': 'PASS', '/video/index.html': 'PASS', '/video/UA-0017.html': 'PASS'})
        self.assertEqual(sleeps, [20])

    def test_timeout(self):
        times = iter([0, 0, 2000])
        with self.assertRaisesRegex(RuntimeError, 'REPUBLISH_TIMEOUT:UA-0017'):
            controller.public_verify(self.CHANGES, fetch=lambda n: catalog({'UA-0017': 'diesel'}),
                                     sleep=lambda s: None, clock=lambda: next(times))

    def test_case_of_old_spelling_matters(self):
        changes = [{'auto_number': 'UA-0005', 'published': 1, 'before': 'Дизель', 'after': 'дизель'}]
        fetch = lambda n: catalog({'UA-0005': 'дизель'}) if n == 'katalog.html' else 'x' * 1000 + 'дизель'
        self.assertEqual(controller.public_verify(changes, fetch=fetch, sleep=None, clock=lambda: 0)['/video/UA-0005.html'], 'PASS')


class FakeAPI:
    def __init__(self):
        self.calls = []

    def bot(self):
        return {'enabled': True, 'state': 'running'}

    def set_bot(self, enabled):
        self.calls.append(enabled)
        return {'enabled': enabled, 'state': 'running' if enabled else 'stopped'}


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'video').mkdir()
        (self.root/'video/katalog.html').write_text('catalog')
        (self.root/'db.py').write_text('code')
        with closing(sqlite3.connect(self.root/'crm.db')) as con:
            con.execute('CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, published INTEGER, fuel TEXT, price INTEGER)')
            con.executemany('INSERT INTO cars VALUES(?,?,?,?,?)', ROWS)
            con.commit()
        self.api = FakeAPI()
        for target, value in ((remote, 'ROOT'), (remote, 'HERE')):
            patcher = patch.object(target, value, self.root)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, value in (('API', lambda token: self.api), ('PROTECTED', ('db.py',)),
                            ('no_bot_processes', lambda: None), ('writer_exclusion', self.exclusion)):
            patcher = patch.object(remote, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def exclusion(self):
        from contextlib import contextmanager
        @contextmanager
        def held():
            with closing(sqlite3.connect(self.root/'crm.db')) as con:
                con.execute('BEGIN IMMEDIATE')
                try:
                    yield con
                finally:
                    con.rollback()
        return held()

    def fuel(self, code):
        with closing(sqlite3.connect(self.root/'crm.db')) as con:
            return con.execute('SELECT fuel FROM cars WHERE auto_number=?', (code,)).fetchone()[0]

    def test_install_verify_rollback(self):
        plan = remote.prepare()
        self.assertEqual(plan['unknown_values'], ['гибрид'])
        plan_sha = remote.sha(remote.canonical(plan))
        backup = remote.backup('5', plan_sha)['backup_manifest_sha256']
        result = remote.lifecycle('install', '5', plan_sha, backup)
        self.assertEqual((result['status'], result['installed'], result['crm_unchanged']), ('PASS', True, True))
        self.assertEqual((self.fuel('UA-0017'), self.api.calls), ('дизель', [False, True]))
        self.assertEqual(remote.installed('5', plan_sha, backup)['plan'], plan)
        result = remote.lifecycle('rollback', '5', plan_sha, backup)
        self.assertEqual((result['status'], result['restored'], self.fuel('UA-0017')), ('PASS', True, 'diesel'))

    def test_drifted_plan_refused_at_backup(self):
        plan_sha = remote.sha(remote.canonical(remote.prepare()))
        with closing(sqlite3.connect(self.root/'crm.db')) as con:
            con.execute("UPDATE cars SET fuel='дизель' WHERE id=1")
            con.commit()
        with self.assertRaisesRegex(remote.DeploymentError, 'LIVE_PLAN_DRIFT'):
            remote.backup('6', plan_sha)

    def test_failed_install_changes_nothing_and_resumes_bot(self):
        plan = remote.prepare()
        plan_sha = remote.sha(remote.canonical(plan))
        backup = remote.backup('7', plan_sha)['backup_manifest_sha256']
        (self.root/'db.py').write_text('edited')
        result = remote.lifecycle('install', '7', plan_sha, backup)
        self.assertEqual((result['status'], self.fuel('UA-0017'), self.api.calls), ('FAIL', 'diesel', [False, True]))
        self.assertIn('PROTECTED_CHANGED', result['error'])


class ScopeTests(unittest.TestCase):
    def test_remote_scope_per_mode(self):
        base = {'status': 'PASS', 'run_id': '1', 'safe_to_stop': True}
        controller.accepted(dict(base, mode='install', crm_write=True), 'install', '1')
        controller.accepted(dict(base, mode='verify', crm_write=False), 'verify', '1')
        with self.assertRaisesRegex(RuntimeError, 'REMOTE_SCOPE'):
            controller.accepted(dict(base, mode='preview', crm_write=True), 'preview', '1')


if __name__ == '__main__':
    unittest.main()
