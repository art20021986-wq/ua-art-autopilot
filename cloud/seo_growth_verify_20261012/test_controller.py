#!/usr/bin/env python3
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402

CARD = ('<html><head><title>Kia K5 2023 из Кореи, 110 000 км — 19 300 $</title>'
        '<script type="application/ld+json" id="ua-seo-ld">{"@graph":[{"@type":"AutoDealer"}]}</script></head>'
        '<body><h1>Kia K5 2023</h1>UA-0018<nav id="ua-seo-links"></nav></body></html>')
SITEMAP = ('<urlset><url><loc>https://www.uaart.com.ua/video/UA-0018.html</loc><lastmod>2026-10-12</lastmod></url>'
           '<url><loc>https://www.uaart.com.ua/video/seo/ua/kia-k5-koreya-kyiv.html</loc><lastmod>2026-10-12</lastmod></url></urlset>')


class Fake:
    def public(self, path):
        pages = {'/robots.txt': 'Sitemap: x', '/sitemap.xml': SITEMAP, '/video/UA-0018.html': CARD,
                 '/video/katalog.html': '<a href="UA-0018.html">', '/video/seo/ua/kia-k5-koreya-kyiv.html': '<h1>K5</h1>'}
        return (200, pages[path].encode()) if path in pages else (404, None)

    def state(self):
        return 200, json.dumps({'revisions': {'1': {}}, 'retry': {'2': {'count': 3, 'error': 'x' * 900, 'sha256': 's'}},
                                'last_success': {'code': 'UA-0018'}}).encode()


class ProbeTests(unittest.TestCase):
    def test_scope(self):
        reader = c.Reader('test-value', opener=object(), public_opener=object())
        for bad in ('/admin', '/video/chat_1.txt', '/video/foto/UA-0018/001.jpg', '/video/seo/ua/../x.html'):
            with self.assertRaises(c.ProbeError):
                reader.public(bad)

    def test_execute(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = 'SEO-GROWTH-VERIFY-20261012-R2'
            request = root / 'tasks/requests' / (task + '.json')
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'read_only': True, 'production_required': False}))
            env = {'UAART_TASK_ID': task, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % task,
                   'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % task,
                   'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '1'}
            receipt = c.execute(env, root=root, reader=Fake())
            evidence = json.loads((root / receipt['evidence_path']).read_text())
        self.assertEqual(receipt['evidence_path'], c.PACKAGE + '/evidence_r2.json')
        self.assertEqual(evidence['summary'], {'cards': 1, 'cards_seo_done': 1, 'landings_ok': 1, 'non_200': []})
        self.assertEqual(evidence['sitemap']['with_lastmod'], 2)
        self.assertEqual(evidence['worker']['retry']['2']['count'], 3)
        self.assertEqual(len(evidence['worker']['retry']['2']['error']), 240)
        self.assertEqual(evidence['pages']['/video/UA-0018.html']['ld_types'], ['AutoDealer'])


if __name__ == '__main__':
    unittest.main()
