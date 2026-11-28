#!/usr/bin/env python3
"""SEO-PRICE-PROBE: sources, changed files, card facts and an in-memory normalize, without secrets; no CRM read."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402
import source_remote as remote  # noqa: E402

CARD = ('<html lang="ru"><head><title>Audi A6 2015</title><meta name="description" content="Audi A6 2015 опис">'
        '</head><body><!-- UA-ART-MARKET-PRICES-V1:START --><div data-ua-market="ukraine" data-ua-value="19900">'
        '</div></body></html>')
NORMALIZE = ('import re\n'
             'def normalize(source, name):\n'
             '    open("/tmp/should-not-be-written-" + name, "w").write("x") if "WRITE" in source else None\n'
             '    price = re.search(r"data-ua-value=\\"([0-9]+)", source)\n'
             '    return re.sub(r"<title>.*?</title>", "<title>T %s</title>" % (price.group(1) if price else ""), source)\n')


class RemoteTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name)
        (self.home / 'ua_seo_metadata.py').write_text(NORMALIZE + 'TOKEN = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"\n',
                                                      encoding='utf-8')
        (self.home / 'old.py').write_text('print(1)\n', encoding='utf-8')
        old = (remote.SINCE - 86400, remote.SINCE - 86400)
        os.utime(self.home / 'old.py', old)
        (self.home / 'new_module.py').write_text('PHONE = "+380 99 222 2002"\n', encoding='utf-8')
        (self.home / 'backups').mkdir()
        (self.home / 'backups/x.py').write_text('X = 1\n', encoding='utf-8')
        for name in remote.CARDS:
            (self.home / name).parent.mkdir(parents=True, exist_ok=True)
            (self.home / name).write_text(CARD, encoding='utf-8')
        (self.home / 'crm.db').write_bytes(b'not read')

    def report(self):
        with patch.object(remote, 'HOME', self.home):
            return remote.report()

    def test_report_without_secrets(self):
        value = self.report()
        text = json.dumps(value, ensure_ascii=False)
        self.assertIn('ua_seo_metadata.py', value['full_sources'])
        self.assertIn('new_module.py', value['files'])
        self.assertTrue(value['files']['new_module.py']['changed_since_26_11'])
        self.assertNotIn('old.py', value['files'])
        self.assertNotIn('backups/x.py', value['files'])
        self.assertNotIn('new_module.py', value['full_sources'])
        for secret in ('AAAAAAAA', '222 2002'):
            self.assertNotIn(secret, text)
        card = value['cards']['video/ua/UA-0017.html']
        self.assertEqual((card['title'], card['market_block'], card['ld_price']), ('Audi A6 2015', True, False))
        self.assertEqual(value['normalize_check'], {'title': 'T 19900', 'price_in_source': True, 'ld_price': False})

    def test_normalize_child_cannot_write(self):
        (self.home / 'video/UA-0017.html').write_text(CARD.replace('Audi', 'WRITE'), encoding='utf-8')
        value = self.report()
        self.assertIn('error', value['normalize_check'])
        self.assertFalse(Path('/tmp/should-not-be-written-UA-0017.html').exists())

    def test_main_writes_only_its_receipt(self):
        with patch.object(remote, 'HOME', self.home), patch.object(remote, 'HERE', self.home / 'pkg'), \
             patch.object(remote.resource, 'setrlimit'), patch.object(sys, 'argv', ['x', '--run', '7']):
            self.assertEqual(remote.main(), 0)
        receipt = json.loads((self.home / 'pkg/runs/7/receipt-probe.json').read_text())
        self.assertEqual((receipt['status'], receipt['remote_write_count']), ('PASS', 0))


class ControllerTests(unittest.TestCase):
    TASK = 'SEO-PRICE-PROBE-20261128'

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
                             ('PASS', 'cloud/seo_price_probe_001/20261128.json'))

    def test_wrong_task_is_refused(self):
        with self.assertRaises(c.ProbeError):
            c.validate_identity({'UAART_TASK_ID': 'OTHER-1'}, Path('.'))


if __name__ == '__main__':
    unittest.main()
