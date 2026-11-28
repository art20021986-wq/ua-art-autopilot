#!/usr/bin/env python3
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from usa_auction import fetch, job, pages, selection, views  # noqa: E402

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def block(lot_id, year, damage, start, odo='48,000'):
    """As the live listing (27.11): each value in its item's title attribute, the label span only for some."""
    item = '<li class="data-list__item"><span class="data-list__value" title="%s: %s">%s</span></li>'
    return ('<div class="table-row"><a href="/VehicleDetail/%s~US"><img></a><h4><a href="/VehicleDetail/%s~US">'
            '%d TOYOTA RAV4 XLE</a></h4><ul><li class="data-list__item"><span class="data-list__label">Stock #: </span>'
            '<span class="data-list__value" title="Stock #: %s">%s</span></li>' % (lot_id, lot_id, year, lot_id, lot_id)
            + item % ('Title/Sale Doc', '', '') + item % ('Primary Damage', damage, damage)
            + item % ('Odometer', odo + ' mi (Actual)', odo) + item % ('Start Code', start, start) + '</ul></div>')


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
        self.assertTrue(selection.popular('TESLA', 'MODEL-3'))
        self.assertTrue(selection.popular('TOYOTA', 'RAV4 HYBRID'))
        self.assertFalse(selection.popular('MAZDA', '323'))
        self.assertFalse(selection.popular('TOYOTA', 'TUNDRA'))

    def test_choose_three_of_a_model(self):
        base = pages.listing(LISTING, 'TOYOTA', 'RAV4')[0]
        lots = [dict(base, id=str(n), auction_start='2026-12-0%dT10:00Z' % (n % 9 + 1)) for n in range(6)]
        self.assertEqual(len(selection.choose(lots)), 3)


