#!/usr/bin/env python3
"""The live home page (HOME-TEXT-001 result) keeps one h1 and loses only the large phrase."""
import base64
import importlib.util
import json
from pathlib import Path
import unittest

import candidate_builder
import edit_home

HERE = Path(__file__).resolve().parent


def load(package, name):
    spec = importlib.util.spec_from_file_location(package + '_' + name, HERE.parent/package/(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LIVE = json.loads((HERE.parent/'home_layout_001/live_home.json').read_text())
LAYOUT = load('home_layout_001', 'build_home').build(base64.b64decode(LIVE['files'][LIVE['home']]['b64']))
INSTALLED = load('home_text_001', 'edit_home').build(LAYOUT)


class EditTests(unittest.TestCase):
    def test_one_heading_without_phrase(self):
        after = edit_home.build(INSTALLED).decode()
        self.assertEqual(after.count('<h1'), 1)
        self.assertIn(edit_home.CHECK, after)
        for phrase in ('під ключ</span>', 'под ключ"', 'Авто під замовлення</span>'):
            self.assertNotIn(phrase, after)

    def test_only_planned_fragments_change(self):
        after = edit_home.build(INSTALLED).decode()
        old = INSTALLED.decode()
        for before, new in edit_home.EDITS:
            old = old.replace(before, new)
        self.assertEqual(after, old)
        self.assertEqual(len(INSTALLED) - len(after.encode()),
                         sum(len(a.encode()) - len(b.encode()) for a, b in edit_home.EDITS))

    def test_refuses_unknown_page(self):
        with self.assertRaisesRegex(ValueError, 'HOME_FRAGMENT_NOT_UNIQUE'):
            edit_home.build(edit_home.build(INSTALLED))

    def test_candidate(self):
        self.assertEqual(candidate_builder.build({'video/index.html': INSTALLED}, {}),
                         {'video/index.html': edit_home.build(INSTALLED)})


if __name__ == '__main__':
    unittest.main()
