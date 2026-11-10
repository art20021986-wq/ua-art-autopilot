import pathlib
import random
import unittest
from datetime import datetime

from korea_auction import lots, nbu, selection, ticker

FIX = pathlib.Path(__file__).with_name('fixtures')


class LotsTest(unittest.TestCase):
    def test_results_rows(self):
        found = lots.parse_results((FIX / 'results_rows.html').read_text())
        self.assertEqual(len(found), 2)
        first = found[0]
        self.assertEqual(first['id'], '20261106043479')
        self.assertEqual((first['house'], first['lot_no']), ('Auto Hub Auction', '3001'))
        self.assertEqual((first['mileage_km'], first['year'], first['engine_cc']), (151000, 2010, 3342))
        self.assertEqual(first['detail_url'], '/vehicle-detail/kr/20261106043479')
        self.assertEqual(len(first['photos']), 3)

    def test_detail(self):
        html = ('<p>Engine: G6DB&nbsp; Fuel: Gasoline&nbsp; Vehicle History: For Private Use&nbsp; '
                'Type: SEDAN&nbsp; Engine: Minor Noise</p> Starting Price 0 KRW Starting Price 2,100,000 KRW'
                '<table><tr><th>Manufacturer</th><td>HYUNDAI</td></tr><tr><th>Chassis No.</th><td>KMH</td></tr></table>'
                '<table><tr><th>Date</th><th>Sold Price</th></tr>'
                '<tr><td>a</td><td>b</td><td>c</td><td>d</td><td>e</td><td>1,900,000</td></tr></table>'
                '<img src="https://image-cdn-hub.beforward.jp/a/1"><img src="https://image-cdn-hub.beforward.jp/a/1">')
        d = lots.parse_detail(html)
        self.assertEqual(d['start_price_krw'], 2100000)
        self.assertEqual((d['fuel'], d['history'], d['body']), ('Gasoline', 'For Private Use', 'SEDAN'))
        self.assertEqual(d['specs']['Chassis No.'], 'KMH')
        self.assertEqual(d['market_sold_krw'], [1900000])
        self.assertEqual(len(d['photos']), 1)


class SelectionTest(unittest.TestCase):
    def test_top_model_whole_words(self):
        self.assertEqual(selection.top_model({'model': 'THE NEW SANTA FE'}), 'SANTA FE')
        self.assertIsNone(selection.top_model({'model': 'K50'}))

    def test_next_date_and_candidates(self):
        lots_ = [{'model': 'K5', 'auction_start': '2026/11/10 13:00', 'photos': [1]},
                 {'model': 'TUCSON', 'auction_start': '2026/11/11 13:00', 'photos': [1]},
                 {'model': 'MORNING', 'auction_start': '2026/11/11 13:00', 'photos': [1]}]
        date = selection.next_auction_date(lots_, datetime(2026, 11, 10, 10, tzinfo=selection.JST))
        self.assertEqual(date, '2026/11/11')
        self.assertEqual([l['model'] for l in selection.candidates(lots_, date, random.Random(0))], ['TUCSON'])

    def test_hot(self):
        self.assertTrue(selection.is_hot(1_000_000, [1_500_000, 1_400_000]))
        self.assertFalse(selection.is_hot(1_300_000, [1_500_000, 1_400_000]))
        self.assertFalse(selection.is_hot(1_000_000, [2_000_000]))


class NbuTest(unittest.TestCase):
    def test_cross_rate(self):
        rates = nbu.parse_rates([{'cc': 'USD', 'rate': 41.5, 'exchangedate': '10.11.2026'},
                                 {'cc': 'KRW', 'rate': 0.0316}])
        self.assertEqual(nbu.krw_to_usd(11_700_000, rates), 8909)
        with self.assertRaises(ValueError):
            nbu.parse_rates([{'cc': 'USD', 'rate': 41.5, 'exchangedate': 'x'}])


class TickerTest(unittest.TestCase):
    ITEM = {'title': 'Kia K5', 'year': 2022, 'mileage_km': 48000, 'score': 'AA', 'start_price_krw': 11700000,
            'start_price_usd': 8909, 'photo': 'https://x/1"><script>', 'auction_start_jst': '2026/11/11 13:00',
            'hot': True}

    def test_render_three_languages_and_escaping(self):
        html = ticker.render({'lots_on_date': 2382, 'items': [self.ITEM]})
        self.assertIn('$8 909', html)
        self.assertIn('₩11,7 млн', html)
        self.assertIn('data-ka="ხვალ აუქციონი"', html)
        self.assertIn('Завтра на торгах 2 382 авто', html)
        self.assertIn('class="kt-lead"', html)
        self.assertIn('<b>2 382</b>', html)
        self.assertNotIn('"><script>', html)
        self.assertEqual(html.count('class="kt-item"'), 2)  # duplicated track for a seamless loop

    def test_empty(self):
        self.assertEqual(ticker.render({'lots_on_date': 0, 'items': []}), '')


if __name__ == '__main__':
    unittest.main()
