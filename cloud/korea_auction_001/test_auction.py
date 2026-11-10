"""auction.py inside a stand-in ua_order package (catalog/contract/quick stubs with the live interfaces)."""
import importlib
import pathlib
import shutil
import sys
import tempfile
import unittest
import uuid

STUBS = {
    'catalog.py': "LANGUAGES = ('uk', 'ru', 'ka')\n",
    'contract.py': ("class Invalid(ValueError):\n    pass\n\n"
                    "def text(value, field, minimum, maximum=80):\n"
                    "    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:\n"
                    "        raise Invalid(field)\n    return value.strip()\n"),
    'quick.py': ("import re\nfrom .contract import Invalid\n\ndef phone(value):\n"
                 "    digits = re.sub(r'[ ()-]', '', value)\n"
                 "    if re.fullmatch(r'0[0-9]{9}', digits):\n        digits = '+38' + digits\n"
                 "    if not re.fullmatch(r'\\+[1-9][0-9]{6,14}', digits):\n        raise Invalid('contact')\n"
                 "    return digits\n"),
}


class Catalog:
    version = '2026-09-27.1'


class AuctionLeadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        pkg = pathlib.Path(cls.tmp, 'ua_order')
        pkg.mkdir()
        (pkg / '__init__.py').write_text('')
        for name, body in STUBS.items():
            (pkg / name).write_text(body)
        shutil.copy(pathlib.Path(__file__).with_name('auction.py'), pkg / 'auction.py')
        sys.path.insert(0, cls.tmp)
        cls.m = importlib.import_module('ua_order.auction')
        cls.Invalid = importlib.import_module('ua_order.contract').Invalid

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(cls.tmp)
        shutil.rmtree(cls.tmp)

    def request(self, **change):
        data = {'schema_version': 'ua_order_request.auction.v1', 'request_id': str(uuid.uuid4()),
                'config_version': Catalog.version, 'purchase_country_code': 'korea', 'customer_name': 'Іван',
                'contact': {'phone': '067 123 45 67'}, 'lang': 'uk', 'source_path': '/video/korea.html',
                'consent': {'accepted': True, 'version': 'c1'}}
        data.update(change)
        return data

    def test_valid_request(self):
        out = self.m.normalize(self.request(), Catalog, 'c1')
        self.assertEqual(out['contact'], {'phone': '+380671234567'})
        self.assertEqual(out['purchase_country_code'], 'korea')

    def test_rejected(self):
        for change, field in (({'source_path': '/video/index.html'}, 'source_path'),
                              ({'purchase_country_code': 'japan'}, 'purchase_country_code'),
                              ({'contact': {'phone': '12'}}, 'contact'),
                              ({'consent': {'accepted': False, 'version': 'c1'}}, 'consent'),
                              ({'config_version': 'old'}, 'config_version'),
                              ({'extra': 1}, 'fields')):
            with self.assertRaises(self.Invalid) as err:
                self.m.normalize(self.request(**change), Catalog, 'c1')
            self.assertEqual(str(err.exception), field)

    def test_payload_sent_by_the_browser(self):
        # captured from the site's dialog on the built page (quick-lead.js + edit_quick_js), 2026-11-10
        sent = {'schema_version': 'ua_order_request.auction.v1', 'request_id': str(uuid.uuid4()),
                'config_version': Catalog.version, 'customer_name': 'Іван', 'contact': {'phone': '067 123 45 67'},
                'lang': 'uk', 'source_path': '/video/korea.html', 'consent': {'accepted': True, 'version': 'c1'},
                'purchase_country_code': 'korea'}
        self.assertEqual(self.m.normalize(sent, Catalog, 'c1')['customer_name'], 'Іван')

    def test_list_label(self):
        self.assertEqual(self.m.label({'purchase_country_code': 'korea'}), 'Аукционы онлайн: Корея')

    def test_inbox_detail(self):
        row = {'number': 'Z-15', 'data': self.m.normalize(self.request(), Catalog, 'c1')}
        text = self.m.detail(row, Catalog)['text']
        self.assertIn('Доступ к аукционам онлайн', text)
        self.assertIn('+380671234567', text)


class QuickJsEditTest(unittest.TestCase):
    def test_live_script_patched_once(self):
        import edit_quick_js as e
        live = pathlib.Path(__file__).with_name('fixtures').joinpath('quick-lead_live.js').read_bytes()
        out = e.build(live)
        self.assertIn(b'[data-quick-lead-auction]', out)
        self.assertIn(b"payload.schema_version = 'ua_order_request.auction.v1'", out)
        self.assertEqual(out.replace(b'\n', b'').count(b'ua_order_request.card.v1'),
                         live.replace(b'\n', b'').count(b'ua_order_request.card.v1'))
        with self.assertRaises(ValueError):
            e.build(out)


class IntakeEditTest(unittest.TestCase):
    def test_hooks_once_and_refuses_twice(self):
        import edit_intake as e
        contract = ("        return normalize_quick(data, catalog, consent_version)\n").encode()
        out = e.build(e.CONTRACT, contract)
        self.assertIn(b'ua_order_request.auction.v1', out)
        with self.assertRaises(ValueError):
            e.build(e.CONTRACT, out)

    def test_crm_hooks_on_the_installed_card_version(self):
        import edit_intake as e
        crm = ("        if data.get('schema_version') == 'ua_order_request.card.v1':\n"
               "            from .card_lead import label as card_label\n"
               "            country = card_label(data)\n"
               "        else:\n"
               "            country = preference_summary.country_label(data, catalog)\n"
               "        return quick_detail(row, catalog)\n").encode()
        out = e.build(e.CRM, crm).decode()
        self.assertIn("from .auction import label as auction_label", out)
        self.assertIn("from .auction import detail as auction_detail", out)
        compile('def f(data, row, catalog):\n    if True:\n' + out.replace('        return quick_detail', '        x = 1\n        return quick_detail'), 'crm', 'exec')




class OrderStringsEditTest(unittest.TestCase):
    def test_only_titles_change(self):
        import json
        import edit_order_strings as e
        live = pathlib.Path(__file__).with_name('fixtures').joinpath('order-strings_live.json').read_bytes()
        out = e.build(live)
        old, new = json.loads(live), json.loads(out)
        changed = [(lang, key) for lang in old for key in old[lang] if old[lang][key] != new[lang][key]]
        self.assertEqual(sorted(changed), [('ka', 'title'), ('ru', 'title'), ('uk', 'title')])
        self.assertEqual(new['uk']['title'], 'Індивідуальне замовлення автомобіля')
        self.assertEqual(len(out.splitlines()), len(live.splitlines()))
        with self.assertRaises(ValueError):
            e.build(out)


if __name__ == '__main__':
    unittest.main()
