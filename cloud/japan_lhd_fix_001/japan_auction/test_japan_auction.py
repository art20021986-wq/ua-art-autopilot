#!/usr/bin/env python3
"""Tests of the Japan left-hand-drive collector (JAPAN-LHD-001). No network, nothing written outside a temp folder."""
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from japan_auction import job, lot_page, money, photos, search, views  # noqa: E402
from korea_auction.selection import JST  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULTS = '<p>43 Results</p>' + (HERE / 'fixtures/results_r3.html').read_text(encoding='utf-8')  # probe R3; ids made up
LOT = (HERE / 'fixtures/lot_r3.html').read_text(encoding='utf-8')  # probe R3: a SellCa Porsche Cayenne, cleaned
RATES = {'USD': 41.5, 'JPY': 0.27, 'date': '27.11.2026'}
FORM = ('<form action="/vehicle-search/jp/index" method="post" id="purchase_search_form">'
        '<input type="hidden" name="auction_country_id" value="2"><input type="hidden" name="favoriteurl" value="/x">'
        '<input type="hidden" name="history_idx_url" value="/h"><input type="checkbox" name="auction_group[]" value="1" checked>'
        '<input type="checkbox" name="left_hd[]" value="L"> Left-Hand Drive<input type="checkbox" name="order_closed[]" value="1">'
        '</form>')


def lot(lot_id, start='2026/11/30 10:00', jpy=1500000, photos=('https://img/a.jpg',), **extra):
    value = {'id': lot_id, 'auction_start': start, 'house': 'SellCa', 'port': '', 'lot_no': '1',
             'detail_url': '/vehicle-detail/jp/' + lot_id, 'score': '4', 'mileage_km': 40000, 'year': 2015,
             'start_price_jpy': jpy, 'photos': list(photos), 'maker': 'MERCEDES BENZ', 'model': 'G CLASS',
             'trim': 'G550', 'engine_cc': 5500, 'transmission': 'AT'}
    value.update(extra)
    return value


class Browser:
    def __init__(self, pages):
        self.pages, self.requests = pages, 0

    def fetch(self, path, data=None):
        self.requests += 1
        return path, self.pages[path] if not callable(self.pages[path]) else self.pages[path](data)


class MoneyTests(unittest.TestCase):
    def test_rates_and_conversion(self):
        payload = [{'cc': 'USD', 'rate': 41.5, 'exchangedate': '27.11.2026'}, {'cc': 'JPY', 'rate': 0.27},
                   {'cc': 'KRW', 'rate': 0.03}]
        rates = money.parse_rates(payload)
        self.assertEqual((rates['JPY'], rates['date']), (0.27, '27.11.2026'))
        self.assertEqual(money.jpy_to_usd(1500000, rates), 9759)

    def test_missing_yen_stops(self):
        with self.assertRaisesRegex(ValueError, 'NBU_RATES_INCOMPLETE'):
            money.parse_rates([{'cc': 'USD', 'rate': 41.5, 'exchangedate': 'x'}])


