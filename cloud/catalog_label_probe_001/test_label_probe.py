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
        self.report, self.calls = report, []

    def run(self, mode, run_id, bundle):
        self.calls.append((mode, run_id, bundle))
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'CATALOG-LABEL-PROBE-20261030'

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
                         ('PASS', 'cloud/catalog_label_probe_001/20261030.json'))

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

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


class RemoteTests(unittest.TestCase):
    def test_finds_catalog_card_and_label_files_sanitized(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'order_requests').mkdir()
            catalog = home / 'order_requests' / 'catalog.json'
            card = {'key': 'classics-1980-1990', 'labels': {'uk': 'Раритетні авто 1980-1990-х років'}}
            catalog.write_text(json.dumps({'version': '7', 'countries': {'japan': {'models': [card]}}},
                                          ensure_ascii=False, indent=1))
            (home / 'order_requests' / 'settings.json').write_text(json.dumps({'catalog_path': str(catalog),
                                                                               'bot_token': 'x'}))
            (home / 'mysite').mkdir()
            (home / 'mysite' / 'bot.py').write_text("TOKEN = 'abc'\nTOP = ['Раритетные авто 1980–1990-х годов']\n")
            (home / 'mysite' / 'other.py').write_text("X = 1\n")
            with patch.object(remote, 'HOME', home), \
                 patch.object(remote, 'SETTINGS', home / 'order_requests' / 'settings.json'):
                value = remote.report()
        self.assertEqual(value['catalog']['card'], [card])
        self.assertEqual(value['catalog']['version'], '7')
        self.assertNotIn('bot_token', json.dumps(value))
        self.assertEqual(sorted(Path(p).name for p in value['label_hits']), ['bot.py', 'catalog.json'])
        lines = value['label_hits'][str(home / 'mysite' / 'bot.py')]['matches'][0]['context']
        self.assertEqual(lines[0], '[REDACTED]')


if __name__ == '__main__':
    unittest.main()
