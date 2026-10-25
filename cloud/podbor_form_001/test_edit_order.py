#!/usr/bin/env python3
"""The live order page files (PODBOR-PROBE-20261025-R3 copy) change only in the planned fragments."""
import base64
import json
from pathlib import Path
import unittest

import candidate_builder
import edit_order

HERE = Path(__file__).resolve().parent
LIVE = json.loads((HERE.parent/'podbor_probe_20261025/live_podbor_r3.json').read_text())['files']
URLS = {edit_order.PAGE: 'https://www.uaart.com.ua/video/podbor.html?strana=korea&lang=uk',
        edit_order.SCRIPT: 'https://www.uaart.com.ua/video/order/order.js?v=20261025.1',
        edit_order.STYLE: 'https://www.uaart.com.ua/video/order/order.css?v=20260927.10',
        edit_order.STRINGS: 'https://www.uaart.com.ua/video/order/order-strings.json'}
SOURCE = {name: base64.b64decode(LIVE[url]['b64']) for name, url in URLS.items()}


class EditTests(unittest.TestCase):
    def test_only_planned_fragments_change(self):
        result = candidate_builder.build(SOURCE, {})
        for name, after in result.items():
            restored = after.decode()
            for old, new in reversed(edit_order.EDITS[name]):
                restored = restored.replace(new, old)
            self.assertEqual(restored.encode(), SOURCE[name])

    def test_click_keeps_scroll_and_default_open_does_not(self):
        script = edit_order.build(edit_order.SCRIPT, SOURCE[edit_order.SCRIPT]).decode()
        open_form = script[script.index('function openForm('):script.index('function openDefaultForm(')]
        select = script[script.index('function selectModel('):]
        select = select[:select.index('\n}\n')]
        self.assertNotIn('scrollIntoView', open_form)
        self.assertIn('scrollIntoView', select)
        self.assertEqual(script.count('openDefaultForm();'), 4)

    def test_ukrainian_button_text(self):
        strings = json.loads(edit_order.build(edit_order.STRINGS, SOURCE[edit_order.STRINGS]))
        self.assertEqual([strings[lang]['other_choose'] for lang in ('uk', 'ru')], ['Обрати інше авто', 'Выбрать другой автомобиль'])
        page = edit_order.build(edit_order.PAGE, SOURCE[edit_order.PAGE]).decode()
        self.assertIn('data-label="other_choose">Обрати інше авто</button>', page)

    def test_refuses_changed_files(self):
        for name in edit_order.EDITS:
            with self.assertRaises(ValueError):
                edit_order.build(name, edit_order.build(name, SOURCE[name]))


if __name__ == '__main__':
    unittest.main()
