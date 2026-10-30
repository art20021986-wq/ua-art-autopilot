#!/usr/bin/env python3
"""Release-specific checks: the candidate built from the live order-page files (after ADS-READY-001)."""
import hashlib
import json
from pathlib import Path
import unittest

import candidate_builder
import edit_price
import price_assets

HERE = Path(__file__).resolve().parent
LIVE = {edit_price.PAGE: 'podbor.html', edit_price.SCRIPT: 'order.js', edit_price.STRINGS: 'order-strings.json'}
SOURCE = {name: (HERE/'fixtures'/file).read_bytes() for name, file in LIVE.items()}
# Live hashes after ADS-READY-INSTALL-20261030 (its deployment_plan.json).
LIVE_SHA256 = {edit_price.PAGE: '56ee3a6c97b668a39e61350856b2520c740dc23aed29056b5e3d88a5c56713d9',
               edit_price.SCRIPT: 'dff1daacce14146e7c59abb82bd654d911ff9478a10feaa3e7510b93bffa8f8d',
               edit_price.STRINGS: '808d37bf59d900b90e3a3ba59c52b9d0e80fdb4cde7d041454f6b3582e3a94f7'}
NBSP = ' '


class ReleaseTests(unittest.TestCase):
    def test_fixtures_are_the_live_files(self):
        for name, value in SOURCE.items():
            self.assertEqual(hashlib.sha256(value).hexdigest(), LIVE_SHA256[name], name)

    def test_planned_files(self):
        result = candidate_builder.build(SOURCE, {})
        self.assertEqual(set(result), set(LIVE) | set(price_assets.FILES))
        self.assertIn(edit_price.CHECK_PAGE.encode(), result[edit_price.PAGE])
        self.assertIn(b'order/order.js?v=' + edit_price.VERSION.encode(), result[edit_price.PAGE])
        self.assertIn(edit_price.CHECK_SCRIPT.encode(), result[edit_price.SCRIPT])
        self.assertIn(edit_price.CHECK_STRINGS.encode(), result[edit_price.STRINGS])
        self.assertIn(edit_price.CHECK_STYLE.encode(), result['video/order/model-price.css'])

    def test_price_texts(self):
        strings = json.loads(candidate_builder.build(SOURCE, {})[edit_price.STRINGS])
        before = json.loads(SOURCE[edit_price.STRINGS])
        self.assertEqual(strings['uk']['price_kia-k5'], 'Від 17' + NBSP + '400 $ до Києва з сертифікатом, без додаткових платежів.')
        self.assertEqual(strings['ru']['price_nissan-note'], 'От 15' + NBSP + '400 $ до Киева с сертификатом, без дополнительных платежей.')
        self.assertEqual(strings['uk']['price_japan'], 'Ціна уточнюється.')
        expected = {'price_' + k for k in edit_price.PRICES} | {'price_japan'}
        for lang in ('uk', 'ru', 'ka'):
            self.assertEqual({k for k in strings[lang] if k.startswith('price_')}, expected)
            self.assertEqual({k: v for k, v in strings[lang].items() if not k.startswith('price_')}, before[lang])

    def test_owner_prices(self):
        self.assertEqual(edit_price.PRICES, {'kia-k5': 17400, 'hyundai-sonata': 17600, 'hyundai-tucson': 19500,
                                             'kia-sportage': 21400, 'hyundai-santa-fe': 19700, 'nissan-note': 15400})

    def test_script_prefers_the_model_price_then_the_country(self):
        script = candidate_builder.build(SOURCE, {})[edit_price.SCRIPT].decode()
        price = script.index("const price=t('price_'+model.key)??t('price_'+state.country);")
        self.assertLess(price, script.index("const note=t('note_'"))

    def test_applied_release_is_refused(self):
        built = candidate_builder.build(SOURCE, {})
        for name in LIVE:
            with self.assertRaises(ValueError):
                edit_price.build(name, built[name])

    def test_bundle_modules_fit(self):
        for path in HERE.glob('*.py'):
            self.assertLessEqual(path.stat().st_size, 1048576, path.name)
            # The server bootstrap unpacks only these names (deployment_bootstrap.py).
            self.assertRegex(path.name, r'^[a-z_]+\.py$')

    def test_server_paths_agree(self):
        # Upload, unpack and receipt use one package folder name on the server.
        bootstrap = (HERE/'deployment_bootstrap.py').read_text()
        transport = (HERE/'deployment_transport.py').read_text()
        self.assertIn("'kjprice-' + args.bundle", bootstrap)
        self.assertIn("INBOX+'/kjprice-'+bundle_sha+'/runs/'", transport)
        self.assertIn("INBOX+'/kjprice-'+digest+'.zip'", transport)
        self.assertIn("INBOX+'/kjprice_bootstrap.py'", transport)
        self.assertNotIn('japannote', bootstrap + transport + (HERE/'deployment_remote.py').read_text())


if __name__ == '__main__':
    unittest.main()
