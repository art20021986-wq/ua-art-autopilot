#!/usr/bin/env python3
"""LOGO-001: the header modules on copies of the live pages (2026-11-28: home, catalogue, card UA-0023, order page,
landing) and the candidate on the installed sources (ua_brand_home.py as installed by PERF-CWV-001)."""
from pathlib import Path
import re
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import ua_brand_home  # noqa: E402
import ua_header_nav  # noqa: E402
import ua_logo_c  # noqa: E402

BLOCK = re.compile(r'<!--UA-BRAND-HOME-V1-->.*?<!--/UA-BRAND-HOME-V1-->', re.S)
PAGES = ('index.html', 'katalog.html', 'card.html', 'podbor.html', 'landing.html')


def fixture(name):
    return (HERE/'fixtures'/name).read_text(encoding='utf-8')


def head(html):
    return html[:html.index('</head>')]


def without_release(html):
    """The page with the header block emptied and the buttons out: what must be identical before and after."""
    return BLOCK.sub('', ua_header_nav.remove(html))


class ModuleTests(unittest.TestCase):
    def test_logo_is_the_approved_file(self):
        self.assertEqual(ua_logo_c.SVG, (HERE.parent/'logo_001/c_badge.svg').read_text(encoding='utf-8'))

    def test_only_the_header_changes(self):
        for name in PAGES:
            with self.subTest(name):
                live = fixture(name)
                page = candidate_builder.page(live)
                self.assertNotEqual(page, live)
                self.assertEqual(without_release(page), without_release(live))
                self.assertEqual(candidate_builder.page(page), page)
                self.assertEqual(len(BLOCK.findall(page)), 1)
                self.assertIn(ua_logo_c.URI, head(page))

    def test_no_ring_and_no_caption(self):
        for home in (False, True):
            style = ua_brand_home.block(home)
            self.assertNotIn('outline:1.5px', style)
            self.assertNotIn('2190', style)
            self.assertNotIn('brand-copy::after', style)
            self.assertIn('outline:0!important', style)

    def test_buttons_before_the_switch_except_home(self):
        self.assertNotIn(ua_header_nav.START, candidate_builder.page(fixture('index.html')))
        self.assertNotIn('.ua-hnav', head(candidate_builder.page(fixture('index.html'))))
        for name in ('katalog.html', 'card.html', 'podbor.html', 'landing.html'):
            with self.subTest(name):
                page = candidate_builder.page(fixture(name))
                self.assertEqual(page.count(ua_header_nav.NAV), 1)
                at = page.index(ua_header_nav.NAV) + len(ua_header_nav.NAV)
                self.assertRegex(page[at:at + 40], r'^<(div|nav) class="lang-toggle')
                self.assertIn('.ua-hnav-home span::after{content:"Головна"}', head(page))
                self.assertEqual(ua_header_nav.remove(page).count('ua-hnav'), head(page).count('ua-hnav'))

    def test_labels_by_language(self):
        style = ua_header_nav.CSS
        for rule in ('html[lang^="ru"] .ua-hnav-home span::after{content:"Главная"}',
                     'html[lang^="ka"] .ua-hnav-home span::after{content:"მთავარი"}',
                     'html[lang^="ka"] .ua-hnav-back span::after{content:"უკან"}',
                     '.ua-hnav-back span::after{content:"Назад"}', 'height:30px!important', 'inset:-7px -3px'):
            self.assertIn(rule, style)

    def test_back_only_from_our_site(self):
        self.assertIn('href="/video/index.html" onclick="event.stopPropagation();try{if(history.length-1)'
                      'if(/(^|\\.)uaart\\.com\\.ua$/.test(new window.URL(document.referrer).hostname))'
                      '{history.back();return false}}catch(e){}"', ua_header_nav.NAV)
        self.assertNotIn('&', ua_header_nav.NAV)

    def test_page_without_header_or_head(self):
        self.assertEqual(ua_header_nav.apply('<p>x</p>'), '<p>x</p>')
        self.assertEqual(ua_brand_home.apply('<p>x</p>'), '<p>x</p>')
        self.assertEqual(ua_brand_home.apply('<p>x</p></body>'), '<p>x</p>' + ua_brand_home.block(False) + '</body>')


class BuildTests(unittest.TestCase):
    def source(self):
        return {'ua_brand_home.py': (HERE/'fixtures/ua_brand_home.txt').read_bytes(),
                'ua_seo_metadata.py': (HERE/'fixtures/ua_seo_metadata.txt').read_bytes(),
                'catalog_design_golden.html': fixture('katalog.html').encode('utf-8'),
                'video/index.html': fixture('index.html').encode('utf-8'),
                'video/katalog.html': fixture('katalog.html').encode('utf-8'),
                'video/podbor.html': fixture('podbor.html').encode('utf-8')}

    def test_candidate(self):
        result = candidate_builder.build(self.source(), {})
        self.assertEqual(set(result) - set(self.source()), set(candidate_builder.NEW_MODULES))
        metadata = self.source()['ua_seo_metadata.py']
        self.assertEqual(result['ua_seo_metadata.py'],
                         metadata.replace(b"\nSEO_REVISION = 'PERF-CWV-001'\n", b"\nSEO_REVISION = 'LOGO-001'\n"))
        self.assertIn(b'# SEO-PRICE-001:', result['ua_seo_metadata.py'])
        self.assertEqual(result['ua_brand_home.py'], (HERE/'ua_brand_home.py').read_bytes())
        for name in ('catalog_design_golden.html', 'video/katalog.html', 'video/podbor.html'):
            self.assertEqual(result[name].decode('utf-8').count(ua_header_nav.NAV), 1)
        self.assertNotIn(ua_header_nav.NAV, result['video/index.html'].decode('utf-8'))
        for name in candidate_builder.NEW_MODULES + ('ua_brand_home.py',):
            compile(result[name], name, 'exec')

    def test_live_modules_must_be_the_installed_ones(self):
        for name in ('ua_brand_home.py', 'ua_seo_metadata.py'):
            source = self.source()
            source[name] += b'\n'
            with self.assertRaisesRegex(ValueError, 'LOGO_LIVE_MODULE_UNEXPECTED:' + name):
                candidate_builder.build(source, {})

    def test_second_application_is_refused(self):
        result = candidate_builder.build(self.source(), {})
        with self.assertRaisesRegex(ValueError, 'LOGO_ALREADY_APPLIED'):
            candidate_builder.edit('ua_seo_metadata.py', result['ua_seo_metadata.py'])
        with self.assertRaisesRegex(ValueError, 'LOGO_REVISION'):
            candidate_builder.edit('ua_seo_metadata.py', b'X = 1\n')


if __name__ == '__main__':
    unittest.main()
