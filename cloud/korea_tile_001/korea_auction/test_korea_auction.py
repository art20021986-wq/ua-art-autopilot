import pathlib
import random
import unittest
from datetime import datetime

import tempfile

from korea_auction import catalog, job, lots, model_lots, nbu, prices, public, selection, ticker

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
                '<img src="/img/icon.png"><img src="/cha_auction/2026/1110/5/a5_1.jpg">'
                '<img src="/cha_auction/2026/1110/5/a5_1.jpg"><img src="https://cdn.example/auction/IMAGE_UPLOAD/CAR/1/CA9/CA9x_2.JPG">'
                '<input id="chassis_no_input" value=""><td><div id="chassis_no_value"> kmhd341cbnu123456 </div></td>')
        d = lots.parse_detail(html)
        self.assertEqual(d['start_price_krw'], 2100000)
        self.assertEqual((d['fuel'], d['history'], d['body']), ('Gasoline', 'For Private Use', 'SEDAN'))
        self.assertEqual(d['specs']['Chassis No.'], 'KMH')
        self.assertEqual(d['market_sold_krw'], [1900000])
        self.assertEqual(d['photos'], ['https://jpauto.auction/cha_auction/2026/1110/5/a5_1.jpg',
                                       'https://cdn.example/auction/IMAGE_UPLOAD/CAR/1/CA9/CA9x_2.JPG'])  # no icon
        self.assertEqual(d['vin'], 'KMHD341CBNU123456')
        self.assertEqual(lots.parse_detail('<div id="chassis_no_value"></div>')['vin'], '')


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

    def test_today_before_next_day_is_listed(self):
        """TICKER-FIX-001: mornings before the next day's lots are listed — today's lots that have not started."""
        lots_ = [{'model': 'K5', 'auction_start': '2026/11/12 13:00', 'photos': [1]}]
        morning = datetime(2026, 11, 12, 10, 7, tzinfo=selection.JST)
        self.assertEqual(selection.next_auction_date(lots_, morning), '2026/11/12')
        evening = datetime(2026, 11, 12, 14, 7, tzinfo=selection.JST)
        self.assertEqual(selection.next_auction_date(lots_, evening), '2026/11/12')  # FIX2: started lots still shown
        self.assertIsNone(selection.next_auction_date([], evening))

    def test_today_wording_and_legend(self):
        html = ticker.render({'lots_today': 7, 'items': [TickerTest.ITEM]}, tomorrow=False)
        self.assertIn('Сьогодні на торгах', html)
        self.assertNotIn('Завтра на торгах', html)
        self.assertIn('kt-legend', html)

    def test_waiting_tile_without_lots(self):
        """TICKER-FIX3-001: the auction lists no lots — the tile with the legend and the owner's cars, no lot photos."""
        own = {'stage': 'sea', 'title': 'Kia K5 2021', 'url': 'https://www.uaart.com.ua/video/ua/UA-0001.html',
               'photo': 'https://www.uaart.com.ua/video/foto/UA-0001/001.jpg', 'price_usd': 15000}
        html = ticker.render({'lots_on_date': 0, 'items': [], 'own': [own]})
        self.assertIn('kt-legend', html)
        self.assertIn('Нові лоти аукціону', html)
        self.assertIn('/video/foto/UA-0001/001.jpg', html)
        self.assertNotIn('/video/korea/img/', html)
        self.assertEqual(ticker.render({'lots_on_date': 0, 'items': [], 'own': []}), '')

    def test_stale_ticker_is_due_next_hour(self):
        import os, tempfile
        night = datetime(2026, 11, 12, 11, 7, tzinfo=selection.JST)
        self.assertTrue(job.due(night, True, stale=True))
        with tempfile.TemporaryDirectory() as temp:
            page = pathlib.Path(temp) / "ticker.html"
            page.write_text('x')
            os.utime(page, (0, 0))
            self.assertTrue(job.stale(page))
            os.utime(page, None)
            self.assertFalse(job.stale(page))
            self.assertFalse(job.stale(pathlib.Path(temp) / "none.html"))

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
        html = ticker.render({'lots_today': 2382, 'items': [self.ITEM]})
        self.assertIn('$8 909', html)
        self.assertIn('₩11,7 млн', html)
        self.assertIn('data-ka="ხვალ აუქციონი"', html)
        self.assertIn('Сьогодні на торгах</span> 2 382 <span', html)
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

    def test_yellow_tile_explains_the_score(self):  # owner 2026-11-11
        html = ticker.render({'lots_on_date': 5, 'items': [self.ITEM]})
        lead = html[html.index('class="kt-lead"'):html.index('class="kt-item"')]
        self.assertIn('class="kt-legend"', lead)
        for key, letters in ticker.LEGEND:
            for k in [key] + ['%s_%s' % (key, letter) for letter in letters]:
                uk, ru, ka = ticker.T[k]
                self.assertIn('data-uk="%s" data-ru="%s" data-ka="%s"' % (uk, ru, ka), lead)
        self.assertIn('<dt>F</dt>', lead)
        self.assertNotIn('ext_E', ticker.T)  # the exterior grade has no E

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

    def test_ticker_photo_original_order_kept_failure_logged(self):
        """TICKER-FIX5-001: the original bytes are written (no compression); order kept; a failure is logged."""
        import contextlib, io
        with tempfile.TemporaryDirectory() as tmp:
            items = [{'id': str(n), 'photo': 'https://cdn.example/%d' % n} for n in range(10)]
            kept = job.localize_photos(items, pathlib.Path(tmp), lambda url: b'original-' + url[-1:].encode())
            self.assertEqual([k['id'] for k in kept], [str(n) for n in range(10)])
            self.assertEqual((pathlib.Path(tmp) / '3.jpg').read_bytes(), b'original-3')
            def down(url):
                raise OSError('timed out')
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                job.localize_photos([{'id': '7', 'photo': 'u'}], pathlib.Path(tmp), down)
            self.assertIn('ticker photo 7 not copied: OSError: timed out', err.getvalue())

    def test_up_to_150_popular_cars(self):
        from korea_auction import collect
        self.assertEqual(collect.TICKER_SIZE, 150)

    def test_ticker_dates_next_days_then_today(self):
        """TICKER-FIX6-001: the next auction days in order, then today; dates past are never used."""
        now = datetime(2026, 11, 12, 17, 20, tzinfo=selection.JST)
        found = [{'auction_start': d + ' 13:00'} for d in ('2026/11/18', '2026/11/11', '2026/11/12', '2026/11/13')]
        self.assertEqual(selection.ticker_dates(found, now), ['2026/11/13', '2026/11/18', '2026/11/12'])
        self.assertEqual(selection.ticker_dates([], now), [])

    def test_fresh_next_day_without_popular_cars_still_fills_the_ticker(self):
        """TICKER-FIX6-001 (12.11 17:20 KST): the next day had 56 lots, none a popular car with a photo and price —
        the ticker took none and showed the waiting tile. Now the later days and today fill it."""
        from unittest import mock
        from korea_auction import collect

        def lot(n, date, model, photos=True, price=0):
            return {'id': str(n), 'maker': 'KIA', 'model': model, 'year': 2021, 'mileage_km': 1000, 'score': 'A',
                    'auction_start': date + ' 13:00', 'start_price_krw': price, 'detail_url': '/d/%d' % n,
                    'house': 'K-Car O-San' if n == 2 else 'Auto Hub Auction',
                    'photos': ['https://cdn.example/%d' % n] if photos else []}
        found = [lot(1, '2026/11/13', 'BONGO'), lot(2, '2026/11/13', 'SORENTO', photos=False),
                 lot(3, '2026/11/13', 'K5'),  # no price yet
                 lot(4, '2026/11/18', 'SORENTO', price=20000000), lot(5, '2026/11/12', 'K5', price=15000000)]

        class Browser:
            requests = 0
            def login(self, *a):
                pass
            def fetch(self, url):
                return 200, ''
        rates = {'USD': 41.0, 'KRW': 0.03, 'date': '12.11.2026'}
        with mock.patch.object(collect, 'fetch_all_lots', return_value=(5, found)), \
                mock.patch.object(collect.nbu, 'fetch_rates', return_value=rates), \
                mock.patch.object(collect.catalog, 'fetch', return_value=''), \
                mock.patch.object(collect.catalog, 'parse', return_value=[]), \
                mock.patch.object(collect.lots, 'parse_detail',
                                  return_value={'start_price_krw': 0, 'fuel': '', 'photos': [], 'market_sold_krw': []}):
            data = collect.collect('a', 'b', now=datetime(2026, 11, 12, 17, 20, tzinfo=selection.JST), session=Browser())
        self.assertEqual(data['auction_date'], '2026/11/13')
        self.assertEqual([(i['id'], i['tomorrow']) for i in data['items']], [('4', False), ('5', False)])
        hub = {'name': 'Auto Hub Auction', 'start': '2026/11/13 13:00'}
        self.assertEqual((data['lots_today'], data['houses_today']),
                         (1, [{'name': 'Auto Hub Auction', 'start': '2026/11/12 13:00'}]))
        self.assertEqual(data['next_days'], [
            {'date': '2026/11/13', 'lots': 3, 'houses': [hub, {'name': 'K-Car O-San', 'start': '2026/11/13 13:00'}]},
            {'date': '2026/11/18', 'lots': 1, 'houses': [{'name': 'Auto Hub Auction', 'start': '2026/11/18 13:00'}]}])

    def test_waiting_tile_shows_day_counts(self):
        """TICKER-FIX6-001: no lot cars yet — the tile still shows today's and the next day's counts."""
        own = {'stage': 'sea', 'title': 'Kia K5 2021', 'url': 'https://www.uaart.com.ua/video/ua/UA-0001.html',
               'photo': 'https://www.uaart.com.ua/video/foto/UA-0001/001.jpg', 'price_usd': 15000}
        html = ticker.render({'items': [], 'own': [own], 'lots_today': 989,
                              'next_days': [{'date': '2026/11/18', 'lots': 585}]})
        self.assertIn('<b>989</b>', html)
        self.assertIn('Торги Ср, 18.11</span></span><span class="kt-num"><b>585</b>', html)

    def test_failed_run_keeps_the_live_ticker_photos(self):
        """TICKER-FIX2-001: no items, or no photo copied — the photos the live ticker shows stay."""
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            (folder / 'live.jpg').write_bytes(b'x')
            with self.assertRaises(RuntimeError):
                job.build({'items': [], 'auction_date': '2026/11/12'}, datetime(2026, 11, 12, 13, 7, tzinfo=selection.JST), folder)
            def down(url):
                raise OSError('down')
            self.assertEqual(job.localize_photos([{'id': '1', 'photo': 'u'}], folder, down), [])
            self.assertEqual([p.name for p in folder.iterdir()], ['live.jpg'])

    def test_login_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'login.txt'
            path.write_text(' a@b.c \n\n secret \n')
            self.assertEqual(job.read_login(path), ('a@b.c', 'secret'))
            path.write_text('a@b.c')
            with self.assertRaises(RuntimeError):
                job.read_login(path)



