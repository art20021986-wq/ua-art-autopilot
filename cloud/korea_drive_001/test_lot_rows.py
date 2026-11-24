import pathlib
import unittest

import lot_rows

LIVE = (pathlib.Path(__file__).with_name('fixtures') / 'korea_live.html').read_bytes()  # live page 17.11


class LotRowsTest(unittest.TestCase):
    def test_drive_row_after_gear_and_nothing_else_changes(self):
        out = lot_rows.build(LIVE).decode('utf-8')
        self.assertIn('row("gear",l.transmission)+drive(l)+color(l)', out)
        self.assertIn('"color_black": ["чорний", "черный", "შავი"]', out)
        self.assertIn('"drive_full": ["повний", "полный", "სრული"]', out)
        rest = out
        for old, new in reversed(lot_rows.EDITS):
            rest = rest.replace(new, old, 1)
        self.assertEqual(rest.encode('utf-8'), LIVE)

    def test_applied_once_and_unknown_page_refused(self):
        with self.assertRaises(ValueError):
            lot_rows.build(lot_rows.build(LIVE))
        with self.assertRaises(ValueError):
            lot_rows.build(LIVE.replace(lot_rows.ROW.encode('utf-8'), b''))

    def test_keys_match_the_collector(self):
        from korea_auction import drive
        from korea_auction import color
        self.assertEqual({'drive_' + name for name, _ in drive.MARKS},
                         {item[0] for item in lot_rows.DRIVE_WORDS} - {'drive'})
        self.assertEqual({'color_' + name for name, _ in color.FAMILIES} | {'color_other'},
                         {item[0] for item in lot_rows.COLOR_WORDS} - {'color'})


if __name__ == '__main__':
    unittest.main()
