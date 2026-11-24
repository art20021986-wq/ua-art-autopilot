#!/usr/bin/env python3
import asyncio
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

API_HASH = 'abcdef0123456789abcdef0123456789'
TOKEN = '123456:SECRETTOKENVALUE'


class RemoteTests(unittest.TestCase):
    def home(self, temp, key='7654321\n' + API_HASH + '\n'):
        home = Path(temp)
        (home / 'telegram_api.txt').write_text(key)
        (home / 'team_token.txt').write_text(TOKEN + '\n')
        return home

    def test_secrets_checked_and_never_in_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(remote, 'HOME', self.home(temp)):
                self.assertEqual(remote.secrets(), (7654321, API_HASH, TOKEN))
            with patch.object(remote, 'HOME', self.home(temp, key='x\n')):
                with self.assertRaisesRegex(RuntimeError, 'KEY_OR_TOKEN_FORMAT'):
                    remote.secrets()

    def test_failure_report_removes_work_and_hides_values(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / 'bigvideo_probe_work'
            with patch.object(remote, 'WORK', work), patch.object(remote, 'install', side_effect=RuntimeError(TOKEN)):
                value = remote.report()
        self.assertEqual((value['status'], value['work_removed']), ('FAIL', True))
        self.assertNotIn('SECRETTOKENVALUE'[:6] + 'TOKEN', json.dumps(value).replace('[N]', ''))
        self.assertNotIn('123456:', json.dumps(value))

    def test_video_size_only_for_videos(self):
        doc = types.SimpleNamespace(mime_type='video/mp4', size=30 * 2**20)
        self.assertEqual(remote.video_size(types.SimpleNamespace(media=types.SimpleNamespace(document=doc))), 30 * 2**20)
        photo = types.SimpleNamespace(mime_type='image/jpeg', size=30 * 2**20)
        self.assertEqual(remote.video_size(types.SimpleNamespace(media=types.SimpleNamespace(document=photo))), 0)
        self.assertEqual(remote.video_size(types.SimpleNamespace(media=None)), 0)

    def test_pinned_packages(self):
        self.assertIn('telethon==1.46.0', remote.PACKAGES)


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'BIG-VIDEO-PROBE-20261119'

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
                         ('PASS', 'cloud/big_video_probe_001/20261119.json'))

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
        self.assertIn('bigvideoprobe-', text)
        self.assertNotIn('videobuild', text)

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
