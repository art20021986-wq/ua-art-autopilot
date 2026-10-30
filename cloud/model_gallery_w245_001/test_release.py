#!/usr/bin/env python3
"""Release-specific checks: the W245 card built from the live order-page files (after MODEL-GALLERY-001 R6)."""
import json
from pathlib import Path
import unittest

import asset_version
import candidate_builder
import card
import make_assets
import card_assets

HERE = Path(__file__).resolve().parent
SOURCE = {asset_version.PAGE: (HERE/'fixtures/podbor.html').read_bytes(),
          card.DATA: (HERE/'fixtures/model-gallery.json').read_bytes()}


class ReleaseTests(unittest.TestCase):
    def test_only_the_card_changes(self):
        result = candidate_builder.build(SOURCE, {})
        self.assertEqual(set(result), set(SOURCE) | set(card_assets.FILES))
        before, after = json.loads(SOURCE[card.DATA]), json.loads(result[card.DATA])
        self.assertEqual(after['version'], asset_version.VERSION)
        self.assertEqual(after['models'][card.KEY], card_assets.ENTRY)
        self.assertEqual({k: v for k, v in after['models'].items() if k != card.KEY},
                         {k: v for k, v in before['models'].items() if k != card.KEY})

    def test_page_gets_only_the_new_order_version(self):
        page = candidate_builder.build(SOURCE, {})[asset_version.PAGE].decode()
        old = asset_version.SCRIPT_TAG.search(SOURCE[asset_version.PAGE].decode()).group(0)
        self.assertEqual(page, SOURCE[asset_version.PAGE].decode().replace(old, asset_version.CHECK_PAGE))

    def test_card_photos(self):
        photos = candidate_builder.photos()
        items = card_assets.ENTRY['photos']
        self.assertTrue(1 <= len(items) <= 8)
        order = [make_assets.VIEWS.index(item['view']) for item in items]
        self.assertEqual(order, sorted(set(order)))
        self.assertIn('W245', card_assets.ENTRY['generation']['uk'])
        for item in items:
            self.assertIn('video/order/' + item['path'], photos)
            self.assertTrue(item['license'] and item['source'].startswith('https://commons.wikimedia.org/'))
        for name, value in photos.items():
            self.assertTrue(name.startswith('video/order/media/') and name.endswith('.webp'), name)
            self.assertEqual(value[8:12], b'WEBP', name)

    def test_applied_or_changed_source_is_refused(self):
        result = candidate_builder.build(SOURCE, {})
        with self.assertRaises(ValueError):
            asset_version.build(result[asset_version.PAGE])
        with self.assertRaises(ValueError):
            card.build(result[card.DATA], card_assets.ENTRY)
        missing = json.loads(SOURCE[card.DATA])
        del missing['models'][card.KEY]
        with self.assertRaises(ValueError):
            card.build(json.dumps(missing).encode(), card_assets.ENTRY)

    def test_bundle_modules_fit(self):
        for path in HERE.glob('*.py'):
            self.assertLessEqual(path.stat().st_size, 1048576, path.name)
            # The server bootstrap unpacks only these names (deployment_bootstrap.py).
            self.assertRegex(path.name, r'^[a-z_]+\.py$')

    def test_server_paths_agree(self):
        # Upload, unpack and receipt use one package folder name on the server.
        bootstrap = (HERE/'deployment_bootstrap.py').read_text()
        transport = (HERE/'deployment_transport.py').read_text()
        self.assertIn("'modelcard-' + args.bundle", bootstrap)
        self.assertIn("INBOX+'/modelcard-'+bundle_sha+'/runs/'", transport)
        self.assertIn("INBOX+'/modelcard-'+digest+'.zip'", transport)
        self.assertIn("INBOX+'/modelcard_bootstrap.py'", transport)
        self.assertNotIn('modelgallery-', bootstrap + transport)


if __name__ == '__main__':
    unittest.main()
