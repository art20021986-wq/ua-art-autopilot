#!/usr/bin/env python3
"""Release-specific checks: the installed inputs (as the read-only probes returned them) and the candidate."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import candidate_builder
import edit_cars_ui
import edit_languages
import edit_metadata
import edit_sitemap

HERE = Path(__file__).resolve().parent
CLOUD = HERE.parent
R1 = json.loads((CLOUD/'card_lang_probe_001'/'20261030.json').read_text())['files']
R2 = json.loads((CLOUD/'card_lang_probe_001'/'20261030-R2.json').read_text())
CRM = json.loads((CLOUD/'crm_clients_probe_001'/'20261030.json').read_text())['files']


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def probe_sources():
    """The probes' sanitized copies (credential lines redacted, long numbers masked): fragment edits apply to them
    as to the live files; the live hashes are the probes' own."""
    ads = load('ads_cars_ui', CLOUD/'ads_ready_001'/'edit_cars_ui.py')
    return {'ua_seo_metadata.py': R1['ua_seo_metadata.py']['source'].encode(),
            'ua_seo_sitemap.py': R1['ua_seo_sitemap.py']['source'].encode(),
            'cars_ui.py': ads.build('cars_ui.py', CRM['cars_ui.py']['source'].encode() + b'\n'),
            'video/ua-site-languages.js': R2['files']['video/ua-site-languages.js']['source'].encode()}


class ReleaseTests(unittest.TestCase):
    def build(self):
        source = probe_sources()
        fake = {name: b'live ' + name.encode() for name in candidate_builder.DEPENDENCY_SHA256}
        with patch.dict(candidate_builder.SOURCE_SHA256, {n: hashlib.sha256(v).hexdigest() for n, v in source.items()}), \
             patch.dict(candidate_builder.DEPENDENCY_SHA256, {n: hashlib.sha256(v).hexdigest() for n, v in fake.items()}):
            return candidate_builder.build(source, fake)

    def test_pins_are_the_probed_live_files(self):
        pins = {**candidate_builder.SOURCE_SHA256, **candidate_builder.DEPENDENCY_SHA256}
        self.assertEqual(R1['ua_seo_metadata.py']['sha256'], pins['ua_seo_metadata.py'])
        self.assertEqual(R1['ua_seo_sitemap.py']['sha256'], pins['ua_seo_sitemap.py'])
        self.assertEqual(R1['ua_seo_index.py']['sha256'], pins['ua_seo_index.py'])
        self.assertEqual(R1['publikaciya.py']['sha256'], pins['publikaciya.py'])
        self.assertEqual(R2['files']['video/ua-site-languages.js']['sha256'], pins['video/ua-site-languages.js'])
        self.assertEqual(R2['writers']['cars_ui.py']['sha256'], pins['cars_ui.py'])
        receipt = json.loads((CLOUD.parent/'state/receipts/ADS-READY-INSTALL-20261030.json').read_text())['code_sha256']
        for name in ('cars_ui.py', 'ua_seo_landings.py', 'ua_seo_order_models.py', 'ua_seo_quick_form.py'):
            self.assertEqual(receipt[name], pins[name], name)

    def test_planned_files(self):
        result = self.build()
        self.assertEqual(sorted(result), ['cars_ui.py', 'ua_card_lang.py', 'ua_card_lang_job.py', 'ua_seo_metadata.py',
                                          'ua_seo_sitemap.py', 'video/ua-site-languages.js'])
        for name in ('ua_card_lang.py', 'ua_card_lang_job.py', 'ua_seo_sitemap.py', 'ua_seo_metadata.py'):
            compile(result[name], name, 'exec')
        self.assertIn(b"SEO_REVISION = 'CARD-LANG-001'", result['ua_seo_metadata.py'])
        self.assertIn(edit_languages.CHECK.encode(), result['video/ua-site-languages.js'])
        self.assertTrue(result['cars_ui.py'].rstrip().endswith(b"log.warning('ua_card_lang_job \xd0\xbd\xd0\xb5 \xd0\xbf\xd0\xbe\xd0\xb4\xd0\xba\xd0\xbb\xd1\x8e\xd1\x87\xd1\x91\xd0\xbd: %s', e)"))

    def test_applied_release_is_refused(self):
        result = self.build()
        for name, module in candidate_builder.EDITS.items():
            with self.assertRaises(ValueError):
                module.build(result[name])

    def test_language_script_dictionary_stays_valid_json(self):
        script = self.build()['video/ua-site-languages.js'].decode()
        import ua_card_lang
        words = ua_card_lang.dictionary(script)
        self.assertEqual(words['На весь экран'], 'На весь екран')
        start = script.index('var dictionaries = ') + len('var dictionaries = ')
        value, _ = json.JSONDecoder().raw_decode(script[start:])
        self.assertEqual(value['ru']['Вперед'], 'Вперёд')
        self.assertEqual(value['ka']['Повторить'], 'გამეორება')


if __name__ == '__main__':
    unittest.main()
