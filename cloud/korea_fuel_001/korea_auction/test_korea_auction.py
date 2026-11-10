import pathlib
import random
import unittest
from datetime import datetime

import tempfile

from korea_auction import catalog, job, lots, nbu, prices, public, selection, ticker

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
        self.assertEqual([l['model'] for l in selection.candidates(lots_, date, rng=random.Random(0))], ['TUCSON'])

    def test_owner_models_first(self):
        lots_ = [{'maker': 'HYUNDAI', 'model': 'TUCSON', 'auction_start': '2026/11/11 13:00', 'photos': [1]},
                 {'maker': 'KIA', 'model': 'K5', 'auction_start': '2026/11/11 13:00', 'photos': [1]}]
        own = selection.candidates(lots_, '2026/11/11', lambda l: l['model'] == 'K5', random.Random(0))
        self.assertEqual([l['model'] for l in own], ['K5', 'TUCSON'])

    def test_hot(self):
        self.assertTrue(selection.is_hot(1_000_000, [1_500_000, 1_400_000]))
        self.assertFalse(selection.is_hot(1_300_000, [1_500_000, 1_400_000]))
        self.assertFalse(selection.is_hot(1_000_000, [2_000_000]))


class CatalogTest(unittest.TestCase):
    def test_owner_catalog_and_models(self):
        cars = catalog.parse((FIX / 'katalog_live.html').read_text())
        self.assertEqual(len(cars), 19)
        k5 = next(c for c in cars if c['code'] == 'UA-0018')
        self.assertEqual((k5['title'], k5['stage'], k5['price_usd']), ('Kia K5 2023', 'kiev', 20300))
        rules = catalog.model_rules(cars)
        same = lambda maker, model: catalog.same_model({'maker': maker, 'model': model}, rules)
        self.assertTrue(same('KIA', 'THE NEW K5'))
        self.assertTrue(same('HYUNDAI', 'SONATA'))
        self.assertTrue(same('MERCEDES-BENZ', 'B Class'))
        self.assertTrue(same('MERCEDES-BENZ', 'E Class'))
        self.assertFalse(same('MERCEDES-BENZ', 'GLS Class'))
        self.assertFalse(same('KIA', 'K50'))
        self.assertEqual(catalog.absolute('ua/UA-0018.html'), 'https://www.uaart.com.ua/video/ua/UA-0018.html')


class NbuTest(unittest.TestCase):
    def test_cross_rate(self):
        rates = nbu.parse_rates([{'cc': 'USD', 'rate': 41.5, 'exchangedate': '10.11.2026'},
                                 {'cc': 'KRW', 'rate': 0.0316}])
        self.assertEqual(nbu.krw_to_usd(11_700_000, rates), 8909)
        with self.assertRaises(ValueError):
            nbu.parse_rates([{'cc': 'USD', 'rate': 41.5, 'exchangedate': 'x'}])


