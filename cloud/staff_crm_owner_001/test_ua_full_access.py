#!/usr/bin/env python3
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ua_full_access as access  # noqa: E402


def fake_db(staff=None, error=None):
    module = types.ModuleType('db')
    module.ROLE_OWNER, module.ROLE_ADMIN, module.ROLE_MANAGER = 'owner', 'admin', 'manager'

    def staff_ids_by_role(role):
        if error:
            raise error
        return [uid for uid, r in (staff or []) if r == role]
    module.staff_ids_by_role = staff_ids_by_role
    return module


class FullAccessTests(unittest.TestCase):
    def test_owner_and_managing_admin_not_manager(self):
        with patch.dict(sys.modules, db=fake_db([(10, 'owner'), (20, 'admin'), (30, 'manager')])):
            self.assertEqual(access.roles(), ('owner', 'admin'))
            self.assertEqual(access.ids(), [10, 20])

    def test_configured_chat_first_and_once(self):
        with patch.dict(sys.modules, db=fake_db([(20, 'admin'), (10, 'owner')])):
            self.assertEqual(access.ids('10'), [10, 20])

    def test_crm_unreadable_keeps_the_configured_chat(self):
        with patch.dict(sys.modules, db=fake_db(error=OSError('locked'))), self.assertLogs(level='ERROR'):
            self.assertEqual(access.ids(10), [10])

    def test_no_configured_chat(self):
        with patch.dict(sys.modules, db=fake_db([(20, 'admin')])):
            self.assertEqual(access.ids(''), [20])
            self.assertEqual(access.ids(None), [20])


if __name__ == '__main__':
    unittest.main()
