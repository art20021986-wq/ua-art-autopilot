import pathlib
import unittest

import engine_page

LIVE = (pathlib.Path(__file__).with_name('fixtures') / 'korea_live.html').read_bytes()  # live page 13.11 (KOREA-TIME)


class EnginePageTest(unittest.TestCase):
    def test_engine_row_gets_the_type_and_nothing_else_changes(self):
        out = engine_page.build(LIVE).decode('utf-8')
        self.assertIn(engine_page.CHECK, out)
        self.assertIn('engine(l)+row("vin",l.vin)', out)
        self.assertNotIn(engine_page.ROW, out)
        self.assertIn('"fuel_diesel": ["дизель", "дизель", "დიზელი"]', out)
        rest = out
        for old, new in reversed(engine_page.EDITS):
            rest = rest.replace(new, old, 1)
        self.assertEqual(rest.encode('utf-8'), LIVE)  # only the three edits

    def test_applied_once(self):
        with self.assertRaises(ValueError):
            engine_page.build(engine_page.build(LIVE))

    def test_unknown_page_is_refused(self):
        with self.assertRaises(ValueError):
            engine_page.build(LIVE.replace(engine_page.ROW.encode('utf-8'), b''))

    def test_types_match_the_collector(self):
        from korea_auction import fuel
        keys = {fuel.key(v) for v in ('Gasoline', 'Diesel', 'LPG', 'Electric', 'Gasoline+Electric', 'Hydrogen')}
        self.assertEqual(keys, {item[0] for item in engine_page.FUEL})


if __name__ == '__main__':
    unittest.main()
