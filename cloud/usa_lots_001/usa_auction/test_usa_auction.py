#!/usr/bin/env python3
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from usa_auction import fetch, job, pages, selection, views  # noqa: E402

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def block(lot_id, year, damage, start, odo='48,000'):
    return ('<div class="table-row"><a href="/VehicleDetail/%s~US"><img></a><h4><a href="/VehicleDetail/%s~US">'
            '%d TOYOTA RAV4 XLE</a></h4><ul><li>Primary Damage: <span>%s</span></li><li>Odometer: %s mi (Actual)</li>'
            '<li>Start Code: %s</li><li>Key: Present</li></ul></div>' % (lot_id, lot_id, year, damage, odo, start))


LISTING = ('<html><body>' + block('41000001', 2021, 'Minor Dent/Scratches', 'Run &amp; Drive')
           + block('41000002', 2019, 'Front End', 'Run &amp; Drive')
           + block('41000003', 2020, 'Normal Wear &amp; Tear', 'Stationary')
           + block('41000004', 2012, 'Hail', 'Run &amp; Drive') + '</body></html>')
LOT = ('<div>Primary Damage: Minor Dent/Scratches Title/Sale Doc: CLEAR (Texas) Start Code: Run &amp; Drive '
       'Odometer: 48,000 mi (Actual) Fuel Type: Gasoline Vehicle Location: Dallas (TX) '
       'Auction Date and Time: Wed Dec 2, 9:30am (CST) Lane/Run #: A - 12 Actual Cash Value: $24,900 USD '
       'Buy Now Price: $15,500</div><script>var u="https://vis.iaai.com/dimensions?imageKeys=41000001~SID~B1~S0~I1";</script>')
PHOTOS = {'keys': [{'K': '41000001~SID~B1~S0~I1~RW2592~H1944~TH0'}, {'K': '41000001~SID~B1~S0~I2~RW2592~H1944~TH0'}]}


class PagesTests(unittest.TestCase):
    def test_listing_one_lot_per_piece(self):
        lots = pages.listing(LISTING, 'TOYOTA', 'RAV4')
        self.assertEqual([l['id'] for l in lots], ['41000001', '41000002', '41000003', '41000004'])
        first = lots[0]
        self.assertEqual((first['year'], first['damage'], first['odometer_mi'], first['runs']),
                         (2021, 'Minor Dent/Scratches', 48000, True))
        self.assertFalse(lots[2]['runs'])

    def test_lot_page(self):
        lot = pages.lot(LOT, NOW)
        self.assertEqual(lot['auction_start'], '2026-12-02T15:30Z')
        self.assertEqual((lot['actual_cash_value_usd'], lot['buy_now_usd']), (24900, 15500))
        self.assertTrue(lot['photo_list'].startswith('https://vis.iaai.com/dimensions?imageKeys=41000001'))
        self.assertEqual(lot['title_type'], 'CLEAR (Texas)')

    def test_auction_year_rolls_over(self):
        self.assertEqual(pages.auction_start('Mon Jan 4, 10:00am (EST)', NOW), '2027-01-04T15:00Z')
        self.assertEqual(pages.auction_start('soon', NOW), '')

    def test_photo_urls(self):
        urls = pages.photo_urls(PHOTOS)
        self.assertEqual(len(urls), 2)
        self.assertTrue(urls[0].startswith('https://vis.iaai.com/resizer?imageKeys=41000001~SID~B1~S0~I1'))


class SelectionTests(unittest.TestCase):
    def test_keep_only_minimal_damage_running_recent_popular(self):
        lots = pages.listing(LISTING, 'TOYOTA', 'RAV4')
        self.assertEqual([l['id'] for l in lots if selection.keep(l)], ['41000001'])

    def test_never_flood(self):
        lot = dict(pages.listing(LISTING, 'TOYOTA', 'RAV4')[0], secondary_damage='Water/Flood')
        self.assertFalse(selection.keep(lot))

    def test_popular(self):
        self.assertTrue(selection.popular('TESLA', 'MODEL Y'))
        self.assertFalse(selection.popular('TOYOTA', 'TUNDRA'))

    def test_choose_three_of_a_model(self):
        base = pages.listing(LISTING, 'TOYOTA', 'RAV4')[0]
        lots = [dict(base, id=str(n), auction_start='2026-12-0%dT10:00Z' % (n % 9 + 1)) for n in range(6)]
        self.assertEqual(len(selection.choose(lots)), 3)


