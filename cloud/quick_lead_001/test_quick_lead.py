#!/usr/bin/env python3
"""Short model-page enquiry: server validation and inbox view on the live order package, the form block, the pages."""
import importlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest
import uuid

HERE = Path(__file__).resolve().parent
# Exact live order package sources (ORDER-INTAKE-PROBE-20261026-R4) and order catalogue (PODBOR-PROBE R3).
LIVE = json.loads((HERE.parent/'order_intake_probe_001/20261026-R4.json').read_text())['package_sources']
CATALOG = json.loads((HERE.parent/'podbor_probe_20261025/live_podbor_r3.json').read_text())['bootstrap']['catalog']
sys.path[:0] = [str(HERE), str(HERE.parent/'seo_models_001'), str(HERE.parent/'gsc_growth_001'),
                str(HERE.parent/'ai_search_001'), str(HERE.parent/'seo_growth_001')]

import edit_intake  # noqa: E402
import ua_seo_landings as landings  # noqa: E402
import ua_seo_quick_form as quick_form  # noqa: E402

CONSENT = 'consent-v1'


def package(temp):
    """The live order package with this release's files, importable as ua_order."""
    root = Path(temp)/'ua_order'
    root.mkdir()
    for name in ('__init__.py', 'catalog.py', 'contract.py', 'crm.py', 'preference_summary.py', 'preferences.py'):
        source = LIVE[name].encode() + b'\n'
        relative = 'ua_order/' + name
        if relative in edit_intake.EDITS:
            source = edit_intake.build(relative, source)
        (root/name).write_bytes(source)
    shutil.copy(HERE/'quick.py', root/'quick.py')
    order = ('korea', 'japan', 'usa', 'europe', 'china', 'canada', 'uae', 'georgia')  # the probe saved sorted keys
    (root/'catalog.json').write_text(json.dumps({**CATALOG, 'countries': {c: CATALOG['countries'][c] for c in order}}),
                                     encoding='utf-8')
    sys.path.insert(0, temp)
    for name in [n for n in sys.modules if n == 'ua_order' or n.startswith('ua_order.')]:
        del sys.modules[name]
    contract, crm, catalog = (importlib.import_module('ua_order.' + n) for n in ('contract', 'crm', 'catalog'))
    sys.path.remove(temp)
    return contract, crm, catalog.Catalog(root/'catalog.json')


def payload(catalog, **change):
    value = {'schema_version': 'ua_order_request.quick.v1', 'request_id': str(uuid.uuid4()),
             'config_version': catalog.version, 'purchase_country_code': 'korea', 'model': 'hyundai-tucson',
             'customer_name': ' Олена ', 'contact': {'phone': '+380 (99) 222-20-02'}, 'lang': 'uk',
             'source_path': '/video/seo/ua/hyundai-tucson-koreya-kyiv.html',
             'consent': {'accepted': True, 'version': CONSENT}}
    value.update(change)
    return value


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.contract, self.crm, self.catalog = package(self.temp)

    def tearDown(self):
        shutil.rmtree(self.temp)

    def normalize(self, **change):
        return self.contract.normalize(payload(self.catalog, **change), self.catalog, CONSENT)

    def test_valid_enquiry(self):
        data = self.normalize()
        self.assertEqual((data['customer_name'], data['contact'], data['model']),
                         ('Олена', {'phone': '+380992222002'}, 'hyundai-tucson'))

    def test_local_ukrainian_numbers(self):
        for typed in ('099 222 20 02', '380992222002'):
            self.assertEqual(self.normalize(contact={'phone': typed})['contact'], {'phone': '+380992222002'})

    def test_rejections(self):
        cases = {'contact': [{'contact': {'phone': '12'}}, {'contact': {'phone': 'abc'}},
                             {'contact': {'phone': '+380992222002', 'telegram': 'x'}}],
                 'customer_name': [{'customer_name': 'A'}],
                 'model': [{'model': 'audi-a6'}, {'purchase_country_code': 'japan'}],
                 'consent': [{'consent': {'accepted': False, 'version': CONSENT}}, {'consent': {'accepted': True, 'version': 'x'}}],
                 'source_path': [{'source_path': '/video/podbor.html'}, {'source_path': 'https://evil.example/a.html'}],
                 'config_version': [{'config_version': 'old'}], 'lang': [{'lang': 'en'}]}
        for field, changes in cases.items():
            for change in changes:
                with self.assertRaises(self.contract.Invalid) as raised:
                    self.normalize(**change)
                self.assertEqual(raised.exception.field, field, change)
        with self.assertRaises(self.contract.Invalid):
            self.contract.normalize({**payload(self.catalog), 'budget': {}}, self.catalog, CONSENT)

    def test_other_schemas_unchanged(self):
        with self.assertRaises(self.contract.Invalid) as raised:
            self.contract.normalize({'schema_version': 'ua_order_request.v1'}, self.catalog, CONSENT)
        self.assertEqual(raised.exception.field, 'request_id')  # the v1 path, as before

    def test_inbox_view(self):
        row = {'id': 7, 'number': 'OR-000007', 'data': self.normalize(), 'telegram_user_id': None}
        view = self.crm.detail_view(row, self.catalog)
        for text in ('OR-000007', 'Олена', '+380992222002', 'Hyundai Tucson', 'Короткая заявка'):
            self.assertIn(text, view['text'])
        self.assertIn('Олена', self.crm.list_view(type('R', (), {'list_requests': lambda s, before: ([row], None)})(),
                                                  self.catalog)['buttons'][0][0][0])


