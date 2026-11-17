import pathlib
import unittest

import lot_rows
import search_filters

LIVE = (pathlib.Path(__file__).with_name('fixtures') / 'korea_live.html').read_bytes()  # live page 17.11
ROWS = lot_rows.build(LIVE)  # the filters use the lot window words (fuel, colour) the rows module adds


class SearchFiltersTest(unittest.TestCase):
    def test_lists_and_conditions(self):
        out = search_filters.build(ROWS).decode('utf-8')
        for piece in ('<select id="kl-year"></select>', '<select id="kl-year-to"></select>', '<select id="kl-km"></select>',
                      '<select id="kl-fuel"></select>', '<select id="kl-color"></select>',
                      '&&(!yt||l.year<=yt)&&(!fu||l.fuel===fu)&&(!co||l.color===co)', 'lists();', 'function years(){',
                      '"any": ["Будь-який", "Любой", "ნებისმიერი"]', 'KMS=[30000,50000,75000,100000,150000,200000,250000,300000]'):
            self.assertIn(piece, out)
        self.assertNotIn('<input id="kl-year"', out)
        self.assertNotIn('<input id="kl-km"', out)
        self.assertIn('<input id="kl-usd"', out)  # the price stays as it is

    def test_only_these_edits(self):
        out = search_filters.build(ROWS).decode('utf-8')
        rest = out
        for old, new in reversed(search_filters.EDITS):
            rest = rest.replace(new, old, 1)
        self.assertEqual(rest.encode('utf-8'), ROWS)

    def test_applied_once_and_unknown_page_refused(self):
        with self.assertRaises(ValueError):
            search_filters.build(search_filters.build(ROWS))
        with self.assertRaises(ValueError):
            search_filters.build(ROWS.replace(search_filters.KM.encode('utf-8'), b''))

    def test_list_keys_match_the_collector_and_the_rows(self):
        from korea_auction import color, fuel
        self.assertEqual(set(search_filters.COLORS), {name for name, _ in color.FAMILIES} | {'other'})
        self.assertEqual({'color_' + c for c in search_filters.COLORS}, {w[0] for w in lot_rows.COLOR_WORDS} - {'color'})
        self.assertTrue(all(fuel.key(f) == f for f in ('gasoline', 'diesel', 'lpg', 'electric', 'hydrogen')))


if __name__ == '__main__':
    unittest.main()
