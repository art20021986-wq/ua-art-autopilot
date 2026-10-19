#!/usr/bin/env python3
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402

LOG = ('1.2.3.4 - - [18/Oct/2026:10:00:00 +0000] "GET /video/UA-0018.html HTTP/1.1" 200 10 "-" '
       '"Mozilla/5.0; compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot" "-" response-time=0.1\n'
       '1.2.3.5 - - [19/Oct/2026:10:00:00 +0000] "GET /video/index.html?utm_source=chatgpt.com HTTP/1.1" 200 10 '
       '"-" "Mozilla/5.0 Safari" "-" response-time=0.1\n'
       '1.2.3.6 - - [19/Oct/2026:11:00:00 +0000] "GET /video/katalog.html HTTP/1.1" 200 10 '
       '"https://www.perplexity.ai/search" "Mozilla/5.0 Safari" "-" response-time=0.1\n'
       'garbage\n')
OLD = ('1.2.3.4 - - [01/Oct/2026:10:00:00 +0000] "GET /robots.txt HTTP/1.1" 200 10 "-" '
       '"Mozilla/5.0 (compatible; bingbot/2.0)" "-" response-time=0.1\n')
HUB = ('<html><head><script type="application/ld+json">{"@graph":[{"@type":"AutoDealer"},{"@type":"ItemList"}]}</script>'
       '</head><body><h1>Авто з Кореї</h1><h2>Як</h2><p>вул. Перемоги, 20 · +380 99 222 20 02</p></body></html>')


class Fake:
    def __init__(self):
        self.calls = []

    def api(self, endpoint):
        self.calls.append(endpoint)
        files = {c.LOG: LOG.encode(), c.LOG + '.2.gz': gzip.compress(OLD.encode()),
                 'webapps/%s/static_files/' % c.DOMAIN: b'[{"url": "/sitemap.xml", "path": "/home/Carix/video/sitemap.xml"}]'}
        return (200, files[endpoint]) if endpoint in files else (404, None)

    def public(self, path, agent='x'):
        return 200, ('User-agent: *\nAllow: /\n' if path == '/robots.txt' else HUB).encode()


class ProbeTests(unittest.TestCase):
    def test_scope(self):
        reader = c.Reader('test-value', opener=object(), public_opener=object())
        for bad in ('files/path/home/Carix/crm.db', 'files/path/var/log/other.access.log',
                    c.LOG + '.15.gz', 'webapps/', 'always_on/'):
            with self.assertRaises(c.ProbeError):
                reader.api(bad)
        for bad in ('/admin', '/video/UA-0018.html', '/video/../crm.db'):
            with self.assertRaises(c.ProbeError):
                reader.public(bad)

    def test_execute(self):
        fake = Fake()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = 'AI-SEARCH-PROBE-20261019'
            request = root / 'tasks/requests' / (task + '.json')
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'read_only': True, 'production_required': False}))
            env = {'UAART_TASK_ID': task, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % task,
                   'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % task,
                   'UAART_REQUEST_SHA256': c.sha(request.read_bytes()), 'UAART_RUN_ID': '1'}
            receipt = c.execute(env, root=root, reader=fake)
            raw = (root / receipt['evidence_path']).read_text()
        evidence = json.loads(raw)
        self.assertNotIn('1.2.3.', raw)
        self.assertEqual(fake.calls[:4], [c.LOG, c.LOG + '.1', c.LOG + '.2.gz', c.LOG + '.3.gz'])
        access = evidence['access']
        self.assertEqual((access['lines'], access['parsed'], access['first_day'], access['last_day']),
                         (5, 4, '2026-10-01', '2026-10-19'))
        self.assertEqual(access['crawlers']['OAI-SearchBot']['top_paths'], [['/video/UA-0018.html', 1]])
        self.assertEqual(access['crawlers']['bingbot']['hits'], 1)
        self.assertIn('GPTBot', access['crawlers_never_seen'])
        self.assertEqual(sorted(access['referrals']), ['chatgpt', 'perplexity'])
        hub = evidence['pages'][c.PAGES[2]]
        self.assertEqual((hub['ld_types'], hub['phone'], hub['address'], hub['faq']),
                         (['AutoDealer', 'ItemList'], True, True, False))
        self.assertEqual(evidence['as_crawler']['OAI-SearchBot']['http'], 200)
        self.assertEqual(evidence['static_routes']['routes'][0]['url'], '/sitemap.xml')


if __name__ == '__main__':
    unittest.main()