class UpcomingTest(unittest.TestCase):
    def test_upcoming_days(self):
        lots_ = [{'auction_start': d} for d in ('2026/11/09 13:00', '2026/11/10 13:00', '2026/11/11 10:00',
                                                 '2026/11/13 09:00')]
        now = datetime(2026, 11, 10, 22, tzinfo=selection.JST)
        self.assertEqual(selection.upcoming(lots_, now), lots_[1:])  # today's lots too, not yesterday's


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
        self.assertEqual(lot['vin'], '')
        self.assertEqual(public.build([dict(self.LOT, vin='KNA1')], '', self.RATES, {'7': ['7-1.jpg']}, '')['lots'][0]['vin'],
                         'KNA1')
        name = public.photo_name('7', 'https://cdn.example/a')
        self.assertRegex(name, r'^7-[0-9a-f]{12}\.jpg$')
        self.assertNotEqual(name, public.photo_name('7', 'https://cdn.example/b'))

    def test_copy_lot_photos_keeps_existing_and_removes_old(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            name = lambda url: public.photo_name('7', 'https://cdn.example/' + url)
            (folder / name('a')).write_bytes(b'kept')
            (folder / '99-1.jpg').write_bytes(b'old')
            fetched = []
            def fetch(url):
                fetched.append(url)
                if url.endswith('/c'):
                    raise OSError('down')
                return b'jpg'
            photos, left = job.copy_lot_photos([self.LOT], folder, fetch)
            self.assertEqual(photos, {'7': [name('a'), name('b'), name('d')]})  # every photo, in the lot's order
            self.assertEqual(sorted(fetched), ['https://cdn.example/b', 'https://cdn.example/c', 'https://cdn.example/d'])
            self.assertFalse(left)
            self.assertEqual((folder / name('a')).read_bytes(), b'kept')
            self.assertFalse((folder / '99-1.jpg').exists())

    def test_photos_copied_gradually_first_photos_first(self):
        other = dict(self.LOT, id='8', photos=['https://cdn.example/%s8' % c for c in 'abcd'])
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp)
            fetched = []
            def fetch(url):
                fetched.append(url)
                return b'jpg'
            photos, left = job.copy_lot_photos([self.LOT, other], folder, fetch, limit=6)
            self.assertTrue(left)  # 2 photos for the next run
            self.assertEqual(sorted(fetched), sorted(['https://cdn.example/a', 'https://cdn.example/b',
                                                      'https://cdn.example/c', 'https://cdn.example/a8',
                                                      'https://cdn.example/b8', 'https://cdn.example/c8']))
            self.assertEqual((len(photos['7']), len(photos['8'])), (3, 3))
            fetched.clear()
            photos, left = job.copy_lot_photos([self.LOT, other], folder, fetch, limit=6)
            self.assertEqual((sorted(fetched), left), (['https://cdn.example/d', 'https://cdn.example/d8'], False))
            self.assertEqual((len(photos['7']), len(photos['8'])), (4, 4))

    def test_pending_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'd' / 'pending'
            job.mark_pending(True, path)
            self.assertTrue(path.exists())
            job.mark_pending(False, path)
            self.assertFalse(path.exists())


