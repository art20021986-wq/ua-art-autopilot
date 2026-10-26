#!/usr/bin/env python3
import base64
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect as c  # noqa: E402

c.PAUSE = 0

PROFILE = 'https://auto.ria.com/uk/dealer/ua-art-1980296/'
LISTINGS = ('<html><head><script type="application/ld+json">{"@type":"ItemList"}</script><style>.x{}</style></head><body>'
            '<img class="logo" src="https://css.riastatic.com/img/logo.svg" alt="AUTO.RIA">'
            '<a href="/uk/dealer/ua-art-1980296/">UA ART</a><a href="/uk/search/?page=2">2</a>'
            '<a href="https://example.com/x">x</a><p>Продано  12 авто</p><script>var a=1</script></body></html>')
PAGES = {
    c.ROBOTS: (200, b'User-agent: *\nDisallow: /private/\n'),
    c.START: (200, LISTINGS.encode()),
    PROFILE: (200, '<p>На AUTO.RIA 6 років</p><p>Відгук: все чудово</p>'.encode()),
    'https://css.riastatic.com/img/logo.svg': (200, b'<svg/>'),
}


def fake(url):
    return PAGES.get(url, (404, b''))


class CollectTests(unittest.TestCase):
    def test_scope(self):
        with self.assertRaises(c.CollectError):
            c.get('https://www.example.com/x')
        self.assertTrue(c.in_scope('https://css.riastatic.com/a.svg'))
        self.assertFalse(c.in_scope('http://auto.ria.com/'))
        self.assertFalse(c.in_scope('https://auto.ria.com.evil.com/'))

    def test_snapshot(self):
        found = c.snapshot(fake)
        start, profile = found['pages']
        self.assertEqual(found['robots_status'], 200)
        self.assertEqual(profile['url'], PROFILE)
        self.assertIn('Продано 12 авто', start['text'])
        self.assertNotIn('var a', start['text'])
        self.assertEqual(start['json_ld'], ['{"@type":"ItemList"}'])
        self.assertEqual(gzip.decompress(base64.b64decode(start['html_gz_b64'])), LISTINGS.encode())
        self.assertIn('На AUTO.RIA 6 років', profile['text'])
        self.assertEqual(base64.b64decode(found['logos'][0]['b64']), b'<svg/>')

    def test_robots_respected(self):
        old = c.START
        c.START = 'https://auto.ria.com/private/x'
        try:
            self.assertEqual(c.snapshot(fake)['pages'][0]['status'], 'ROBOTS_DISALLOWED')
        finally:
            c.START = old

    def test_execute_writes_evidence_and_receipt(self):
        task = c.TASKS[0]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = root/('tasks/requests/%s.json' % task)
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'read_only': True, 'production_required': False}))
            env = {'UAART_TASK_ID': task, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % task,
                   'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % task, 'UAART_RUN_ID': '1',
                   'UAART_REQUEST_SHA256': hashlib.sha256(request.read_bytes()).hexdigest()}
            receipt = c.execute(env, root=root, fetch=fake)
            self.assertEqual(receipt['status'], 'FINISHED')
            evidence = json.loads((root/c.evidence_path(task)).read_text())
            self.assertEqual(evidence['remote_write_count'], 0)
            self.assertEqual(len(evidence['pages']), 2)
            with self.assertRaises(c.CollectError):
                c.execute({**env, 'UAART_TASK_ID': 'OTHER'}, root=root, fetch=fake)


if __name__ == '__main__':
    unittest.main()
