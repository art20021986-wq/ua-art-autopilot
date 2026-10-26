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
    TASK = 'ORDER-INTAKE-PROBE-20261025'

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
                         ('PASS', 'cloud/order_intake_probe_001/20261025.json'))

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
    def test_finds_order_modules_and_sanitizes(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'orders_api.py').write_text("TOKEN = 'abc'\n@app.route('/api/orders/submit')\ndef submit():\n"
                                                "    phone = '+380 99 222 20 02'\nx = 'https://evil.example/p'\n")
            (home / 'helper.py').write_text("print('handoff')\n")
            (home / 'other.py').write_text('print(1)\n')
            (home / 'mysite' / 'api').mkdir(parents=True)
            (home / 'mysite' / 'api' / 'orders.py').write_text("ROUTE = '/api/orders/bootstrap'\n")
            with patch.object(remote, 'ROOTS', (home,)), patch.object(remote, 'APP_DIRS', (home / 'mysite',)):
                value = remote.report()
        self.assertEqual(sorted(Path(p).name for p in value['source_hits']), ['helper.py', 'orders.py', 'orders_api.py'])
        self.assertEqual(sorted(Path(p).name for p in value['order_sources']), ['orders.py', 'orders_api.py'])
        full = value['order_sources'][str(home / 'orders_api.py')]
        self.assertIn('[REDACTED]', full)
        self.assertNotIn('abc', full)
        self.assertIn('[URL]', full)
        self.assertIn('[N]', full)


if __name__ == '__main__':
    unittest.main()
