"""The KOREA-GALLERY candidate from the Korea page as KOREA-ENGINE-INSTALL leaves it."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder as cb  # noqa: E402
import lot_gallery_page  # noqa: E402


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.page = (HERE / 'fixtures' / 'korea_live.html').read_bytes()

    def test_only_the_korea_page_with_the_viewer(self):
        files = cb.build({cb.PAGE: self.page}, {})
        self.assertEqual(set(files), {cb.PAGE})
        self.assertEqual(files[cb.PAGE], lot_gallery_page.build(self.page))
        self.assertFalse(cb.is_page(cb.PAGE))

    def test_installed_page_is_refused(self):
        with self.assertRaises(ValueError):
            cb.build({cb.PAGE: cb.build({cb.PAGE: self.page}, {})[cb.PAGE]}, {})


if __name__ == '__main__':
    unittest.main()
