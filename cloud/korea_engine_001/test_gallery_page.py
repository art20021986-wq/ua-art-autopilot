import pathlib
import unittest

import gallery_page

LIVE = (pathlib.Path(__file__).with_name('fixtures') / 'korea_live.html').read_bytes()


class GalleryPageTest(unittest.TestCase):
    def test_only_the_card_gallery_changes(self):
        out = gallery_page.build(LIVE).decode('utf-8')
        self.assertIn(gallery_page.CHECK, out)
        self.assertIn('scrollTop=0;gallery(l);', out)
        rest = out
        for old, new in reversed(gallery_page.EDITS):
            rest = rest.replace(new, old, 1)
        self.assertEqual(rest.encode('utf-8'), LIVE)

    def test_applied_once_and_unknown_page_refused(self):
        with self.assertRaises(ValueError):
            gallery_page.build(gallery_page.build(LIVE))
        with self.assertRaises(ValueError):
            gallery_page.build(LIVE.replace(gallery_page.SHOWN.encode('utf-8'), b''))


if __name__ == '__main__':
    unittest.main()
