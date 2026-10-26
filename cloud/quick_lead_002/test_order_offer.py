#!/usr/bin/env python3
"""Order page model-card offer: server accepts the order page path, the card button and dialog, shared form contract."""
import base64
import hashlib
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
sys.path[:0] = [str(HERE), str(HERE.parent/'quick_lead_001'), str(HERE.parent/'seo_models_001'),
                str(HERE.parent/'gsc_growth_001'), str(HERE.parent/'ai_search_001'), str(HERE.parent/'seo_growth_001')]

import candidate_builder  # noqa: E402
import edit_order  # noqa: E402
import quick_assets  # noqa: E402
import ua_seo_landings as landings  # noqa: E402  (installed QUICK-LEAD-001 version, unchanged)
import ua_seo_quick_form as quick_form  # noqa: E402

LIVE = json.loads((HERE.parent/'order_intake_probe_001/20261026-R4.json').read_text())['package_sources']
PROBE = json.loads((HERE.parent/'podbor_probe_20261025/live_podbor_r3.json').read_text())
CATALOG = PROBE['bootstrap']['catalog']
CONSENT = 'consent-v1'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live_order_files():
    """The order page files as installed: probe R3 + PODBOR-FORM-001, PODBOR-MODEL-001 edits + GA4-TAG-001 tag."""
    form = load(HERE.parent/'podbor_form_001/edit_order.py', 'form_edit')
    model = load(HERE.parent/'podbor_model_001/edit_order.py', 'model_edit')
    tag = load(HERE.parent/'ga4_tag_001/ua_google_tag.py', 'google_tag')
    urls = {edit_order.PAGE: 'https://www.uaart.com.ua/video/podbor.html?strana=korea&lang=uk',
            edit_order.SCRIPT: 'https://www.uaart.com.ua/video/order/order.js?v=20261025.1',
            edit_order.STRINGS: 'https://www.uaart.com.ua/video/order/order-strings.json'}
    files = {}
    for name, url in urls.items():
        value = base64.b64decode(PROBE['files'][url]['b64'])
        for edit in (form, model):
            if name in edit.EDITS:
                value = edit.build(name, value)
        files[name] = tag.apply(value.decode()).encode() if name == edit_order.PAGE else value
    return files


def package(temp):
    """The order package as installed by QUICK-LEAD-001, with this release's quick.py."""
    edit_intake = load(HERE.parent/'quick_lead_001/edit_intake.py', 'edit_intake')
    root = Path(temp)/'ua_order'
    root.mkdir()
    for name in ('__init__.py', 'catalog.py', 'contract.py', 'crm.py', 'preference_summary.py', 'preferences.py'):
        source = LIVE[name].encode() + b'\n'
        if 'ua_order/' + name in edit_intake.EDITS:
            source = edit_intake.build('ua_order/' + name, source)
        (root/name).write_bytes(source)
    shutil.copy(HERE/'quick.py', root/'quick.py')
    order = ('korea', 'japan', 'usa', 'europe', 'china', 'canada', 'uae', 'georgia')
    (root/'catalog.json').write_text(json.dumps({**CATALOG, 'countries': {c: CATALOG['countries'][c] for c in order}}))
    sys.path.insert(0, temp)
    for name in [n for n in sys.modules if n == 'ua_order' or n.startswith('ua_order.')]:
        del sys.modules[name]
    contract, crm, catalog = (importlib.import_module('ua_order.' + n) for n in ('contract', 'crm', 'catalog'))
    sys.path.remove(temp)
    return contract, crm, catalog.Catalog(root/'catalog.json')


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.contract, self.crm, self.catalog = package(self.temp)

    def tearDown(self):
        shutil.rmtree(self.temp)

    def payload(self, **change):
        value = {'schema_version': 'ua_order_request.quick.v1', 'request_id': str(uuid.uuid4()),
                 'config_version': self.catalog.version, 'purchase_country_code': 'japan', 'model': 'nissan-note',
                 'customer_name': 'Олена', 'contact': {'phone': '0992222002'}, 'lang': 'ka',
                 'source_path': '/video/podbor.html', 'consent': {'accepted': True, 'version': CONSENT}}
        value.update(change)
        return value

    def test_order_page_paths_and_any_country(self):
        for path in ('/video/podbor.html', '/podbor.html', '/site/podbor.html', '/video/seo/ru/kia-k5-koreya-kiev.html'):
            data = self.contract.normalize(self.payload(source_path=path), self.catalog, CONSENT)
            self.assertEqual(data['contact'], {'phone': '+380992222002'})
        for path in ('/video/podbor.html?x=1', '/video/other.html', '/videopodbor.html'):
            with self.assertRaises(self.contract.Invalid) as raised:
                self.contract.normalize(self.payload(source_path=path), self.catalog, CONSENT)
            self.assertEqual(raised.exception.field, 'source_path')

    def test_live_check_answers(self):
        # The release's live check: an invalid phone from the order page is refused by the phone, not the path.
        with self.assertRaises(self.contract.Invalid) as raised:
            self.contract.normalize(self.payload(contact={'phone': 'x'}), self.catalog, CONSENT)
        self.assertEqual(raised.exception.field, 'contact')

    def test_inbox_names_the_order_page(self):
        row = {'id': 8, 'number': 'OR-000008', 'telegram_user_id': None,
               'data': self.contract.normalize(self.payload(), self.catalog, CONSENT)}
        text = self.crm.detail_view(row, self.catalog)['text']
        self.assertIn('Короткая заявка (страница подбора)', text)
        self.assertIn('Nissan Note', text)


