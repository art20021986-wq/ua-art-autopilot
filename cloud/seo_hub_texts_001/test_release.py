#!/usr/bin/env python3
"""SEO-HUB-TEXTS-001: owner-approved sections on the Korea hub and custom-order pages (FINANCE-001 fixtures)."""
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
FIXTURES = FINANCE / 'fixtures'
MODULES = Path(tempfile.mkdtemp())
for name in ('ua_seo_order_models', 'ua_seo_quick_form', 'ua_seo_schema'):
    (MODULES / (name + '.py')).write_bytes((FIXTURES / (name + '.txt')).read_bytes())
(MODULES / 'ua_seo_header.py').write_bytes((HEADER / 'ua_seo_header.py').read_bytes())
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(FINANCE))
sys.path.insert(2, str(MODULES))
import candidate_builder  # noqa: E402
import edit_landings  # noqa: E402
import ua_seo_hub_texts as texts  # noqa: E402


def _module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live_landings():
    """The landing generator after FINANCE-001 and SEO-HEADER-001 (the fixture with those releases' edits)."""
    source = _module(FINANCE / 'edit_landings.py', 'finance_edit_landings').build((FIXTURES / 'ua_seo_landings.txt').read_bytes())
    return _module(HEADER / 'edit_landings.py', 'header_edit_landings').build(source)


def candidate():
    folder = Path(tempfile.mkdtemp())
    for name, value in candidate_builder.build({edit_landings.NAME: live_landings()}, {}).items():
        (folder / name).write_bytes(value)
    sys.path.insert(0, str(folder))
    for name in ('ua_seo_landings', 'ua_seo_hub_texts'):
        sys.modules.pop(name, None)
    try:
        return importlib.import_module('ua_seo_landings')
    finally:
        sys.path.remove(str(folder))


def faq_questions(page):
    for block in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', page, re.S):
        data = json.loads(block)
        for node in data.get('@graph', [data]) if isinstance(data, dict) else data:
            if node.get('@type') == 'FAQPage':
                return [q['name'] for q in node['mainEntity']]
    return []


class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.L = candidate()
        cls.pages = cls.L.pages([], (), frozenset())

    def test_hub_sections_once_after_intro_with_links(self):
        for lang in ('uk', 'ru'):
            page = self.pages[self.L.path(lang)]
            t = texts.TEXTS[lang]
            for title in (t['why_title'], t['models_title'], t['check_title']):
                self.assertEqual(page.count('<h2>%s</h2>' % title), 1, (lang, title))
            self.assertLess(page.index(t['why_title']), page.index('<h2>%s</h2>' % self.L.T[lang]['models']))
            for key in (texts.K5, texts.SONATA) + texts.CROSSOVERS:
                self.assertIn('<a href="/video/%s">%s %s</a>' % ((self.L.path(lang, key),) + key), page)
            self.assertIn('<a href="/video/%s">' % self.L.path(lang, texts.LPI), page)
            self.assertIn('132', page)

    def test_order_page_steps_and_questions_in_text_and_markup(self):
        for lang in ('uk', 'ru'):
            page = self.pages[self.L.path(lang, self.L.ORDER)]
            t = texts.TEXTS[lang]
            self.assertEqual(page.count('<h2>%s</h2><ol>' % t['steps_title']), 1)
            questions = faq_questions(page)
            for question, _ in t['faq']:
                self.assertIn('<h3>%s</h3>' % question, page)
                self.assertIn(question, questions)

    def test_other_pages_unchanged(self):
        folder = Path(tempfile.mkdtemp())
        (folder / 'ua_seo_landings.py').write_bytes(live_landings())
        sys.path.insert(0, str(folder))
        sys.modules.pop('ua_seo_landings', None)
        try:
            live = importlib.import_module('ua_seo_landings').pages([], (), frozenset())
        finally:
            sys.path.remove(str(folder))
            sys.modules.pop('ua_seo_landings', None)
        changed = {self.L.path(lang) for lang in ('uk', 'ru')} | {self.L.path(lang, self.L.ORDER) for lang in ('uk', 'ru')}
        self.assertEqual(set(live), set(self.pages))
        for name in set(live) - changed:
            self.assertEqual(live[name], self.pages[name], name)
        for name in changed:
            self.assertNotEqual(live[name], self.pages[name], name)

    def test_edit_refused_twice(self):
        once = edit_landings.build(live_landings())
        with self.assertRaisesRegex(ValueError, 'LANDINGS_FRAGMENT_NOT_UNIQUE'):
            edit_landings.build(once)


if __name__ == '__main__':
    unittest.main()
