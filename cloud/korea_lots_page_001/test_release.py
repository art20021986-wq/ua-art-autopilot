"""The KOREA-LOTS-PAGE candidate from the sources as installed by KOREA-AUCTION-INSTALL-20261110-R3."""
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import types
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import edit_quick_js  # noqa: E402
import ua_korea_lots  # noqa: E402

FIX = HERE / 'fixtures'
PAGE = (FIX / 'korea_live.html').read_text()
AUCTION_INSTALLED = (FIX / 'auction_installed.txt').read_bytes()


def installed_script():
    """quick-lead.js as KOREA-AUCTION-INSTALL-20261110-R3 left it: the live fixture with that release's edits."""
    path = str(HERE.parent / 'korea_auction_001' / 'edit_quick_js.py')
    loader = importlib.machinery.SourceFileLoader('installed_edit_quick_js', path)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader('installed_edit_quick_js', loader))
    loader.exec_module(module)
    return module.build((FIX / 'quick-lead_live.js').read_bytes())


def auction_module():
    """The new ua_order/auction.py with small stand-ins for the order package it imports."""
    package = types.ModuleType('ua_order'); package.__path__ = []
    contract = types.ModuleType('ua_order.contract')

    class Invalid(ValueError):
        def __init__(self, field):
            self.field = field
            super().__init__(field)

    def text(value, field, minimum=0, maximum=80):
        if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
            raise Invalid(field)
        return value.strip()
    contract.Invalid, contract.text = Invalid, text
    catalog = types.ModuleType('ua_order.catalog'); catalog.LANGUAGES = ('uk', 'ru', 'ka')
    quick = types.ModuleType('ua_order.quick')

    def phone(value):
        if not str(value).startswith('+'):
            raise Invalid('contact')
        return value
    quick.phone = phone
    sys.modules.update({'ua_order': package, 'ua_order.contract': contract, 'ua_order.catalog': catalog,
                        'ua_order.quick': quick})
    loader = importlib.machinery.SourceFileLoader('ua_order.auction', str(HERE / 'auction.py'))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader('ua_order.auction', loader))
    loader.exec_module(module)
    return module, Invalid


class CandidateTests(unittest.TestCase):
    def source(self):
        return {'video/korea.html': PAGE.encode(), 'ua_order/auction.py': AUCTION_INSTALLED,
                'video/order/quick-lead.js': installed_script()}

    def test_page_gets_the_list_and_nothing_else(self):
        result = candidate_builder.build(self.source(), {})
        page = result['video/korea.html'].decode()
        self.assertEqual(page.count(ua_korea_lots.MARK), 1)
        self.assertEqual(ua_korea_lots.remove(page), PAGE)
        self.assertEqual(page.count(ua_korea_lots.WATCH_TO), 2)
        self.assertNotIn(ua_korea_lots.WATCH_FROM, page)
        self.assertEqual((page.count(ua_korea_lots.LABEL_TO), page.count('Дивитися онлайн')), (2, 0))
        self.assertNotIn('beforward', page.lower())
        self.assertIn('/video/korea/lots.json', page)
        self.assertIn('data-quick-lead-lot', page)
        self.assertEqual(result['ua_order/auction.py'], (HERE / 'auction.py').read_bytes())
        self.assertIn(b'payload.lot = {id: form.dataset.lot', result['video/order/quick-lead.js'])

    def test_other_installed_auction_module_is_refused(self):
        source = self.source()
        source['ua_order/auction.py'] += b'# edited'
        with self.assertRaises(ValueError):
            candidate_builder.build(source, {})

    def test_second_build_refused(self):
        result = candidate_builder.build(self.source(), {})
        with self.assertRaises(ValueError):
            edit_quick_js.build(result['video/order/quick-lead.js'])
        self.assertEqual(ua_korea_lots.apply(result['video/korea.html'].decode()), result['video/korea.html'].decode())


class AuctionLotTests(unittest.TestCase):
    def setUp(self):
        self.auction, self.Invalid = auction_module()
        self.catalog = types.SimpleNamespace(version='v1')
        self.data = {'schema_version': self.auction.SCHEMA, 'request_id': '6f1c1b1e-1111-4a4a-8a8a-123456789abc',
                     'config_version': 'v1', 'purchase_country_code': 'korea', 'customer_name': 'Іван',
                     'contact': {'phone': '+380991112233'}, 'lang': 'uk', 'source_path': '/video/korea.html',
                     'consent': {'accepted': True, 'version': 'c1'}}

    def test_enquiry_without_a_lot_still_works(self):
        self.assertNotIn('lot', self.auction.normalize(self.data, self.catalog, 'c1'))

    def test_chosen_lot_is_kept_and_shown_in_the_crm(self):
        value = self.auction.normalize(dict(self.data, lot={'id': '20261111000123', 'title': 'Kia K5 2021'}),
                                       self.catalog, 'c1')
        self.assertEqual(value['lot'], {'id': '20261111000123', 'title': 'Kia K5 2021'})
        row = {'number': 'UA-1', 'data': value}
        self.assertIn('Kia K5 2021 (лот 20261111000123)', self.auction.detail(row, self.catalog)['text'])

    def test_bad_lot_is_refused(self):
        for lot in ({'id': 'x', 'title': 'Kia'}, {'id': '20261111000123'}, 'Kia', {'id': 1, 'title': 'Kia'}):
            with self.assertRaises(self.Invalid):
                self.auction.normalize(dict(self.data, lot=lot), self.catalog, 'c1')
        with self.assertRaises(self.Invalid):
            self.auction.normalize(dict(self.data, extra=1), self.catalog, 'c1')

    def test_invalid_phone_with_lot_is_the_contact_field(self):
        """What the live check after the install expects (deployment_controller.INTAKE_FIELD)."""
        data = dict(self.data, contact={'phone': 'x'}, lot={'id': '20261111000001', 'title': 'Перевірка'})
        with self.assertRaises(self.Invalid) as error:
            self.auction.normalize(data, self.catalog, 'c1')
        self.assertEqual(error.exception.field, 'contact')


if __name__ == '__main__':
    unittest.main()
