#!/usr/bin/env python3
import json
from pathlib import Path
import re
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402
import source_remote as remote  # noqa: E402
import transport  # noqa: E402


class RemoteTests(unittest.TestCase):
    def test_timeout_stops_the_whole_group(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / 'late'
            started = time.monotonic()
            code, _, _ = remote.run(['sh', '-c', '(sleep 3; touch %s) & sleep 30' % marker], timeout=1)
            time.sleep(3.5)
            self.assertEqual(code, 'TIMEOUT')
            self.assertLess(time.monotonic() - started, 10)
            self.assertFalse(marker.exists())

    def test_gperf_checksum_refused(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n): return b'not gperf'
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(remote, 'WORK', Path(temp)), patch.object(remote.shutil, 'which', return_value=None), \
                    patch.object(remote.urllib.request, 'urlopen', return_value=Response()):
                with self.assertRaisesRegex(RuntimeError, 'GPERF_SHA256'):
                    remote.gperf([])
            self.assertFalse((Path(temp) / 'gperf-3.1.tar.gz').exists())

    def test_built_program_is_kept_and_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / 'videobuild_work'
            binary = work / 'install/bin/telegram-bot-api'
            binary.parent.mkdir(parents=True)
            binary.write_text('#!/bin/sh\necho Bot API 9.9\n')
            binary.chmod(0o755)
            with patch.object(remote, 'WORK', work), patch.object(remote, 'gperf', return_value='/usr/bin/gperf'), \
                    patch.object(remote, 'sources', return_value=work / 'src'):
                value = remote.report()
        self.assertEqual((value['status'], value['built'], value['version']), ('PASS', True, ['Bot API 9.9']))

    def test_pinned_sources(self):
        self.assertRegex(remote.COMMIT, r'^[0-9a-f]{40}$')
        self.assertTrue(remote.GPERF_URL.startswith('https://ftp.gnu.org/'))
        self.assertLessEqual(remote.BUILD_SECONDS, 45 * 60)


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'VIDEO-SERVER-BUILD-20261119'

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
                         ('PASS', 'cloud/video_server_build_001/20261119.json'))

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
        self.assertIn('videobuild-', text)
        self.assertNotIn('videoprobe', text)

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
