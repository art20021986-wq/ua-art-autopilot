#!/usr/bin/env python3
"""Card enquiry schema in the live order package (fixtures are the installed sources, byte for byte)."""
import importlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import edit_order  # noqa: E402

CONSENT = 'consent-2026'
REQUEST = '6f2c5a1e-8a51-4f56-9a0f-3f1d2b3c4d5e'


class Catalog:
    version = 'cat-1'

    def export(self):
        return {'countries': {'korea': {}}}

    def country(self, code):
        return {'name': {'ru': 'Корея'}}


def payload(**changes):
    value = {'schema_version': 'ua_order_request.card.v1', 'request_id': REQUEST, 'config_version': 'cat-1',
             'car_code': 'UA-0018', 'customer_name': ' Иван ', 'contact': {'phone': '099 222 20 02'}, 'lang': 'ru',
             'source_path': '/video/ru/UA-0018.html', 'consent': {'accepted': True, 'version': CONSENT}}
    value.update(changes)
    return value


class OrderPackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.mkdtemp()
        package = Path(cls.temp) / 'ua_order'
        shutil.copytree(HERE / 'fixtures/ua_order', package)
        (package / '__init__.py').write_text('')
        # crm.py imports preference_summary; the installed one needs the full preferences catalogue.
        (package / 'preference_summary.py').write_text(
            "def country_label(data, catalog, lang='ru'):\n    return catalog.country(data['purchase_country_code'])['name'][lang]\n")
        for name in edit_order.EDITS:
            path = Path(cls.temp) / name
            path.write_bytes(edit_order.build(name, path.read_bytes()))
        shutil.copy(HERE / 'card_lead.py', package / 'card_lead.py')
        sys.path.insert(0, cls.temp)
        for name in [n for n in sys.modules if n == 'ua_order' or n.startswith('ua_order.')]:
            del sys.modules[name]
        cls.contract = importlib.import_module('ua_order.contract')
        cls.crm = importlib.import_module('ua_order.crm')
        cls.Invalid = cls.contract.Invalid

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(cls.temp)
        shutil.rmtree(cls.temp)

    def normalize(self, value):
        return self.contract.normalize(value, Catalog(), CONSENT)

    def test_card_enquiry_saved_clean(self):
        data = self.normalize(payload())
        self.assertEqual((data['car_code'], data['customer_name'], data['contact']), ('UA-0018', 'Иван', {'phone': '+380992222002'}))

    def test_attribution_kept(self):
        data = self.normalize(payload(attribution={'utm_source': 'google'}))
        self.assertEqual(data['attribution'], {'utm_source': 'google'})

    def test_refused(self):
        cases = {'car_code': payload(car_code='UA-18'), 'source_path': payload(source_path='/video/ru/UA-0019.html'),
                 'fields': payload(model='x'), 'consent': payload(consent={'accepted': True, 'version': 'old'}),
                 'contact': payload(contact={'phone': 'abc'})}
        for field, value in cases.items():
            with self.assertRaises(self.Invalid, msg=field) as caught:
                self.normalize(value)
            self.assertEqual(caught.exception.field, field)
        for page in ('/video/UA-0018.html', '/video/ua/UA-0018.html', '/site/UA-0018.html'):
            self.assertEqual(self.normalize(payload(source_path=page))['source_path'], page)

    def test_other_schemas_unchanged(self):
        with self.assertRaises(self.Invalid):
            self.normalize(payload(schema_version='ua_order_request.quick.v1'))

    def test_owner_views(self):
        row = {'id': 7, 'number': 'OR-000007', 'data': self.normalize(payload()), 'telegram_user_id': None}
        text = self.crm.detail_view(row, Catalog())['text']
        for part in ('OR-000007', 'Связаться с менеджером (карточка авто)', 'Иван', '+380992222002', 'UA-0018'):
            self.assertIn(part, text)

        class Repository:
            def list_requests(self, before=None):
                return [row], None
        view = self.crm.list_view(Repository(), Catalog())
        self.assertEqual(view['buttons'][0][0], ('Иван · UA-0018', 'orders:open:7'))

    def test_edit_refused_twice(self):
        for name in edit_order.EDITS:
            source = (HERE / 'fixtures' / name).read_bytes()
            with self.assertRaises(ValueError):
                edit_order.build(name, edit_order.build(name, source))


if __name__ == '__main__':
    unittest.main()
