#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import discover as d  # noqa: E402

d.PAUSE = 0
ROOT = 'https://www.kiamedia.com/us/en/models'
PAGES = {
    ROOT: '<title>Models</title><a href="/us/en/models/k5/2025">K5</a><a href="/us/en/models/ev9">EV9</a>'
          '<a href="https://evil.example/k5">K5 elsewhere</a>',
    'https://www.kiamedia.com/us/en/models/k5/2025': '<a href="/us/en/models/k5/2025/photos">Photos</a>'
          '<img src="/img/k5-front.jpg" alt="K5 front"><meta property="og:image" content="/img/k5-og.png">',
    'https://www.kiamedia.com/us/en/models/k5/2025/photos': '<img data-src="/img/k5-interior.jpg?w=300" alt="Interior">'
          '<script>var a="https://www.kiamedia.com/img/k5-trunk.webp";</script>',
}


def fake(url):
    if url not in PAGES:
        return 404, url, b''
    return 200, url, PAGES[url].encode()


class DiscoverTests(unittest.TestCase):
    def test_scope(self):
        with self.assertRaises(d.DiscoverError):
            d.get('https://evil.example/x')

    def test_every_model_has_a_brand(self):
        self.assertTrue(all(brand in d.BRANDS for _, brand, _ in d.MODELS.values()))

    def test_names_model(self):
        self.assertTrue(d.names_model('https://x/models/santa-fe/2025', (('santa', 'fe'),)))
        self.assertTrue(d.names_model('/vehicles/2024-rav4hybrid', (('rav4',),)))
        self.assertFalse(d.names_model('/models/k50', (('k5',),)))
        self.assertTrue(d.names_model('/tesla/model-y', (('model', 'y'),)))

    def test_crawl_follows_model_and_gallery_links_only(self):
        old = d.BRANDS['kia']
        d.BRANDS['kia'] = (ROOT,)
        try:
            found = d.crawl(fake, 'kia-k5')
        finally:
            d.BRANDS['kia'] = old
        self.assertEqual([p['url'] for p in found['pages']], [ROOT, ROOT + '/k5/2025', ROOT + '/k5/2025/photos'])
        urls = {i['url'] for i in found['images']}
        self.assertEqual(urls, {'https://www.kiamedia.com/img/k5-front.jpg', 'https://www.kiamedia.com/img/k5-og.png',
                                'https://www.kiamedia.com/img/k5-interior.jpg?w=300',
                                'https://www.kiamedia.com/img/k5-trunk.webp'})

    def test_execute_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = d.TASKS[0]
            request = root/'tasks/requests'/(task + '.json')
            request.parent.mkdir(parents=True)
            request.write_text(json.dumps({'read_only': True, 'production_required': False}))
            env = {'UAART_TASK_ID': task, 'UAART_RECEIPT_PATH': 'state/receipts/%s.json' % task,
                   'UAART_REQUEST_PATH': 'tasks/requests/%s.json' % task, 'UAART_RUN_ID': '1',
                   'UAART_REQUEST_SHA256': hashlib.sha256(request.read_bytes()).hexdigest()}
            with self.assertRaises(d.DiscoverError):
                d.execute({**env, 'UAART_RUN_ID': 'x'}, root=root, fetch=fake)
            old = d.MODELS
            d.MODELS = {'kia-k5': old['kia-k5']}
            try:
                receipt = d.execute(env, root=root, fetch=fake)
            finally:
                d.MODELS = old
            self.assertEqual(receipt['evidence_path'], [d.evidence_path('korea')])


if __name__ == '__main__':
    unittest.main()