class TickerTest(unittest.TestCase):
    ITEM = {'id': '20261111000123', 'title': 'Kia K5', 'year': 2022, 'mileage_km': 48000, 'score': 'AA', 'start_price_krw': 11700000,
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
        self.assertEqual(html.count('class="kt-item"'), 1)  # a slider: each card once
        self.assertEqual((html.count('kt-arrow kt-prev'), html.count('kt-arrow kt-next')), (1, 1))
        self.assertIn('},2000);', html)  # a step every 2 seconds (owner 2026-11-10)
        self.assertIn('class="kt-clock" data-kt-start="2026/11/11 13:00"', html)  # live countdown, every second
        self.assertIn('setInterval(tick,1000)', html)
        self.assertIn('href="korea.html#lot-%s"' % self.ITEM['id'], html)  # the card opens its lot (owner 2026-11-10)

    def test_fuel_type_in_the_card(self):
        html = ticker.render({'lots_on_date': 5, 'items': [dict(self.ITEM, fuel='Gasoline+Electric')]})
        self.assertIn('data-uk="гібрид" data-ru="гибрид" data-ka="ჰიბრიდი"', html)
        self.assertEqual([ticker.fuel_key(v) for v in ('Gasoline', 'Diesel', 'LPG', 'Electric', 'Gasoline+Electric', '')],
                         ['gasoline', 'diesel', 'lpg', 'electric', 'hybrid', None])
        self.assertNotIn(' ·  · ', ticker.render({'lots_on_date': 5, 'items': [dict(self.ITEM, fuel='')]}))

    def test_owner_cars_mixed_in(self):
        own = {'code': 'UA-0018', 'title': 'Kia K5 2023', 'stage': 'kiev', 'price_usd': 20300,
               'photo': 'https://www.uaart.com.ua/video/foto/UA-0018/001.jpg',
               'url': 'https://www.uaart.com.ua/video/ua/UA-0018.html'}
        html = ticker.render({'lots_on_date': 5, 'items': [self.ITEM, self.ITEM], 'own': [own]})
        self.assertEqual(html.count('class="kt-item kt-own"'), 1)
        self.assertIn('★ У нас · у Києві', html)
        self.assertIn('$20 300</b>', html)
        self.assertIn('href="https://www.uaart.com.ua/video/ua/UA-0018.html"', html)

    def test_empty(self):
        self.assertEqual(ticker.render({'lots_on_date': 0, 'items': []}), '')



class JobTest(unittest.TestCase):
    def test_due(self):
        at = lambda d, h: datetime(2026, 11, d, h, 7, tzinfo=selection.JST)  # 2026-11-09 is a Monday
        self.assertTrue(job.due(at(10, 10), True))
        self.assertFalse(job.due(at(10, 11), True))
        self.assertTrue(job.due(at(10, 20), False))      # missing ticker: built at the next run
        self.assertFalse(job.due(at(15, 10), False))     # Sunday: nothing

    def test_photos_copied_to_site_and_old_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            (folder / 'old.jpg').write_bytes(b'x')
            def fetch(url):
                if 'bad' in url:
                    raise OSError('down')
                return b'jpg'
            items = [{'id': '1', 'photo': 'https://cdn.example/a'}, {'id': '2', 'photo': 'https://cdn.example/bad'}]
            kept = job.localize_photos(items, folder, fetch)
            self.assertEqual(kept, [{'id': '1', 'photo': '/video/korea/img/1.jpg'}])
            self.assertEqual(sorted(p.name for p in folder.iterdir()), ['1.jpg'])

    def test_login_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'login.txt'
            path.write_text(' a@b.c \n\n secret \n')
            self.assertEqual(job.read_login(path), ('a@b.c', 'secret'))
            path.write_text('a@b.c')
            with self.assertRaises(RuntimeError):
                job.read_login(path)



class PublicLotsTest(unittest.TestCase):
    LOT = {'id': '7', 'maker': 'KIA', 'model': 'SORENTO', 'trim': 'Signature', 'year': 2021, 'mileage_km': 40000,
           'score': 'A', 'engine_cc': 2497, 'transmission': 'AT', 'house': 'Auto Hub Auction', 'lot_no': '3001',
           'auction_start': '2026/11/11 13:00', 'start_price_krw': 20000000,
           'photos': ['https://cdn.example/a', 'https://cdn.example/b', 'https://cdn.example/c', 'https://cdn.example/d']}
    RATES = {'USD': 41.0, 'KRW': 0.03, 'date': '10.11.2026'}

    def test_public_view_has_only_site_photos(self):
        value = public.build([self.LOT, dict(self.LOT, id='8')], '2026/11/11', self.RATES,
                             {'7': ['7-1.jpg', '7-2.jpg']}, '2026-11-10T20:00+09:00')
        self.assertEqual([v['id'] for v in value['lots']], ['7'])  # a lot without copied photos is not shown
        lot = value['lots'][0]
        self.assertEqual(lot['title'], 'Kia Sorento')
        self.assertEqual(lot['start_usd'], round(20000000 * 0.03 / 41.0))
        self.assertEqual(lot['photos'], ['/video/korea/lots/7-1.jpg', '/video/korea/lots/7-2.jpg'])
        self.assertNotIn('cdn.example', str(value))

    def test_copy_lot_photos_keeps_existing_and_removes_old(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            (folder / '7-1.jpg').write_bytes(b'kept')
            (folder / '99-1.jpg').write_bytes(b'old')
            fetched = []
            def fetch(url):
                fetched.append(url)
                if url.endswith('/c'):
                    raise OSError('down')
                return b'jpg'
            photos = job.copy_lot_photos([self.LOT], folder, fetch)
            self.assertEqual(photos, {'7': ['7-1.jpg', '7-2.jpg']})
            self.assertEqual(sorted(fetched), ['https://cdn.example/b', 'https://cdn.example/c'])  # 3 per lot
            self.assertEqual((folder / '7-1.jpg').read_bytes(), b'kept')
            self.assertFalse((folder / '99-1.jpg').exists())



class PricesTest(unittest.TestCase):
    class Browser:
        def __init__(self):
            self.urls = []

        def fetch(self, url):
            self.urls.append(url)
            return url, 'Starting Price 9,400,000 KRW'

    def test_each_lot_page_read_once_and_remembered(self):
        day = [{'id': str(n), 'detail_url': '/vehicle-detail/kr/%d' % n, 'start_price_krw': 0} for n in range(5)]
        browser = self.Browser()
        known, left = prices.fill(browser, day, {'0': 5000000, 'gone': 1}, limit=3)
        self.assertEqual((len(browser.urls), left), (3, 1))  # 3 new pages read, 1 left for the next run
        self.assertNotIn('gone', known)                       # a lot that left the auction is forgotten
        self.assertEqual(known['1'], 9400000)
        self.assertEqual([l['start_price_krw'] for l in prices.apply(day, known)][:2], [5000000, 9400000])
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'p.json'
            prices.save(known, path)
            self.assertEqual(prices.load(path), known)
            self.assertEqual(prices.load(pathlib.Path(tmp) / 'none.json'), {})

    def test_unread_prices_make_the_next_hour_due(self):
        night = datetime(2026, 11, 10, 22, 7, tzinfo=selection.JST)
        self.assertFalse(job.due(night, True))
        self.assertTrue(job.due(night, True, prices_pending=True))


if __name__ == '__main__':
    unittest.main()