class SearchTests(unittest.TestCase):
    def test_form_sends_defaults_and_the_left_hand_box_only(self):
        action, data = search.form_data(FORM)
        self.assertEqual(action, '/vehicle-search/jp/index')
        self.assertEqual(data, [('auction_country_id', '2'), ('auction_group[]', '1'), ('left_hd[]', 'L')])

    def test_no_left_hand_box_no_search(self):
        with self.assertRaisesRegex(RuntimeError, 'LEFT_HAND_BOX_MISSING'):
            search.form_data(FORM.replace('left_hd[]', 'other[]'))

    def test_rows_of_the_real_table(self):
        found = search.rows(RESULTS)
        self.assertEqual(search.total(RESULTS), 43)
        self.assertEqual(len(found), 5)
        first = found[0]
        self.assertEqual((first['id'], first['house'], first['port'], first['lot_no'], first['start_price_jpy']),
                         ('20261127000001', 'SellCa', '', '1001', 50000))
        self.assertEqual((first['maker'], first['model'], first['trim'], first['score'], first['year']),
                         ('PORSCHE', 'CAYENNE', 'S', '3.5', 2012))
        self.assertEqual(found[3]['trim'], 'S500L')  # full-width «Ｓ５００Ｌ» made plain
        self.assertEqual(first['detail_url'], '/vehicle-detail/20261127000001')
        self.assertTrue(first['photos'][0].startswith('https://jpauto.auction/sellca-public/images/MAIN/'))
        self.assertNotIn('start_price_krw', first)
        real = ('<a href="/vehicle-search/page=2?order_closed%5B0%5D=1&amp;mode=list&amp;auction_country_id=47'
                '&amp;left_hd%5B0%5D=L&amp;auction%5B0%5D=69">2</a>')  # the pager link probe R3 saw
        self.assertEqual(search.pages(real), '/vehicle-search/page=2?order_closed%5B0%5D=1&mode=list'
                                             '&auction_country_id=47&left_hd%5B0%5D=L&auction%5B0%5D=69')

    def test_all_pages_read(self):
        pager = '<p>43 Results</p><a href="/vehicle-search/page=2?left_hd%5B0%5D=L&amp;mode=list">2</a>'
        browser = Browser({search.SEARCH_PAGE: FORM, '/vehicle-search/jp/index': lambda data: pager + RESULTS[17:],
                           '/vehicle-search/page=1?left_hd%5B0%5D=L&mode=list&limit=2000': RESULTS,
                           '/vehicle-search/page=2?left_hd%5B0%5D=L&mode=list&limit=2000': '<p>43 Results</p>'})
        count, found = search.left_hand_lots(browser)  # pages until one is empty (or every lot is read)
        self.assertEqual((count, len(found), browser.requests), (43, 5, 4))


class LotPageTests(unittest.TestCase):
    def test_real_lot_page(self):
        page = lot_page.entry(LOT)
        self.assertEqual((page['jpy'], page['vin'], page['fuel'], page['color'], page['steering']),
                         (50000, 'WP1AB2A22CLA45131', 'Gasoline', 'black', 'Left'))
        self.assertGreaterEqual(len(page['photos']), 10)
        self.assertEqual(len(page['photos']), len(set(page['photos'])))
        self.assertTrue(all('/sellca-public/' in url and not url.endswith('icon.png') for url in page['photos']))
        self.assertTrue(any(url.endswith('.png') for url in page['photos']))

    def test_start_price_in_yen(self):
        html = '<div>Starting Price 1,250,000 JPY</div><table><tr><th>Chassis No.</th><td>X</td></tr></table>'
        self.assertEqual(lot_page.start_jpy(html), 1250000)
        self.assertEqual(lot_page.entry(html)['jpy'], 1250000)
        self.assertEqual(lot_page.start_jpy('<p>no price</p>'), 0)


class ViewsTests(unittest.TestCase):
    def test_list_ticker_and_week(self):
        lots = [lot('1', '2026/11/30 10:00'), lot('2', '2026/11/28 09:00', jpy=0), lot('3', photos=())]
        value = views.build(lots, RATES, {'1': ['1-a.jpg', '1-b.jpg'], '2': ['2-a.jpg']}, 'now')
        self.assertEqual([v['id'] for v in value['lots']], ['2', '1'])
        first = value['lots'][1]
        self.assertEqual((first['start_jpy'], first['start_usd'], first['photos'][0]),
                         (1500000, 9759, '/video/japan/lots/1-a.jpg'))
        self.assertEqual(value['nbu'], {'date': '27.11.2026', 'usd_uah': 41.5, 'jpy_uah': 0.27})
        feed = views.feed(value['lots'], '2026/11/27', 'now')
        self.assertEqual([i['id'] for i in feed['items']], ['1'])  # no price: no ticker card
        self.assertEqual(feed['items'][0]['start_price_jpy'], 1500000)
        self.assertEqual([(d['date'], d['lots']) for d in feed['week']][:4],
                         [('2026/11/27', 0), ('2026/11/28', 1), ('2026/11/29', 0), ('2026/11/30', 1)])
        self.assertEqual(views.gallery(['1-a.jpg']), {'photos': ['/video/japan/lots/1-a.jpg']})


