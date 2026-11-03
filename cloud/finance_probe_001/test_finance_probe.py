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
import partner_site  # noqa: E402
import source_remote as remote  # noqa: E402
import transport  # noqa: E402

PAGE = ('<html><head><title>Лізинг - ХАПАЙ авто</title><meta name="description" content="Авто в лізинг">'
        '<link rel="icon" href="/favicon.png"><script>var x="skip";</script></head><body>'
        '<header><img src="/img/logo.svg" alt="ХАПАЙ авто" class="logo"></header>'
        '<h1>Лізинг авто</h1><p>Аванс від 20% вартості авто</p><ul><li>Термін до 5 років</li></ul></body></html>')


def fake_fetch(url, limit):
    if url.endswith('.svg'):
        return 200, 'image/svg+xml', b'<svg/>'
    if url.endswith('.png'):
        return 200, 'text/html', b'<html>'
    return 200, 'text/html', PAGE.encode()


class FakeAPI:
    def __init__(self, report):
        self.report = report

    def run(self, mode, run_id, bundle):
        return self.report


class PartnerTests(unittest.TestCase):
    def test_page_facts_and_logo(self):
        pages, files = partner_site.collect(fake_fetch)
        page = pages['/ua/leasing']
        self.assertEqual(page['title'], 'Лізинг - ХАПАЙ авто')
        self.assertIn(('h1', 'Лізинг авто'), page['headings'])
        self.assertIn('Аванс від 20% вартості авто', page['texts'])
        self.assertNotIn('skip', json.dumps(page))
        logo = files['https://hapai.kiev.ua/img/logo.svg']
        self.assertEqual((logo['type'], logo['bytes']), ('image/svg+xml', b'<svg/>'))
        self.assertEqual(files['https://hapai.kiev.ua/favicon.png'], {'error': 'TYPE:text/html'})

    def test_foreign_host_refused(self):
        with self.assertRaisesRegex(ValueError, 'FOREIGN_HOST'):
            partner_site.get('https://evil.example/x', 10)


class ControllerTests(unittest.TestCase):
    TASK = 'FINANCE-PROBE-20261103'

    def env(self, root):
        request = root / 'tasks/requests' / (self.TASK + '.json')
        request.parent.mkdir(parents=True)
        request.write_text(json.dumps({'production_required': False}))
        return {'UAART_TASK_ID': self.TASK, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % self.TASK,
                'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % self.TASK,
                'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '7'}

    def test_report_saved_with_logo_base64(self):
        with tempfile.TemporaryDirectory() as temp:
            receipt = c.execute(self.env(Path(temp)), root=temp, api=FakeAPI({'status': 'PASS'}),
                                upload=lambda a: 'b' * 64, collect=lambda: partner_site.collect(fake_fetch))
            report = json.loads((Path(temp) / receipt['evidence_path']).read_text())
        self.assertEqual((receipt['probe_status'], receipt['partner_status']), ('PASS', 'PASS'))
        self.assertEqual(report['partner_site']['logo_files']['https://hapai.kiev.ua/img/logo.svg']['base64'], 'PHN2Zy8+')

    def test_partner_failure_does_not_stop_server_read(self):
        def broken():
            raise OSError('dns')
        with tempfile.TemporaryDirectory() as temp:
            receipt = c.execute(self.env(Path(temp)), root=temp, api=FakeAPI({'status': 'PASS'}),
                                upload=lambda a: 'b' * 64, collect=broken)
        self.assertEqual((receipt['probe_status'], receipt['partner_status']), ('PASS', 'FAIL'))

    def test_key_material_never_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(c.ProbeError, 'KEY_MATERIAL'):
                c.execute(self.env(Path(temp)), root=temp, api=FakeAPI({'x': '-----BEGIN PRIVATE KEY'}),
                          upload=lambda a: 'b' * 64, collect=lambda: ({}, {}))


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
    def test_reads_sources_storage_kind_only_and_ua115(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            (home / 'ua_order').mkdir()
            (home / 'order_requests').mkdir()
            (home / 'ua_order/web.py').write_text("X = 1\nTOKEN = 'abc'\n")
            (home / 'order_requests/settings.json').write_text(json.dumps({'storage': 'mysql', 'mysql': {'password': 'p'}}))
            (home / 'ua_crm_public_sync.py').write_text("raise RuntimeError('UA115_UNAPPROVED_EXTERNAL_HOST')\n")
            (home / 'publish_guard.py').write_text("x = 1\nerrors.append('SEO068 canonical')\n")
            (home / '.crm_public_sync_state.json').write_text(json.dumps({'retries': {'UA-1': 2}, 'revisions': {'a': 1}}))
            (home / 'cars_ui.py').write_text('a\nb\ndef clients_screen():\n    pass\n')
            wsgi = home / 'wsgi.py'
            wsgi.write_text('from ua_order.web import mount\napplication = mount(app, x)\n')
            value = remote.report(home, wsgi)
        self.assertEqual(value['order_storage'], 'mysql')
        self.assertNotIn('"p"', json.dumps(value))
        self.assertIn('[REDACTED]', value['files']['ua_order/web.py']['source'])
        self.assertIn('ua_crm_public_sync.py', value['ua115_sources'])
        self.assertEqual(len(value['guard_sources']['publish_guard.py']['lines']), 2)
        self.assertIn('retries', value['sync_state'])
        self.assertNotIn('revisions', value['sync_state'])
        self.assertEqual(len(value['files']['cars_ui.py']['lines']), 4)
        self.assertEqual(len(value['files']['wsgi']['lines']), 2)
        self.assertIsNone(value['files']['ua_seo_landings.py'])
        self.assertIn('video/order/order.css', value['files'])


if __name__ == '__main__':
    unittest.main()
