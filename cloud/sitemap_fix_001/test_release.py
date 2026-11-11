#!/usr/bin/env python3
"""SITEMAP-FIX-001: the catalogue's ua/ card links are read; the sitemap poll waits for card versions."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

import candidate_builder as builder
import deployment_controller as controller

OLD = builder.EDITS['ua_seo_sitemap.py'][0][0]
SOURCE = ("from urllib.parse import urlsplit\nimport re\nCARD = re.compile(r'UA-[0-9]{4,}\\.html', re.I)\n"
          "from html.parser import HTMLParser\n"
          "class CatalogLinks(HTMLParser):\n"
          "    def __init__(self, source):\n        super().__init__()\n        self.names = set()\n        self.feed(source)\n\n"
          "    def handle_starttag(self, tag, attrs):\n        if tag != 'a':\n            return\n"
          "        href = urlsplit(dict(attrs).get('href', ''))\n"
          "        if href.netloc and href.netloc.lower() != 'www.uaart.com.ua':\n            return\n"
          + OLD + "\n            return\n"
          "        name = href.path.rsplit('/', 1)[-1]\n        if CARD.fullmatch(name):\n            self.names.add(name)\n")
CATALOG = ('<a href="ua/UA-0001.html">a</a><a href="UA-0022.html">b</a><a href="/video/ua/UA-0003.html">c</a>'
           '<a href="ru/UA-0004.html">d</a><a href="seo/ua/x.html">e</a><a href="https://other.example/video/UA-0009.html">f</a>')


def parser(source):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'candidate_sitemap.py'
        path.write_text(source)
        spec = importlib.util.spec_from_file_location('candidate_sitemap', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module.CatalogLinks


class FixTests(unittest.TestCase):
    def test_reads_speed002_links_only_adds_ua_ru(self):
        before = parser(SOURCE)(CATALOG).names
        after = parser(builder.build({'ua_seo_sitemap.py': SOURCE.encode()}, {})['ua_seo_sitemap.py'].decode())(CATALOG).names
        self.assertEqual(before, {'UA-0022.html', 'UA-0003.html'})
        self.assertEqual(after, {'UA-0001.html', 'UA-0022.html', 'UA-0003.html', 'UA-0004.html'})

    def test_refuses_missing_or_applied(self):
        for source in (SOURCE.replace(OLD, ''), SOURCE + '# SITEMAP-FIX-001\n'):
            with self.assertRaises(ValueError):
                builder.build({'ua_seo_sitemap.py': source.encode()}, {})


class SitemapPollTests(unittest.TestCase):
    def test_waits_until_versions_listed(self):
        pages = iter(['<loc>https://www.uaart.com.ua/video/UA-0001.html</loc>'] * 2
                     + ['<loc>https://www.uaart.com.ua/video/ua/UA-0001.html</loc>'
                        '<loc>https://www.uaart.com.ua/video/ua/UA-0003.html</loc>'])
        sleeps = []
        self.assertEqual(controller.sitemap_lists_versions(lambda: next(pages), sleeps.append, lambda: 0), 2)
        self.assertEqual(len(sleeps), 2)

    def test_gives_up_after_deadline(self):
        clock = iter([0, controller.SITEMAP_WAIT_SECONDS + 1])
        with self.assertRaisesRegex(RuntimeError, 'SITEMAP_CARD_VERSIONS_MISSING:0'):
            controller.sitemap_lists_versions(lambda: '<urlset/>', lambda s: None, lambda: next(clock))


if __name__ == '__main__':
    unittest.main()
