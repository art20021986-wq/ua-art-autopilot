#!/usr/bin/env python3
"""SEO-PREPAY-001: on the live generator (FINANCE-001 fixtures + SEO-HEADER-001, SEO-HUB-TEXTS-001 and
SEO-UKRAINE-PAGE-001 as installed) the «how we work» step and the «how to order a car from Korea» answer say
«service 600 $ + prepayment 1 000 $»; 500 $ stays only for catalogue cars."""
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
UKRAINE = HERE.parent / 'seo_ukraine_page_001'
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

NEW = {'uk': 'послуга — 600 $, передоплата — 1 000 $ (зараховується у вартість авто)',
       'ru': 'услуга — 600 $, предоплата — 1 000 $ (засчитывается в стоимость авто)'}
ORDER_Q = {'uk': 'Як замовити авто з Кореї?', 'ru': 'Как заказать авто из Кореи?'}


def _module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live_sources():
    """ua_seo_landings as installed after SEO-UKRAINE-PAGE-001 (its modules are copied in by render)."""
    text = (FIXTURES / 'ua_seo_landings.txt').read_bytes()
    for package in (FINANCE, HEADER, HUB, UKRAINE):
        text = _module(package / 'edit_landings.py', package.name + '_edit').build(text)
    return {edit_landings.NAME: text}


def installed_modules():
    models = _module(UKRAINE / 'edit_models.py', 'ukraine_models').build((FIXTURES / 'ua_seo_order_models.txt').read_bytes())
    return {'ua_seo_order_models.py': models, 'ua_seo_hub_texts.py': (UKRAINE / 'ua_seo_hub_texts.py').read_bytes(),
            'ua_seo_ukraine_page.py': (UKRAINE / 'ua_seo_ukraine_page.py').read_bytes()}


def render(files):
    folder = Path(tempfile.mkdtemp())
    for name, value in dict(installed_modules(), **files).items():
        (folder / name).write_bytes(value)
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

    def test_no_new_pages(self):
        self.assertEqual(set(self.pages), set(self.before))

    def test_order_answer_and_step_say_600_and_1000(self):
        for lang in ('uk', 'ru'):
            hub = self.pages[self.L.path(lang)]
            self.assertEqual(hub.count(NEW[lang]), 3, lang)  # «how we work» step, FAQ text, FAQPage answer
            answers = {}
            for block in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', hub, re.S):
                data = json.loads(block)
                for node in data.get('@graph', [data]):
                    if node.get('@type') == 'FAQPage':
                        answers = {q['name']: q['acceptedAnswer']['text'] for q in node['mainEntity']}
            self.assertIn(NEW[lang], answers[ORDER_Q[lang]])

    def test_500_only_for_catalogue_cars(self):
        contract_500 = re.compile(r'(договір|договор)[^<]{0,40}(депозит|передоплата|предоплата) 500')
        for name, html in self.pages.items():  # Japan's own order terms are not part of this task
            if any(v in html for v in NEW.values()):
                self.assertIsNone(contract_500.search(html.split('<body', 1)[-1]), name)  # head: catalogue description
        for lang in ('uk', 'ru'):
            self.assertIn('в каталозі від' if lang == 'uk' else 'в каталоге от', self.pages[self.L.path(lang)])
            self.assertIn('500 $', self.pages[self.L.path(lang)])  # the hub description (catalogue cars) keeps it

    def test_only_pages_with_the_step_or_the_answer_change(self):
        changed = {n for n in self.before if self.before[n] != self.pages[n]}
        carrying = {n for n, html in self.pages.items() if any(v in html for v in NEW.values())}
        self.assertTrue(changed)
        self.assertEqual(changed, {n for n in carrying if self.before[n].count('1 000 $') < self.pages[n].count('1 000 $')})

    def test_edits_refused_twice(self):
        once = candidate_builder.build(self.live, {})
        with self.assertRaisesRegex(ValueError, 'LANDINGS_FRAGMENT_NOT_UNIQUE'):
            edit_landings.build(once[edit_landings.NAME])


if __name__ == '__main__':
    unittest.main()
