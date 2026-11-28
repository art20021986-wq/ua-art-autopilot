#!/usr/bin/env python3
"""LOGO-CARD-001: the fixed ua_header_nav in the installed writer chain. The installed modules are taken from their
packages (LOGO-001: cloud/logo_site_001, PERF-CWV-001: cloud/perf_cwv_site_001), pinned by hash; pages: copies of the
live pages of 2026-11-28 (LOGO-001 fixtures) and a fresh card as the writers have it before ua_lang_bar."""
import hashlib
import importlib.util
from pathlib import Path
import re
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402

LOGO = HERE.parent/'logo_site_001'
PERF = HERE.parent/'perf_cwv_site_001'
# name -> (reference copy, sha256 of the copy installed on the server).
INSTALLED = {'ua_header_nav.py': (LOGO, candidate_builder.MODULE_SHA256),
             'ua_brand_home.py': (LOGO, '7e296af87c9b6d74a0cb67b8a78a6e5ce3f7ce28d400ac205ae80a3ff8760e74'),
             'ua_logo_c.py': (LOGO, 'c1e35eecd094427695f20b0c15f6b3e2594826e606d8930f1ef32f5991b9d17b'),
             'ua_head_block.py': (PERF, 'd2f5dbead3de3678ef4f74d27b602ae69a239cf6a1014595894c29767aa29c75'),
             'ua_layout_reserve.py': (PERF, '1782d0ee3d654d62aae5d10ef525952931f0fae7ea2c264e483ca78067f609bc'),
             'ua_lang_bar.py': (PERF, '34a623dcd79439b34cbee2607349930d9da23e7e9263fbd81c06698754d7574a'),
             'ua_mobile_comfort.py': (PERF, 'bc5f48b409f059071eda4e1bb15cfac36c22d72d636417a76f10f6019c972131')}
ORDER = ('ua_logo_c', 'ua_header_nav', 'ua_head_block', 'ua_brand_home', 'ua_layout_reserve', 'ua_lang_bar',
         'ua_mobile_comfort')
PAGES = ('index.html', 'katalog.html', 'card.html', 'podbor.html', 'landing.html')


def sha(value):
    return hashlib.sha256(value).hexdigest()


def installed(name):
    folder, digest = INSTALLED[name]
    value = (folder/name).read_bytes()
    if sha(value) != digest:
        raise AssertionError('REFERENCE_COPY_CHANGED:' + name)
    return value


