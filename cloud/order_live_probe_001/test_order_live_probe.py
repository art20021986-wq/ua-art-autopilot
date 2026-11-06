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
    TASK = 'ORDER-LIVE-PROBE-20261106'

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
                         ('PASS', 'cloud/order_live_probe_001/20261106.json'))


class TransportTests(unittest.TestCase):
    def test_never_the_bot(self):
        api = transport.API('test-token')
        with patch.object(api, 'file', return_value=None), patch.object(api, 'json', return_value={'id': transport.BOT_ID}):
            with self.assertRaisesRegex(transport.TransportError, 'TRIGGER_IDENTITY'):
                api.run('probe', '1', 'a' * 64)

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


class RemoteTests(unittest.TestCase):
    def test_only_public_get_requests(self):
        seen = []

        class Response:
            status, url, headers = 200, 'https://www.uaart.com.ua/video/podbor.html', {}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n):
                return b'<p data-label="thanks">x</p> order.js?v=20261106.2'

        def opener(request, timeout):
            seen.append((request.get_method(), request.full_url))
            return Response()
        with patch.object(remote.urllib.request, 'urlopen', side_effect=opener):
            value = remote.report()
        self.assertTrue(all(m == 'GET' and u.startswith('https://www.uaart.com.ua/') for m, u in seen))
        self.assertTrue(value['public']['/video/podbor.html']['markers']['data-label="thanks"'])


if __name__ == '__main__':
    unittest.main()
