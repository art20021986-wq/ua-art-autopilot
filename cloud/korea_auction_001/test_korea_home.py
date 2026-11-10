import pathlib
import unittest

import ua_korea_home as m

LIVE = (pathlib.Path(__file__).parent / 'fixtures' / 'index_live.html').read_text()


class KoreaHomeTest(unittest.TestCase):
    def test_adds_mark_and_slot_once(self):
        out = m.apply(LIVE)
        self.assertEqual(out.count(m.MARK), 1)
        self.assertEqual(out.count('id="ua-korea-ticker"'), 1)
        self.assertEqual(out.count('class="ua-kr-live"'), 1)
        self.assertEqual(m.apply(out), out)  # idempotent

    def test_flag_leads_to_korea_page(self):
        out = m.apply(LIVE)
        self.assertEqual(out.count(m.FLAG_TO), 1)
        self.assertNotIn(m.FLAG_FROM, out)

    def test_upgrade_of_a_page_from_the_first_version(self):
        first = m.apply(LIVE).replace(m.FLAG_TO, m.FLAG_FROM)  # as installed by KOREA-AUCTION-INSTALL-20261110-R3
        out = m.apply(first)
        self.assertEqual(out, m.apply(LIVE))
        self.assertEqual(out.count('class="ua-kr-live"'), 1)

    def test_badge_inside_korea_flag_link(self):
        out = m.apply(LIVE)
        link = out[out.index(m.FLAG_TO):]
        self.assertLess(link.index('ua-kr-live'), link.index('</a>'))

    def test_slot_right_after_hero(self):
        out = m.apply(LIVE)
        hero_end = out.index('</section>', out.index(m.HERO)) + len('</section>')
        self.assertTrue(out[hero_end:].startswith(m.MARK))

    def test_only_additions(self):
        out = m.apply(LIVE)
        changed = out.replace(m.BADGE, '').replace(m.MARK + m.STYLE + m.SLOT, '').replace(m.FLAG_TO, m.FLAG_FROM)
        self.assertEqual(changed, LIVE)  # only the mark, the slot and the flag link change

    def test_remove_restores_the_page(self):
        self.assertEqual(m.remove(m.apply(LIVE)), LIVE)

    def test_other_pages_unchanged(self):
        for page in ('<html><body>katalog</body></html>', None, ''):
            self.assertEqual(m.apply(page), page)


if __name__ == '__main__':
    unittest.main()
