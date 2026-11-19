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


class RemoteTests(unittest.TestCase):
    def test_localhost_roundtrip(self):
        self.assertEqual(remote.localhost(), {'listen': True, 'roundtrip': True})

    def test_machine_reports_tools(self):
        value = remote.machine()
        self.assertIn('cmake', value['tools'])
        self.assertIn('MemTotal', value['memory'])

    def test_videos_and_sources_without_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'video/x').mkdir(parents=True)
            (home / 'video/x/a.mp4').write_bytes(b'0' * 2048)
            (home / 'bot.py').write_text('LIMIT = 19 * 1024 * 1024  # 20 МБ\nTOKEN = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"\n'
                                         'url = file.download_to_drive()  # getFile\n', encoding='utf-8')
            with patch.object(remote, 'HOME', home):
                value = remote.videos()
                found = remote.sources()
        self.assertEqual((value['count'], value['total_bytes']), (1, 2048))
        text = json.dumps(found)
        self.assertIn('download_to_drive', text)
        self.assertNotIn('AAAAAAAA', text)


class KeyFileTests(unittest.TestCase):
    def test_key_content_never_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'telegram_api.txt').write_text('1234567\nabcdefabcdefabcdefabcdefabcdef12\n')
            (home / 'start_safe.py').write_text('API_HASH = "abcdefabcdefabcdefabcdefabcdef12"\napp = ApplicationBuilder()\n')
            with patch.object(remote, 'HOME', home):
                key, full = remote.key_file(), remote.full_sources()
        text = json.dumps([key, full])
        self.assertEqual((key['present'], key['two_non_empty_lines'], key['first_line_is_number']), (True, True, True))
        self.assertNotIn('abcdefabcdef', text)
        self.assertNotIn('1234567', text)
        self.assertIn('ApplicationBuilder', text)

    def test_missing_key_file(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(remote, 'HOME', Path(temp)):
                self.assertEqual(remote.key_file(), {'present': False})


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report


class ControllerTests(unittest.TestCase):
    TASK = 'VIDEO-LIMIT-PROBE-20261119'

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
                         ('PASS', 'cloud/video_limit_probe_001/20261119.json'))

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
        self.assertIn('videoprobe-', text)
        self.assertNotIn('photoaddprobe', text)

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


if __name__ == '__main__':
    unittest.main()
