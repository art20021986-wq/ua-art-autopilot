import pathlib
import unittest

import drive_page

LIVE = (pathlib.Path(__file__).with_name('fixtures') / 'korea_live.html').read_bytes()  # live page 17.11


class DrivePageTest(unittest.TestCase):
    def test_drive_row_after_gear_and_nothing_else_changes(self):
        out = drive_page.build(LIVE).decode('utf-8')
        self.assertIn('row("gear",l.transmission)+drive(l)', out)
        self.assertIn('"drive_full": ["повний", "полный", "სრული"]', out)
        rest = out
        for old, new in reversed(drive_page.EDITS):
            rest = rest.replace(new, old, 1)
        self.assertEqual(rest.encode('utf-8'), LIVE)

    def test_applied_once_and_unknown_page_refused(self):
        with self.assertRaises(ValueError):
            drive_page.build(drive_page.build(LIVE))
        with self.assertRaises(ValueError):
            drive_page.build(LIVE.replace(drive_page.ROW.encode('utf-8'), b''))

    def test_keys_match_the_collector(self):
        from korea_auction import drive
        self.assertEqual({'drive_' + name for name, _ in drive.MARKS},
                         {item[0] for item in drive_page.WORDS} - {'drive'})


if __name__ == '__main__':
    unittest.main()