class FixFiveTests(unittest.TestCase):
    def test_value_written_twice_is_kept_once(self):
        self.assertEqual(pages.once('Hail Hail'), 'Hail')
        self.assertEqual(pages.once('Normal Wear & Tear Normal Wear & Tear'), 'Normal Wear & Tear')
        self.assertEqual(pages.once('Front End'), 'Front End')
        lot = pages.lot(LOT.replace('Primary Damage: Minor Dent/Scratches', 'Primary Damage: Hail Hail'), NOW)
        self.assertEqual(lot['damage'], 'Hail')

    def test_names(self):
        self.assertEqual([views.model_name(m) for m in ('ROGUE', 'RAV4', 'CR-V', 'XC90', 'X3', 'MODEL Y', 'GRAND CHEROKEE')],
                         ['Rogue', 'RAV4', 'CR-V', 'XC90', 'X3', 'Model Y', 'Grand Cherokee'])
        self.assertEqual([views.make_name(m) for m in ('BMW', 'TOYOTA', 'MERCEDES-BENZ')], ['BMW', 'Toyota', 'Mercedes-Benz'])


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
            # listing fresh, page known, photos copied; only the unreadable lot page is tried again
            self.assertEqual(again.urls, ['https://www.iaai.com/VehicleDetail/41000003~US'])

    def test_refusal_keeps_published_lots(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'usa'
            data = {'models': {}, 'models_at': '', 'listings': {}, 'pages': {}}
            job.run(FakeClient(self.answers()), data, NOW, folder)
            data['listings']['toyota|rav4']['at'] = '2026-11-01T00:00Z'
            report = job.run(FakeClient([], closed=('iaai.com',)), data, NOW, folder)
            self.assertEqual((report['stop'], report['shown']), ('HTTP_418', 1))

    def test_one_unreadable_listing_is_skipped_not_a_stop(self):
        """USA-LOTS-FIX-003: one odd model page no longer stops every run (it waits its next turn)."""
        with tempfile.TemporaryDirectory() as temp:
            blank = LISTING.replace('Primary Damage', 'Something')
            data = {'models': {'toyota|rav4': 'https://www.iaai.com/Vehiclelisting/TOYOTA/RAV4/'},
                    'models_at': '2026-11-27T00:00Z',
                    'listings': {'toyota|rav4': {'at': '2026-11-27T11:00Z', 'lots': [{'id': '1', 'damage': ''}]}},
                    'pages': {}}
            client = FakeClient([('Vehiclelisting', blank)])
            report = job.run(client, data, NOW, Path(temp))
            self.assertEqual((report['stop'], client.requests), ('', 1))
            self.assertEqual(data['listings'], {'toyota|rav4': {'at': '2026-11-27T12:00Z', 'lots': []}})
            again = FakeClient([])
            job.run(again, data, NOW, Path(temp))
            self.assertEqual(again.requests, 0)  # it waits LISTING_HOURS, it is not read again every hour

    def test_every_listing_unreadable_stops(self):
        with tempfile.TemporaryDirectory() as temp:
            blank = LISTING.replace('Primary Damage', 'Something')
            models = {'toyota|%s' % m: 'https://www.iaai.com/Vehiclelisting/TOYOTA/%s/' % m.upper()
                      for m in ('rav4', 'camry', 'corolla')}
            data = {'models': models, 'models_at': '2026-11-27T00:00Z', 'listings': {}, 'pages': {}}
            report = job.run(FakeClient([('Vehiclelisting', blank)]), data, NOW, Path(temp))
            self.assertEqual(report['stop'], 'LISTING_UNREADABLE')

    def test_request_limit_keeps_the_lot_pages_read(self):
        """USA-LOTS-FIX-003: a run that hits its limit while reading lot pages keeps them (live 28.11: it lost them
        every hour, so no lot page was ever kept)."""
        with tempfile.TemporaryDirectory() as temp:
            data = {'models': {}, 'models_at': '', 'listings': {}, 'pages': {}}
            client = FakeClient(self.answers())
            client.limit = 5  # sitemap, make-model sitemap, listing, one lot page and its photo list
            original = client._get

            def capped(url, _original=original):
                if client.requests >= client.limit:
                    raise fetch.Closed('REQUEST_CAP')
                return _original(url)
            client.page = client.json = client.photo = capped
            report = job.run(client, data, NOW, Path(temp))
            self.assertEqual(report['stop'], 'REQUEST_CAP')
            self.assertIn('41000001', data['pages'])

    def test_runs_from_lot_page_when_listing_has_no_start_code(self):
        """Live 27.11: the listing shows no start code; «runs» comes from the lot page, photos only then."""
        with tempfile.TemporaryDirectory() as temp:
            listing = LISTING.replace('Start Code', 'Something Else')
            data = {'models': {}, 'models_at': '', 'listings': {}, 'pages': {}}
            answers = [(p, listing if p.startswith('Vehiclelisting') else a) for p, a in self.answers()]
            answers.insert(0, ('VehicleDetail/41000003', LOT.replace('Run &amp; Drive', 'Stationary')))
            client = FakeClient(answers)
            report = job.run(client, data, NOW, Path(temp))
            self.assertEqual(report['shown'], 1)
            self.assertFalse(data['pages']['41000003']['runs'])
            self.assertEqual(data['pages']['41000003']['photos'], [])
            self.assertEqual(sum('dimensions' in u for u in client.urls), 1)

    def test_one_unreadable_lot_page_is_skipped(self):
        with tempfile.TemporaryDirectory() as temp:
            data = {'models': {}, 'models_at': '', 'listings': {}, 'pages': {}}
            report = job.run(FakeClient(self.answers()), data, NOW, Path(temp))  # 41000003's page: 404
            self.assertEqual((report['shown'], report['stop']), (1, ''))

    def test_lot_page_without_auction_date_is_skipped_not_a_crash(self):
        """Live 28.11: a lot page with no auction date made every run fail (KeyError: auction_start)."""
        with tempfile.TemporaryDirectory() as temp:
            undated = LOT.replace('Auction Date and Time: Wed Dec 2, 9:30am (CST)', 'Auction Date and Time: TBA')
            answers = [('VehicleDetail/41000001', undated)] + self.answers()
            data = {'models': {}, 'models_at': '', 'listings': {}, 'pages': {}}
            report = job.run(FakeClient(answers), data, NOW, Path(temp))
            self.assertEqual((report['shown'], report['stop']), (0, ''))
            self.assertEqual(data['pages']['41000001']['auction_start'], '')

    def test_main_reports_an_error_and_keeps_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with unittest.mock.patch.object(job, 'DATA', root / 'data'), \
                    unittest.mock.patch.object(job, 'OUT', root / 'usa'), \
                    unittest.mock.patch.object(job, 'LOCK', root / '.lock'), \
                    unittest.mock.patch.object(job, 'run', side_effect=TypeError('boom')):
                self.assertEqual(job.main(NOW), 0)
            report = json.loads((root / 'data' / 'last_run.json').read_text())
            self.assertEqual(report['error'], 'TypeError: boom')
            self.assertTrue((root / 'data' / 'state.json').exists())

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
