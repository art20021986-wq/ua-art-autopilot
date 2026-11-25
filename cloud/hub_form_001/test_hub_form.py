#!/usr/bin/env python3
"""ADS-LP-001 edits against the live sources (sanitized copies: phone numbers read [N]; no edited line has one)."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder as cb  # noqa: E402

FIX = HERE / 'fixtures'


def quick_module(text):
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'quick_preview.py'
        path.write_text(text, encoding='utf-8')
        spec = importlib.util.spec_from_file_location('quick_preview', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class EditTests(unittest.TestCase):
    def test_landings(self):
        text = cb.edit('ua_seo_landings.py', (FIX / 'ua_seo_landings.txt').read_text())
        self.assertIn('перевіряє їх і робить пригон через Грузію до Києва.', text)
        self.assertIn('проверяет их и делает пригон через Грузию в Киев.', text)
        self.assertNotIn('доставляє через Грузію та передає в Києві', text)
        self.assertEqual(text.count('quick_form.hub_block(lang) + hub_texts.hub('), 1)
        with self.assertRaisesRegex(ValueError, 'HUB_FRAGMENT'):
            cb.edit('ua_seo_landings.py', text)  # never twice

    def test_auction(self):
        text = cb.edit('ua_order/auction.py', (FIX / 'auction.txt').read_text())
        self.assertIn("SOURCE_PATHS = frozenset(('/video/korea.html',)) | HUB_PATHS", text)
        for path in cb.HUB_PATHS:
            self.assertIn(path, text)
        self.assertIn("'Корея под ключ'", text)
        self.assertIn("'Авто из Кореи под ключ' if hub else 'Доступ к аукционам онлайн'", text)

    def test_hub_form(self):
        source = (FIX / 'ua_seo_quick_form.txt').read_text()
        module = quick_module(source.rstrip('\n') + cb.QUICK_TAIL)
        uk, ru = module.hub_block('uk'), module.hub_block('ru')
        self.assertEqual(module.hub_block('ka'), '')
        for html, title in ((uk, 'Отримати пропозицію на авто з Кореї'), (ru, 'Получить предложение на авто из Кореи')):
            self.assertEqual(html.count('data-auction="korea"'), 1)
            self.assertNotIn('data-model=', html)
            self.assertIn('<h2>%s</h2>' % title, html)
            self.assertIn('quick-lead.js', html)
            self.assertIn('autocomplete="tel"', html)
        self.assertIn('data-model="kia-k5"', module.block('uk', ('Kia', 'K5')))  # model pages unchanged

    def test_build_pins_live_files(self):
        with self.assertRaisesRegex(ValueError, 'INPUT_HASH'):
            cb.build({name: b'x' for name in cb.SOURCE_SHA256}, {name: b'x' for name in cb.DEPENDENCY_SHA256})
        self.assertEqual(set(cb.targets(None)), set(cb.SOURCE_SHA256))


if __name__ == '__main__':
    unittest.main()
