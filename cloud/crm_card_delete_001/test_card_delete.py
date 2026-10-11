#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import sqlite3
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ua_card_delete', HERE / 'ua_card_delete.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FakeDb:
    """Minimal in-memory stand-in for db.py with the same call signatures."""

    def __init__(self, published=1):
        self.con = sqlite3.connect(':memory:')
        self.con.row_factory = sqlite3.Row
        self.con.executescript(
            'CREATE TABLE cars(id INTEGER PRIMARY KEY, auto_number TEXT, published INT);'
            'CREATE TABLE audit(action TEXT, entity_id INT, old_value TEXT);')
        self.con.execute('INSERT INTO cars VALUES (14, "UA-0008", ?)', (published,))

    def get_card(self, table, cid):
        row = self.con.execute('SELECT * FROM %s WHERE id=?' % table, (cid,)).fetchone()
        return dict(row) if row else None

    def update_card_field(self, table, cid, field, value, actor_id):
        self.con.execute('UPDATE %s SET %s=? WHERE id=?' % (table, field), (value, cid))

    def connect(self):
        return self.con

    def log_action(self, actor_id, action, entity_type, entity_id, field, old_value, new_value):
        self.con.execute('INSERT INTO audit VALUES (?,?,?)', (action, entity_id, old_value))

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
        # The catalog must be rebuilt while the card is already unpublished.
        self.seen = self.db.get_card('cars', 14)
        if self.error:
            raise self.error
        return self.result


class DeleteCardTests(unittest.TestCase):
    def test_published_card_leaves_site_before_crm(self):
        db = FakeDb()
        pub = Publisher().bind(db)
        result = m.delete_card(14, 1, db=db, publisher=pub)
        self.assertTrue(result.deleted)
        self.assertEqual(pub.calls, 1)
        self.assertEqual(pub.seen['published'], 0)
        self.assertIsNone(db.get_card('cars', 14))
        self.assertEqual(db.audit(), [('card_delete', 14, 'UA-0008')])

    def test_catalog_failure_keeps_card_unchanged(self):
        for pub in (Publisher(result=(False, 'mismatch')), Publisher(error=RuntimeError('timeout'))):
            db = FakeDb()
            result = m.delete_card(14, 1, db=db, publisher=pub.bind(db))
            self.assertFalse(result.deleted)
            self.assertIn('Удаление отменено', result.text)
            self.assertEqual(db.get_card('cars', 14)['published'], 1)
            self.assertEqual(db.audit(), [])

    def test_unpublished_card_needs_no_catalog_rebuild(self):
        db = FakeDb(published=0)
        pub = Publisher().bind(db)
        self.assertTrue(m.delete_card(14, 1, db=db, publisher=pub).deleted)
        self.assertEqual(pub.calls, 0)
        self.assertIsNone(db.get_card('cars', 14))

    def test_repeated_press_is_harmless(self):
        db = FakeDb()
        pub = Publisher().bind(db)
        m.delete_card(14, 1, db=db, publisher=pub)
        again = m.delete_card(14, 1, db=db, publisher=pub)
        self.assertEqual(again, m.Result(False, 'Карточка уже удалена.'))
        self.assertEqual(pub.calls, 1)
        self.assertEqual(len(db.audit()), 1)


if __name__ == '__main__':
    unittest.main()
