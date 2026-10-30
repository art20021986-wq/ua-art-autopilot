#!/usr/bin/env python3
"""Release-specific checks: exact installed inputs, the planned files, the ad source, texts and privacy page."""
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import attribution
import candidate_builder
import edit_order
import privacy_page

HERE = Path(__file__).resolve().parent
CLOUD = HERE.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live_files():
    """The installed inputs, from the packages that released them (their plans hold the live hashes)."""
    quick = load('quick_assets_live', CLOUD/'quick_lead_002'/'quick_assets.py')
    sys.path.insert(0, str(CLOUD/'japan_note_001'))
    try:
        japan = load('japan_builder', CLOUD/'japan_note_001'/'candidate_builder.py')
        names = {edit_order.PAGE: 'podbor.html', edit_order.SCRIPT: 'order.js', edit_order.STRINGS: 'order-strings.json'}
        pages = japan.build({n: (CLOUD/'japan_note_001'/'fixtures'/f).read_bytes() for n, f in names.items()}, {})
    finally:
        sys.path.remove(str(CLOUD/'japan_note_001'))
    return {'ua_order/contract.py': (HERE/'fixtures'/'ua_order'/'contract.py').read_bytes(),
            'ua_order/crm.py': (HERE/'fixtures'/'ua_order'/'crm.py').read_bytes(),
            'ua_seo_landings.py': (CLOUD/'quick_lead_001'/'ua_seo_landings.py').read_bytes(),
            'ua_seo_order_models.py': (CLOUD/'seo_models_001'/'ua_seo_order_models.py').read_bytes(),
            'ua_seo_quick_form.py': (CLOUD/'quick_lead_002'/'ua_seo_quick_form.py').read_bytes(),
            'video/order/quick-lead.js': quick.JS.encode(), 'video/order/quick-lead.css': quick.CSS.encode(),
            **{name: pages[name] for name in candidate_builder.PAGE_FILES}}


