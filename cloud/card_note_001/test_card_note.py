#!/usr/bin/env python3
"""Card note fix: the plan, compare-and-set write and rollback on a real SQLite file, the whole lifecycle, page check."""
from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import card_note  # noqa: E402
import deployment_controller as controller  # noqa: E402
import deployment_remote as remote  # noqa: E402

HINT = card_note.HINT
SCHEMA = ('CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, vin TEXT, model TEXT, year TEXT, '
          'condition_text TEXT, opisanie TEXT, price_uah)')
LINE = '🚘 Mercedes-Benz B-Class 2013 — уже в пути в Украину'
TEXT = ('Описание\nСейчас: ' + LINE + '\n\nБез ДТП.\n📩 Для бронирования напишите нашему менеджеру.\n\n' + HINT
        + '\n\n' + card_note.PROMPT)
FIXED = LINE + '\n\nБез ДТП.\n📩 Для бронирования напишите нашему менеджеру.'
SCRIPT = ('(function(){var dictionaries = {"ru":{"Повторити":"Повторить"},"uk":{"Повторить":"Повторити",'
          '"Сейчас: ' + LINE + '":"Зараз: 🚘 Mercedes-Benz B-Class 2013 — уже в дорозі в Україну"},'
          '"ka":{"Сейчас: ' + LINE + '":"ახლა: 🚘 Mercedes-Benz B-Class 2013 — უკვე გზაშია"}};})();')
ROWS = [(5, 'UA-0005', 'WDD2462011J123456', 'B-Class', '2013', TEXT, 'Описание', 9900),
        (7, 'UA-0007', 'WDD2452322J660244', 'B 180', '2012', 'Чисто.\n' + HINT, None, 8000)]
COLUMNS = ('id', 'auto_number', 'vin', 'model', 'year', 'condition_text', 'opisanie', 'price_uah')


def as_rows(*rows):
    return [dict(zip(COLUMNS, row)) for row in rows]


class PlanTests(unittest.TestCase):
    def test_plan_removes_only_the_hint_line_of_ua0005(self):
        plan = card_note.plan_for(as_rows(*ROWS))
        self.assertEqual([(c['auto_number'], c['field'], c['before'], c['after']) for c in plan['changes']], [
            ('UA-0005', 'condition_text', TEXT, FIXED)])
        self.assertEqual(card_note.new_line(plan['changes'][0]), LINE)

    def test_script_edit_adds_only_the_new_line(self):
        edited = card_note.script_edit(SCRIPT, LINE)
        words = card_note.dictionaries(edited)
        self.assertEqual(words['uk'][LINE], '🚘 Mercedes-Benz B-Class 2013 — уже в дорозі в Україну')
        self.assertEqual(words['ka'][LINE], '🚘 Mercedes-Benz B-Class 2013 — უკვე გზაშია')
        before = card_note.dictionaries(SCRIPT)
        self.assertEqual({k: v for k, v in words['uk'].items() if k != LINE}, before['uk'])
        self.assertEqual(words['ru'], before['ru'])
        self.assertEqual(card_note.script_edit(edited, LINE), edited)
        with self.assertRaisesRegex(ValueError, 'SCRIPT_ENTRY_MISSING'):
            card_note.script_edit(SCRIPT, 'другая строка')

    def test_line_rules(self):
        self.assertEqual(card_note.without_hint('a\n  %s  \nb' % HINT), 'a\nb')
        self.assertEqual(card_note.without_hint('Описание\nСейчас: x\ny\n' + card_note.PROMPT), 'Описание\nСейчас: x\ny\n' + card_note.PROMPT)
        self.assertEqual(card_note.without_hint('a\nb'), 'a\nb')
        with self.assertRaisesRegex(ValueError, 'HINT_NOT_ALONE'):
            card_note.plan_for(as_rows((5, 'UA-0005', 'V', 'B', '2013', 'текст ' + HINT, None, 1)))
        with self.assertRaisesRegex(ValueError, 'HINT_ABSENT'):
            card_note.plan_for(as_rows((5, 'UA-0005', 'V', 'B', '2013', 'текст', None, 1)))

    def test_card_found_once(self):
        with self.assertRaisesRegex(ValueError, 'CARD_IDENTITY'):
            card_note.plan_for(as_rows(ROWS[1]))
        with self.assertRaisesRegex(ValueError, 'CARD_IDENTITY'):
            card_note.plan_for(as_rows(ROWS[0], ROWS[0]))

    def test_only_approved_edits_are_allowed(self):
        change = card_note.plan_for(as_rows(*ROWS))['changes'][0]
        self.assertTrue(card_note.allowed(change))
        bad = [dict(change, field='vin'), dict(change, after='free text'), dict(change, auto_number='UA-0007'),
               dict(change, before='Без ДТП.', after='Без ДТП.'), dict(change, after='Сейчас: ' + FIXED)]
        self.assertFalse(any(card_note.allowed(c) for c in bad))


class CrmWriteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name)/'crm.db'
        with closing(sqlite3.connect(self.db)) as con:
            con.execute(SCHEMA)
            con.executemany('INSERT INTO cars VALUES(%s)' % ','.join('?' * len(COLUMNS)), ROWS)
            con.commit()
        (Path(self.temp.name)/'video').mkdir()
        self.script = Path(self.temp.name)/card_note.SCRIPT
        self.script.write_text(SCRIPT, encoding='utf-8')
        patcher = patch.object(remote, 'ROOT', Path(self.temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def connect(self):
        return closing(sqlite3.connect(self.db))

    def all_rows(self):
        with self.connect() as con:
            return remote.rows(con)

    def test_prepare_lists_change_and_row_hashes(self):
        plan = remote.prepare()
        self.assertEqual(len(plan['changes']), 1)
        rows = {r['id']: r for r in self.all_rows()}
        self.assertEqual(plan['rows_before_sha256'], {'5': remote.row_digest(rows[5])})
        self.assertNotEqual(plan['rows_after_sha256']['5'], plan['rows_before_sha256']['5'])
        self.assertEqual(plan['script']['line'], LINE)
        self.assertEqual(plan['script']['after_sha256'], remote.sha(card_note.script_edit(SCRIPT, LINE).encode()))

    def test_apply_writes_only_the_line_and_rollback_restores(self):
        before = self.all_rows()
        changes = remote.prepare()['changes']
        with self.connect() as con:
            remote.apply(con, changes, True)
            con.commit()
        after = {r['auto_number']: r for r in self.all_rows()}
        self.assertEqual(after['UA-0005']['condition_text'], FIXED)
        self.assertEqual(after['UA-0007'], {r['auto_number']: r for r in before}['UA-0007'])
        with self.connect() as con:
            remote.apply(con, changes, True)  # idempotent
            remote.apply(con, changes, False)
            con.commit()
        self.assertEqual(self.all_rows(), before)

    def test_concurrent_edit_refused(self):
        changes = remote.prepare()['changes']
        with self.connect() as con:
            con.execute("UPDATE cars SET condition_text='новый текст' WHERE id=5")
            with self.assertRaisesRegex(remote.DeploymentError, 'CONCURRENT_CHANGE:condition_text'):
                remote.apply(con, changes, True)

    def test_field_outside_scope_refused(self):
        changes = remote.prepare()['changes']
        changes[0]['field'] = 'vin'
        with self.connect() as con:
            with self.assertRaisesRegex(remote.DeploymentError, 'FIELD_SCOPE'):
                remote.apply(con, changes, True)

    def test_other_value_change_refused(self):
        changes = remote.prepare()['changes']
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
        (self.saved/remote.SCRIPT_COPY).write_text(SCRIPT, encoding='utf-8')
        self.events = []
        before = self.all_rows()
        plan = remote.prepare()
        result = self.run_lifecycle('install', plan)
        self.assertTrue(result['installed'])
        rows = {str(r['id']): r for r in self.all_rows()}
        self.assertEqual(remote.row_digest(rows['5']), plan['rows_after_sha256']['5'])
        self.assertIn(LINE, card_note.dictionaries(self.script.read_text(encoding='utf-8'))['uk'])
        result = self.run_lifecycle('rollback', plan)
        self.assertTrue(result['restored'])
        self.assertEqual(self.all_rows(), before)
        self.assertEqual(self.script.read_text(encoding='utf-8'), SCRIPT)
        self.assertEqual(self.events, [False, True, False, True])

    def test_concurrent_edit_fails_and_crm_kept(self):
        self.saved = Path(self.temp.name)/'backup'
        self.saved.mkdir()
        self.events = []
        plan = remote.prepare()
        with self.connect() as con:
            con.execute("UPDATE cars SET condition_text='правка' WHERE id=5")
            con.commit()
        before = self.all_rows()
        result = self.run_lifecycle('install', plan)
        self.assertEqual((result['status'], result['error']), ('FAIL', 'DeploymentError:CONCURRENT_CHANGE:condition_text'))
        self.assertEqual(self.all_rows(), before)
        self.assertEqual(self.events, [False, True])

    def test_script_changed_by_someone_else_refused_and_crm_kept(self):
        self.saved = Path(self.temp.name)/'backup'
        self.saved.mkdir()
        self.events = []
        before = self.all_rows()
        plan = remote.prepare()
        self.script.write_text(SCRIPT + '//', encoding='utf-8')
        result = self.run_lifecycle('install', plan)
        self.assertEqual((result['status'], result['error']), ('FAIL', 'DeploymentError:SCRIPT_CONCURRENT_CHANGE'))
        self.assertEqual(self.all_rows(), before)


class PublicVerifyTests(unittest.TestCase):
    CHANGES = card_note.plan_for(as_rows(*ROWS))['changes']

    @staticmethod
    def pages(stale):
        def page(name):
            if not stale or 'UA-0005' not in name:
                return 'x' * 2000
            return 'x' * 2000 + ''.join(card_note.MARKS['ua/' if name.startswith('ua/') else ''])
        return page

    def test_marks_cover_every_version_in_its_language(self):
        marks = controller.stale_marks(self.CHANGES)
        self.assertEqual(sorted(marks), ['UA-0005.html', 'ru/UA-0005.html', 'ua/UA-0005.html'])
        self.assertEqual(marks['ua/UA-0005.html'], set(card_note.UK_MARKS))

    def test_install_waits_until_the_line_is_gone(self):
        result = controller.public_verify(self.CHANGES, fetch=self.pages(False), sleep=None, clock=lambda: 0)
        self.assertEqual(set(result.values()), {'PASS'})
        with self.assertRaisesRegex(RuntimeError, 'REPUBLISH_TIMEOUT:UA-0005.html,ru/UA-0005.html,ua/UA-0005.html'):
            controller.public_verify(self.CHANGES, fetch=self.pages(True), sleep=lambda s: None,
                                     clock=iter([0, 10**6]).__next__)

    def test_rollback_waits_until_the_line_is_back(self):
        result = controller.public_verify(self.CHANGES, forward=False, fetch=self.pages(True), sleep=None, clock=lambda: 0)
        self.assertEqual(set(result.values()), {'PASS'})


if __name__ == '__main__':
    unittest.main()
