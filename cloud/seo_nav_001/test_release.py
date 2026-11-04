#!/usr/bin/env python3
"""SEO-NAV-001 on the live landing generator (FINANCE-001 fixture + FINANCE-001 and SEO-HEADER-001 edits)."""
import importlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
CLOUD = HERE.parent
FIXTURES = CLOUD / 'finance_001' / 'fixtures'
MODULES = Path(tempfile.mkdtemp())
for name in ('ua_seo_order_models', 'ua_seo_quick_form', 'ua_seo_schema'):
    (MODULES / (name + '.py')).write_bytes((FIXTURES / (name + '.txt')).read_bytes())
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(CLOUD / 'finance_001'))
sys.path.insert(2, str(CLOUD / 'seo_header_001'))
sys.path.insert(3, str(MODULES))
import candidate_builder  # noqa: E402
import edit_landings  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def live():
    finance = load('finance_edit', CLOUD / 'finance_001' / 'edit_landings.py')
    header = load('header_edit', CLOUD / 'seo_header_001' / 'edit_landings.py')
    return header.build(finance.build((FIXTURES / 'ua_seo_landings.txt').read_bytes()))


def pages(source):
    folder = Path(tempfile.mkdtemp())
    (folder / 'ua_seo_landings.py').write_bytes(source)
    sys.path.insert(0, str(folder))
    sys.modules.pop('ua_seo_landings', None)
    try:
        return importlib.import_module('ua_seo_landings').pages([], (), frozenset())
    finally:
        sys.path.remove(str(folder))


class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = pages(live())
        cls.after = pages(candidate_builder.build({edit_landings.NAME: live()}, {})[edit_landings.NAME])

    def test_only_terms_left(self):
        uk, ru = self.after['seo/ua/kredyt-lizynh-avto.html'], self.after['seo/ru/kredit-lizing-avto.html']
        self.assertIn('<header><nav><a href="/video/info.html">Умови</a></nav></header>', uk)
        self.assertIn('<header><nav><a href="/video/info.html">Условия</a></nav></header>', ru)
        for page in self.after.values():
            nav = page[page.index('<header><nav>'):page.index('</nav></header>')]
            for gone in ('/video/index.html', '/video/katalog.html', '/video/podbor.html', 'hreflang'):
                self.assertNotIn(gone, nav)

    def test_top_block_and_rest_unchanged(self):
        import re
        nav = re.compile(r'<header><nav>.*?</nav></header>', re.S)
        self.assertEqual(sorted(self.before), sorted(self.after))
        for name in self.before:
            self.assertEqual(nav.sub('', self.before[name]), nav.sub('', self.after[name]), name)
            self.assertIn('<header class="site-header">', self.after[name])

    def test_edit_refused_twice(self):
        once = edit_landings.build(live())
        with self.assertRaisesRegex(ValueError, 'LANDINGS_NAV_FRAGMENT'):
            edit_landings.build(once)


if __name__ == '__main__':
    unittest.main()
