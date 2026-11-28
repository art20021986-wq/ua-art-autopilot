#!/usr/bin/env python3
"""CARD-FULLSCREEN-001: the candidate on copies of the live Korea and Japan pages (2026-11-28) and the stylesheet."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import release_constants  # noqa: E402

STYLE = (HERE/'lot-card.css').read_text(encoding='utf-8')


def live():
    return {name: (HERE/'fixtures'/(Path(name).stem + '_live.html')).read_bytes() for name in candidate_builder.PAGES}


class CandidateTests(unittest.TestCase):
    def test_candidate_is_the_stylesheet_and_one_line_on_each_auction_page(self):
        source = live()
        files = candidate_builder.build(source, {})
        self.assertEqual(set(files), {'video/order/lot-card.css', 'video/korea.html', 'video/japan.html'})
        self.assertEqual(files['video/order/lot-card.css'].decode('utf-8'), STYLE)
        for name in candidate_builder.PAGES:
            page = files[name].decode('utf-8')
            self.assertEqual(page.count(candidate_builder.LINE), 1)
            self.assertIn(candidate_builder.LINE + '</head>', page)
            self.assertEqual(candidate_builder.unpage(page).encode('utf-8'), source[name])  # nothing else changes

    def test_refuses_twice_and_pages_without_the_lot_card(self):
        page = candidate_builder.page(live()['video/korea.html'].decode('utf-8'))
        with self.assertRaises(ValueError):
            candidate_builder.page(page)
        with self.assertRaises(ValueError):
            candidate_builder.page('<html><head></head><body><p>catalog</p></body></html>')

    def test_health_checks_name_only_pages_that_exist_before_the_install(self):
        for url in release_constants.HEALTH_CHECKS:
            self.assertTrue(url.startswith('https://www.uaart.com.ua/video/'))
            self.assertIn(url.rsplit('/', 1)[1], ('index.html', 'korea.html', 'japan.html'))


class StyleTests(unittest.TestCase):
    def test_phone_only(self):
        body = STYLE[STYLE.index('*/') + 2:].strip()
        self.assertTrue(body.startswith('@media (max-width: 760px) {'))
        self.assertTrue(body.endswith('}'))

    def test_full_screen_pinned_buttons_and_no_background_scroll(self):
        for piece in ('height: 100dvh', 'max-height: 100dvh', 'overscroll-behavior: contain', 'html:has(#kl-card[open])',
                      'overflow: hidden', 'env(safe-area-inset-top)', '#kl-card .um-toolbar', 'position: sticky',
                      '#kl-card .kl-close { position: fixed', '#kl-card .ls-btn { position: fixed'):
            self.assertIn(piece, STYLE)

    def test_no_new_buttons_or_content(self):
        self.assertNotIn('content:', STYLE)
        self.assertNotIn('display: none', STYLE)


if __name__ == '__main__':
    unittest.main()
