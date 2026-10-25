#!/usr/bin/env python3
"""The installed home page (HOME-LAYOUT-001 result) loses only the Kyiv binding of two labels."""
import base64
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'home_layout_001'))
import build_home  # noqa: E402
sys.path.remove(str(HERE.parent/'home_layout_001'))
import candidate_builder  # noqa: E402
import edit_home  # noqa: E402

LIVE = json.loads((HERE.parent/'home_layout_001/live_home.json').read_text())
INSTALLED = build_home.build(base64.b64decode(LIVE['files'][LIVE['home']]['b64']))


class EditTests(unittest.TestCase):
    def test_only_two_labels_change(self):
        after = edit_home.build(INSTALLED)
        restored = after
        for old, new in edit_home.EDITS:
            restored = restored.replace(new.encode(), old.encode())
        self.assertEqual(restored, INSTALLED)
        self.assertIn(edit_home.CHECK.encode(), after)
        hero = after[after.index(b'<section class="hero ua-order-first"'):after.index(b'</h1>')].decode()
        for word in ('Києв', 'КИЇВ', 'Киев', 'КИЕВ', 'კიევ'):
            self.assertNotIn(word, hero)

    def test_refuses_unknown_page(self):
        with self.assertRaisesRegex(ValueError, 'HOME_LABEL_NOT_UNIQUE'):
            edit_home.build(edit_home.build(INSTALLED))

    def test_candidate(self):
        self.assertEqual(candidate_builder.build({'video/index.html': INSTALLED}, {}),
                         {'video/index.html': edit_home.build(INSTALLED)})


if __name__ == '__main__':
    unittest.main()
