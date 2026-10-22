#!/usr/bin/env python3
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import controller as c  # noqa: E402

SAFARI = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile Safari'
LOG = ('1.2.3.4 - - [21/Oct/2026:10:00:00 +0000] "GET /video/index.html HTTP/1.1" 200 10 '
       '"https://www.google.com/" "%s" "-" response-time=0.4\n'
       '1.2.3.4 - - [21/Oct/2026:10:01:00 +0000] "GET /video/UA-0018.html HTTP/1.1" 200 10 '
       '"https://www.uaart.com.ua/video/index.html" "%s" "-" response-time=0.2\n'
       '1.2.3.4 - - [21/Oct/2026:10:01:01 +0000] "GET /video/img/1.jpg HTTP/1.1" 200 10 "-" "%s" "-" response-time=0.1\n'
       '1.2.3.9 - - [21/Oct/2026:11:00:00 +0000] "GET /video/old.html HTTP/1.1" 404 10 "-" "%s" "-" response-time=0.1\n'
       '66.249.1.1 - - [21/Oct/2026:12:00:00 +0000] "GET /video/katalog.html HTTP/1.1" 200 10 "-" '
       '"Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)" "-" response-time=0.1\n'
       '5.5.5.5 - - [21/Oct/2026:12:00:00 +0000] "GET /video/index.html HTTP/1.1" 200 10 "-" "ua-art-monitor/1" "-"\n'
       'garbage\n') % (SAFARI, SAFARI, SAFARI, SAFARI)
OLD = ('1.2.3.7 - - [12/Oct/2026:10:00:00 +0000] "GET /video/katalog.html HTTP/1.1" 502 10 "https://t.me/x" '
       '"Mozilla/5.0 (Windows NT 10.0) Chrome/130" "-" response-time=9.0\n')
HOME = ('<html lang="ru"><head><title>UA ART</title><meta name="description" content="Авто из Кореи">'
        '<meta name="viewport" content="x"></head><body><h1>Авто <b>из Кореи</b></h1><img src="a.jpg">'
        '<a href="tel:+380992222002">тел</a><a href="https://t.me/uaart">tg</a><script>x</script></body></html>')


class Fake:
    def __init__(self):
        self.calls = []

    def api(self, endpoint):
        self.calls.append(endpoint)
        files = {c.LOG: LOG.encode(), c.LOG + '.2.gz': gzip.compress(OLD.encode()),
                 'webapps/%s/' % c.DOMAIN: b'{"expiry": "2027-01-01"}', 'cpu/': b'{"daily_cpu_total_usage_seconds": 10}'}
        return (200, files[endpoint]) if endpoint in files else (404, None)

    def public(self, url, agent='x'):
        if url in c.ENTRIES and url != c.ENTRIES[-1]:
            return 301, None, {'location': 'https://www.uaart.com.ua/'}, 0.1
        if url.endswith('robots.txt'):
            return 200, b'User-agent: *\nAllow: /\n', {}, 0.1
        if url.endswith('sitemap.xml'):
            return 200, b'<loc>a</loc><lastmod>2026-10-20</lastmod><loc>b</loc>', {}, 0.1
        return 200, HOME.encode(), {}, 0.3


class ProbeTests(unittest.TestCase):
    def test_scope(self):
        reader = c.Reader('test-value', opener=object(), public_opener=object())
        for bad in ('files/path/home/Carix/crm.db', 'files/path/var/log/other.access.log',
                    c.LOG + '.15.gz', 'webapps/', 'always_on/', 'consoles/'):
            with self.assertRaises(c.ProbeError):
                reader.api(bad)
        for bad in ('https://www.uaart.com.ua/admin', 'https://www.uaart.com.ua/video/../crm.db', 'https://evil.example/'):
            with self.assertRaises(c.ProbeError):
                reader.public(bad)

    def test_execute(self):
        fake = Fake()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = c.TASKS[0]
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
        self.assertNotIn('66.249', raw)
        self.assertEqual(fake.calls[:4], [c.LOG, c.LOG + '.1', c.LOG + '.2.gz', c.LOG + '.3.gz'])
        day = evidence['access']['daily']['2026-10-21']
        self.assertEqual((day['human_page_views'], day['human_visitors'], day['one_page_visitors'], day['mobile_visitors']),
                         (3, 2, 1, 2))
        self.assertEqual(day['visitors_by_source'], {'google': 1, 'direct': 1})
        self.assertEqual((day['human_404'], day['googlebot']), (1, {'200': 1}))
        old = evidence['access']['daily']['2026-10-12']
        self.assertEqual((old['human_5xx'], old['visitors_by_source'], old['max_page_seconds']), (1, {'telegram': 1}, 9.0))
        self.assertEqual(evidence['access']['top_404'], [['/video/old.html', 1]])
        self.assertEqual(evidence['entries']['http://uaart.com.ua/'], {'http': 301, 'seconds': 0.1, 'location': 'https://www.uaart.com.ua/'})
        home = evidence['pages']['/video/index.html']
        self.assertEqual((home['title'], home['description'], home['h1'], home['images_without_alt'], home['links_tel']),
                         ('UA ART', 'Авто из Кореи', ['Авто из Кореи'], 1, 1))
        self.assertEqual(home['links_messengers'], ['t.me'])
        self.assertEqual(evidence['pages']['/sitemap.xml']['urls'], 2)
        self.assertEqual(evidence['webapps']['body'], {'expiry': '2027-01-01'})

    def test_utm_source(self):
        self.assertEqual(c.source('-', '/video/index.html?utm_source=chatgpt.com'), 'utm:chatgpt.com')
        self.assertEqual(c.source('https://uaart.com.ua/x', '/'), 'internal')


if __name__ == '__main__':
    unittest.main()
