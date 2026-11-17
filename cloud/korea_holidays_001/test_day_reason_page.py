import pathlib
import unittest

import day_reason_page
import korea_holidays

LIVE = (pathlib.Path(__file__).with_name('fixtures') / 'korea_live.html').read_bytes()  # live page 17.11


class DayReasonTest(unittest.TestCase):
    def test_reason_replaces_the_zero_count_only(self):
        out = day_reason_page.build(LIVE).decode('utf-8')
        self.assertIn('"<small>"+reason(d,c)+"</small></button>"', out)
        self.assertIn('"dayoff": ["Вихідний", "Выходной", "დასვენების დღე"]', out)
        self.assertIn('var HOL={"2026/12/25":["Різдво","Рождество","შობა"]};', out)
        self.assertIn('t("days")+"</b><small>"+n(lots.length)+" "+t("cars")', out)  # «Усі дні» keeps its count
        rest = out
        for old, new in reversed(day_reason_page.edits()):
            rest = rest.replace(new, old, 1)
        self.assertEqual(rest.encode('utf-8'), LIVE)

    def test_applied_once_and_unknown_page_refused(self):
        with self.assertRaises(ValueError):
            day_reason_page.build(day_reason_page.build(LIVE))
        with self.assertRaises(ValueError):
            day_reason_page.build(LIVE.replace(day_reason_page.COUNT.encode('utf-8'), b''))

    def test_table_shape(self):
        for day, names in korea_holidays.HOLIDAYS.items():
            self.assertRegex(day, r'^20\d\d/(0[1-9]|1[0-2])/(0[1-9]|[12]\d|3[01])$')
            self.assertEqual(len(names), 3)
            self.assertTrue(all(names))


if __name__ == '__main__':
    unittest.main()
