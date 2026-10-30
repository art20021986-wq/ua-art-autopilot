#!/usr/bin/env python3
"""Release-specific checks: the candidate built from the live order-page files (after MODEL-GALLERY-001 R6)."""
import hashlib
import json
from pathlib import Path
import unittest

import candidate_builder
import edit_japan
import note_assets

HERE = Path(__file__).resolve().parent
LIVE = {edit_japan.PAGE: 'podbor.html', edit_japan.SCRIPT: 'order.js', edit_japan.STRINGS: 'order-strings.json'}
SOURCE = {name: (HERE/'fixtures'/file).read_bytes() for name, file in LIVE.items()}
# Live hashes after MODEL-GALLERY-INSTALL-20261027-R6 (its deployment_plan.json; strings from QUICK-LEAD-002 + gallery R5).
LIVE_SHA256 = {edit_japan.PAGE: 'ffd6a623ce77cfa057d20a0efb33b67cb7d7e1519e58ddd2c7f13e0f4d9c7ac3',
               edit_japan.SCRIPT: '61b9e2bff68b818cbde9b86066948b27b290b7d2340693ef82e149ec2b5e5f62',
               edit_japan.STRINGS: 'b9d1bd196ca1c6331cb07c09ca282a118b32af03bc964e22088ab70d1e51d373'}


class ReleaseTests(unittest.TestCase):
    def test_fixtures_are_the_live_files(self):
        for name, value in SOURCE.items():
            self.assertEqual(hashlib.sha256(value).hexdigest(), LIVE_SHA256[name], name)

    def test_planned_files(self):
        result = candidate_builder.build(SOURCE, {})
        self.assertEqual(set(result), set(LIVE) | set(note_assets.FILES))
        self.assertIn(edit_japan.CHECK_PAGE.encode(), result[edit_japan.PAGE])
        self.assertIn(b'order/order.js?v=' + edit_japan.VERSION.encode(), result[edit_japan.PAGE])
        self.assertIn(edit_japan.CHECK_SCRIPT.encode(), result[edit_japan.SCRIPT])
        self.assertIn(edit_japan.CHECK_STRINGS.encode(), result[edit_japan.STRINGS])
        self.assertIn(edit_japan.CHECK_STYLE.encode(), result['video/order/model-note.css'])

    def test_texts_only_for_japan(self):
        strings = json.loads(candidate_builder.build(SOURCE, {})[edit_japan.STRINGS])
        before = json.loads(SOURCE[edit_japan.STRINGS])
        for lang, (model, category) in edit_japan.NOTES.items():
            self.assertEqual(strings[lang]['note_japan_model'], model)
            self.assertEqual(strings[lang]['note_japan_category'], category)
            self.assertEqual([k for k in strings[lang] if k.startswith('note_')], ['note_japan_model', 'note_japan_category'])
            self.assertEqual({k: v for k, v in strings[lang].items() if not k.startswith('note_')}, before[lang])

    def test_applied_release_is_refused(self):
        built = candidate_builder.build(SOURCE, {})
        for name in LIVE:
            with self.assertRaises(ValueError):
                edit_japan.build(name, built[name])


if __name__ == '__main__':
    unittest.main()
