#!/usr/bin/env python3
import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import candidates as c  # noqa: E402
import discover  # noqa: E402

LEXUS = 'https://lexus-cms-media.s3.us-east-2.amazonaws.com/wp-content/uploads/2026/09/2027_Lexus_RX_350_1-1000x600.jpg'
HYUNDAI = 'https://www.hyundai.news/newsroom/dam/eu/models/x/tucson-01.jpg'
PAGE = ('<title>2027 RX</title><p>The fifth-generation RX</p><img src="%s">'
        '<img src="https://evil.example/a.jpg"><script>var x=1</script>' % LEXUS)


def page_fetch(url):
    return 200, url, PAGE.encode()


def image_fetch(url):
    if url.endswith(c.RENDITION):
        return 404, b''
    return 200, b'img:' + url.encode()


class CandidateTests(unittest.TestCase):
    def test_scope(self):
        self.assertTrue(c.allowed(LEXUS) and c.allowed(HYUNDAI))
        self.assertFalse(c.allowed('https://evil.example/a.jpg'))
        with self.assertRaises(discover.DiscoverError):
            c.get_image('https://evil.example/a.jpg', image_fetch)

    def test_rendition_first_then_original(self):
        tried = []

        def fetch(url):
            tried.append(url)
            return image_fetch(url)
        used, data = c.get_image(HYUNDAI, fetch)
        self.assertEqual(tried, [HYUNDAI + c.RENDITION, HYUNDAI])
        self.assertEqual(used, HYUNDAI)

    def test_model(self):
        old = c.SOURCES
        c.SOURCES = {'lexus-rx-350': {'images': [LEXUS], 'pages': ['https://pressroom.lexus.com/vehicle/2027-lexus-rx/']}}
        try:
            found = c.model('lexus-rx-350', page_fetch, image_fetch)
        finally:
            c.SOURCES = old
        self.assertEqual([p['url'] for p in found['photos']], [LEXUS])
        self.assertEqual(base64.b64decode(found['photos'][0]['b64']), b'img:' + LEXUS.encode())
        self.assertIn('fifth-generation RX', found['pages'][0]['text'])
        self.assertNotIn('var x', found['pages'][0]['text'])

    def test_sources_are_in_scope(self):
        for source in c.SOURCES.values():
            self.assertTrue(all(c.allowed(url) for url in source['images']))
            self.assertTrue(all(discover.official(url) for url in source['pages']))


if __name__ == '__main__':
    unittest.main()
