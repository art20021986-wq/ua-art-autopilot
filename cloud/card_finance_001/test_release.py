#!/usr/bin/env python3
"""CARD-FINANCE-001: the link on a live card (UA-0013 as FINANCE-PROBE read it), the edits on the live modules."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / 'fixtures'
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent / 'finance_001'))  # ua_finance_partners, installed by FINANCE-001
import candidate_builder  # noqa: E402
import edit_card_lang  # noqa: E402
import edit_metadata  # noqa: E402
import ua_card_finance  # noqa: E402

CARD = (FIXTURES / 'UA-0013.html').read_text(encoding='utf-8')


def candidate_card_lang():
    folder = Path(tempfile.mkdtemp())
    path = folder / 'ua_card_lang.py'
    path.write_bytes(edit_card_lang.build((FIXTURES / 'ua_card_lang.txt').read_bytes()))
    spec = importlib.util.spec_from_file_location('candidate_card_lang', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LinkTests(unittest.TestCase):
    def test_link_after_ask_question_once(self):
        out = ua_card_finance.add(CARD, '/home/Carix/video/UA-0013.html')
        self.assertEqual(out.count('id="ua-finance-link"'), 1)
        self.assertLess(out.index("id='vopros'"), out.index('id="ua-finance-link"'))
        self.assertLess(out.index('id="ua-finance-link"'), out.index('← Все машины'))
        self.assertIn('href="/video/seo/ru/kredit-lizing-avto.html?card=UA-0013"', out)
        self.assertEqual(ua_card_finance.add(out, 'UA-0013.html'), out)
        self.assertEqual(out.replace(ua_card_finance.link('UA-0013'), ''), CARD)  # nothing else changes

    def test_top_block_untouched(self):
        out = ua_card_finance.add(CARD, 'UA-0013.html')
        top = CARD.index("id='vopros'")
        self.assertEqual(out[:top], CARD[:top])

    def test_page_without_anchor_unchanged(self):
        self.assertEqual(ua_card_finance.add('<html><body>x</body></html>', 'UA-0099.html'), '<html><body>x</body></html>')
        self.assertEqual(ua_card_finance.add(CARD, 'katalog.html'), CARD)

    def test_ukrainian_version_text_and_address(self):
        lang = candidate_card_lang()
        page = '<html><body><p>x</p>%s</body></html>' % ua_card_finance.link('UA-0013')
        uk, missing = lang.ukrainian(page, {})
        self.assertEqual(missing, [])
        self.assertIn('href="/video/seo/ua/kredyt-lizynh-avto.html?card=UA-0013"', uk)
        self.assertIn('>Кредити та лізинг</a>', uk)


class EditTests(unittest.TestCase):
    def test_candidate(self):
        source = {name: (FIXTURES / (name[:-3] + '.txt')).read_bytes() for name in candidate_builder.SOURCE_FILES}
        result = candidate_builder.build(source, {})
        self.assertEqual(sorted(result), ['ua_card_finance.py', 'ua_card_lang.py', 'ua_seo_metadata.py'])
        meta = result['ua_seo_metadata.py'].decode()
        self.assertIn("SEO_REVISION = 'CARD-FINANCE-001'", meta)
        self.assertIn('        source = ua_card_finance.add(source, name)', meta)
        for value in result.values():
            compile(value, 'x', 'exec')
        with self.assertRaisesRegex(ValueError, 'METADATA_FRAGMENT'):
            edit_metadata.build(result['ua_seo_metadata.py'])


if __name__ == '__main__':
    unittest.main()