class OrderPageTests(unittest.TestCase):
    def setUp(self):
        self.live = live_order_files()
        self.built = {name: edit_order.build(name, value) for name, value in self.live.items()}

    def test_pins_match_the_reconstructed_live_files(self):
        for name, value in self.live.items():
            self.assertEqual(hashlib.sha256(value).hexdigest(), candidate_builder.SOURCE_SHA256[name], name)

    def test_only_planned_fragments_change(self):
        for name, after in self.built.items():
            restored = after.decode()
            for old, new in edit_order.EDITS[name]:
                restored = restored.replace(new, old)
            if name == edit_order.PAGE:
                restored = restored.replace('order/order.js?v=' + edit_order.VERSION, 'order/order.js?v=20261025.3')
            self.assertEqual(restored.encode(), self.live[name])
            with self.assertRaises(ValueError):
                edit_order.build(name, after)

    def test_page_edit_independent_of_the_gallery_release(self):
        gallery = load(HERE.parent/'model_gallery_install_001/edit_order.py', 'gallery_edit')
        after_gallery = gallery.build(edit_order.PAGE, self.live[edit_order.PAGE])
        both = edit_order.build(edit_order.PAGE, after_gallery).decode()
        self.assertEqual(both.count('order/order.js?v=' + edit_order.VERSION), 1)
        self.assertIn('order/gallery.css', both)
        self.assertIn('id="quick-lead-dialog"', both)
        script = edit_order.build(edit_order.SCRIPT, gallery.build(edit_order.SCRIPT, self.live[edit_order.SCRIPT])).decode()
        self.assertIn('import {gallery}', script)
        self.assertIn('info.append(offer,button)', script)

    def test_card_button_before_calculate(self):
        script = self.built[edit_order.SCRIPT].decode()
        self.assertIn("info.append(offer,button)", script)
        self.assertIn("quickLeadModel:model.key", script)

    def test_strings_complete_in_three_languages(self):
        strings = json.loads(self.built[edit_order.STRINGS])
        for lang, texts in edit_order.TEXTS.items():
            for key, value in texts.items():
                self.assertEqual(strings[lang][key], value)
        self.assertEqual(strings['uk']['quick_offer'], 'Отримати пропозицію в месенджері')

    def test_dialog_uses_the_shared_form_contract(self):
        page = self.built[edit_order.PAGE].decode()
        dialog = page[page.index('<dialog'):page.index('</dialog>')]
        for marker in ('data-ua-quick-lead', 'autocomplete="name"', 'autocomplete="tel"', 'type="tel"', 'data-fields',
                       'data-status', 'data-consent', 'data-quick-close', 'data-quick-model-title'):
            self.assertIn(marker, dialog)
        for key in ('ok', 'error', 'bad_phone', 'bad_name'):
            self.assertIn('data-msg="%s"' % key, dialog)
        self.assertIn('order/quick-lead.js?v=%s' % quick_form.ASSET_VERSION, page)
        self.assertIn('order/quick-lead.css?v=%s' % quick_form.ASSET_VERSION, page)
        self.assertEqual(edit_order.ASSET_VERSION, quick_form.ASSET_VERSION)
        self.assertGreater(page.index('<dialog'), page.index('id="ua-order"'))  # inside the order root


class FormContractTests(unittest.TestCase):
    def test_landing_block_messages(self):
        html = quick_form.block('ru', ('Kia', 'K5'))
        self.assertIn('data-lang="ru" data-country="korea" data-model="kia-k5"', html)
        self.assertIn('<span data-msg="bad_phone" hidden>Проверьте номер телефона.</span>', html)
        self.assertNotIn('data-ok=', html)

    def test_script_reads_the_shared_contract(self):
        for marker in ('[data-msg="', '[data-quick-lead-model]', 'showModal', 'ua_order_request.quick.v1'):
            self.assertIn(marker, quick_assets.JS)

    def test_landing_pages_change_only_by_the_form_block(self):
        cars = [{'key': ('Kia', 'K5'), 'name': 'Kia K5 2021', 'code': 'UA-0018', 'price_usd': 19300, 'mileage_km': 1,
                 'stage': 2, 'url': 'https://www.uaart.com.ua/video/UA-0018.html', 'image': None}]
        previous = load(HERE.parent/'quick_lead_001/ua_seo_quick_form.py', 'previous_form')
        new = landings.pages(cars)
        sys.modules['ua_seo_quick_form'] = previous
        try:
            old = load(HERE.parent/'quick_lead_001/ua_seo_landings.py', 'previous_landings').pages(cars)
        finally:
            sys.modules['ua_seo_quick_form'] = quick_form
        changed = {name for name in new if new[name] != old[name]}
        self.assertEqual(changed, {landings.path(lang, key) for lang in landings.LANGS
                                   for key in quick_form.MODELS if landings.path(lang, key) in new})
        block = re.compile(r'<link rel="stylesheet" href="/video/order/quick-lead\.css.*?</script>')
        for name in changed:
            self.assertEqual(block.sub('', new[name]), block.sub('', old[name]))


if __name__ == '__main__':
    unittest.main()
