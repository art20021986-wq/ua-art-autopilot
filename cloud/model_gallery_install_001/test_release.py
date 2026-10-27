#!/usr/bin/env python3
"""Release-specific checks: the candidate built from the live order-page files (after QUICK-LEAD-002)."""
import json
from pathlib import Path
import unittest

import candidate_builder
import edit_order
import gallery_assets
import generations
import make_assets

HERE = Path(__file__).resolve().parent
LIVE = {edit_order.PAGE: 'podbor.html', edit_order.SCRIPT: 'order.js', edit_order.STRINGS: 'order-strings.json'}
SOURCE = {name: (HERE/'fixtures'/file).read_bytes() for name, file in LIVE.items()}
DATA = json.loads(gallery_assets.FILES['video/order/model-gallery.json'])


class ReleaseTests(unittest.TestCase):
    def test_planned_files(self):
        result = candidate_builder.build(SOURCE, {})
        photos = candidate_builder.photos()
        self.assertEqual(set(result), set(LIVE) | set(gallery_assets.FILES) | set(photos))
        self.assertIn(edit_order.CHECK_PAGE.encode(), result[edit_order.PAGE])
        self.assertIn(edit_order.CHECK_SCRIPT.encode(), result[edit_order.SCRIPT])
        self.assertIn(edit_order.CHECK_STRINGS.encode(), result[edit_order.STRINGS])
        for lang in ('uk', 'ru', 'ka'):
            self.assertEqual(len(json.loads(result[edit_order.STRINGS])[lang]['photo_prev']) > 0, True)
        for name, value in photos.items():
            self.assertTrue(name.startswith('video/order/media/') and name.endswith('.webp'), name)
            self.assertEqual(value[8:12], b'WEBP', name)

    def test_gallery_data_matches_photos(self):
        photos = candidate_builder.photos()
        self.assertEqual(set(DATA['models']), set(generations.GENERATIONS))
        for key in ('classics-1980-1990', 'lexus-tx', 'toyota-tacoma-trailhunter'):
            self.assertNotIn(key, DATA['models'])
        for key, model in DATA['models'].items():
            self.assertEqual(set(model['generation']), {'uk', 'ru', 'ka'})
            self.assertTrue(1 <= len(model['photos']) <= 8, key)
            order = [make_assets.VIEWS.index(item['view']) for item in model['photos']]
            self.assertEqual(order, sorted(set(order)), key)
            for item in model['photos']:
                self.assertIn('video/order/' + item['path'], photos)
                self.assertTrue(item['license'] and item['source'].startswith('https://commons.wikimedia.org/'))

    def test_generation_line(self):
        self.assertEqual(generations.line('kia-k5'), {'uk': '3-тє покоління (DL3), з 2019 р.',
                                                      'ru': '3-е поколение (DL3), с 2019 г.',
                                                      'ka': 'მე-3 თაობა (DL3), 2019 წლიდან'})

    def test_applied_or_changed_source_is_refused(self):
        result = candidate_builder.build(SOURCE, {})
        with self.assertRaises(ValueError):
            edit_order.build(edit_order.SCRIPT, result[edit_order.SCRIPT])
        # Another release may have raised the order.js version: the gallery still applies.
        raised = SOURCE[edit_order.PAGE].replace(b'20261026.5', b'20261026.7')
        self.assertIn(edit_order.CHECK_PAGE.encode(), edit_order.build(edit_order.PAGE, raised))
        with self.assertRaises(ValueError):
            edit_order.build(edit_order.PAGE, result[edit_order.PAGE])

    def test_installed_gallery_gets_new_versions_only(self):
        # The live files after the earlier gallery release (20261026.9): only the asset versions change.
        built = candidate_builder.build(SOURCE, {})
        earlier = {name: built[name].replace(edit_order.VERSION.encode(), b'20261026.9') for name in LIVE}
        result = candidate_builder.build(earlier, {})
        self.assertNotIn(edit_order.STRINGS, result)
        for name in (edit_order.PAGE, edit_order.SCRIPT):
            self.assertEqual(result[name], built[name], name)

    def test_bundle_modules_fit(self):
        for path in HERE.glob('*.py'):
            self.assertLessEqual(path.stat().st_size, 1048576, path.name)


if __name__ == '__main__':
    unittest.main()
