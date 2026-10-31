#!/usr/bin/env python3
"""Release-specific checks: the installed inputs, the candidate and what its pages say."""
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import candidate_builder
import edit_landings
import edit_metadata

HERE = Path(__file__).resolve().parent
CLOUD = HERE.parent
R1 = json.loads((CLOUD/'card_lang_probe_001'/'20261030.json').read_text())['files']


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live_sources():
    """ua_seo_order_models and ua_seo_landings exactly as installed (ADS-READY-001); ua_seo_metadata as
    CARD-LANG-001 left it, built from the probe's sanitized copy (credential lines redacted)."""
    ads = load('ads_landings', CLOUD/'ads_ready_001'/'edit_landings.py')
    card = load('card_metadata', CLOUD/'card_lang_001'/'edit_metadata.py')
    return {'ua_seo_order_models.py': (CLOUD/'ads_ready_001'/'ua_seo_order_models.py').read_bytes(),
            'ua_seo_landings.py': ads.build(ads.NAME, (CLOUD/'quick_lead_001'/'ua_seo_landings.py').read_bytes()),
            'ua_seo_metadata.py': card.build(R1['ua_seo_metadata.py']['source'].encode())}


class ReleaseTests(unittest.TestCase):
    def build(self):
        source = live_sources()
        fake = {name: b'live ' + name.encode() for name in candidate_builder.DEPENDENCY_SHA256}
        pins = {'ua_seo_metadata.py': hashlib.sha256(source['ua_seo_metadata.py']).hexdigest()}
        with patch.dict(candidate_builder.SOURCE_SHA256, pins), \
             patch.dict(candidate_builder.DEPENDENCY_SHA256, {n: hashlib.sha256(v).hexdigest() for n, v in fake.items()}):
            return candidate_builder.build(source, fake)

    def test_pins_are_the_installed_files(self):
        source = live_sources()
        for name in ('ua_seo_order_models.py', 'ua_seo_landings.py'):
            self.assertEqual(hashlib.sha256(source[name]).hexdigest(), candidate_builder.SOURCE_SHA256[name], name)
        receipt = json.loads((CLOUD.parent/'state/receipts/CARD-LANG-INSTALL-20261030.json').read_text())['code_sha256']
        self.assertEqual(receipt['ua_seo_metadata.py'], candidate_builder.SOURCE_SHA256['ua_seo_metadata.py'])
        for name in ('ua_seo_sitemap.py', 'ua_card_lang.py'):
            self.assertEqual(receipt[name], candidate_builder.DEPENDENCY_SHA256[name], name)

    def test_planned_files_and_refused_reapply(self):
        result = self.build()
        self.assertEqual(sorted(result), ['ua_seo_landings.py', 'ua_seo_metadata.py', 'ua_seo_order_models.py'])
        for name, value in result.items():
            compile(value, name, 'exec')
        with self.assertRaises(ValueError):
            edit_landings.build(result['ua_seo_landings.py'])
        with self.assertRaises(ValueError):
            edit_metadata.build(result['ua_seo_metadata.py'])

    def test_pages(self):
        result = self.build()
        with tempfile.TemporaryDirectory() as folder:
            for name in ('ua_seo_order_models.py', 'ua_seo_landings.py'):
                Path(folder, name).write_bytes(result[name])
            Path(folder, 'ua_seo_schema.py').write_bytes((CLOUD/'ai_search_001'/'ua_seo_schema.py').read_bytes())
            Path(folder, 'ua_seo_quick_form.py').write_bytes((CLOUD/'ads_ready_001'/'ua_seo_quick_form.py').read_bytes())
            sys.path.insert(0, folder)
            try:
                for name in ('ua_seo_schema', 'ua_seo_quick_form', 'ua_seo_order_models', 'ua_seo_landings'):
                    sys.modules.pop(name, None)
                pages = importlib.import_module('ua_seo_landings').pages([])
            finally:
                sys.path.remove(folder)
                for name in ('ua_seo_schema', 'ua_seo_quick_form', 'ua_seo_order_models', 'ua_seo_landings'):
                    sys.modules.pop(name, None)
        note, lpi = pages['seo/ua/nissan-note-yaponiya-kyiv.html'], pages['seo/ru/avto-iz-korei-na-gaze-lpi.html']
        self.assertIn('<h1>Nissan Note з Японії під замовлення</h1>', note)
        self.assertIn('переробляють на ліве кермо наші колеги в Грузії', note)
        self.assertIn('hreflang="ru" href="https://www.uaart.com.ua/video/seo/ru/nissan-note-yaponiya-kiev.html"', note)
        self.assertIn('podbor.html?strana=japan&amp;model=nissan-note&amp;lang=uk', note)
        self.assertIn('<h1>Авто из Кореи на заводском газе (LPi)</h1>', lpi)
        self.assertIn('href="/video/seo/ru/kia-k5-koreya-kiev.html"', lpi)
        order = pages['seo/ua/avto-pid-zamovlennia-kyiv.html']
        self.assertIn('<title>Авто під замовлення в Києві — підбір з Кореї, Японії, США, Європи, Китаю | UA ART</title>', order)
        self.assertIn('<h2>Що ви отримуєте</h2>', order)
        self.assertIn('Чи можна замовити авто з лівим кермом з Японії?', order)
        self.assertIn('nissan-note-yaponiya-kyiv.html', pages['seo/ua/avto-z-yaponii-pid-zamovlennia.html'])
        self.assertIn('avto-z-korei-na-gazu-lpi.html', pages['seo/ua/kia-k5-koreya-kyiv.html'])
        self.assertIn('avto-z-korei-na-gazu-lpi.html', pages['seo/ua/hyundai-sonata-koreya-kyiv.html'])
        self.assertNotIn('avto-z-korei-na-gazu-lpi.html', pages['seo/ua/hyundai-tucson-koreya-kyiv.html'])

    def test_diagnostics_page_noindex(self):
        source = self.build()['ua_seo_metadata.py'].decode()
        start = source.index('    if name not in CORE and not is_card:')
        self.assertIn("UA-[0-9]{4,}-diag", source[start:start + 400])
        self.assertIn("SEO_REVISION = 'SEO-CONTENT-001'", source)


if __name__ == '__main__':
    unittest.main()
