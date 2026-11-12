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
import week  # noqa: E402

FORM = ('<form id="purchase_search_form" action="/vehicle-search/kr/index">'
        '<input type="checkbox" name="auction_group[]" value="1" id="g1"><label for="g1">Mon. AutoPlus</label>'
        '<input type="checkbox" name="auction_group[]" value="4" checked> Thu. <b>Show Detail</b>'
        '<input type="checkbox" name="auction[]" value="50004|4"> K-Car O-San'
        '<input type="checkbox" name="auction_group[]" value="5" checked>Fri.'
        '</form>')


def lot(day, house):
    return {'auction_start': day + ' 12:00', 'house': house}


class WeekTests(unittest.TestCase):
    def test_schedule_days_auctions_and_default(self):
        self.assertEqual(week.schedule('<p>x</p>' + FORM), [
            {'value': '1', 'label': 'Mon. AutoPlus', 'checked': False, 'auctions': []},
            {'value': '4', 'label': 'Thu. Show Detail', 'checked': True, 'auctions': ['K-Car O-San']},
            {'value': '5', 'label': 'Fri.', 'checked': True, 'auctions': []}])

    def test_week_counts_auction_and_site_lots(self):
        lots = [lot('2026/11/13', 'AutoPlus'), lot('2026/11/13', 'AutoPlus'), lot('2026/11/18', 'Auto Hub'),
                lot('2026/11/20', 'Late'), lot('2026/11/12', 'Old')]
        self.assertEqual(week.week(lots, [lot('2026/11/13', 'AutoPlus')], '2026/11/13'), [
            {'date': '2026/11/13', 'weekday': 'Fri', 'house': 'AutoPlus', 'lots': 2, 'on_site': 1},
            {'date': '2026/11/18', 'weekday': 'Wed', 'house': 'Auto Hub', 'lots': 1, 'on_site': 0}])

    def test_compare_finds_new_house_day_schedule_and_misses(self):
        old = {'schedule': [{'label': 'Wed.', 'auctions': []}],
               'week': [{'house': 'Auto Hub', 'weekday': 'Wed', 'lots': 1, 'on_site': 1}]}
        new = {'schedule': [{'label': 'Wed.', 'auctions': ['Auto Hub']}],
               'week': [{'house': 'Auto Hub', 'weekday': 'Wed', 'lots': 1, 'on_site': 1},
                        {'house': 'Auto Hub', 'weekday': 'Sat', 'lots': 2, 'on_site': 2},
                        {'house': 'New', 'weekday': 'Sat', 'lots': 3, 'on_site': 0}]}
        value = week.compare(old, new)
        self.assertEqual((value['new_houses'], value['gone_houses'], value['new_days'], value['new_schedule'],
                          value['auctions_before'], value['auctions_now'], len(value['site_misses_now'])),
                         (['New'], [], {'Auto Hub': ['Sat']}, ['Wed. / Auto Hub'], 1, 3, 1))


class RemoteTests(unittest.TestCase):
    def test_site_lots_missing_is_empty(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(remote, 'ROOT', Path(temp)):
            self.assertEqual(remote.site_lots(), [])
            folder = Path(temp) / 'video/korea'
            folder.mkdir(parents=True)
            (folder / 'lots.json').write_text(json.dumps({'lots': [{'house': 'A'}]}))
            self.assertEqual(remote.site_lots(), [{'house': 'A'}])


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'KOREA-WEEK-PROBE-20261112'

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
                         ('PASS', 'cloud/korea_week_001/20261112.json'))

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
        text = Path(transport.__file__).read_text() + Path(__file__).with_name('bootstrap.py').read_text()
        self.assertIn('weekprobe-', text)
        self.assertNotIn('lotprobe', text)

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
