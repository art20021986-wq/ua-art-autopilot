#!/usr/bin/env python3
import json
from pathlib import Path
import re
import sqlite3
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
    TASK = 'CARD-DIAG-PROBE-20261105'

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
                         ('PASS', 'cloud/card_diag_probe_001/20261105.json'))

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
        self.assertIn('diagprobe-', Path(transport.__file__).read_text())
        self.assertNotIn('crmprobe', Path(transport.__file__).read_text())

    def test_bundle_names_pass_bootstrap_filter(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertRegex(path.name, re.compile(r'[a-z_]+\.py'))


class RemoteTests(unittest.TestCase):
    def test_cards_pages_and_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'video/ua').mkdir(parents=True)
            with sqlite3.connect(home / 'crm.db') as db:
                db.execute('CREATE TABLE cars (id, auto_number, stage, diag_text, client_phone)')
                db.execute("INSERT INTO cars VALUES (1, 'UA-0013', 'ua_arrived', 'secret words', '+380992222002')")
            (home / 'video/UA-0013.html').write_text(
                "<title>Mercedes-Benz B-Class 2015</title><!--ua-art-diagnostics-permanent-v1-->"
                "<a class='mcf-diag-cta' href='UA-0013-diag.html'>x</a>")
            (home / 'video/ua/UA-0013.html').write_text('<title>Mercedes-Benz B-Class</title>no link')
            (home / 'video/UA-0013-diag.html').write_text('<video></video>')
            (home / 'stranica.py').write_text("TOKEN = 'abc'\nCTA = 'mcf-diag-cta'\n")
            value = remote.report(home)
        row = value['cars']['rows'][0]
        self.assertEqual(row, {'id': 1, 'auto_number': 'UA-0013', 'stage': 'ua_arrived', 'diag_text_length': 12})
        cards = value['pages']['cards']
        self.assertEqual(cards['UA-0013.html']['markers']['mcf-diag-cta'], 1)
        self.assertEqual(cards['UA-0013.html']['diag_hrefs'], ['UA-0013-diag.html'])
        self.assertEqual(cards['ua/UA-0013.html']['markers']['mcf-diag-cta'], 0)
        self.assertEqual(value['pages']['diag_pages']['UA-0013-diag.html']['videos'], 1)
        lines = [l['text'] for l in value['sources']['stranica.py']['lines']]
        self.assertIn('[REDACTED]', lines)
        self.assertEqual(sorted(value['mercedes_pages']), ['UA-0013.html', 'ua/UA-0013.html'])
        self.assertNotIn('+380', json.dumps(value))


if __name__ == '__main__':
    unittest.main()
