#!/usr/bin/env python3
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ua_owners  # noqa: E402


def fake_db(ids=None, error=None):
    module = types.ModuleType('db')
    module.ROLE_OWNER = 'owner'

    def staff_ids_by_role(role):
        if error:
            raise error
        return list(ids) if role == 'owner' else []
    module.staff_ids_by_role = staff_ids_by_role
    return module


class OwnersTests(unittest.TestCase):
    def test_configured_first_then_crm_owners_once(self):
        with patch.dict(sys.modules, db=fake_db([20, 10, 30])):
            self.assertEqual(ua_owners.ids('10'), [10, 20, 30])

    def test_crm_unreadable_keeps_the_configured_owner(self):
        with patch.dict(sys.modules, db=fake_db(error=OSError('locked'))), self.assertLogs(level='ERROR'):
            self.assertEqual(ua_owners.ids(10), [10])

    def test_no_configured_chat(self):
        with patch.dict(sys.modules, db=fake_db([20])):
            self.assertEqual(ua_owners.ids(''), [20])
            self.assertEqual(ua_owners.ids(None), [20])
            self.assertEqual(ua_owners.ids('-5'), [20])


if __name__ == '__main__':
    unittest.main()
