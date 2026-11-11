#!/usr/bin/env python3
"""TERMS-LINKS-001: the candidate on the live sources (pages fetched 2026-11-11, module fixtures of the installed chain)."""
from pathlib import Path
import re
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import ua_terms_links  # noqa: E402

F = HERE / 'fixtures'
PAGES = {'video/index.html': 'index.html', 'video/katalog.html': 'katalog.html', 'video/podbor.html': 'podbor.html',
         'video/korea.html': 'korea.html'}
ANCHOR = re.compile(r'<a\b[^>]*info\.html', re.I)


def source():
    value = {name: (F / fixture).read_bytes() for name, fixture in PAGES.items()}
    value['video/info.html'] = (F / 'info.html').read_bytes()  # no link on it: left out of the candidate
    value['site_ge_inject.py'] = (F / 'site_ge_inject.txt').read_bytes()
    value['ua_seo_landings.py'] = (F / 'ua_seo_landings.txt').read_bytes()
    value['catalog_design_golden.html'] = (F / 'katalog.html').read_bytes()
    return value


class Release(unittest.TestCase):
    def setUp(self):
        self.source = source()
        self.result = candidate_builder.build(self.source, {})

    def test_every_live_link_removed(self):
        for name in PAGES:
            before, after = self.source[name].decode(), self.result[name].decode()
            self.assertTrue(ANCHOR.search(before), name)
            self.assertFalse(ANCHOR.search(after), name)
            self.assertEqual(ua_terms_links.apply(after), after)
        home = self.result['video/index.html'].decode()
        self.assertNotIn('Умови, строки та гарантії', home)
        self.assertIn('href="katalog.html"', home)
        podbor = self.result['video/podbor.html'].decode()
        self.assertIn('id="ua-seo-order-intro"', podbor)  # kept, so ua_seo_metadata does not add the link again
        self.assertNotIn('Умови купівлі та доставки', podbor)

    def test_terms_page_stays(self):
        self.assertNotIn('video/info.html', self.result)

    def test_only_links_removed(self):
        for name in PAGES:
            before, after = self.source[name].decode(), self.result[name].decode()
            removed = [m.group() for m in ua_terms_links.LINK.finditer(before)]
            rest = before
            for item in removed:
                rest = rest.replace(item, '', 1)
            self.assertEqual(rest, after, name)

    def test_landing_header(self):
        page = (F / 'landing_uk.html').read_text(encoding='utf-8')
        after = ua_terms_links.apply(page)
        self.assertNotIn('<header><nav>', after)
        self.assertEqual(len(page) - len(after), len('<header><nav><a href="/video/info.html">Умови</a></nav></header>'))
        self.assertIn('<link rel="canonical"', after)

    def test_tails_and_refusal(self):
        inject = self.result['site_ge_inject.py'].decode()
        self.assertTrue(inject.rstrip().endswith('return ua_terms_links.apply(_ua_terms_base_inject(source))'))
        landings = self.result['ua_seo_landings.py'].decode()
        self.assertIn('_ua_terms_base_pages = pages', landings)
        for name in ('site_ge_inject.py', 'ua_seo_landings.py'):
            compile(self.result[name], name, 'exec')
            with self.assertRaisesRegex(ValueError, 'TERMS_ALREADY_APPLIED'):
                candidate_builder.edit(name, self.result[name])

    def test_chains_run(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'ua_terms_links.py').write_bytes(self.result['ua_terms_links.py'])
            sys.path.insert(0, folder)
            try:
                namespace = {'inject_html': lambda s: s + '<a href="info.html">x</a>'}
                code = self.result['site_ge_inject.py'].decode()
                exec(code[code.index('# TERMS-LINKS-001'):], namespace)
                self.assertEqual(namespace['inject_html']('<p>'), '<p>')
                namespace = {'pages': lambda *a, **k: {'seo/ua/x.html': '<header><nav><a href="/video/info.html">Умови</a></nav></header><h1>x</h1>'}}
                code = self.result['ua_seo_landings.py'].decode()
                exec(code[code.index('# TERMS-LINKS-001'):], namespace)
                self.assertEqual(namespace['pages']([], set(), set()), {'seo/ua/x.html': '<h1>x</h1>'})
            finally:
                sys.path.remove(folder)

    def test_untouched(self):
        self.assertEqual(ua_terms_links.apply('<a href="katalog.html">k</a>'), '<a href="katalog.html">k</a>')
        self.assertEqual(ua_terms_links.apply('<a href="korea-info.html">k</a>'), '<a href="korea-info.html">k</a>')
        self.assertEqual(ua_terms_links.apply('<link rel="canonical" href="https://x/video/info.html">'),
                         '<link rel="canonical" href="https://x/video/info.html">')
        self.assertEqual(ua_terms_links.apply('<a href="info.html?v=5">Условия и гарантии</a>|'), '|')


if __name__ == '__main__':
    unittest.main()