class PricesTest(unittest.TestCase):
    class Browser:
        def __init__(self):
            self.urls = []

        def fetch(self, url):
            self.urls.append(url)
            return url, ('Starting Price 9,400,000 KRW<td><div id="chassis_no_value">KNAG541BBNA169806</div></td>'
                         '<img src="/cha_auction/2026/1110/1/a1_1.jpg"><img src="https://cdn.example/cha_auction/1/a1_2.jpg">')

    def test_each_lot_page_read_once_and_remembered(self):
        day = [{'id': str(n), 'detail_url': '/vehicle-detail/kr/%d' % n, 'start_price_krw': 0} for n in range(5)]
        browser = self.Browser()
        old = {'0': {'krw': 5000000, 'vin': '', 'photos': []}, 'gone': {'krw': 1}}
        known, left = prices.fill(browser, day, old, limit=3)
        self.assertEqual((len(browser.urls), left), (3, 1))  # 3 new pages read, 1 left for the next run
        self.assertNotIn('gone', known)                       # a lot that left the auction is forgotten
        self.assertEqual(known['1'], {'krw': 9400000, 'vin': 'KNAG541BBNA169806',
                                      'photos': ['https://jpauto.auction/cha_auction/2026/1110/1/a1_1.jpg',
                                                 'https://cdn.example/cha_auction/1/a1_2.jpg']})
        shown = prices.apply([dict(l, photos=['t']) for l in day], known)
        self.assertEqual([l['start_price_krw'] for l in shown][:2], [5000000, 9400000])
        self.assertEqual((shown[1]['vin'], len(shown[1]['photos']), shown[0]['photos'], shown[4]['vin']),
                         ('KNAG541BBNA169806', 2, ['t'], ''))  # unread lot: the table's photos, no VIN yet
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'p.json'
            prices.save(known, path)
            self.assertEqual(prices.load(path), known)
            self.assertEqual(prices.load(pathlib.Path(tmp) / 'none.json'), {})
            path.write_text('{"5": 9400000}')  # the price-only cache of the previous version: read again once
            self.assertEqual(prices.load(path), {})

    def test_unread_prices_make_the_next_hour_due(self):
        night = datetime(2026, 11, 10, 22, 7, tzinfo=selection.JST)
        self.assertFalse(job.due(night, True))
        self.assertTrue(job.due(night, True, pending=True))