class EditTests(unittest.TestCase):
    def test_only_planned_fragments_change(self):
        for name in edit_intake.EDITS:
            source = LIVE[name.split('/')[1]].encode() + b'\n'
            restored = edit_intake.build(name, source).decode()
            for old, new in edit_intake.EDITS[name]:
                restored = restored.replace(new, old)
            self.assertEqual(restored.encode(), source)
            with self.assertRaises(ValueError):
                edit_intake.build(name, edit_intake.build(name, source))


class FormTests(unittest.TestCase):
    def test_autofill_and_required(self):
        html = quick_form.block('uk', ('Kia', 'K5'))
        self.assertIn('name="customer_name" autocomplete="name" required', html)
        self.assertIn('name="phone" type="tel" autocomplete="tel" inputmode="tel" required', html)
        self.assertIn('Отримати пропозицію в месенджері', html)
        self.assertIn('data-model="kia-k5"', html)
        self.assertIn('Получить предложение в мессенджере', quick_form.block('ru', ('Kia', 'K5')))

    def test_only_advertised_models(self):
        self.assertEqual(quick_form.block('uk', ('Audi', 'A6')), '')
        catalog_keys = {m['key'] for m in CATALOG['countries']['korea']['models']}
        self.assertEqual(set(quick_form.MODELS.values()), catalog_keys)


class PageTests(unittest.TestCase):
    CARS = [{'key': ('Kia', 'K5'), 'name': 'Kia K5 2021', 'code': 'UA-0018', 'price_usd': 19300, 'mileage_km': 50000,
             'stage': 2, 'url': 'https://www.uaart.com.ua/video/UA-0018.html', 'image': None},
            {'key': ('Audi', 'A6'), 'name': 'Audi A6 2016', 'code': 'UA-0020', 'price_usd': 17700, 'mileage_km': 148000,
             'stage': 4, 'url': 'https://www.uaart.com.ua/video/UA-0020.html', 'image': None}]

    def test_form_only_on_advertised_model_pages(self):
        spec = importlib.util.spec_from_file_location('previous', HERE.parent/'seo_landings_002'/'ua_seo_landings.py')
        previous = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(previous)
        kept = [('Hyundai', 'Sonata')]  # live: a kept model page
        old, new = previous.pages(self.CARS, kept), landings.pages(self.CARS, kept)
        self.assertEqual(set(old), set(new))
        changed = {relative for relative in new if new[relative] != old[relative]}
        expected = {landings.path(lang, key) for lang in landings.LANGS for key in quick_form.MODELS}
        self.assertEqual(changed, expected)
        for relative in changed:
            self.assertEqual(re.sub(r'<link rel="stylesheet" href="/video/order/quick-lead\.css.*?</script>', '',
                                    new[relative]), old[relative])
            self.assertEqual(new[relative].count('data-ua-quick-lead'), 1)


if __name__ == '__main__':
    unittest.main()
