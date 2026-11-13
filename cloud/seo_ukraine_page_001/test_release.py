#!/usr/bin/env python3
"""SEO-UKRAINE-PAGE-001: the all-Ukraine topic page on the live generator (FINANCE-001 fixtures + SEO-HEADER-001 and
SEO-HUB-TEXTS-001 edits), rendered uk/ru and linked from the Korea hub and the custom-order page."""
import importlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
FINANCE = HERE.parent / 'finance_001'
HEADER = HERE.parent / 'seo_header_001'
HUB = HERE.parent / 'seo_hub_texts_001'
FIXTURES = FINANCE / 'fixtures'
MODULES = Path(tempfile.mkdtemp())
for name in ('ua_seo_quick_form', 'ua_seo_schema'):
    (MODULES / (name + '.py')).write_bytes((FIXTURES / (name + '.txt')).read_bytes())
(MODULES / 'ua_seo_header.py').write_bytes((HEADER / 'ua_seo_header.py').read_bytes())
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(FINANCE))
sys.path.insert(2, str(MODULES))
import candidate_builder  # noqa: E402
import edit_landings  # noqa: E402
import edit_models  # noqa: E402
import ua_seo_ukraine_page as page  # noqa: E402


def _module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live_sources():
    """ua_seo_landings after FINANCE-001, SEO-HEADER-001, SEO-HUB-TEXTS-001; ua_seo_order_models as FINANCE-001 read it."""
    text = (FIXTURES / 'ua_seo_landings.txt').read_bytes()
    for package in (FINANCE, HEADER, HUB):
        text = _module(package / 'edit_landings.py', package.name + '_edit').build(text)
    return {edit_landings.NAME: text, edit_models.NAME: (FIXTURES / 'ua_seo_order_models.txt').read_bytes(),
            'ua_seo_hub_texts.py': (HUB / 'ua_seo_hub_texts.py').read_bytes()}


def render(files):
    folder = Path(tempfile.mkdtemp())
    for name, value in files.items():
        (folder / name).write_bytes(value)
    (folder / 'ua_seo_ukraine_page.py').write_bytes((HERE / 'ua_seo_ukraine_page.py').read_bytes())
    sys.path.insert(0, str(folder))
    for name in [n for n in sys.modules if n.startswith('ua_seo_') and n not in ('ua_seo_header', 'ua_seo_schema', 'ua_seo_quick_form')]:
        sys.modules.pop(name, None)
    try:
        module = importlib.import_module('ua_seo_landings')
        return module, module.pages([], (), frozenset())
    finally:
        sys.path.remove(str(folder))


class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = live_sources()
        cls.before_module, cls.before = render(cls.live)
        cls.L, cls.pages = render(candidate_builder.build(cls.live, {}))

    def test_new_pages_only_the_ukraine_pair(self):
        new = set(self.pages) - set(self.before)
        self.assertEqual(new, {'seo/ua/avto-pid-zamovlennia-v-ukrainu.html', 'seo/ru/avto-pod-zakaz-v-ukrainu.html'})

    def test_page_content_and_markup(self):
        for lang in ('uk', 'ru'):
            html = self.pages[self.L.path(lang, 'ukraine')]
            t = page.TOPIC[lang]
            self.assertEqual(html.count('<h1>%s</h1>' % t['h1']), 1)
            for head, _ in t['sections']:
                self.assertIn('<h2>%s</h2>' % head, html)
            self.assertIn('hreflang="x-default" href="https://www.uaart.com.ua/video/seo/ua/avto-pid-zamovlennia-v-ukrainu.html"', html)
            questions = []
            for block in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
                data = json.loads(block)
                for node in data.get('@graph', [data]):
                    if node.get('@type') == 'FAQPage':
                        questions = [q['name'] for q in node['mainEntity']]
            self.assertEqual(questions, [q for q, _ in t['faq']])
            self.assertNotIn('Запор', html)
            self.assertIsNone(re.search(r'[Пп]ідб|[Пп]одб', repr(t)))  # owner: support, not «подбор» (SERVICE-WORDS)
            self.assertIn('500 $', html)
            self.assertNotIn('без передоплати' if lang == 'uk' else 'без предоплаты', html)
            self.assertIn('1 000 $', html)

    def test_linked_from_hub_and_order_page_only_change_there(self):
        for lang in ('uk', 'ru'):
            href = 'href="/video/%s"' % self.L.path(lang, 'ukraine')
            for key in (None, self.L.ORDER):
                self.assertEqual(self.pages[self.L.path(lang, key)].count(href), 1, (lang, key))
        for lang in ('uk', 'ru'):
            order = self.pages[self.L.path(lang, self.L.ORDER)]
            self.assertNotIn('500 $', order, lang)
            self.assertIn('1 000 $', order)
            self.assertIn('<a class="cta" href="/video/podbor.html">', order)
            self.assertIn('500 $', self.pages[self.L.path(lang)])  # the Korea hub (catalogue cars) keeps it
        changed = {n for n in self.before if self.before[n] != self.pages[n]}
        # The price page shares the «can the price change» answer.
        self.assertEqual(changed, {self.L.path(l, k) for l in ('uk', 'ru') for k in (None, self.L.ORDER, self.L.PRICE)})

    def test_edits_refused_twice(self):
        once = candidate_builder.build(self.live, {})
        with self.assertRaisesRegex(ValueError, 'LANDINGS_FRAGMENT_NOT_UNIQUE'):
            edit_landings.build(once[edit_landings.NAME])
        with self.assertRaisesRegex(ValueError, 'MODELS_FRAGMENT'):
            edit_models.build(once[edit_models.NAME])


if __name__ == '__main__':
    unittest.main()