class Fix4Test(unittest.TestCase):
    """TICKER-FIX4-001 (owner 2026-11-12): browser-like search post; today's and next day's counts in the ticker."""

    def test_search_posts_default_checked_boxes(self):
        from korea_auction import collect
        html = ('<form action="/vehicle-search/kr/index" id="purchase_search_form">'
                '<input type="hidden" name="mode" value="search">'
                '<input type="checkbox" name="order_closed[]" value="1" checked="checked">'
                '<input type="checkbox" name="auction_group[]" value="3">'
                '<input type="checkbox" name="auction_group[]" value="4" checked>'
                '<input type="checkbox" name="auction_group[]" value="5" checked></form>')
        action, data = collect._search_form_data(html)
        self.assertEqual(action, '/vehicle-search/kr/index')
        self.assertEqual(data, [('mode', 'search'), ('order_closed[]', '1'), ('auction_group[]', '4'),
                                ('auction_group[]', '5')])

    def test_today_and_next_days(self):
        """Owner 2026-11-13: the 3 nearest auction days after today, each with its listed car count."""
        now = datetime(2026, 11, 13, 14, 0, tzinfo=selection.JST)
        dates = ('2026/11/13 12:00', '2026/11/18 10:00', '2026/11/17 10:00', '2026/11/18 11:00', '2026/11/19 10:00',
                 '2026/11/20 10:00')
        lots_ = [{'auction_start': d} for d in dates]
        self.assertEqual(selection.today_and_next_days(lots_, now),
                         ('2026/11/13', [('2026/11/17', 1), ('2026/11/18', 2), ('2026/11/19', 1)]))
        self.assertEqual(selection.today_and_next_days(lots_[:1], now), ('2026/11/13', []))
        self.assertEqual(selection.day_after('2026/11/30'), '2026/12/01')

    def _data(self, **kw):
        item = {'id': '1', 'title': 'Kia K5', 'model': 'K5', 'year': 2022, 'mileage_km': 1000, 'score': 'A3',
                'fuel': 'Gasoline', 'start_price_krw': 10000000, 'start_price_usd': 7000,
                'photo': '/video/korea/img/1.jpg', 'auction_start_jst': '2026/11/13 10:00', 'hot': False}
        return dict({'lots_on_date': 500, 'own': [], 'items': [item]}, **kw)

    DAYS = [{'date': '2026/11/17', 'lots': 766, 'houses': [{'name': 'K-Car O-San', 'start': '2026/11/17 13:00'},
                                                          {'name': 'SK Rent Car Auction', 'start': '2026/11/17 13:00'}]},
            {'date': '2026/11/18', 'lots': 585, 'houses': [{'name': 'Auto Hub Auction', 'start': '2026/11/18 06:00'}]},
            {'date': '2026/11/19', 'lots': 12}]
    KYIV_TAG = '<span data-uk="старт %s Київ" data-ru="старт %s Киев" data-ka="დაწყება %s კიევი">старт %s Київ</span>'

    def test_tile_names_the_auction_houses_and_kyiv_start(self):
        """Owner 2026-11-13: «название аукционов допиши», «старт время по Украине добавь» — under each tile line, that
        day's auction houses, each with its start in Kyiv time."""
        html = ticker.render(self._data(lots_today=56, houses_today=[{'name': 'AutoPlus', 'start': '2026/11/13 12:00'}],
                                        next_days=self.DAYS))
        lead = html[html.index('class="kt-lead"'):html.index('class="kt-legend"')]
        self.assertIn('<span class="kt-houses"><span>AutoPlus · %s</span></span>' % (self.KYIV_TAG % (('05:00',) * 4)),
                      lead)
        self.assertIn('<span>K-Car O-San · %s</span><span>SK Rent Car Auction · ' % (self.KYIV_TAG % (('06:00',) * 4)),
                      lead)
        # 06:00 in Korea is the day before in Kyiv: the Kyiv day is named
        self.assertIn('data-uk="старт 23:00 (Вт, 17.11) Київ"', lead)
        self.assertIn('data-ru="старт 23:00 (Вт, 17.11) Киев"', lead)
        self.assertEqual(lead.count('kt-houses'), 3)  # 19.11 lists no house: no empty line
        self.assertNotIn('AutoPlus', html[html.index('class="kt-end"'):])  # closing card: counts only

    def test_house_without_a_readable_start_shows_the_name_only(self):
        html = ticker.render(self._data(lots_today=1, houses_today=[{'name': 'AutoPlus', 'start': ''}]))
        self.assertIn('<span class="kt-houses"><span>AutoPlus</span></span>', html)

    def test_houses_of_a_day(self):
        lots_ = [{'auction_start': d, 'house': h} for d, h in (('2026/11/17 13:00', 'SK Rent Car Auction'),
                                                              ('2026/11/17 10:30', 'K-Car O-San'),
                                                              ('2026/11/17 10:00', 'K-Car O-San'),
                                                              ('2026/11/18 10:00', 'Auto Hub Auction'))]
        self.assertEqual(selection.houses(lots_, '2026/11/17'),
                         [('K-Car O-San', '2026/11/17 10:00'), ('SK Rent Car Auction', '2026/11/17 13:00')])
        self.assertEqual(selection.houses(lots_, '2026/11/19'), [])

    def test_tile_today_count_and_next_auction_days(self):
        """KOREA-TILE-001 (owner 2026-11-13): today's count, then the 3 nearest auction days — date, weekday and
        car count each («Торги Вт, 17.11 3 авто · Торги Ср, 18.11 585 авто …»)."""
        html = ticker.render(self._data(lots_today=56, next_days=self.DAYS))
        lead = html[html.index('class="kt-lead"'):html.index('class="kt-legend"')]
        self.assertIn('Сьогодні на торгах</span></span><span class="kt-num"><b>56</b> <span', lead)
        self.assertIn('Торги Вт, 17.11</span></span><span class="kt-num"><b>766</b> <span', lead)
        self.assertIn('Торги Ср, 18.11</span></span><span class="kt-num"><b>585</b> <span', lead)
        self.assertIn('Торги Чт, 19.11</span></span><span class="kt-num"><b>12</b> <span', lead)
        self.assertIn('data-ka="ვაჭრობა ოთხ, 18.11"', lead)
        self.assertEqual(lead.count('class="kt-count"'), 4)
        self.assertNotIn('Наступний аукціон', html)
        self.assertNotIn('Завтра на торгах', html)
        self.assertIn('kt-legend', html)

    def test_tile_shows_zero_today(self):
        html = ticker.render(self._data(lots_today=0, next_days=self.DAYS[:1]))
        self.assertIn('Сьогодні на торгах</span></span><span class="kt-num"><b>0</b>', html)
        self.assertIn('Торги Вт, 17.11</span></span><span class="kt-num"><b>766</b>', html)

    def test_tile_without_next_days(self):
        html = ticker.render(self._data(lots_today=989, next_days=[]), tomorrow=False)
        self.assertIn('<b>989</b>', html)
        self.assertEqual(html.count('class="kt-count"'), 1)