class ViewsTests(unittest.TestCase):
    def test_view_and_feed(self):
        lot = dict(pages.listing(LISTING, 'TOYOTA', 'RAV4')[0], **pages.lot(LOT, NOW))
        value = views.build([lot], {'41000001': ['a.jpg', 'b.jpg']}, '2026-11-27T12:00Z')
        view = value['lots'][0]
        self.assertEqual((view['title'], view['maker'], view['mileage_km'], view['start_usd']),
                         ('Toyota RAV4', 'Toyota', 77200, 15500))
        self.assertEqual(views.feed(value['lots'], 'x')['items'][0]['photo'], '/video/usa/lots/a.jpg')
        self.assertEqual(views.build([lot], {}, 'x')['lots'], [])


class FakeClient:
    def __init__(self, answers, closed=()):
        self.answers, self.closed, self.requests, self.urls = answers, closed, 0, []

    def _get(self, url):
        self.requests += 1
        self.urls.append(url)
        if any(c in url for c in self.closed):
            raise fetch.Closed('HTTP_418')
        for part, answer in self.answers:
            if part in url:
                return answer
        raise OSError('404')

    page = json = photo = _get


SITEMAP_INDEX = '<sitemapindex><sitemap><loc>https://www.iaai.com/x/ms-sitemapMakeModel1.xml</loc></sitemap></sitemapindex>'
MAKE_MODEL = ('<urlset><url><loc>https://www.iaai.com/Vehiclelisting/TOYOTA/RAV4/</loc></url>'
              '<url><loc>https://www.iaai.com/Vehiclelisting/TOYOTA/TUNDRA/</loc></url></urlset>')


class JobTests(unittest.TestCase):
    def answers(self):
        return [('sitemap_index', SITEMAP_INDEX), ('MakeModel1', MAKE_MODEL), ('Vehiclelisting/TOYOTA/RAV4', LISTING),
                ('VehicleDetail/41000001', LOT), ('dimensions', PHOTOS), ('resizer', b'\xff\xd8jpeg')]

    def test_run_publishes_and_remembers(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'usa'
            data = {'models': {}, 'models_at': '', 'listings': {}, 'pages': {}}
            client = FakeClient(self.answers())
            report = job.run(client, data, NOW, folder)
            self.assertEqual((report['shown'], report['stop']), (1, ''))
            self.assertEqual(list(data['models']), ['toyota|rav4'])
            value = json.loads((folder / 'lots.json').read_text())
            self.assertEqual(value['lots'][0]['title'], 'Toyota RAV4')
            self.assertEqual(len(json.loads((folder / 'gallery/41000001.json').read_text())['photos']), 2)
            self.assertEqual(len(json.loads((folder / 'feed.json').read_text())['items']), 1)
            again = FakeClient(self.answers())
            job.run(again, data, NOW, folder)
            self.assertEqual(again.requests, 0)  # listing fresh, page known, photos copied

    def test_refusal_keeps_published_lots(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'usa'
            data = {'models': {}, 'models_at': '', 'listings': {}, 'pages': {}}
            job.run(FakeClient(self.answers()), data, NOW, folder)
            data['listings']['toyota|rav4']['at'] = '2026-11-01T00:00Z'
            report = job.run(FakeClient([], closed=('iaai.com',)), data, NOW, folder)
            self.assertEqual((report['stop'], report['shown']), ('HTTP_418', 1))

    def test_past_auction_dropped(self):
        with tempfile.TemporaryDirectory() as temp:
            data = {'models': {}, 'models_at': '', 'listings': {}, 'pages': {}}
            report = job.run(FakeClient(self.answers()), data, datetime(2026, 12, 3, tzinfo=timezone.utc), Path(temp))
            self.assertEqual(report['shown'], 0)

    def test_client_cap_and_pause(self):
        pauses = []
        client = fetch.Client(1, sleep=pauses.append)
        client.requests = 1
        with self.assertRaises(fetch.Closed):
            client.get('https://www.iaai.com/')
        self.assertEqual(fetch.UA.split('/')[0], 'UAArtAutopilot')


if __name__ == '__main__':
    unittest.main()
