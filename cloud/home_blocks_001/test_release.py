#!/usr/bin/env python3
"""HOME-BLOCKS-001: the module on a copy of the live home page (2026-11-27) and the candidate on the installed sources."""
import hashlib
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import ua_home_blocks  # noqa: E402
import ua_layout_reserve  # noqa: E402

INJECT = (HERE/'fixtures/site_ge_inject.txt').read_text(encoding='utf-8')


def home():
    return (HERE/'fixtures/index.html').read_text(encoding='utf-8')


class ModuleTests(unittest.TestCase):
    def test_home_gets_the_block_in_head_once(self):
        page = ua_home_blocks.apply(home())
        head = page[:page.index('</head>')]
        self.assertEqual(page.count('<!--UA-HOME-BLOCKS-V1-->'), 1)
        self.assertIn('<style id="ua-home-blocks">', head)
        self.assertEqual(ua_home_blocks.apply(page), page)
        self.assertEqual(ua_home_blocks.remove(page), home())

    def test_only_css_is_added(self):
        page = ua_home_blocks.apply(home())
        added = page.replace(home()[:home().index('</head>')], '', 1)
        self.assertEqual(len(page) - len(home()), len('<!--UA-HOME-BLOCKS-V1--><!--/UA-HOME-BLOCKS-V1-->')
                         + len(ua_home_blocks.STYLE))
        self.assertTrue(added.startswith('<!--UA-HOME-BLOCKS-V1-->' + ua_home_blocks.STYLE))

    def test_other_pages_unchanged(self):
        for name in ('katalog.html', 'card.html', 'podbor.html'):
            text = (HERE/'fixtures'/name).read_text(encoding='utf-8')
            self.assertEqual(ua_home_blocks.apply(text), text)

    def test_style_matches_the_approved_mockup(self):
        mockup = (HERE/'mockup.css').read_text(encoding='utf-8')
        for rule in ('rgba(232,200,125,.34)', 'border-radius:22px', 'top:-19px', 'rotate(45deg)',
                     '.hero.ua-order-first{overflow:visible', 'margin:44px 40px 0'):
            self.assertIn(rule, mockup)
            self.assertIn(rule, ua_home_blocks.STYLE)

    def test_head_helper_is_the_installed_one(self):
        digest = hashlib.sha256((HERE/'ua_head_block.py').read_bytes()).hexdigest()
        self.assertEqual(digest, candidate_builder.DEPENDENCY_SHA256['ua_head_block.py'])


class BuildTests(unittest.TestCase):
    def source(self):
        installed = INJECT.rstrip('\n') + ('\n\n# PERF-CWV-001\n_ua_perf_base_inject = inject_html\n'
                                           'def inject_html(source):\n    return _ua_perf_base_inject(source)\n')
        catalog = (HERE/'fixtures/katalog.html').read_bytes()
        return {'site_ge_inject.py': installed.encode('utf-8'), 'video/index.html': home().encode('utf-8'),
                'ua_layout_reserve.py': (HERE/'fixtures/ua_layout_reserve_installed.txt').read_bytes(),
                'catalog_design_golden.html': catalog, 'video/katalog.html': catalog,
                'video/korea.html': (HERE/'fixtures/korea.html').read_bytes()}

    def dependencies(self):
        return {'ua_head_block.py': (HERE/'ua_head_block.py').read_bytes()}

    def test_candidate(self):
        result = candidate_builder.build(self.source(), self.dependencies())
        self.assertEqual(set(result), {'ua_home_blocks.py', 'ua_layout_reserve.py', 'site_ge_inject.py', 'video/index.html',
                                       'catalog_design_golden.html', 'video/katalog.html', 'video/korea.html'})
        for name in ('catalog_design_golden.html', 'video/katalog.html', 'video/korea.html'):
            text = result[name].decode('utf-8')
            self.assertIn(ua_layout_reserve.MENU, text)
            self.assertNotIn('UA-HOME-BLOCKS-V1', text)
            self.assertNotIn('ua-korea-ticker,html', text)
        page = result['video/index.html'].decode('utf-8')
        self.assertIn('min-height:max(calc(30vw + 770px),calc(60vw + 620px))', page)
        self.assertNotIn('min-height:494px', page)
        self.assertEqual(page.count('<!--UA-LAYOUT-RESERVE-V1-->'), 1)
        inject = result['site_ge_inject.py'].decode('utf-8')
        self.assertTrue(inject.endswith(candidate_builder.INJECT_TAIL))
        compile(inject, 'site_ge_inject.py', 'exec')
        self.assertIn('<!--UA-HOME-BLOCKS-V1-->', result['video/index.html'].decode('utf-8'))

    def test_installed_reserve_must_be_part_one(self):
        source = self.source()
        source['ua_layout_reserve.py'] += b'\n'
        with self.assertRaisesRegex(ValueError, 'HOME_BLOCKS_LIVE_MODULE_UNEXPECTED'):
            candidate_builder.build(source, self.dependencies())

    def test_refusals(self):
        with self.assertRaisesRegex(ValueError, 'HOME_BLOCKS_DEPENDENCY'):
            candidate_builder.build(self.source(), {'ua_head_block.py': b'other'})
        result = candidate_builder.build(self.source(), self.dependencies())
        with self.assertRaisesRegex(ValueError, 'HOME_BLOCKS_ALREADY_APPLIED'):
            candidate_builder.edit('site_ge_inject.py', result['site_ge_inject.py'])
        with self.assertRaisesRegex(ValueError, 'HOME_BLOCKS_INJECT_MISSING'):
            candidate_builder.edit('site_ge_inject.py', INJECT.encode('utf-8'))


if __name__ == '__main__':
    unittest.main()


class TickerRoomTests(unittest.TestCase):
    def test_room_below_the_measured_ticker(self):
        # measured 2026-11-27 on the live home page: width -> ticker height (px)
        measured = {320: 898, 360: 910, 412: 926, 480: 946, 600: 1023, 768: 669, 1280: 669}
        for width, height in measured.items():
            room = max(0.30 * width + 770, 0.60 * width + 620) if width <= 600 else 640
            self.assertLessEqual(room, height, width)
            self.assertLess(height - room, 60, width)

    def test_room_replaces_the_old_one_in_place(self):
        page = ua_layout_reserve.apply(home())
        self.assertEqual(page.count('<!--UA-LAYOUT-RESERVE-V1-->'), 1)
        self.assertIn(ua_layout_reserve.style(home()), page)
        self.assertEqual(len(page.split('<!--UA-LAYOUT-RESERVE-V1-->')[0]), len(home().split('<!--UA-LAYOUT-RESERVE-V1-->')[0]))


class MenuRoomTests(unittest.TestCase):
    def test_menu_room_only_on_header_pages(self):
        self.assertIn(ua_layout_reserve.MENU, ua_layout_reserve.style(home()))
        card = (HERE/'fixtures/card.html').read_text(encoding='utf-8')
        self.assertEqual(ua_layout_reserve.apply(card), card)
        self.assertEqual(ua_layout_reserve.apply('<html><head></head><body></body></html>'),
                         '<html><head></head><body></body></html>')