class ModelLotsTest(unittest.TestCase):
    LOT = {'id': '1', 'maker': 'KIA', 'model': 'K5', 'year': 2023, 'mileage_km': 50000,
           'score': 'BB', 'auction_start': '2026/11/13 12:00', 'start_usd': 15000}
    NOW = '2026/11/12 20:00'

    def pick(self, lots_, photos=None):
        photos = photos if photos is not None else {l['id']: ['/video/korea/lots/%s-x.jpg' % l['id']] for l in lots_}
        return model_lots.select(lots_, model_lots.KOREA, photos, self.NOW, '/video/korea.html')['models']

    def test_grade_rank(self):
        self.assertEqual([model_lots.grade_rank(g) for g in ('AA', 'AB', 'BA', 'A2', 'BB', 'B1', 'CD', '', 'A', 'X1')],
                         [0, 1, 1, 1.5, 2, 3.5, 5, 99, 99, 99])

    def test_generation_and_order(self):
        lots_ = [dict(self.LOT, id='bb'), dict(self.LOT, id='aa', score='AA'), dict(self.LOT, id='ba', score='BA'),
                 dict(self.LOT, id='ab', score='AB', mileage_km=10000),
                 dict(self.LOT, id='old', model='K5', year=2019),                        # change-over year: left out
                 dict(self.LOT, id='a2', score='A2', mileage_km=1000),                    # after AB, before BB
                 dict(self.LOT, id='sold', auction_start='2026/11/12 10:00'),            # started already
                 dict(self.LOT, id='tuc', maker='HYUNDAI', model='TUCSON')]
        found = self.pick(lots_)
        self.assertEqual([l['id'] for l in found['kia-k5']], ['aa', 'ab', 'ba', 'a2', 'bb'])  # AA, AB/BA, A2, BB
        self.assertEqual([l['id'] for l in found['hyundai-tucson']], ['tuc'])
        self.assertEqual(set(found), {'kia-k5', 'hyundai-tucson'})                       # no lots: no entry
        self.assertEqual(found['kia-k5'][0], {'id': 'aa', 'href': '/video/korea.html#lot-aa',
                                              'photo': '/video/korea/lots/aa-x.jpg', 'date': '13.11',
                                              'start': '2026/11/13 12:00', 'score': 'AA', 'year': 2023, 'km': 50000,
                                              'usd': 15000})

    def test_six_per_model_photo_and_price_first(self):
        lots_ = [dict(self.LOT, id=str(n), mileage_km=n) for n in range(9)]
        lots_.append(dict(self.LOT, id='free', score='AA', start_usd=0))
        found = self.pick(lots_, {l['id']: ['p'] for l in lots_ if l['id'] != '0'})
        self.assertEqual([l['id'] for l in found['kia-k5']], ['1', '2', '3', '4', '5', '6'])  # no photo: left out

    def test_same_grade_newer_year_first(self):
        lots_ = [dict(self.LOT, id='a', year=2021), dict(self.LOT, id='b', year=2024)]
        self.assertEqual([l['id'] for l in self.pick(lots_)['kia-k5']], ['b', 'a'])

    def test_santa_fe_tm_only(self):
        fe = dict(self.LOT, maker='HYUNDAI', model='SANTA FE', year=2021)
        found = self.pick([dict(fe, id='tm'), dict(fe, id='mx5', year=2024), dict(fe, id='dm', year=2018)])
        self.assertEqual([l['id'] for l in found['hyundai-santa-fe']], ['tm'])


