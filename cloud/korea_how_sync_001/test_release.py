"""The KOREA-HOW-SYNC candidate from the live Korea page."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder as cb  # noqa: E402


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.page = (HERE / 'fixtures' / 'korea_live.html').read_text()

    def test_script_follows_the_block(self):
        new = cb.build({cb.PAGE: self.page.encode()}, {})[cb.PAGE].decode()
        self.assertEqual(new.count(cb.SCRIPT), 1)
        self.assertEqual(new.replace(cb.SCRIPT, '', 1), self.page)
        start = new.index(cb.START)
        self.assertEqual(new.index(cb.END, start) + len(cb.END), new.index(cb.SCRIPT))

    def test_installed_page_is_refused(self):
        with self.assertRaises(ValueError):
            cb.apply(cb.apply(self.page))

    def test_page_without_the_block_is_refused(self):
        with self.assertRaises(ValueError):
            cb.apply(self.page.replace(cb.START, '<section class="other">'))


if __name__ == '__main__':
    unittest.main()
