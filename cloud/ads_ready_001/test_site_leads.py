#!/usr/bin/env python3
"""ua_site_leads: who may open the site enquiries in the CRM bot, and where «В меню» goes."""
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import ua_site_leads


def update(user_id):
    return SimpleNamespace(effective_user=SimpleNamespace(id=user_id) if user_id else None)


class SiteLeadsTests(unittest.TestCase):
    def setUp(self):
        staff = {1: {'active': 1, 'role': 'owner'}, 2: {'active': 1, 'role': 'manager'},
                 3: {'active': 0, 'role': 'admin'}, 4: {'active': 1, 'role': 'viewer'}}
        db = types.ModuleType('db')
        db.ROLE_OWNER, db.ROLE_ADMIN, db.ROLE_MANAGER = 'owner', 'admin', 'manager'
        db.get_staff = staff.get
        patcher = patch.dict(sys.modules, {'db': db})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_only_active_owner_admin_manager(self):
        self.assertEqual([ua_site_leads.allowed(update(u)) for u in (1, 2, 3, 4, 5, None)],
                         [True, True, False, False, False, False])

    def test_without_order_package_nothing_is_registered(self):
        with patch.object(ua_site_leads, '_runtime', return_value=None):
            self.assertIsNone(ua_site_leads.register(object()))
            self.assertFalse(ua_site_leads.available())

    def test_inbox_returns_to_clients(self):
        registered = {}

        class Adapter:
            def __init__(self, repository, catalog, *, authorize, menu_callback):
                registered.update(authorize=authorize, menu=menu_callback, repository=repository)

            def register(self, app, *, group):
                registered['group'] = group
        order = types.ModuleType('ua_order')
        order.__path__ = []
        modules = {'ua_order': order,
                   'ua_order.bindings': SimpleNamespace(first_group=lambda app: -5),
                   'ua_order.telegram': SimpleNamespace(CRMAdapter=Adapter)}
        loaded = SimpleNamespace(service=SimpleNamespace(repository='repo', catalog='cat'))
        with patch.dict(sys.modules, modules), patch.object(ua_site_leads, '_runtime', return_value=loaded):
            ua_site_leads.register(object())
        self.assertEqual(registered, {'authorize': ua_site_leads.allowed, 'menu': 'cards_clients',
                                      'repository': 'repo', 'group': -5})


if __name__ == '__main__':
    unittest.main()
