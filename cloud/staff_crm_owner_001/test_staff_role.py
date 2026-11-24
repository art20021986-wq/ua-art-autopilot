#!/usr/bin/env python3
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import staff_role as r  # noqa: E402

SCHEMA = """
CREATE TABLE staff (user_id INTEGER PRIMARY KEY, full_name TEXT, username TEXT, role TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1, added_by INTEGER, added_at TEXT NOT NULL, note TEXT);
CREATE TABLE audit (id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id INTEGER, action TEXT NOT NULL, entity_type TEXT,
                    entity_id INTEGER, field TEXT, old_value TEXT, new_value TEXT, created_at TEXT NOT NULL);
CREATE TABLE cars (id INTEGER PRIMARY KEY, title TEXT);
"""


def crm(*staff):
    connection = sqlite3.connect(':memory:')
    connection.executescript(SCHEMA)
    connection.executemany('INSERT INTO staff VALUES (?,?,?,?,?,?,?,?)', staff)
    connection.execute("INSERT INTO cars VALUES (1, 'Kia')")
    return connection


OWNER = (1, 'Owner', 'own', 'owner', 1, None, 't0', None)
MANAGER = (2, 'OlG', 'Beetle204', 'admin', 1, 1, 't1', None)


class RoleTests(unittest.TestCase):
    def test_promote_exactly_one_role_and_one_audit_row(self):
        c = crm(OWNER, MANAGER)
        before = r.snapshot(c)
        self.assertEqual(r.promote(c, 't2'), (2, 1))
        after = r.snapshot(c)
        r.verify(before, after, 2, 'admin', 'owner')
        self.assertEqual(c.execute('SELECT role FROM staff WHERE user_id=2').fetchone(), ('owner',))
        self.assertEqual(after['audit'][-1][1:], (1, 'staff_role', 'staff', 2, 'role', 'admin', 'owner', 't2'))

    def test_demote_restores_the_role(self):
        c = crm(OWNER, MANAGER)
        r.promote(c, 't2')
        before = r.snapshot(c)
        r.demote(c, 2, 1, 't3')
        r.verify(before, r.snapshot(c), 2, 'owner', 'admin')

    def test_target_must_be_one_active_admin(self):
        for rows in ((OWNER,), (OWNER, MANAGER[:4] + (0,) + MANAGER[5:]), (OWNER, MANAGER[:3] + ('manager',) + MANAGER[4:])):
            with self.subTest(rows=len(rows)), self.assertRaisesRegex(r.RoleError, 'ROLE_TARGET_COUNT'):
                r.promote(crm(*rows), 't2')

    def test_second_owner_stops(self):
        with self.assertRaisesRegex(r.RoleError, 'ROLE_TARGET_COUNT'):
            r.promote(crm(OWNER, (3, 'X', 'x', 'owner', 1, None, 't', None), MANAGER), 't2')

    def test_any_other_change_is_caught(self):
        c = crm(OWNER, MANAGER)
        before = r.snapshot(c)
        r.promote(c, 't2')
        c.execute("UPDATE cars SET title='Hyundai'")
        with self.assertRaisesRegex(r.RoleError, 'CRM_OTHER_DATA_CHANGED'):
            r.verify(before, r.snapshot(c), 2, 'admin', 'owner')
        c = crm(OWNER, MANAGER)
        before = r.snapshot(c)
        r.promote(c, 't2')
        c.execute("UPDATE staff SET full_name='Z' WHERE user_id=1")
        with self.assertRaisesRegex(r.RoleError, 'STAFF_OTHER_ROW_CHANGED'):
            r.verify(before, r.snapshot(c), 2, 'admin', 'owner')


if __name__ == '__main__':
    unittest.main()
