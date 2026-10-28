#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import sqlite3
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ua_card_sold', HERE / 'ua_card_sold.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FakeDb:
    """Minimal in-memory stand-in for db.py; 'sold' is stored as 'hidden' like the live CRM."""

    def __init__(self, published=1, status='ua_arrived'):
        self.con = sqlite3.connect(':memory:')
        self.con.row_factory = sqlite3.Row
        self.con.executescript(
            'CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, published INT, status TEXT);'
            'CREATE TABLE audit(field TEXT, old_value TEXT, new_value TEXT);')
        self.con.execute('INSERT INTO cars VALUES (30, "UA-0020", ?, ?)', (published, status))

    def get_card(self, table, cid):
        row = self.con.execute('SELECT * FROM %s WHERE id=?' % table, (cid,)).fetchone()
        return dict(row) if row else None

    def update_card_field(self, table, cid, field, value, actor_id):
        if field == 'status' and value == 'sold':
            value = 'hidden'
        old = self.get_card(table, cid)[field]
        self.con.execute('UPDATE %s SET %s=? WHERE id=?' % (table, field), (value, cid))
        self.con.execute('INSERT INTO audit VALUES (?,?,?)', (field, str(old), str(value)))

    def audit(self):
        return [tuple(r) for r in self.con.execute('SELECT * FROM audit')]


class Publisher:
    def __init__(self, result=(True, 'ok'), error=None):
        self.result, self.error, self.calls, self.seen = result, error, 0, None

    def bind(self, db):
        self.db = db
        return self

    def obnovit_katalog(self):
        self.calls += 1
        # The catalog must be rebuilt while the card is already unpublished and sold.
        self.seen = self.db.get_card('cars', 30)
        if self.error:
            raise self.error
        return self.result


class MarkSoldTests(unittest.TestCase):
    def test_sold_card_leaves_catalog_and_stays_in_crm(self):
        db = FakeDb()
        pub = Publisher().bind(db)
        result = m.mark_sold(30, 1, db=db, publisher=pub)
        self.assertTrue(result.sold)
        self.assertIn('UA-0020', result.text)
        self.assertEqual(pub.calls, 1)
        self.assertEqual((pub.seen['published'], pub.seen['status']), (0, 'hidden'))
        self.assertEqual(db.get_card('cars', 30)['auto_number'], 'UA-0020')
        self.assertEqual([a[0] for a in db.audit()], ['published', 'status'])

    def test_catalog_failure_restores_card(self):
        for pub in (Publisher(result=(False, 'mismatch')), Publisher(error=RuntimeError('timeout'))):
            db = FakeDb()
            result = m.mark_sold(30, 1, db=db, publisher=pub.bind(db))
            self.assertFalse(result.sold)
            self.assertIn('Карточка не изменена', result.text)
            card = db.get_card('cars', 30)
            self.assertEqual((card['published'], card['status']), (1, 'ua_arrived'))

    def test_already_unpublished_sold_car_is_removed_on_repeat(self):
        # Today's case: CRM already says sold/unpublished, catalog still shows the car.
        db = FakeDb(published=0, status='hidden')
        pub = Publisher().bind(db)
        self.assertTrue(m.mark_sold(30, 1, db=db, publisher=pub).sold)
        self.assertEqual(pub.calls, 1)
        failing = FakeDb(published=0, status='hidden')
        m.mark_sold(30, 1, db=failing, publisher=Publisher(result=(False, 'x')).bind(failing))
        card = failing.get_card('cars', 30)
        self.assertEqual((card['published'], card['status']), (0, 'hidden'))

    def test_missing_card(self):
        db = FakeDb()
        pub = Publisher().bind(db)
        self.assertEqual(m.mark_sold(99, 1, db=db, publisher=pub), m.Result(False, 'Карточка не найдена.'))
        self.assertEqual(pub.calls, 0)


if __name__ == '__main__':
    unittest.main()
