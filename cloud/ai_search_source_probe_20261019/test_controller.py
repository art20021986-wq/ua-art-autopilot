#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402

MODULE = ("ORIGIN = 'https://www.uaart.com.ua'\n"
          "token = 'abc'\n"
          "HOOK = 'https://api.telegram.org/bot1/x'\n"
          "PHONE = '+380501234567'\n"
          "def normalize(html, path):\n    return html\n")


class Fake:
    def __init__(self):
        self.public_seen = []

    def api(self, endpoint):
        if endpoint not in c.ALLOWED_API:
            raise c.ProbeError('API_PATH_OUTSIDE_SCOPE')
        if endpoint.endswith('publish_transaction_guard.py'):
            return 200, MODULE.encode()
        if endpoint == c.ROUTES:
            return 200, b'{"daily_cpu_limit_seconds": 5000, "daily_cpu_total_usage_seconds": 120.5}'
        return 404, None

    def public(self, path):
        self.public_seen.append(path)
        if path == '/video/index.html':
            return 200, b'<a href="/video/seo/ua/kia-k5-koreya-kyiv.html">K5</a>'
        return 200, b'<html></html>'


class ProbeTests(unittest.TestCase):
    def test_scope(self):
        reader = c.Reader('test-value', opener=object(), public_opener=object())
        for bad in ('files/path/home/Carix/crm.db', 'files/path/home/Carix/', 'files/path/home/Carix/cars_ui.py',
                    'webapps/', 'files/path/var/log/x.log', 'files/path/home/Carix/video/', 'files/path/home/Carix/ua_public_freshness.py'):
            with self.assertRaises(c.ProbeError):
                reader.api(bad)
        for bad in ('/admin', '/video/foto/x.jpg', '/video/katalog.html', '/video/seo/ua/kia-k5-koreya-kyiv.html'):
            with self.assertRaises(c.ProbeError):
                reader.public(bad)

    def test_execute(self):
        fake = Fake()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / c.REQUEST).parent.mkdir(parents=True)
            (root / c.REQUEST).write_text(json.dumps({'read_only': True, 'production_required': False}))
            env = {'UAART_TASK_ID': c.TASK_ID, 'UAART_RECEIPT_PATH': c.RECEIPT, 'UAART_REQUEST_PATH': c.REQUEST,
                   'UAART_REQUEST_SHA256': c.sha((root / c.REQUEST).read_bytes()), 'UAART_RUN_ID': '1'}
            c.execute(env, root=root, reader=fake)
            sources = (root / c.SOURCES).read_text()
            evidence = json.loads((root / c.EVIDENCE).read_text())
            pages = json.loads((root / c.PAGES).read_text())
            receipt = json.loads((root / c.RECEIPT).read_text())
        self.assertIn('def normalize', sources)
        self.assertIn('https://www.uaart.com.ua', sources)
        for secret in ("'abc'", 'api.telegram.org', '380501234567'):
            self.assertNotIn(secret, sources + json.dumps(evidence))
        self.assertEqual(evidence['cpu']['value']['daily_cpu_limit_seconds'], 5000)
        self.assertIsNone(evidence['modules']['ua_site_counters.py']['sha256'])
        self.assertEqual(fake.public_seen, ['/video/index.html'])
        self.assertEqual(list(pages), ['/video/index.html'])
        self.assertEqual(receipt['status'], 'FINISHED')


if __name__ == '__main__':
    unittest.main()
