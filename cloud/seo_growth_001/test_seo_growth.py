#!/usr/bin/env python3
"""SEO-GROWTH-001 modules on the real public pages saved by SEO-SOURCE-PROBE-20261012."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from html.parser import HTMLParser

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_guard  # noqa: E402
import ua_seo_catalog  # noqa: E402
import ua_seo_index  # noqa: E402
import ua_seo_landings  # noqa: E402
import ua_seo_metadata  # noqa: E402
import ua_seo_sitemap  # noqa: E402

PROBE = HERE.parent / 'seo_source_probe_20261012'
PAGES = json.loads((PROBE / 'public_pages.json').read_text(encoding='utf-8'))
SOURCES = (PROBE / 'sanitized_sources.txt').read_text(encoding='utf-8')
CATALOG = PAGES['/video/katalog.html']['body']
LD = re.compile(r'<script type="application/ld\+json" id="ua-seo-ld">(.*?)</script>', re.S)


def installed(name):
    """Exact installed source of one module (the probe export is byte-identical, hash-checked)."""
    part = SOURCES.split('# ===== %s =====\n' % name, 1)[1]
    return re.split(r'\n# ===== [a-z_]+\.py =====\n', part, maxsplit=1)[0].rstrip('\n') + '\n'


def load(name, source):
    """Import Python source text as a module from a temporary file."""
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / (name + '.py')
        path.write_text(source, encoding='utf-8')
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def original_metadata():
    return load('ua_seo_metadata_installed', installed('ua_seo_metadata.py'))


def seo_fields_removed(html):
    html = LD.sub('', html)
    html = re.sub(r'<nav id="ua-seo-links".*?</nav>', '', html, flags=re.S)
    html = re.sub(r'<title\b.*?</title>', '', html, flags=re.S)
    return re.sub(r'<meta (?:name="description"|property="og:(?:title|description)")[^>]*>', '', html)


class Structure(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.tags, self.attrs = [], []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.append((tag, dict(attrs)))


class InstalledSources(unittest.TestCase):
    def test_probe_export_is_the_installed_bytes(self):
        digest = lambda name: hashlib.sha256(installed(name).encode()).hexdigest()
        self.assertEqual(digest('ua_seo_metadata.py'), 'c630fa7f5d939684353c5a41ee6cef2dd421bec667be400288c3f2459b15e567')
        self.assertEqual(digest('ua_seo_sitemap.py'), 'c73b249ee546310b20da8acc4d66d2006a8950ea4378366cb74f25c971b8b00d')
        self.assertEqual(digest('publish_transaction_guard.py'), build_guard.EXPECTED_SHA256)


class CatalogFacts(unittest.TestCase):
    def test_real_catalog_groups_models_despite_cyrillic_lookalikes(self):
        cars = ua_seo_catalog.cars(CATALOG)
        self.assertEqual(len(cars), 20)
        counts = {}
        for car in cars:
            counts[car['key']] = counts.get(car['key'], 0) + 1
        self.assertEqual(counts, {('Kia', 'K5'): 11, ('Hyundai', 'Sonata'): 3, ('Mercedes-Benz', 'B-Class'): 3,
                                  ('Mercedes-Benz', 'E-Class'): 1, ('Audi', 'A6'): 2})
        k5 = next(c for c in cars if c['code'] == 'UA-0018')
        self.assertEqual((k5['price_usd'], k5['mileage_km'], k5['stage']), (19300, 110000, 4))
        self.assertTrue(k5['image'].startswith('https://www.uaart.com.ua/video/foto/UA-0018/'))

    def test_unknown_brand_has_no_model_page_and_duplicates_fail(self):
        self.assertIsNone(ua_seo_catalog.model_key('Самодельный 2020'))
        article = re.search(r'<article\b.*?</article>', CATALOG, re.S).group(0)
        with self.assertRaises(ValueError):
            ua_seo_catalog.cars(article + article)


class CardMetadata(unittest.TestCase):
    def setUp(self):
        self.old = original_metadata()

    def test_real_cards_change_only_seo_fields(self):
        for code in ('UA-0018', 'UA-0021'):
            source = PAGES['/video/%s.html' % code]['body']
            path = '/home/Carix/video/%s.html' % code
            new = ua_seo_metadata.normalize(source, path)
            self.assertEqual(ua_seo_metadata.normalize(new, path), new)
            self.assertEqual(seo_fields_removed(new), seo_fields_removed(self.old.normalize(source, path)))
            h1 = re.search(r'<h1>(.*?)</h1>', new).group(1)
            title = re.search(r'<title[^>]*>(.*?)</title>', new).group(1)
            self.assertTrue(title.startswith(h1 + ' '))
            self.assertIn('из Кореи', title)
            # Publisher contracts: no other car code, exactly one diagnostics link.
            self.assertEqual(set(re.findall(r'UA-[0-9]{4,}', new)), {code})
            self.assertEqual(len(re.findall(code + r'-diag\.html', new)), len(re.findall(code + r'-diag\.html', source)))
            graph = json.loads(LD.search(new).group(1))['@graph']
            car = graph[0]
            self.assertEqual(car['sku'], code)
            self.assertEqual(car['offers']['priceCurrency'], 'USD')
            self.assertIn(str(car['offers']['price']), re.sub(r'\D', '', title))
            self.assertNotIn('/m/', car['image'][0])
            self.assertEqual(new.count('id="ua-seo-links"'), 1)

    def test_core_pages_unchanged(self):
        for name in ('index.html', 'katalog.html', 'podbor.html', 'info.html'):
            source = PAGES['/video/' + name]['body']
            self.assertEqual(ua_seo_metadata.normalize(source, name), self.old.normalize(source, name))

    def test_price_missing_gives_no_offer(self):
        source = re.sub(r'data-ua-value="[0-9]+"', 'data-ua-value=""', PAGES['/video/UA-0018.html']['body'])
        new = ua_seo_metadata.normalize(source, 'UA-0018.html')
        self.assertNotIn('offers', json.loads(LD.search(new).group(1))['@graph'][0])
        self.assertNotIn('$ |', re.search(r'<title[^>]*>(.*?)</title>', new).group(1))


class Landings(unittest.TestCase):
    def setUp(self):
        self.existing = {k[len('/video/'):] for k in PAGES if '/seo/' in k}
        self.pages = ua_seo_landings.pages(ua_seo_catalog.cars(CATALOG), (), self.existing)

    def test_pages_are_valid_reciprocal_and_list_only_catalog_cars(self):
        self.assertEqual(len(self.pages), 12)
        codes = set(re.findall(r'href="(UA-[0-9]{4,})\.html"', CATALOG))
        for relative, html in self.pages.items():
            tags = Structure(html)
            self.assertEqual(tags.tags.count('h1'), 1, relative)
            canonical = [a['href'] for t, a in tags.attrs if t == 'link' and a.get('rel') == 'canonical']
            self.assertEqual(canonical, ['https://www.uaart.com.ua/video/' + relative])
            alternates = {a['hreflang']: a['href'] for t, a in tags.attrs if t == 'link' and a.get('rel') == 'alternate'}
            self.assertIn('https://www.uaart.com.ua/video/' + relative, alternates.values())
            for lang in ('uk', 'ru'):
                other = self.pages[alternates[lang].split('/video/', 1)[1]]
                self.assertIn('href="https://www.uaart.com.ua/video/%s"' % relative, other)
            lang = re.search(r'<html lang="(\w+)"', html).group(1)
            self.assertEqual(lang, 'uk' if '/ua/' in relative else 'ru')
            json.loads(LD.search(html).group(1))
            self.assertLessEqual(set(re.findall(r'(UA-[0-9]{4,})\.html', html)), codes)
            self.assertNotIn('380992222020', html)

    def test_known_urls_kept_and_georgian_pages_linked(self):
        for relative in ('seo/ua/kia-k5-koreya-kyiv.html', 'seo/ru/kia-k5-koreya-kiev.html',
                         'seo/ua/hyundai-sonata-koreya-kyiv.html', 'seo/ru/avto-iz-korei-v-kiev-pod-kluch.html'):
            self.assertIn(relative, self.pages)
        self.assertIn('hreflang="ka" href="https://www.uaart.com.ua/video/seo/gu/kia-k5-koreidan-sakartveloshi.html"',
                      self.pages['seo/ua/kia-k5-koreya-kyiv.html'])
        self.assertNotIn('hreflang="ka"', self.pages['seo/ua/audi-a6-koreya-kyiv.html'])

    def test_sold_out_model_page_stays_and_offers_selection(self):
        cars = [c for c in ua_seo_catalog.cars(CATALOG) if c['key'] != ('Audi', 'A6')]
        pages = ua_seo_landings.pages(cars, [('Audi', 'A6')], self.existing)
        html = pages['seo/ru/audi-a6-koreya-kiev.html']
        self.assertIn('Сейчас Audi A6 нет в каталоге', html)
        self.assertNotIn('class="cars"', html)
        self.assertNotIn('audi-a6', pages['seo/ru/avto-iz-korei-v-kiev-pod-kluch.html'])


class IndexAndSitemap(unittest.TestCase):
    def test_refresh_writes_only_derived_files_and_is_stable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'katalog.html').write_text(CATALOG, encoding='utf-8')
            for name in ('index.html', 'podbor.html', 'info.html', 'UA-0018.html', 'UA-0099.html'):
                (root / name).write_text('<html></html>', encoding='utf-8')
            (root / 'seo' / 'gu').mkdir(parents=True)
            (root / 'seo' / 'gu' / 'kia-k5-koreidan-sakartveloshi.html').write_text('ka', encoding='utf-8')
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            first = ua_seo_index.refresh(root)
            self.assertEqual(len(first['landings_changed']), 12)
            self.assertTrue(first['sitemap_changed'])
            for path, data in before.items():
                self.assertEqual(path.read_bytes(), data)
            second = ua_seo_index.refresh(root)
            self.assertEqual((second['landings_changed'], second['sitemap_changed']), ([], False))
            sitemap = (root / 'sitemap.xml').read_text(encoding='utf-8')
            self.assertIn('/video/UA-0018.html</loc><lastmod>', sitemap)
            self.assertNotIn('UA-0099', sitemap)  # orphan file, not in the catalog
            self.assertNotIn('UA-0021', sitemap)  # in the catalog but no file here
            self.assertIn('/video/seo/gu/kia-k5-koreidan-sakartveloshi.html', sitemap)
            self.assertEqual(sitemap.count('<url>'), 4 + 1 + 13)
            self.assertTrue(re.search(r'<lastmod>20[0-9]{2}-[0-9]{2}-[0-9]{2}</lastmod>', sitemap))
            # The Audi cars leave the catalog: its pages stay as selection pages.
            catalog = ''.join(a for a in re.findall(r'<article\b.*?</article>', CATALOG, re.S) if 'Audi' not in a)
            (root / 'katalog.html').write_text(catalog, encoding='utf-8')
            third = ua_seo_index.refresh(root)
            self.assertIn('Зараз Audi A6 немає в каталозі',
                          (root / 'seo/ua/audi-a6-koreya-kyiv.html').read_text(encoding='utf-8'))
            self.assertIn('seo/ua/audi-a6-koreya-kyiv.html', third['landings_changed'])

    def test_legacy_sync_hook_writes_the_same_sitemap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'video'
            root.mkdir()
            (root / 'katalog.html').write_text(CATALOG, encoding='utf-8')
            (root / 'UA-0018.html').write_text('x', encoding='utf-8')
            ua_seo_sitemap.sync_after_write(root / 'katalog.html', CATALOG)
            self.assertEqual((root / 'sitemap.xml').read_bytes(), ua_seo_sitemap.sitemap(root))
            self.assertEqual(oct((root / 'sitemap.xml').stat().st_mode & 0o777), '0o644')


class GuardHook(unittest.TestCase):
    def test_builds_on_exact_installed_source_only(self):
        source = installed('publish_transaction_guard.py').encode()
        result = build_guard.build(source).decode()
        self.assertTrue(result.startswith(source.decode().rstrip('\n')))
        self.assertEqual(result.count(build_guard.MARKER), 1)
        with self.assertRaises(build_guard.BuildError):
            build_guard.build(source + b'\n')
        with self.assertRaises(build_guard.BuildError):
            build_guard.build(result.encode(), expected=hashlib.sha256(result.encode()).hexdigest())

    STUBS = ("from pathlib import Path\nVIDEO = Path('/v')\nLOG = []\n_append_log = LOG.append\n\n\n"
             "def _install_catalog(source, target):\n    return {'installed': {source: target}}\n")

    def run_block(self, refresh):
        module = type(sys)('ua_seo_index')
        module.refresh = refresh
        sys.modules['ua_seo_index'] = module
        try:
            guard = load('guard_block', self.STUBS + build_guard.BLOCK)
            return guard._install_catalog('s', 't'), guard.LOG
        finally:
            sys.modules['ua_seo_index'] = ua_seo_index

    def test_refresh_runs_after_install_and_failure_never_blocks(self):
        result, log = self.run_block(lambda root: {'status': 'PASS', 'root': str(root)})
        self.assertEqual(result, {'installed': {'s': 't'}, 'seo_index': {'status': 'PASS', 'root': '/v'}})
        self.assertEqual(log, [])

        def broken(root):
            raise OSError('disk')
        result, log = self.run_block(broken)
        self.assertEqual(result['installed'], {'s': 't'})
        self.assertEqual(result['seo_index']['status'], 'FAIL')
        self.assertEqual(log, ['SEO_INDEX_FAIL OSError:disk'])


if __name__ == '__main__':
    unittest.main()
