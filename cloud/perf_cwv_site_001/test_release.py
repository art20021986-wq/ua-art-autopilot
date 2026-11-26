#!/usr/bin/env python3
"""PERF-CWV-001: the modules on copies of the live pages (2026-11-26) and the candidate on the installed sources
(ua_brand_home.py and site_ge_inject.py as read by PERF-CWV-PROBE-20261126-R2)."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import ua_brand_home  # noqa: E402
import ua_head_block  # noqa: E402
import ua_lang_bar  # noqa: E402
import ua_layout_reserve  # noqa: E402
import ua_lcp_photo  # noqa: E402
import ua_mobile_comfort  # noqa: E402


def fixture(name):
    return (HERE/'fixtures'/name).read_text(encoding='utf-8')


def head(html):
    return html[:html.index('</head>')]


class ModuleTests(unittest.TestCase):
    def test_every_block_in_head_once_and_stable(self):
        for name in ('index.html', 'katalog.html', 'card.html', 'podbor.html'):
            with self.subTest(name):
                page = candidate_builder.page(fixture(name))
                self.assertEqual(candidate_builder.page(page), page)
                for mark in ('UA-MOBILE-COMFORT-V1', 'UA-BRAND-HOME-V1'):
                    self.assertEqual(page.count('<!--%s-->' % mark), 1)
                    self.assertIn('<!--%s-->' % mark, head(page))

    def test_home_keeps_the_ticker_height(self):
        page = ua_layout_reserve.apply(fixture('index.html'))
        self.assertIn('html #ua-korea-ticker:empty{display:block;min-height:494px}', head(page))
        self.assertEqual(ua_layout_reserve.apply(fixture('card.html')), fixture('card.html'))
        self.assertEqual(ua_layout_reserve.remove(page), fixture('index.html'))

    def test_card_switch_written_before_the_contacts(self):
        card = fixture('card.html')
        page = ua_lang_bar.apply(card)
        self.assertEqual(page.count(ua_lang_bar.BAR), 1)
        self.assertLess(page.index("<div class='shapka'>"), page.index(ua_lang_bar.BAR))
        self.assertEqual(page.index(ua_lang_bar.BAR) + len(ua_lang_bar.BAR), page.index("<div class='svyaz'>"))
        self.assertIn('<style id="ua-lang-bar">', head(page))
        self.assertEqual(ua_lang_bar.remove(page), card)

    def test_catalogue_switch_gets_ge_like_the_script(self):
        catalog = fixture('katalog.html')
        self.assertNotIn('data-lang="ka"', catalog)
        page = ua_lang_bar.apply(catalog)
        self.assertEqual(page.count(ua_lang_bar.GE), 1)
        self.assertNotIn('UA-LANG-BAR-V1', page)
        self.assertEqual(ua_lang_bar.apply(page), page)
        self.assertEqual(ua_lang_bar.remove(page), catalog)

    def test_home_switch_with_ge_is_unchanged(self):
        self.assertEqual(ua_lang_bar.apply(fixture('index.html')), fixture('index.html'))

    def test_first_two_catalogue_photos_at_once(self):
        catalog = fixture('katalog.html')
        page = ua_lcp_photo.apply(catalog)
        self.assertEqual(page.count(ua_lcp_photo.FIRST), 1)
        self.assertEqual(page.count(' loading="eager"'), 2)
        self.assertEqual(page.count(' loading="lazy"'), catalog.count(' loading="lazy"') - 2)
        self.assertEqual(ua_lcp_photo.apply(page), page)
        self.assertEqual(ua_lcp_photo.remove(page), catalog)
        for name in ('index.html', 'card.html', 'podbor.html'):
            self.assertEqual(ua_lcp_photo.apply(fixture(name)), fixture(name))

    def test_logo_style_moves_into_head(self):
        card = fixture('card.html')
        self.assertGreater(card.index(ua_brand_home.MARK), card.index('</head>'))
        page = ua_brand_home.apply(card)
        self.assertEqual(page.count(ua_brand_home.MARK), 1)
        self.assertIn(ua_brand_home.MARK, head(page))
        self.assertIn(ua_brand_home.block(False), page)
        self.assertEqual(ua_brand_home.apply(page), page)
        self.assertEqual(len(page), len(card))

    def test_logo_style_on_page_without_head(self):
        self.assertEqual(ua_brand_home.apply('<p>x</p></body>'), '<p>x</p>' + ua_brand_home.block(False) + '</body>')
        self.assertEqual(ua_brand_home.apply('<p>x</p>'), '<p>x</p>')

    def test_phone_sizes(self):
        page = ua_mobile_comfort.apply(fixture('card.html'))
        style = head(page)
        for rule in ('.header-phone b{white-space:nowrap}', 'font-size:12px!important',
                     '.korea-ticker .kt-arrow{width:44px;height:44px', '.site-header .header-contacts a{min-height:48px}'):
            self.assertIn(rule, style)
        self.assertEqual(ua_mobile_comfort.remove(page), fixture('card.html'))

    def test_head_block_replaced_in_place(self):
        html = '<head><b>1</b></head><body></body>'
        once = ua_head_block.put(html, 'M', 'x')
        self.assertEqual(once, '<head><b>1</b><!--M-->x<!--/M--></head><body></body>')
        self.assertEqual(ua_head_block.put(once, 'M', 'y'), '<head><b>1</b><!--M-->y<!--/M--></head><body></body>')
        self.assertEqual(ua_head_block.put('<p></p>', 'M', 'x'), '<p></p>')
        self.assertEqual(ua_head_block.take(once, 'M'), html)


class BuildTests(unittest.TestCase):
    def source(self):
        return {'ua_brand_home.py': (HERE/'fixtures/ua_brand_home.txt').read_bytes(),
                'site_ge_inject.py': (HERE/'fixtures/site_ge_inject.txt').read_bytes(),
                'ua_seo_metadata.py': b"X = 1\nSEO_REVISION = 'CHAT-BRAND-001'\n",
                'catalog_design_golden.html': fixture('katalog.html').encode('utf-8'),
                'video/index.html': fixture('index.html').encode('utf-8'),
                'video/katalog.html': fixture('katalog.html').encode('utf-8'),
                'video/podbor.html': fixture('podbor.html').encode('utf-8')}

    def test_candidate(self):
        result = candidate_builder.build(self.source(), {})
        self.assertEqual(set(result) - set(self.source()), set(candidate_builder.NEW_MODULES))
        inject = result['site_ge_inject.py'].decode('utf-8')
        self.assertTrue(inject.endswith(candidate_builder.INJECT_TAIL))
        compile(inject, 'site_ge_inject.py', 'exec')
        self.assertIn("SEO_REVISION = 'PERF-CWV-001'", result['ua_seo_metadata.py'].decode('utf-8'))
        golden = result['catalog_design_golden.html'].decode('utf-8')
        self.assertNotIn(ua_lcp_photo.FIRST, golden)
        self.assertIn(ua_lcp_photo.FIRST, result['video/katalog.html'].decode('utf-8'))
        self.assertEqual(result['ua_brand_home.py'], (HERE/'ua_brand_home.py').read_bytes())

    def test_live_module_must_be_the_installed_one(self):
        source = self.source()
        source['ua_brand_home.py'] += b'\n'
        with self.assertRaisesRegex(ValueError, 'PERF_CWV_LIVE_MODULE_UNEXPECTED'):
            candidate_builder.build(source, {})

    def test_second_application_is_refused(self):
        result = candidate_builder.build(self.source(), {})
        with self.assertRaisesRegex(ValueError, 'PERF_CWV_ALREADY_APPLIED'):
            candidate_builder.edit('site_ge_inject.py', result['site_ge_inject.py'])
        with self.assertRaisesRegex(ValueError, 'PERF_CWV_REVISION'):
            candidate_builder.edit('ua_seo_metadata.py', b'X = 1\n')


if __name__ == '__main__':
    unittest.main()