class ReleaseTests(unittest.TestCase):
    def build(self):
        source = live_files()
        fake = {name: b'live ' + name.encode() for name in candidate_builder.DEPENDENCY_SHA256}
        with patch.dict(candidate_builder.DEPENDENCY_SHA256, {n: hashlib.sha256(v).hexdigest() for n, v in fake.items()}):
            return candidate_builder.build(source, fake)

    def test_inputs_are_the_installed_files(self):
        source = live_files()
        for name, digest in candidate_builder.SOURCE_SHA256.items():
            self.assertEqual(hashlib.sha256(source[name]).hexdigest(), digest, name)
        # The order page as JAPAN-NOTE-001 left it (its receipt).
        receipt = json.loads((CLOUD.parent/'state/receipts/JAPAN-NOTE-INSTALL-20261030.json').read_text())
        for name in candidate_builder.PAGE_FILES:
            self.assertEqual(hashlib.sha256(source[name]).hexdigest(), receipt['code_sha256'][name], name)

    def test_planned_files(self):
        result = self.build()
        self.assertEqual(sorted(result), sorted([
            'ua_order/attribution.py', 'ua_order/contract.py', 'ua_order/crm.py', 'ua_seo_landings.py',
            'ua_seo_order_models.py', 'ua_seo_quick_form.py', 'video/order/attribution.js', 'video/order/order-strings.json',
            'video/order/order.js', 'video/order/quick-lead.css', 'video/order/quick-lead.js', 'video/podbor.html',
            'video/privacy.html']))
        for name, value in result.items():
            if name.endswith('.py'):
                compile(value, name, 'exec')
        json.loads(result[edit_order.STRINGS])
        self.assertIn(edit_order.CHECK_PAGE.encode(), result[edit_order.PAGE])
        self.assertIn(edit_order.CHECK_SCRIPT.encode(), result[edit_order.SCRIPT])
        self.assertIn(edit_order.CHECK_STRINGS.encode(), result[edit_order.STRINGS])
        self.assertEqual(result[edit_order.PAGE].count(b'href="/video/privacy.html"'), 2)

    def test_applied_release_is_refused(self):
        result = self.build()
        for name in candidate_builder.PAGE_FILES + ('ua_order/contract.py', 'ua_order/crm.py', 'ua_seo_landings.py'):
            module = __import__({'ua_order/contract.py': 'edit_intake', 'ua_order/crm.py': 'edit_intake',
                                 'ua_seo_landings.py': 'edit_landings'}.get(name, 'edit_order'))
            with self.assertRaises(ValueError):
                module.build(name, result[name])

    def test_attribution_keeps_clean_values_only(self):
        data, clean = attribution.split({'a': 1, 'attribution': {
            'gclid': 'Cj0KCQjw_ABC-123', 'utm_source': 'google', 'utm_term': 'kia k5 газ',
            'utm_medium': '<script>', 'gbraid': 'short', 'other': 'x', 'utm_campaign': 5}})
        self.assertEqual(data, {'a': 1})
        self.assertEqual(clean, {'gclid': 'Cj0KCQjw_ABC-123', 'utm_source': 'google', 'utm_term': 'kia k5 газ'})
        self.assertEqual(attribution.split({'a': 1}), ({'a': 1}, {}))
        self.assertEqual(attribution.split({'attribution': 'x'}), ({}, {}))
        self.assertEqual(attribution.lines({}), [])
        self.assertEqual(attribution.lines(clean)[0], '<b>Источник:</b> Google Ads')
        self.assertEqual(attribution.lines({'utm_source': 'fb<x>'}), ['<b>Источник:</b> fb&lt;x&gt;'])

    def test_model_pages_name_the_fuel(self):
        result = self.build()
        modules = {}
        with tempfile.TemporaryDirectory() as folder:
            for name in ('ua_seo_order_models', 'ua_seo_quick_form', 'ua_seo_landings'):
                Path(folder, name + '.py').write_bytes(result[name + '.py'])
            Path(folder, 'ua_seo_schema.py').write_bytes((CLOUD/'ai_search_001'/'ua_seo_schema.py').read_bytes())
            sys.path.insert(0, folder)
            try:
                for name in ('ua_seo_schema', 'ua_seo_order_models', 'ua_seo_quick_form', 'ua_seo_landings'):
                    sys.modules.pop(name, None)
                    modules[name] = importlib.import_module(name)
                pages = modules['ua_seo_landings'].pages([])
            finally:
                sys.path.remove(folder)
                for name in modules:
                    sys.modules.pop(name, None)
        expected = {'kia-k5-koreya-kyiv': 'Kia K5 на газу (LPi) з Кореї під ключ',
                    'hyundai-sonata-koreya-kyiv': 'Hyundai Sonata на газу (LPi) з Кореї під ключ',
                    'hyundai-tucson-koreya-kyiv': 'Hyundai Tucson дизель з Кореї під ключ',
                    'kia-sportage-koreya-kyiv': 'Kia Sportage дизель з Кореї під ключ',
                    'hyundai-santa-fe-koreya-kyiv': 'Hyundai Santa Fe дизель з Кореї під ключ',
                    'kia-k5-koreya-kiev': 'Kia K5 на газе (LPi) из Кореи под ключ',
                    'hyundai-tucson-koreya-kiev': 'Hyundai Tucson дизель из Кореи под ключ'}
        for slug, heading in expected.items():
            page = next(v for k, v in pages.items() if k.endswith(slug + '.html'))
            page = page if isinstance(page, str) else page[0]
            self.assertIn('<h1>%s</h1>' % heading, page, slug)
            self.assertIn('/video/order/attribution.js', page, slug)
            self.assertIn('/video/privacy.html', page, slug)
        tucson = next(v for k, v in pages.items() if k.endswith('hyundai-tucson-koreya-kyiv.html'))
        self.assertNotIn('гібрид', tucson if isinstance(tucson, str) else tucson[0])

    def test_privacy_page(self):
        page = privacy_page.html()
        self.assertIn('<section id="ru" lang="ru">', page)
        self.assertIn('Закон України «Про захист персональних даних»', page)
        self.assertIn('вул. Перемоги, 20', page)


if __name__ == '__main__':
    unittest.main()
