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
    TASK = 'LOT-PROBE-20261105'

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
                         ('PASS', 'cloud/lot_probe_001/20261105.json'))

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
        self.assertIn('lotprobe-', Path(transport.__file__).read_text())
        self.assertNotIn('crmprobe', Path(transport.__file__).read_text())

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


class RemoteTests(unittest.TestCase):
    def test_photo_shape_hides_host_and_numbers(self):
        self.assertEqual(remote.shape('https://cdn.example/a/20261111000123/photo_01.jpg?w=640'),
                         '/a/[N]/photo_01.jpg?w=640')

    def test_folder_size(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'a.jpg').write_bytes(b'12345')
            self.assertEqual(remote.folder_size(Path(temp)), {'files': 1, 'bytes': 5})

    def test_published_lot_list(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(remote, 'ROOT', Path(temp)):
            folder = Path(temp) / 'video/korea'
            folder.mkdir(parents=True)
            (folder / 'lots.json').write_text(json.dumps({'auction_date': '2026/11/12', 'lots': [
                {'id': '1', 'start_krw': 100, 'photos': ['a', 'b', 'c']}, {'id': '2', 'start_krw': 0, 'photos': ['a']}]}))
            self.assertEqual(remote.published(), {'auction_date': '2026/11/12', 'lots': 2, 'priced': 1,
                                                  'photos_per_lot': {3: 1, 1: 1}, 'keys': ['id', 'photos', 'start_krw']})


if __name__ == '__main__':
    unittest.main()
