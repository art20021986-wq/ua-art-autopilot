#!/usr/bin/env python3
"""JAPAN-STOCK-001 step 1: the exact edits on the live sources (fixtures: sanitized copies read by
JAPAN-STOCK-PROBE-20261126-R2), the stage choices and labels, the car country storage and the menu rows."""
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import edit_cars_ui  # noqa: E402
import edit_delivery_status  # noqa: E402
import edit_konteyner  # noqa: E402
import edits  # noqa: E402

LIVE = {e.NAME: (HERE / 'fixtures' / e.NAME.replace('.py', '.txt')).read_bytes()
        for e in (edit_delivery_status, edit_cars_ui, edit_konteyner)}


def module(name, source):
    folder = tempfile.mkdtemp()
    path = Path(folder) / (name + '.py')
    path.write_bytes(source)
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def statuses():
    return module('ds_built', edit_delivery_status.build(LIVE['ua_delivery_status.py']))


class EditTests(unittest.TestCase):
    def text(self, edit):
        return edits.replace_once(LIVE[edit.NAME].decode(), edit.PAIRS, edit.NAME)

    def test_each_anchor_once_and_not_twice(self):
        for edit in (edit_delivery_status, edit_cars_ui, edit_konteyner):
            after = self.text(edit)
            with self.assertRaisesRegex(ValueError, 'EDIT_ANCHOR'):
                edits.replace_once(after, edit.PAIRS, edit.NAME)

    def test_cars_ui_changes_only_stage_labels_and_menu(self):
        before, after = LIVE['cars_ui.py'].decode(), self.text(edit_cars_ui)
        self.assertEqual(after.count('S.status_label('), before.count('S.status_label(') - 8 + 2)  # 8 uses replaced; the helper falls back twice
        self.assertNotIn('public_status(card.get("status")) == code', after)
        self.assertEqual(after.count('_ua_jp_label('), 10)  # the helper and 9 uses
        self.assertIn('ua_car_country.set_country(cid, CHOICE_COUNTRY[requested], q.from_user.id)', after)
        self.assertLess(after.index('ua_car_country.set_country('), after.index('set_field(cid, "status", code'))
        removed = [line for line in before.splitlines() if line not in after.splitlines()]
        self.assertEqual(len(removed), 11)

    def test_konteyner_marks_the_country_choice(self):
        after = self.text(edit_konteyner)
        self.assertIn('choice_code(card.get("status"), country) == code', after)
        compile(after, 'konteyner.py', 'exec')


class StatusTests(unittest.TestCase):
    def test_choices_rows_and_storage(self):
        ds = statuses()
        rows = []
        for number in (1, 2, 3, 4):
            pair = [label for _, _, no, label in ds.CHOICES if no == number]
            rows += [pair[i:i + 2] for i in range(0, len(pair), 2)]
        self.assertEqual(rows, [['В Корее', 'В Японии'], ['Паром Корея', 'Паром Япония'], ['В Грузии'], ['В Киеве']])
        self.assertEqual({c: ds.storage_status(c) for c, *_ in ds.CHOICES},
                         {'korea': 'kr_bought', 'japan': 'kr_bought', 'ferry': 'sea_loaded', 'ferry_jp': 'sea_loaded',
                          'georgia': 'ge_waiting', 'kyiv': 'ua_arrived'})
        for bad in ('hidden', 'archive', None, 5):
            self.assertEqual(ds.storage_status(bad), 'hidden')

    def test_public_view_unchanged(self):
        ds = statuses()
        self.assertEqual(ds.LABELS['ferry'], 'На пароме')
        self.assertEqual(ds.catalog_counts(['kr_bought', 'sea_loaded', 'ge_waiting', 'archive']),
                         {'korea': 1, 'ferry': 1, 'georgia': 1, 'kyiv': 0})
        self.assertEqual(ds.public_label('kr_bought'), 'В Корее')
        self.assertEqual(ds.stage_number('sea_loaded'), 2)

    def test_country_labels(self):
        ds = statuses()
        self.assertEqual(ds.choice_label('kr_bought', 'japan'), 'В Японии')
        self.assertEqual(ds.choice_label('sea_loaded', 'japan'), 'Паром Япония')
        self.assertEqual(ds.choice_label('sea_loaded', 'korea'), 'Паром Корея')
        self.assertEqual(ds.choice_label('ge_waiting', 'japan'), 'В Грузии')
        self.assertIsNone(ds.choice_label('archive', 'japan'))
        self.assertEqual(ds.choice_code('kr_bought', 'japan'), 'japan')
        self.assertEqual(ds.choice_code('ua_arrived', 'japan'), 'kyiv')


class CountryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        database = Path(folder.name) / 'crm.db'
        sqlite3.connect(database).close()
        self.journal = []
        fake = types.ModuleType('db')
        fake.connect = lambda: sqlite3.connect(database)
        fake.now = lambda: '2026-11-26T10:00:00'
        fake.log_action = lambda *a: self.journal.append(a)
        with patch.dict(sys.modules, {'db': fake}):
            self.cc = module('cc_built', (HERE / 'ua_car_country.py').read_bytes())
        self.database = database

    def test_default_korea_without_table(self):
        self.assertEqual(self.cc.country_of(1), 'korea')
        self.assertEqual(self.cc.japan_ids(), frozenset())
        self.assertFalse(self.cc.set_country(1, 'korea', 9))
        with sqlite3.connect(self.database) as connection:
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='car_country'").fetchone())
        self.assertEqual(self.journal, [])

    def test_save_change_and_journal(self):
        self.assertTrue(self.cc.set_country(5, 'japan', 9))
        self.assertFalse(self.cc.set_country(5, 'japan', 9))
        self.assertEqual((self.cc.country_of(5), self.cc.japan_ids()), ('japan', frozenset({5})))
        self.assertTrue(self.cc.set_country(5, 'korea', 9))
        self.assertEqual(self.cc.country_of(5), 'korea')
        self.assertEqual(self.journal, [(9, 'card_edit', 'cars', 5, 'country', 'korea', 'japan'),
                                        (9, 'card_edit', 'cars', 5, 'country', 'japan', 'korea')])

    def test_refuses_unknown_country(self):
        with self.assertRaises(ValueError):
            self.cc.set_country(5, 'usa', 9)
        with self.assertRaises(sqlite3.IntegrityError):
            with sqlite3.connect(self.database) as connection:
                connection.execute(self.cc._TABLE)
                connection.execute("INSERT INTO car_country VALUES (1, 'usa', 'x')")


if __name__ == '__main__':
    unittest.main()