class KoreaTimeTests(unittest.TestCase):
    """KOREA-TIME-001 (owner 2026-11-12): each ticker lot card shows the auction start in Korea and Kyiv time."""

    def test_winter_and_summer_kyiv_time(self):
        from korea_auction import ticker
        self.assertIn('>Торги Ср, 18.11 · 12:00 Корея · 05:00 Київ<', ticker._when('2026/11/18 12:00'))
        self.assertIn('data-ru="Торги Ср, 18.11 · 12:00 Корея · 05:00 Киев"', ticker._when('2026/11/18 12:00'))
        self.assertIn('>Торги Ср, 15.07 · 10:00 Корея · 04:00 Київ<', ticker._when('2026/07/15 10:00'))

    def test_weekday_per_language(self):
        from korea_auction import ticker
        sunday = ticker._when('2026/11/22 12:00')
        self.assertIn('data-uk="Торги Нд, 22.11 ', sunday)
        self.assertIn('data-ru="Торги Вс, 22.11 ', sunday)
        self.assertIn('data-ka="ვაჭრობა კვი, 22.11 ', sunday)

    def test_kyiv_day_shown_when_it_differs(self):
        from korea_auction import ticker
        self.assertIn('Ср, 18.11 · 06:00 Корея · 23:00 (Вт, 17.11) Київ', ticker._when('2026/11/18 06:00'))

    def test_unreadable_start_shows_nothing(self):
        from korea_auction import ticker
        self.assertEqual(ticker._when(''), '')
        self.assertEqual(ticker._when('soon'), '')

    def test_lot_card_carries_the_time_line(self):
        from korea_auction import ticker
        item = {'id': '7', 'title': 'Kia K5', 'year': 2022, 'mileage_km': 1000, 'score': 'A', 'fuel': 'Gasoline',
                'start_price_krw': 10**7, 'start_price_usd': 7000, 'photo': '/p.jpg', 'hot': False,
                'auction_start_jst': '2026/11/18 12:00'}
        html = ticker.render({'lots_on_date': 1, 'own': [], 'items': [item]})
        self.assertEqual(html.count('class="kt-when"'), 1)
        self.assertIn('data-kt-start="2026/11/18 12:00"', html)


if __name__ == '__main__':
    unittest.main()
