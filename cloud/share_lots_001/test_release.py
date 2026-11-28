#!/usr/bin/env python3
"""SHARE-LOTS-001: the candidate on copies of the live Korea and Japan pages (2026-11-28) and the share script."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import release_constants  # noqa: E402

SCRIPT = (HERE/'lot-share.js').read_text(encoding='utf-8')


def live():
    return {name: (HERE/'fixtures'/(Path(name).stem + '_live.html')).read_bytes() for name in candidate_builder.PAGES}


class CandidateTests(unittest.TestCase):
    def test_candidate_is_the_script_and_one_line_on_each_auction_page(self):
        source = live()
        files = candidate_builder.build(source, {})
        self.assertEqual(set(files), {'video/order/lot-share.js', 'video/korea.html', 'video/japan.html'})
        self.assertEqual(files['video/order/lot-share.js'].decode('utf-8'), SCRIPT)
        for name in candidate_builder.PAGES:
            page = files[name].decode('utf-8')
            self.assertEqual(page.count(candidate_builder.LINE), 1)
            self.assertIn(candidate_builder.LINE + '</body>', page)
            self.assertEqual(candidate_builder.unpage(page).encode('utf-8'), source[name])  # nothing else changes

    def test_refuses_twice_and_pages_without_the_lot_card(self):
        page = candidate_builder.page(live()['video/korea.html'].decode('utf-8'))
        with self.assertRaises(ValueError):
            candidate_builder.page(page)
        with self.assertRaises(ValueError):
            candidate_builder.page('<html><body><p>catalog</p></body></html>')

    def test_health_checks_name_only_pages_that_exist_before_the_install(self):
        for url in release_constants.HEALTH_CHECKS:
            self.assertTrue(url.startswith('https://www.uaart.com.ua/video/'))
            self.assertIn(url.rsplit('/', 1)[1], ('index.html', 'korea.html', 'japan.html'))


class ScriptTests(unittest.TestCase):
    def test_web_share_first_then_the_catalog_menu(self):
        # MDN Web Share API: call share() from the click, check canShare(), a cancelled sheet (AbortError) is no error
        for piece in ('navigator.share(current)', 'navigator.canShare(current)', "e.name !== 'AbortError'",
                      'https://t.me/share/url?url=', 'https://wa.me/?text=', 'navigator.clipboard.writeText',
                      "getElementById('kl-card')", 'menu.showModal()'):
            self.assertIn(piece, SCRIPT)

    def test_link_is_the_country_page_with_the_lot(self):
        self.assertIn("/^#lot-[\\w-]+$/.exec(location.hash)", SCRIPT)
        self.assertIn('location.origin + location.pathname', SCRIPT)  # filters in the address are not shared

    def test_three_languages(self):
        for word in ('Поділитися', 'Поделиться', 'გაზიარება', 'Скопіювати посилання', 'Скопировать ссылку'):
            self.assertIn(word, SCRIPT)

    def test_no_partner_or_auction_names(self):
        for word in ('2mcars', 'vsbrothers', 'vs brothers', 'copart', 'iaai', 'autoplus', 'sellca'):
            self.assertNotIn(word, SCRIPT.lower())


if __name__ == '__main__':
    unittest.main()
