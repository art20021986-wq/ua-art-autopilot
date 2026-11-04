#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402
import ping_remote as remote  # noqa: E402
import transport  # noqa: E402


def notifier(folder, name, body):
    (folder / (name + '.py')).write_text(body)


class PingTests(unittest.TestCase):
    def home(self, indexnow='PASS', google='PASS'):
        folder = Path(tempfile.mkdtemp())
        notifier(folder, 'ua_indexnow', 'SENT = []\ndef submit(urls):\n    SENT.extend(urls)\n'
                 '    return {"status": "%s", "urls": len(urls)}\n' % indexnow)
        notifier(folder, 'ua_google_sitemap', 'def submit():\n    return {"status": "%s"}\n' % google)
        for name in ('ua_indexnow', 'ua_google_sitemap'):
            sys.modules.pop(name, None)
        return folder

    def test_both_notices_for_exactly_the_two_finance_pages(self):
        value = remote.report(self.home())
        self.assertEqual(value['status'], 'PASS')
        self.assertEqual(sys.modules['ua_indexnow'].SENT, list(remote.URLS))
        self.assertEqual(len(remote.URLS), 2)
        for url in remote.URLS:
            self.assertTrue(url.startswith('https://www.uaart.com.ua/video/seo/'))

    def test_failed_notice_is_reported_not_raised(self):
        self.assertEqual(remote.report(self.home(google='FAIL'))['status'], 'FAIL')

    def test_controller_writes_report_and_receipt(self):
        root = Path(tempfile.mkdtemp())
        request = root / 'tasks/requests' / (c.TASK + '.json')
        request.parent.mkdir(parents=True)
        request.write_text(json.dumps({'production_required': False}))
        env = {'UAART_TASK_ID': c.TASK, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % c.TASK,
               'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % c.TASK, 'UAART_RUN_ID': '7',
               'UAART_REQUEST_SHA256': hashlib.sha256(request.read_bytes()).hexdigest()}

        class API:
            def run(self, mode, run_id, bundle):
                assert mode == 'ping' and run_id == '7'
                return {'status': 'PASS', 'mode': 'ping', 'run_id': '7'}
        receipt = c.execute(env, root=root, api=API(), upload=lambda api: 'a' * 64)
        self.assertEqual(receipt['ping_status'], 'PASS')
        self.assertTrue((root / c.PACKAGE / 'report.json').is_file())
        with self.assertRaises(c.PingError):
            c.execute(dict(env, UAART_TASK_ID='OTHER'), root=root, api=API(), upload=lambda api: 'a' * 64)

    def test_transport_runs_only_the_ping_and_never_the_bot(self):
        with self.assertRaises(transport.TransportError):
            transport.API('x').run('install', '7', 'a' * 64)
        self.assertEqual(transport.BOT_ID, 266084)


if __name__ == '__main__':
    unittest.main()