class Writers:
    """The writer modules with the given ua_header_nav, loaded apart from sys.modules (ua_brand_home imports it)."""

    def __init__(self, nav):
        saved = {name: sys.modules.pop(name) for name in ORDER if name in sys.modules}
        try:
            for name in ORDER:
                path = nav if name == 'ua_header_nav' else INSTALLED[name + '.py'][0]/(name + '.py')
                if name != 'ua_header_nav':
                    installed(name + '.py')
                spec = importlib.util.spec_from_file_location(name, path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                setattr(self, name, module)
        finally:
            for name in ORDER:
                sys.modules.pop(name, None)
            sys.modules.update(saved)

    def card(self, html):
        """The card chain: ua_mobile_comfort(ua_lang_bar(ua_layout_reserve(ua_brand_home(html))))."""
        return self.ua_mobile_comfort.apply(self.ua_lang_bar.apply(self.ua_layout_reserve.apply(
            self.ua_brand_home.apply(html))))


OLD = Writers(LOGO/'ua_header_nav.py')
NEW = Writers(HERE/'ua_header_nav.py')
NAV = NEW.ua_header_nav.NAV
SWITCH = re.compile(r'<(?:div|nav) class="lang-toggle')


def fixture(name):
    return (LOGO/'fixtures'/name).read_text(encoding='utf-8')


def fresh():
    value = (HERE/candidate_builder.FIXTURE).read_bytes()
    assert sha(value) == candidate_builder.FIXTURE_SHA256
    return value.decode('utf-8')


def head(html):
    return html[:html.index('</head>')]


def before_switch(html):
    at = html.index(NAV) + len(NAV)
    return html.count(NAV) == 1 and SWITCH.match(html, at) is not None


class ModuleTests(unittest.TestCase):
    def test_installed_module_is_the_logo_001_one(self):
        self.assertEqual(sha(installed('ua_header_nav.py')), candidate_builder.MODULE_SHA256)
        self.assertNotEqual(sha((HERE/'ua_header_nav.py').read_bytes()), candidate_builder.MODULE_SHA256)
        self.assertEqual((OLD.ua_header_nav.NAV, OLD.ua_header_nav.CSS), (NEW.ua_header_nav.NAV, NEW.ua_header_nav.CSS))

    def test_pages_with_a_switch_as_before(self):
        for name in PAGES:
            with self.subTest(name):
                live = fixture(name)
                self.assertEqual(NEW.ua_brand_home.apply(live), OLD.ua_brand_home.apply(live))
                self.assertEqual(NEW.ua_header_nav.apply(live), OLD.ua_header_nav.apply(live))
                self.assertEqual(NEW.card(live), OLD.card(live))

    def test_buttons_before_the_switch_except_home(self):
        self.assertNotIn(NEW.ua_header_nav.START, NEW.ua_brand_home.apply(fixture('index.html')))
        for name in ('katalog.html', 'card.html', 'podbor.html', 'landing.html'):
            with self.subTest(name):
                page = NEW.ua_brand_home.apply(fixture(name))
                self.assertTrue(before_switch(page))
                self.assertIn('.ua-hnav-home span::after{content:"Головна"}', head(page))

    def test_labels_by_language(self):
        style = NEW.ua_header_nav.CSS
        for rule in ('html[lang^="ru"] .ua-hnav-home span::after{content:"Главная"}',
                     'html[lang^="ka"] .ua-hnav-home span::after{content:"მთავარი"}',
                     'html[lang^="ka"] .ua-hnav-back span::after{content:"უკან"}',
                     '.ua-hnav-back span::after{content:"Назад"}', 'height:30px!important', 'inset:-7px -3px'):
            self.assertIn(rule, style)

    def test_back_only_from_our_site(self):
        self.assertIn('href="/video/index.html" onclick="event.stopPropagation();try{if(history.length-1)'
                      'if(/(^|\\.)uaart\\.com\\.ua$/.test(new window.URL(document.referrer).hostname))'
                      '{history.back();return false}}catch(e){}"', NAV)
        self.assertNotIn('&', NAV)

    def test_page_without_header(self):
        self.assertEqual(NEW.ua_header_nav.apply('<p>x</p>'), '<p>x</p>')
        self.assertEqual(NEW.ua_header_nav.apply("<div class='svyaz'></div>"), "<div class='svyaz'></div>")
        self.assertEqual(NEW.ua_brand_home.apply('<p>x</p>'), '<p>x</p>')


class FreshCardTests(unittest.TestCase):
    """The card as the writers have it when ua_brand_home runs: no switch yet (ua_lang_bar writes it later)."""

    def test_fixture_has_no_switch_and_no_buttons(self):
        card = fresh()
        self.assertNotIn('lang-toggle', card)
        self.assertNotIn(NAV, card)
        self.assertEqual(card.count("<div class='svyaz'>"), 1)

    def test_logo_001_gave_the_card_no_buttons(self):
        card = fresh()
        self.assertEqual(OLD.ua_brand_home.apply(card), card)
        self.assertNotIn(NAV, OLD.card(card))

    def test_brand_home_then_lang_bar(self):
        card = fresh()
        page = NEW.ua_lang_bar.apply(NEW.ua_brand_home.apply(card))
        self.assertTrue(before_switch(page))
        self.assertEqual(page.count(NAV), 1)
        self.assertEqual(page.index(NAV) + len(NAV), page.index(NEW.ua_lang_bar.BAR))
        # Everything else byte for byte as the chain writes it now.
        self.assertEqual(NEW.ua_header_nav.remove(page), OLD.ua_lang_bar.apply(OLD.ua_brand_home.apply(card)))
        self.assertEqual(page, OLD.ua_lang_bar.apply(card).replace(NEW.ua_lang_bar.BAR, NAV + NEW.ua_lang_bar.BAR, 1))

    def test_whole_card_chain(self):
        card = fresh()
        page = NEW.card(card)
        self.assertTrue(before_switch(page))
        self.assertEqual(NEW.ua_header_nav.remove(page), OLD.card(card))
        at = page.index(NAV)
        self.assertRegex(page[:at], r"<div class='logo'><div class='znak'>UA</div><div><div class='imya'>UA ART COMPANY"
                                    r"</div><div class='pod'>[^<]*</div></div></div>$")

    def test_reapplying_changes_nothing(self):
        page = NEW.card(fresh())
        self.assertEqual(NEW.card(page), page)
        self.assertEqual(NEW.ua_brand_home.apply(page), page)
        self.assertEqual(NEW.ua_header_nav.apply(page), page)


class BuildTests(unittest.TestCase):
    def source(self):
        metadata = (LOGO/'fixtures/ua_seo_metadata.txt').read_bytes().replace(
            b"\nSEO_REVISION = 'PERF-CWV-001'\n", b"\nSEO_REVISION = 'LOGO-001'\n")
        return {'ua_header_nav.py': installed('ua_header_nav.py'), 'ua_seo_metadata.py': metadata}

    def test_installed_metadata_is_what_logo_001_wrote(self):
        self.assertEqual(sha(self.source()['ua_seo_metadata.py']), candidate_builder.METADATA_SHA256)

    def test_candidate(self):
        source = self.source()
        result = candidate_builder.build(source, {})
        self.assertEqual(set(result), {'ua_header_nav.py', 'ua_seo_metadata.py'})
        self.assertEqual(result['ua_header_nav.py'], (HERE/'ua_header_nav.py').read_bytes())
        self.assertEqual(result['ua_seo_metadata.py'], source['ua_seo_metadata.py'].replace(
            b"\nSEO_REVISION = 'LOGO-001'\n", b"\nSEO_REVISION = 'LOGO-CARD-001'\n"))
        self.assertIn(b'# SEO-PRICE-001:', result['ua_seo_metadata.py'])
        for name, value in result.items():
            compile(value, name, 'exec')

    def test_live_modules_must_be_the_installed_ones(self):
        for name in ('ua_header_nav.py', 'ua_seo_metadata.py'):
            source = self.source()
            source[name] += b'\n'
            with self.assertRaisesRegex(ValueError, 'LOGO_CARD_LIVE_MODULE_UNEXPECTED:' + name):
                candidate_builder.build(source, {})

    def test_second_application_is_refused(self):
        result = candidate_builder.build(self.source(), {})
        with self.assertRaisesRegex(ValueError, 'LOGO_CARD_ALREADY_APPLIED'):
            candidate_builder.edit(result['ua_seo_metadata.py'])
        with self.assertRaisesRegex(ValueError, 'LOGO_CARD_REVISION'):
            candidate_builder.edit(b"SEO_REVISION = 'PERF-CWV-001'\n")


if __name__ == '__main__':
    unittest.main()
