"""Staff invite through the access guard: the invite rule, and the one-block edit of the live guard (probe R9)."""
import contextlib
import datetime
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate  # noqa: E402
import ua_staff_invite  # noqa: E402

GUARD = json.loads((HERE.parent / 'lead_desk_probe_001' / '20261105-R9.json').read_text())['files']['bezopasnost.py']['source']
NOW = datetime.datetime(2026, 11, 5, 18, 0, 0)


class InviteRuleTests(unittest.TestCase):
    def setUp(self):
        self.path = str(Path(tempfile.mkdtemp()) / 'crm.db')
        with contextlib.closing(sqlite3.connect(self.path)) as c, c:
            c.execute('CREATE TABLE invites (code TEXT PRIMARY KEY, role TEXT, created_by INTEGER, created_at TEXT, '
                      'used_by INTEGER, used_at TEXT)')
            c.executemany('INSERT INTO invites VALUES (?,?,?,?,?,?)', [
                ('812DFF', 'admin', 1, '2026-11-05T16:31:56', None, None),
                ('A1B2C3', 'manager', 1, '2026-11-04T17:59:00', None, None),
                ('0A0B0C', 'manager', 1, '2026-11-05T17:00:00', 7, '2026-11-05T17:10:00')])

    def test_fresh_unused_code_passes_any_case_and_spaces(self):
        self.assertTrue(ua_staff_invite.valid(' 812dff ', self.path, NOW))

    def test_old_used_unknown_or_malformed_codes_do_not(self):
        for text in ('A1B2C3', '0A0B0C', '7030AC', '', None, 'hello', '812DFF0', 'XYZ123'):
            self.assertFalse(ua_staff_invite.valid(text, self.path, NOW), text)

    def test_read_only(self):
        before = Path(self.path).read_bytes()
        ua_staff_invite.valid('812DFF', self.path, NOW)
        self.assertEqual(Path(self.path).read_bytes(), before)


class GuardEditTests(unittest.TestCase):
    def test_one_block_before_refusal(self):
        after = candidate.guard(GUARD)
        self.assertEqual(after.replace(candidate.NEW, candidate.OLD, 1), GUARD)
        self.assertLess(after.index(candidate.MARK), after.index('Это рабочий бот компании. Доступ по приглашению.'))
        self.assertGreater(after.index(candidate.MARK), after.index('def _propusk(update):'))
        with self.assertRaises(candidate.CandidateError):
            candidate.guard(after)

    def test_strangers_still_refused(self):
        after = candidate.guard(GUARD)
        self.assertEqual(after.count('Это рабочий бот компании. Доступ по приглашению.'), 1)
        self.assertEqual(after.count('return False'), GUARD.count('return False'))


if __name__ == '__main__':
    unittest.main()
