"""Staff invite without a time limit: any unused CRM invite passes; used, unknown or malformed ones do not."""
import contextlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import ua_staff_invite  # noqa: E402


class InviteRuleTests(unittest.TestCase):
    def setUp(self):
        self.path = str(Path(tempfile.mkdtemp()) / 'crm.db')
        with contextlib.closing(sqlite3.connect(self.path)) as c, c:
            c.execute('CREATE TABLE invites (code TEXT PRIMARY KEY, role TEXT, created_by INTEGER, created_at TEXT, '
                      'used_by INTEGER, used_at TEXT)')
            c.executemany('INSERT INTO invites VALUES (?,?,?,?,?,?)', [
                ('812DFF', 'admin', 1, '2026-11-05T16:31:56', None, None),
                ('A1B2C3', 'manager', 1, '2025-01-01T10:00:00', None, None),
                ('0A0B0C', 'manager', 1, '2026-11-05T17:00:00', 7, '2026-11-05T17:10:00')])

    def test_unused_codes_pass_whatever_their_age(self):
        self.assertTrue(ua_staff_invite.valid(' 812dff ', self.path))
        self.assertTrue(ua_staff_invite.valid('A1B2C3', self.path))

    def test_used_unknown_or_malformed_codes_do_not(self):
        for text in ('0A0B0C', '7030AC', '', None, 'hello', '812DFF0', 'XYZ123'):
            self.assertFalse(ua_staff_invite.valid(text, self.path), text)

    def test_read_only(self):
        before = Path(self.path).read_bytes()
        ua_staff_invite.valid('812DFF', self.path)
        self.assertEqual(Path(self.path).read_bytes(), before)

    def test_guard_call_signature_unchanged(self):
        # The installed guard calls ua_staff_invite.valid(tekst, DB).
        self.assertEqual(ua_staff_invite.valid.__code__.co_argcount, 2)

    def test_only_the_invite_module_changes(self):
        self.assertEqual(list(candidate_builder.REPLACED_MODULES + candidate_builder.NEW_MODULES), ['ua_staff_invite.py'])


if __name__ == '__main__':
    unittest.main()
