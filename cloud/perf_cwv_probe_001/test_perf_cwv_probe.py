#!/usr/bin/env python3
"""PERF-CWV-PROBE: marker scan and full sources, without secrets or personal data; no CRM read."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402
import source_remote as remote  # noqa: E402


class RemoteTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name)
        (self.home / 'master_card.py').write_text(
            'TOKEN = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"\nCSS = ".shapka .logo > div:not(.znak)::after{}"\n'
            'PHONE = "+380 99 222 2002"\n', encoding='utf-8')
        (self.home / 'other.py').write_text('print(1)\n', encoding='utf-8')
        (self.home / 'korea_auction').mkdir()
        (self.home / 'korea_auction/tick.py').write_text('X = "ua-korea-ticker"\n', encoding='utf-8')
        (self.home / 'backups').mkdir()
        (self.home / 'backups/old.py').write_text('X = "ua-korea-ticker"\n', encoding='utf-8')
        (self.home / 'spec_x').mkdir()
        (self.home / 'spec_x/old.py').write_text('X = "ua-korea-ticker"\n', encoding='utf-8')
        (self.home / 'brand.py').write_text('M = "<!--UA-BRAND-HOME-V1-->"\n', encoding='utf-8')
        site = self.home / remote.USERCUSTOMIZE
        site.parent.mkdir(parents=True)
        site.write_text('import vitrina  # mcf-chat\n', encoding='utf-8')
        (self.home / 'video/opt').mkdir(parents=True)
        (self.home / 'video/opt/a.webp').write_bytes(b'1234')
        (self.home / 'crm.db').write_bytes(b'not read')

    def report(self):
        with patch.object(remote, 'HOME', self.home):
            return remote.report()

    def test_report_reads_markers_without_secrets(self):
        value = self.report()
        text = json.dumps(value, ensure_ascii=False)
        self.assertEqual(value['files']['master_card.py']['hits']['not(.znak)::after'], [2])
        self.assertIn('korea_auction/tick.py', value['files'])
        self.assertIn(remote.USERCUSTOMIZE, value['full_sources'])
        self.assertNotIn('other.py', value['files'])
        self.assertNotIn('backups/old.py', value['files'])
        self.assertNotIn('spec_x/old.py', value['files'])
        self.assertEqual(value['files']['brand.py']['hits']['UA-BRAND-HOME'], [1])
        for secret in ('AAAAAAAA', '222 2002'):
            self.assertNotIn(secret, text)
        self.assertNotIn('_text', text)
        self.assertNotIn('crm', json.dumps(sorted(value['files'])))
        self.assertEqual(value['light_images'], {'exists': True, 'count': 1, 'bytes': 4, 'sample': ['a.webp']})
        self.assertIn('ffmpeg', value['image_tools'])

    def test_main_writes_only_its_receipt(self):
        with patch.object(remote, 'HOME', self.home), patch.object(remote, 'HERE', self.home / 'pkg'), \
             patch.object(remote.resource, 'setrlimit'), patch.object(sys, 'argv', ['x', '--run', '7']):
            self.assertEqual(remote.main(), 0)
        receipt = json.loads((self.home / 'pkg/runs/7/receipt-probe.json').read_text())
        self.assertEqual((receipt['status'], receipt['remote_write_count']), ('PASS', 0))


class ControllerTests(unittest.TestCase):
    TASK = 'PERF-CWV-PROBE-20261126'

    def test_execute_writes_evidence_and_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = root / ('tasks/requests/%s.json' % self.TASK)
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'production_required': False}))
            env = {'UAART_TASK_ID': self.TASK, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % self.TASK,
                   'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % self.TASK, 'UAART_RUN_ID': '42',
                   'UAART_REQUEST_SHA256': c.sha(request.read_bytes())}

            class FakeAPI:
                def run(self, mode, run_id, bundle):
                    return {'status': 'PASS', 'mode': mode}

                def json(self, method, path):
                    return {'daily_cpu_limit_seconds': 1}

            receipt = c.execute(env, root=root, api=FakeAPI(), upload=lambda api: 'b' * 64)
            self.assertEqual((receipt['probe_status'], receipt['evidence_path']),
                             ('PASS', 'cloud/perf_cwv_probe_001/20261126.json'))

    def test_wrong_task_is_refused(self):
        with self.assertRaises(c.ProbeError):
            c.validate_identity({'UAART_TASK_ID': 'OTHER-1'}, Path('.'))


if __name__ == '__main__':
    unittest.main()
