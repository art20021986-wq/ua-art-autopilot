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

FORM = ('<form action="/vehicle-search/kr/index" method="post" id="purchase_search_form">'
        '<input type="hidden" name="token" value="abc">'
        '<input type="hidden" name="koreafavoriteurl" value="x">'
        '<div><input type="checkbox" name="auction_group[]" value="1" checked> AutoPlus</div>'
        '<div><input type="checkbox" name="auction_group[]" value="2" checked> K-Car O-San</div>'
        '<div><input type="checkbox" name="auction_group[]" value="7"> Hyundai Glovis</div>'
        '<div><input type="checkbox" name="auction_group[]" value="8"> Lotte Auction</div>'
        '<div><input type="checkbox" name="closed[]" value="1" checked> Closed orders</div>'
        '</form>')
RESULTS = ('<p>3 Results</p><table><tr><th>Auction Start</th><th>Auction / Lot</th><th>Maker</th></tr>'
           '<tr><td>2026/12/01 09:00</td><td><a href="/vehicle-detail/kr/20261201000001">AutoPlus (1234)</a></td>'
           '<td>KIA</td></tr>'
           '<tr><td>2026/12/01 09:00</td><td><a href="/vehicle-detail/kr/20261201000002">AutoPlus (77)</a></td>'
           '<td>HYUNDAI</td></tr>'
           '<tr><td>2026/12/02 10:00</td><td><a href="/vehicle-detail/kr/20261202000003">K-Car O-San (5)</a></td>'
           '<td>KIA</td></tr></table>')


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'KOREA-HOUSES-PROBE-20261128'

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
                         ('PASS', 'cloud/korea_houses_probe_001/20261128.json'))

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
            self.assertIn('krhouseprobe', source)
            self.assertNotIn('bidprobe', source)

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


class RemoteTests(unittest.TestCase):
    def test_form_default_data_and_house_boxes(self):
        form = remote.search_form(FORM)
        self.assertEqual(form['action'], '/vehicle-search/kr/index')
        self.assertEqual(form['data'], [('token', 'abc'), ('auction_group[]', '1'), ('auction_group[]', '2'),
                                        ('closed[]', '1')])
        every = remote.boxes(form['block'])
        houses = remote.house_boxes(every)
        self.assertEqual([b['label'] for b in houses], ['AutoPlus', 'K-Car O-San', 'Hyundai Glovis', 'Lotte Auction'])
        self.assertEqual([b['label'] for b in houses if not b['checked']], ['Hyundai Glovis', 'Lotte Auction'])

    def test_counts_by_house_drop_lot_numbers(self):
        header, lots = remote.rows(RESULTS)
        self.assertEqual(remote.total(RESULTS), 3)
        found = remote.by_house(header, lots)
        self.assertEqual(found['by_house'], {'AutoPlus': 2, 'K-Car O-San': 1})
        self.assertEqual(found['by_day'], {'2026/12/01': 2, '2026/12/02': 1})
        self.assertNotIn('1234', json.dumps(found))

    def test_report_adds_one_house_at_a_time(self):
        sent = []

        class FakeBrowser:
            requests = 0

            def fetch(self, path, data=None):
                sent.append((path, data))
                self.requests += 1
                if path == '/login/login':
                    return path, 'ok'
                if path == '/vehicle-search/kr/':
                    return path, FORM
                return path, RESULTS if data and len(data) == 4 else '<p>5 Results</p>'

        with patch.object(remote, 'Browser', FakeBrowser), patch.object(remote, 'login_pair', return_value=('e', 'p')):
            value = remote.report()
        self.assertEqual(value['status'], 'PASS')
        self.assertEqual(value['glovis_lotte_in_form'], ['Hyundai Glovis', 'Lotte Auction'])
        self.assertEqual(value['default_total'], 3)
        self.assertEqual(value['added_one_house_total'], {'Hyundai Glovis': 5, 'Lotte Auction': 5})
        self.assertTrue(value['no_bid_placed'])
        self.assertFalse(any('bid' in path.lower() for path, _ in sent))

    def test_sanitized_drops_scripts_values_and_names(self):
        html = ('<head><title>x</title></head><script>var t=1</script><p>Welcome, Ivan Petrov</p>'
                '<input type="hidden" name="_csrf" value="abc123"><a href="/vehicle-detail/kr/20261201000001">L</a>')
        out = remote.sanitized(html)
        self.assertNotIn('abc123', out)
        self.assertNotIn('var t', out)
        self.assertNotIn('Petrov', out)
        self.assertIn('/vehicle-detail/kr/[N]', out)

    def test_results_sample(self):
        sample = remote.results_sample(RESULTS + '<a href="/vehicle-search/kr/index/page=2?x=1">2</a>')
        self.assertEqual(sample['count_text'], '3')
        self.assertEqual(len(sample['detail_links']), 3)
        self.assertEqual(sample['pager_links'], ['/vehicle-search/kr/index/page=2?x=1'])
        self.assertIn('AutoPlus', sample['table'])

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
