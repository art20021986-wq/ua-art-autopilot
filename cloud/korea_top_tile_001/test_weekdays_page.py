"""KOREA-TOP-TILE-001: the Korea page says the auctions run Monday to Friday."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import weekdays_page  # noqa: E402

LIVE = (HERE / 'fixtures' / 'korea_live.html').read_bytes()  # the live Korea page, 26.11


class WeekdaysPageTest(unittest.TestCase):
    def test_two_texts_change_and_nothing_else(self):
        page = weekdays_page.build(LIVE).decode('utf-8')
        self.assertNotIn('по суботу', page)
        self.assertNotIn('по субботу', page)
        self.assertNotIn('შაბათამდე', page)
        self.assertEqual(page.count("з понеділка по п'ятницю"), 4)  # two attributes + two texts
        rest = LIVE.decode('utf-8')
        for old, new in weekdays_page.EDITS:
            rest = rest.replace(old, new, 1)
        self.assertEqual(rest, page)
        with self.assertRaises(ValueError):
            weekdays_page.build(page.encode('utf-8'))  # applied once only


if __name__ == '__main__':
    unittest.main()