class JobTests(unittest.TestCase):
    def test_due(self):
        friday = datetime(2026, 11, 27, 12, tzinfo=JST)
        self.assertTrue(job.due(friday, True))
        self.assertFalse(job.due(friday.replace(hour=13), True))
        self.assertTrue(job.due(friday.replace(hour=13), True, pending=True))
        self.assertFalse(job.due(datetime(2026, 11, 29, 12, tzinfo=JST), False))  # Sunday

    def test_right_hand_page_is_left_out(self):
        applied = job.with_pages([lot('1'), lot('2'), lot('3')], {'1': {'steering': 'Right'}, '2': {'steering': 'Left'}})
        self.assertEqual([l['id'] for l in applied], ['2'])  # '3': page not read yet — waits

    def test_left_hand_only_on_proof(self):
        """Live 27.11: the auction's box matched «LEFT SIDE DOOR» — right-hand-drive Japanese cars."""
        left = {'steering': 'Left'}
        cases = [('N BOX', 'L. ORIGINAL NAVIGATION /CD/ REAR CAMERA / LEFT ELECTRIC DOOR /', left, False),
                 ('ELF', '2T FFL 10 SHAKU ALUMINUM VAN LEFT SIDE DOOR VERTICAL P', left, False),
                 ('MOVE', 'X BACK CAMERA KEY FREE LEFT SIDE POWER SLA DOOR', {}, False),
                 ('NV100 CLIPPER RIO', 'G TURBO HIGH ROOF . LEFT RIGHT POWER SLA/ NAVIGATION /TV/', left, False),
                 ('BEETLE', 'TYPE . 1995 YEAR LEFT STEERING WHEEL INSIDE OUT LIMEIK', {}, True),
                 ('GHIBLI', 'S. SUNROOF . RED LEATHER . LEFT HAND DRIVE .OPULA-NOAW', {}, True),
                 ('CAYENNE', 'S', left, True), ('SEQUOIA', '', left, True), ('G CLASS', 'G63 AMG', {}, False),
                 ('X5', 'LHD', {}, True), ('S CLASS', 'S500L', {'steering': 'Right'}, False)]
        for model, trim, page, expected in cases:
            self.assertEqual(job.left_hand({'model': model, 'trim': trim}, page), expected, model)

    def test_photo_copies_keep_their_type(self):
        urls = ['https://cdn/a/MAIN/x.png', 'https://cdn/a/t.jpg', 'https://cdn/a/MAIN/x.png']
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'old-1.jpg').write_bytes(b'x')
            copies, left = photos.copy([lot('1', photos=urls)], folder, fetch=lambda url: b'img')
            self.assertEqual([name[-4:] for name in copies['1']], ['.png', '.jpg'])
            self.assertFalse((folder / 'old-1.jpg').exists())
            self.assertFalse(left)
            _, left = photos.copy([lot('2', photos=urls)], folder, fetch=lambda url: b'img', deadline=0,
                                  clock=lambda: 1)
            self.assertTrue(left)

    def test_pages_read_once_and_applied(self):
        page = '<div>Starting Price 2,000,000 JPY</div><table><tr><th>Steering Wheel</th><td>Left</td></tr></table>'
        browser = Browser({'/vehicle-detail/jp/1': page, '/vehicle-detail/jp/2': page})
        known, left = job.read_pages(browser, [lot('1'), lot('2')], {'1': {'jpy': 1}, 'gone': {}})
        self.assertEqual((sorted(known), left, browser.requests), (['1', '2'], 0, 1))
        applied = job.with_pages([lot('2')], known)
        self.assertEqual(applied[0]['start_price_jpy'], 2000000)

    def test_publish_and_roll(self):
        now = datetime(2026, 11, 27, 12, tzinfo=JST)
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            shown, left = job.publish([lot('1'), lot('2', '2026/11/27 09:00')], RATES, now, folder,
                                      fetch=lambda url: b'\xff\xd8jpeg')
            self.assertEqual((shown, left), (2, False))
            value = json.loads((folder / 'lots.json').read_bytes())
            self.assertEqual(len(value['lots']), 2)
            self.assertTrue((folder / 'gallery/1.json').exists())
            feed = json.loads((folder / 'feed.json').read_bytes())
            self.assertEqual(feed['week'][0]['date'], '2026/11/27')
            job.roll(datetime(2026, 11, 28, 0, 5, tzinfo=JST), folder)
            self.assertEqual([l['id'] for l in json.loads((folder / 'lots.json').read_bytes())['lots']], ['1'])
            self.assertEqual(json.loads((folder / 'feed.json').read_bytes())['week'][0]['date'], '2026/11/28')


if __name__ == '__main__':
    unittest.main()
