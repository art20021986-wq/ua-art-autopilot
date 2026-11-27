#!/usr/bin/env python3
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402
import source_remote as remote  # noqa: E402
import transport  # noqa: E402


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'USA-LOTS-PROBE-20261127'

    def env(self, root):
        request = root / 'tasks/requests' / (self.TASK + '.json')
        request.parent.mkdir(parents=True)
        request.write_text(json.dumps({'production_required': False}))
        return {'UAART_TASK_ID': self.TASK, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % self.TASK,
                'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % self.TASK,
                'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '7'}

    def test_report_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt = c.execute(self.env(Path(temp)), root=temp, api=FakeAPI({'status': 'PASS'}), upload=lambda a: 'b' * 64)
        self.assertEqual((receipt['probe_status'], receipt['evidence_path']),
                         ('PASS', 'cloud/usa_lots_probe_001/20261127.json'))

    def test_key_material_never_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(c.ProbeError, 'KEY_MATERIAL'):
                c.execute(self.env(Path(temp)), root=temp, api=FakeAPI({'x': '-----BEGIN PRIVATE KEY'}),
                          upload=lambda a: 'b' * 64)


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), \
             patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_own_server_prefix(self):
        for name in ('transport.py', 'bootstrap.py'):
            source = (Path(__file__).resolve().parent / name).read_text()
            self.assertIn('usaprobe', source)
            self.assertNotIn('bidprobe', source)

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


CSV = ('"Yard number","Lot number","Year","Make","Model Group","Damage Description","Runs/Drives","VIN",'
       '"Image URL","Sale Date M/D/CY"\n'
       '"1","12345678","2021","TOYOTA","RAV4","MINOR DENT/SCRATCHES","Run & Drive Verified","2T3P1RFV5MC123456",'
       '"https://inventoryv2.copart.io/v1/lotImages/12345678?country=us","20261130"\n'
       '"2","22345678","2019","FORD","ESCAPE","FRONT END","","1FMCU0GD4KUA12345","","20261201"\n'
       '"3","3234')


class FakeBrowser:
    def __init__(self, answers):
        self.answers, self.requests, self.urls = answers, 0, []

    def fetch(self, url, limit=0):
        self.requests += 1
        self.urls.append(url)
        for part, answer in self.answers:
            if part in url:
                return answer
        return 404, 'text/html', 'x', b''


class RemoteTests(unittest.TestCase):
    def test_clean_drops_vin_ids_and_queries(self):
        self.assertEqual(remote.clean('a@b.co 2T3P1RFV5MC123456 https://vis.iaai.com/x/12345678?k=1'),
                         '[EMAIL] [VIN] vis.iaai.com/x/[N]')

    def test_csv_cut_row_dropped_and_counted(self):
        rows = remote.csv_rows(CSV.encode())
        summary = remote.csv_summary(rows)
        self.assertEqual(summary['rows_read'], 2)
        self.assertEqual(summary['makes'], [['TOYOTA', 1], ['FORD', 1]])
        self.assertEqual(summary['years'], [2019, 2021])
        self.assertEqual(summary['image_url_filled'], 1)
        self.assertNotIn('2T3P1RFV5MC123456', json.dumps(summary))
        self.assertNotIn('12345678', json.dumps(summary))

    def test_copart_photo_list_and_photo(self):
        photos = b'{"lotImages":[{"link":[{"url":"https://cs.copart.com/v1/AUTH_svc/12345678_ful.jpg"}]}]}'
        browser = FakeBrowser([('salesdata', (200, 'text/csv', 'inventory.copart.io', CSV.encode())),
                               ('lotImages', (200, 'application/json', 'inventoryv2.copart.io', photos)),
                               ('_ful.jpg', (200, 'image/jpeg', 'cs.copart.com', b'\xff\xd8'))])
        value = remote.probe_copart(browser)
        self.assertEqual(value['photo_list']['photos'], 1)
        self.assertEqual(value['photo']['type'], 'image/jpeg')
        self.assertEqual(browser.requests, 3)

    def test_challenge_stops_source(self):
        page = b'<html><script src="/_Incapsula_Resource?x=1"></script></html>'
        browser = FakeBrowser([('salesdata', (200, 'text/html', 'inventory.copart.io', page))])
        value = remote.probe_copart(browser)
        self.assertTrue(value['file']['challenge'])
        self.assertEqual(browser.requests, 1)

    def test_iaai_sitemap_lot_and_photo(self):
        index = b'<sitemapindex><sitemap><loc>https://www.iaai.com/sm/ms-sitemapMake1.xml</loc></sitemap><sitemap><loc>https://www.iaai.com/sm/ms-sitemap1.xml</loc></sitemap></sitemapindex>'
        lots = b'<urlset><url><loc>https://www.iaai.com/VehicleDetail/43123456~US</loc></url></urlset>'
        lot = (b'<title>2020 TOYOTA CAMRY</title><div>Primary Damage: Front End</div><div>Odometer 10,000</div>'
               b'<img src="https://vis.iaai.com/resizer?imageKeys=43123456~SID~B1~I1">')
        browser = FakeBrowser([('sitemap_index', (200, 'text/xml', 'www.iaai.com', index)),
                               ('ms-sitemap1.xml', (200, 'text/xml', 'www.iaai.com', lots)),
                               ('VehicleDetail/', (200, 'text/html', 'www.iaai.com', lot)),
                               ('vis.iaai.com', (200, 'image/jpeg', 'vis.iaai.com', b'\xff\xd8'))])
        value = remote.probe_iaai(browser)
        self.assertEqual(value['vehicle_sitemap']['lots'], 1)
        self.assertEqual(value['lot_page']['labels'], ['Primary Damage', 'Odometer'])
        self.assertEqual(value['photo']['host'], 'vis.iaai.com')

    def test_one_source_failing_keeps_the_other(self):
        class Broken(FakeBrowser):
            def fetch(self, url, limit=0):
                if 'copart' in url:
                    raise OSError('down')
                return super().fetch(url, limit)
        value = remote.report(Broken([]), [('copart', remote.probe_copart), ('iaai', remote.probe_iaai)])
        self.assertIn('error', value['copart'])
        self.assertIn('sitemap', value['iaai'])


if __name__ == '__main__':
    unittest.main()
