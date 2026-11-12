#!/usr/bin/env python3
import json
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402
import source_remote as remote  # noqa: E402
import transport  # noqa: E402
import week  # noqa: E402

FORM = ('<form id="purchase_search_form" action="/vehicle-search/kr/index">'
        '<input type="checkbox" name="auction_group[]" value="1" id="g1"><label for="g1">Mon AutoPlus</label>'
        '<input type="checkbox" name="auction_group[]" value="4" checked> Wed <b>Auto Hub</b>'
        '<input type="checkbox" name="auction[]" value="50004|4">'
        '<input type="checkbox" name="auction_group[]" value="5" checked>Thu'
        '</form>')


def lot(lot_id, day, house):
    return {'id': lot_id, 'auction_start': day + ' 12:00', 'house': house}


class WeekTests(unittest.TestCase):
    def test_groups_labels_and_default(self):
        self.assertEqual(week.groups('<p>x</p>' + FORM), [
            {'value': '1', 'label': 'Mon AutoPlus', 'checked': False},
            {'value': '4', 'label': 'Wed Auto Hub', 'checked': True},
            {'value': '5', 'label': 'Thu', 'checked': True}])

    def test_week_counts_each_lot_once_and_marks_site(self):
        by_group = {'1': [lot('a', '2026/11/16', 'AutoPlus'), lot('b', '2026/11/16', 'AutoPlus')],
                    '4': [lot('c', '2026/11/18', 'Auto Hub'), lot('d', '2026/11/26', 'Auto Hub')],
                    '5': [lot('c', '2026/11/18', 'Auto Hub'), lot('e', '2026/11/11', 'Old')]}
        self.assertEqual(week.week(by_group, ['4', '5'], '2026/11/12'), [
            {'date': '2026/11/16', 'weekday': 'Mon', 'house': 'AutoPlus', 'lots': 2, 'groups': ['1'], 'on_site': False},
            {'date': '2026/11/18', 'weekday': 'Wed', 'house': 'Auto Hub', 'lots': 1, 'groups': ['4', '5'],
             'on_site': True}])

    def test_compare_finds_new_house_day_and_group(self):
        old = {'groups': [{'value': '4', 'label': 'Wed'}],
               'week': [{'house': 'Auto Hub', 'weekday': 'Wed', 'on_site': True}]}
        new = {'groups': [{'value': '4', 'label': 'Wed'}, {'value': '9', 'label': 'Sat New'}],
               'week': [{'house': 'Auto Hub', 'weekday': 'Wed', 'on_site': True},
                        {'house': 'Auto Hub', 'weekday': 'Sat', 'on_site': True},
                        {'house': 'New', 'weekday': 'Sat', 'on_site': False}]}
        value = week.compare(old, new)
        self.assertEqual((value['new_houses'], value['gone_houses'], value['new_days'], value['new_groups'],
                          value['auctions_before'], value['auctions_now'], len(value['not_on_site_now'])),
                         (['New'], [], {'Auto Hub': ['Sat']}, {'9': 'Sat New'}, 1, 3, 1))


class RemoteTests(unittest.TestCase):
    def test_search_group_sends_only_that_group_and_restores(self):
        sent = []
        original = lambda html: ('/a', [('mode', 'search'), ('order_closed[]', '1'), ('auction_group[]', '4'),
                                        ('auction[]', '50004|4')])
        collect = types.SimpleNamespace(_search_form_data=original)
        collect.fetch_all_lots = lambda browser: sent.append(collect._search_form_data('')) or (0, [])
        remote.search_group(None, collect, '1')
        self.assertEqual(sent, [('/a', [('mode', 'search'), ('order_closed[]', '1'), ('auction_group[]', '1')])])
        self.assertIs(collect._search_form_data, original)


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
