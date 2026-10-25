#!/usr/bin/env python3
"""The live order page files (PODBOR-PROBE-20261025 copy) change only in the planned fragments."""
import base64
import json
from pathlib import Path
import unittest

import candidate_builder
import edit_order

HERE = Path(__file__).resolve().parent
LIVE = json.loads((HERE.parent/'podbor_probe_20261025/live_podbor.json').read_text())['files']
URLS = {edit_order.PAGE: 'https://www.uaart.com.ua/video/podbor.html?strana=korea&lang=uk',
        edit_order.SCRIPT: 'https://www.uaart.com.ua/video/order/order.js?v=20260927.10',
        edit_order.STRINGS: 'https://www.uaart.com.ua/video/order/order-strings.json'}
SOURCE = {name: base64.b64decode(LIVE[url]['b64']) for name, url in URLS.items()}


class EditTests(unittest.TestCase):
    def test_only_planned_fragments_change(self):
        result = candidate_builder.build(SOURCE, {})
        for name, after in result.items():
            restored = after.decode()
            for old, new in edit_order.EDITS[name]:
                restored = restored.replace(new, old)
            self.assertEqual(restored.encode(), SOURCE[name])

    def test_strings_stay_valid_and_complete(self):
        strings = json.loads(edit_order.build(edit_order.STRINGS, SOURCE[edit_order.STRINGS]))
        self.assertEqual({lang: strings[lang]['other_choose'] for lang in ('uk', 'ru', 'ka')},
                         {'uk': 'Обрати інший автомобіль', 'ru': 'Выбрать другой автомобиль', 'ka': 'სხვა ავტომობილის არჩევა'})
        self.assertEqual(strings['uk']['other'], 'Інша модель')

    def test_button_is_gold_and_has_own_label(self):
        page = edit_order.build(edit_order.PAGE, SOURCE[edit_order.PAGE]).decode()
        button = page[page.index('<button type="button" id="other-model"'):]
        button = button[:button.index('</button>')]
        self.assertNotIn('secondary', button)
        self.assertIn(edit_order.CHECK_PAGE, button)

    def test_refuses_changed_files(self):
        for name in edit_order.EDITS:
            with self.assertRaises(ValueError):
                edit_order.build(name, edit_order.build(name, SOURCE[name]))


if __name__ == '__main__':
    unittest.main()
