#!/usr/bin/env python3
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archive as a  # noqa: E402
import discover  # noqa: E402

discover.PAUSE = 0
ROOT = 'https://www.hyundai.news/eu/models.html'
PAGES = {
    ROOT: '<a href="/eu/models/suv/tucson.html">TUCSON</a><a href="/eu/models/suv/kona.html">KONA</a>',
    'https://www.hyundai.news/eu/models/suv/tucson.html':
        '<title>TUCSON</title><img src="/newsroom/dam/eu/models/20200915_tucson/hyundai-tucson-exterior-01.jpg">'
        '<img src="/newsroom/dam/eu/models/20261001_tucson/hyundai-tucson-1026-exterior-01.jpg">'
        '<img src="/newsroom/dam/eu/models/20200915_kona/hyundai-kona-01.jpg">',
}


def page_fetch(url, hosts=None):
    if not discover.official(url, hosts):
        raise AssertionError('outside scope ' + url)
    return (200, url, PAGES[url].encode()) if url in PAGES else (404, url, b'')


def image_fetch(url):
    return (404, b'') if 'renditions' in url else (200, b'img')


class ArchiveTests(unittest.TestCase):
    def test_every_brand_has_archives(self):
        self.assertTrue(all(brand in a.ARCHIVES for _, brand, _ in discover.MODELS.values()))
        self.assertNotIn('lexus-tx', a.KEYS)
        self.assertEqual(sorted(a.part_keys('A') + a.part_keys('B')), sorted(a.KEYS))
        self.assertTrue(all(len(a.part_keys(p)) < 30 for p in a.PARTS))

    def test_only_model_and_2018_2023(self):
        old = a.ARCHIVES['hyundai']
        a.ARCHIVES['hyundai'] = (ROOT,)
        try:
            found = a.model('hyundai-tucson', page_fetch, image_fetch)
        finally:
            a.ARCHIVES['hyundai'] = old
        self.assertEqual([p['url'] for p in found['photos']],
                         ['https://www.hyundai.news/newsroom/dam/eu/models/20200915_tucson/hyundai-tucson-exterior-01.jpg'])


if __name__ == '__main__':
    unittest.main()
