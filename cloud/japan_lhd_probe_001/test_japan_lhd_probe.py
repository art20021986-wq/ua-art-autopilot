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

FORM = ('<form action="/vehicle-search/jp/index" method="post" id="purchase_search_form">'
        '<input type="hidden" name="token" value="abc">'
        '<input type="hidden" name="japanfavoriteurl" value="x">'
        '<select name="maker[]"><option>TOYOTA</option></select>'
        '<ul><li><input type="checkbox" name="left_hd[]" value="1"> Left Hand Drive</li></ul>'
        '<div><input type="checkbox" name="auction[]" value="11" checked> USS Tokyo</div>'
        '<div><input type="checkbox" name="auction[]" value="12" checked> TAA Kinki</div>'
        '</form>')
RESULTS = ('<p>3 Results</p><table><tr><th>Auction Start</th><th>Auction / Lot</th><th>Maker</th></tr>'
           '<tr><td>2026/12/01 09:00</td><td><a href="/vehicle-detail/jp/20261201000001">USS Tokyo (1234)</a></td>'
           '<td>MERCEDES BENZ</td></tr>'
           '<tr><td>2026/12/01 09:00</td><td><a href="/vehicle-detail/jp/20261201000002">USS Tokyo (77)</a></td>'
           '<td>PORSCHE</td></tr>'
           '<tr><td>2026/12/02 10:00</td><td><a href="/vehicle-detail/jp/20261202000003">TAA Kinki (5)</a></td>'
           '<td>MERCEDES BENZ</td></tr></table>')


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'JAPAN-LHD-PROBE-20261127'

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
                         ('PASS', 'cloud/japan_lhd_probe_001/20261127.json'))

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
            self.assertIn('jplhdprobe', source)
            self.assertNotIn('bidprobe', source)

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


class RemoteTests(unittest.TestCase):
    def test_countries(self):
        self.assertEqual(remote.countries('<a href="/vehicle-search/kr/">K</a><a href="/vehicle-search/jp/">J</a>'),
                         ['jp', 'kr'])

    def test_form_default_data_and_lhd_box(self):
        form = remote.search_form(FORM)
        self.assertEqual(form['action'], '/vehicle-search/jp/index')
        self.assertEqual(form['data'], [('token', 'abc'), ('auction[]', '11'), ('auction[]', '12')])
        summary = remote.form_summary(form['block'])
        self.assertEqual([(b['name'], b['label']) for b in summary['lhd_boxes']], [('left_hd[]', 'Left Hand Drive')])
        self.assertEqual((summary['auction_boxes'], summary['uss_auction_boxes']), (2, 1))

    def test_counts_drop_lot_numbers(self):
        header, lots = remote.rows(RESULTS)
        self.assertEqual(remote.total(RESULTS), 3)
        found = remote.counts(header, lots)
        self.assertEqual(found['by_house'], {'USS Tokyo': 2, 'TAA Kinki': 1})
        self.assertEqual(found['uss'], 2)
        self.assertEqual(found['by_maker'], {'MERCEDES BENZ': 2, 'PORSCHE': 1})
        self.assertEqual(found['by_day'], {'2026/12/01': 2, '2026/12/02': 1})
        self.assertNotIn('1234', json.dumps(found))

    def test_lot_page_steering_and_photos(self):
        html = ('<table><tr><th>Handle</th><td>Left</td></tr><tr><th>Mileage</th><td>45,000 km</td></tr></table>'
                '<img src="https://image-cdn-hub.beforward.jp/a/1.jpg"><img src="/img/logo.png"> Auction Sheet')
        page = remote.lot_page(html)
        self.assertEqual(page['steering'], {'Handle': 'Left'})
        self.assertEqual((page['photo_count'], page['photo_hosts'], page['auction_sheet']),
                         (1, {'image-cdn-hub.beforward.jp': 1}, True))

    def test_clean(self):
        self.assertEqual(remote.clean('a@b.co lot 20261201000001 https://x.jp/p?q=1'), '[EMAIL] lot [N] /p')

    def test_login_file_is_needed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'login.txt'
            path.write_text('only-one-line')
            with patch.object(remote, 'LOGIN', path):
                with self.assertRaisesRegex(RuntimeError, 'LOGIN_FILE_INCOMPLETE'):
                    remote.login_pair()


if __name__ == '__main__':
    unittest.main()
