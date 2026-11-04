#!/usr/bin/env python3
"""SEO-HEADER-001: the top block on every landing page, built on the live generator (FINANCE-001 fixtures)."""
import importlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
FINANCE = HERE.parent / 'finance_001'
FIXTURES = FINANCE / 'fixtures'
MODULES = Path(tempfile.mkdtemp())
for name in ('ua_seo_order_models', 'ua_seo_quick_form', 'ua_seo_schema'):
    (MODULES / (name + '.py')).write_bytes((FIXTURES / (name + '.txt')).read_bytes())
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(FINANCE))
sys.path.insert(2, str(MODULES))
import candidate_builder  # noqa: E402
import edit_landings  # noqa: E402
import ua_seo_header  # noqa: E402



def live_landings():
    """The landing generator as FINANCE-001 installed it (the fixture with that release's edit)."""
    spec = importlib.util.spec_from_file_location('finance_edit_landings', FINANCE / 'edit_landings.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build((FIXTURES / 'ua_seo_landings.txt').read_bytes())


def candidate():
    folder = Path(tempfile.mkdtemp())
    for name, value in candidate_builder.build({edit_landings.NAME: live_landings()}, {}).items():
        (folder / name).write_bytes(value)
    sys.path.insert(0, str(folder))
    for name in ('ua_seo_landings', 'ua_seo_header'):
        sys.modules.pop(name, None)
    try:
        return importlib.import_module('ua_seo_landings')
    finally:
        sys.path.remove(str(folder))


class ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = candidate().pages([], (), frozenset())

    def test_every_page_has_the_block_once_before_its_navigation(self):
        for name, page in self.pages.items():
            self.assertEqual(page.count('<header class="site-header">'), 1, name)
            self.assertLess(page.index('<header class="site-header">'), page.index('<header><nav>'), name)
            self.assertIn('href="https://wa.me/380992222002"', page)
            self.assertIn('Viber</a>', page)

    def test_languages_link_the_page_versions(self):
        uk = self.pages['seo/ua/kredyt-lizynh-avto.html']
        self.assertIn('<a href="/video/seo/ru/kredit-lizing-avto.html" hreflang="ru" lang="ru">RU</a>', uk)
        self.assertIn('<a href="/video/seo/ua/kredyt-lizynh-avto.html" hreflang="uk" lang="uk" aria-current="true">UA</a>', uk)
        self.assertIn('<a href="/video/index.html?lang=ka" hreflang="ka" lang="ka">GE</a>', uk)
        ru = self.pages['seo/ru/kredit-lizing-avto.html']
        self.assertIn('>Позвонить<', ru)
        self.assertIn('>Офис на карте<', ru)

    def test_not_sticky(self):
        self.assertNotIn('sticky', ua_seo_header.CSS)
        self.assertIn('.site-header{position:static', ua_seo_header.CSS)

    def test_edit_refused_twice(self):
        once = edit_landings.build(live_landings())
        with self.assertRaisesRegex(ValueError, 'LANDINGS_FRAGMENT_NOT_UNIQUE'):
            edit_landings.build(once)


if __name__ == '__main__':
    unittest.main()
