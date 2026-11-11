"""The KOREA-HOW candidate from the live Korea and home pages."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder as cb  # noqa: E402


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.page = (HERE / 'fixtures' / 'korea_live.html').read_text()
        self.home = (HERE / 'fixtures' / 'home_live.html').read_text()

    def test_block_is_placed_before_the_auctions(self):
        new = cb.build({cb.PAGE: self.page.encode(), cb.HOME: self.home.encode()}, {})[cb.PAGE].decode()
        steps = cb.block(self.home)
        self.assertIn('5 кроків до вашого авто', steps)
        self.assertEqual(new.count(cb.START), 1)
        self.assertEqual(new.replace(steps, '', 1), self.page)
        self.assertLess(new.index('Два способи купити авто з UA ART'), new.index(cb.START))
        self.assertEqual(new.index(cb.START) + len(steps), new.index(cb.ANCHOR))

    def test_installed_page_is_refused(self):
        new = cb.apply(self.page, cb.block(self.home))
        with self.assertRaises(ValueError):
            cb.apply(new, cb.block(self.home))

    def test_unexpected_home_is_refused(self):
        with self.assertRaises(ValueError):
            cb.block(self.home.replace(cb.START, '<section class="other">'))


if __name__ == '__main__':
    unittest.main()
